from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, Domain, Mailbox, Vm2Connection
from ..services import vm2_client
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(prefix="/admin/domains", tags=["domains"], dependencies=[Depends(require_setup_complete)])


@router.get("")
def list_domains(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    domains = db.query(Domain).order_by(Domain.source_domain).all()
    counts = dict(
        db.query(Mailbox.domain_id, func.count(Mailbox.id)).group_by(Mailbox.domain_id).all()
    )
    # Zużycie WSPÓLNEJ PULI domeny = suma zajętości docelowej wszystkich jej
    # skrzynek (dest_bytes cache'owany z doveadm po każdej synchronizacji).
    usage = dict(
        db.query(Mailbox.domain_id, func.coalesce(func.sum(Mailbox.dest_bytes), 0))
        .group_by(Mailbox.domain_id)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "domains/list.html",
        {"active": "domains", "current_user": current_user, "domains": domains,
         "counts": counts, "usage": usage},
    )


@router.post("/{domain_id}")
def update_domain(
    domain_id: int,
    request: Request,
    destination_domain: str = Form(...),
    source_imap_host: str = Form(...),
    source_imap_port: int = Form(993),
    default_quota_mb: int = Form(0),
    total_quota_mb: int = Form(0),
    apply_quota_to_all: bool = Form(False),
    is_active: bool = Form(False),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    domain = db.get(Domain, domain_id)
    if domain is None:
        return RedirectResponse("/admin/domains", status_code=303)

    domain.destination_domain = destination_domain
    domain.source_imap_host = source_imap_host
    domain.source_imap_port = source_imap_port
    domain.default_quota_mb = default_quota_mb
    domain.total_quota_mb = total_quota_mb
    domain.is_active = is_active
    db.add(domain)

    applied = 0
    if apply_quota_to_all:
        # Wypycha domyślną quotę domeny na WSZYSTKIE istniejące, zaprowizonowane
        # skrzynki tej domeny (aktualizuje limit na VM2 i lokalnie).
        conn = db.query(Vm2Connection).first()
        mailboxes = db.query(Mailbox).filter(Mailbox.domain_id == domain.id).all()
        for m in mailboxes:
            if conn is not None and m.vm2_mailbox_id:
                try:
                    vm2_client.update_mailbox_quota(conn, m.vm2_mailbox_id, default_quota_mb)
                except Exception:
                    continue
            m.quota_mb = default_quota_mb
            db.add(m)
            applied += 1

    record(
        db,
        actor_admin_user_id=current_user.id,
        action="domain.update",
        target_type="domain",
        target_id=str(domain.id),
        details={
            "destination_domain": destination_domain,
            "source_imap_host": source_imap_host,
            "source_imap_port": source_imap_port,
            "default_quota_mb": default_quota_mb,
            "total_quota_mb": total_quota_mb,
            "quota_applied_to_mailboxes": applied,
            "is_active": is_active,
        },
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/domains", status_code=303)
