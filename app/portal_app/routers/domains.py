import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, Domain, DomainLoginAlias, Mailbox, Vm2Connection
from ..services import vm2_client
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(prefix="/admin/domains", tags=["domains"], dependencies=[Depends(require_setup_complete)])

# Poprawna nazwa domeny (walidacja aliasu logowania).
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


def _redir(msg: str = "", err: str = "") -> RedirectResponse:
    q = f"?msg={quote(msg)}" if msg else (f"?err={quote(err)}" if err else "")
    return RedirectResponse(f"/admin/domains{q}", status_code=303)


@router.get("")
def list_domains(
    request: Request,
    msg: str = "",
    err: str = "",
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    domains = db.query(Domain).order_by(Domain.source_domain).all()
    counts = dict(
        db.query(Mailbox.domain_id, func.count(Mailbox.id)).group_by(Mailbox.domain_id).all()
    )
    # Aliasy logowania per domena (do wyświetlenia i usuwania w UI).
    aliases: dict[int, list] = {}
    for a in db.query(DomainLoginAlias).order_by(DomainLoginAlias.alias_name).all():
        aliases.setdefault(a.domain_id, []).append(a)
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
         "counts": counts, "usage": usage, "aliases": aliases, "msg": msg, "err": err},
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


@router.post("/{domain_id}/aliases")
def add_alias(
    domain_id: int,
    request: Request,
    alias: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Dodaje domenę logowania (alias) dla domeny. Najpierw wypycha na VM2
    (walidacja + faktyczne działanie w Dovecocie), potem zapisuje lokalnie —
    dzięki temu nie trzymamy aliasu, którego VM2 nie przyjął."""
    domain = db.get(Domain, domain_id)
    if domain is None:
        return _redir(err="Nie ma takiej domeny.")
    alias_n = alias.strip().lower().rstrip(".")
    if not _DOMAIN_RE.match(alias_n):
        return _redir(err="Alias musi być poprawną nazwą domeny (np. example.net).")
    if alias_n == domain.destination_domain.lower():
        return _redir(err="Alias nie może być równy domenie docelowej.")
    if db.query(DomainLoginAlias).filter(DomainLoginAlias.alias_name == alias_n).first():
        return _redir(err=f"Alias {alias_n} już istnieje.")
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        return _redir(err="Brak konfiguracji połączenia z VM2.")
    try:
        vm2_client.add_domain_alias(conn, domain=domain.destination_domain, alias=alias_n)
    except vm2_client.Vm2ApiError as exc:
        return _redir(err=f"VM2 odrzuciło alias: {exc}")
    db.add(DomainLoginAlias(domain_id=domain.id, alias_name=alias_n))
    record(
        db, actor_admin_user_id=current_user.id, action="domain.alias.add",
        target_type="domain", target_id=str(domain.id),
        details={"alias": alias_n, "destination_domain": domain.destination_domain},
        source_ip=client_ip(request),
    )
    return _redir(msg=f"Dodano alias logowania {alias_n}.")


@router.post("/{domain_id}/aliases/{alias_id}/delete")
def delete_alias(
    domain_id: int,
    alias_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    domain = db.get(Domain, domain_id)
    alias = db.get(DomainLoginAlias, alias_id)
    if domain is None or alias is None or alias.domain_id != domain.id:
        return _redir(err="Nie ma takiego aliasu.")
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        return _redir(err="Brak konfiguracji połączenia z VM2.")
    try:
        vm2_client.delete_domain_alias(conn, domain=domain.destination_domain, alias=alias.alias_name)
    except vm2_client.Vm2ApiError as exc:
        return _redir(err=f"VM2 niedostępne — nie usunięto aliasu: {exc}")
    alias_name = alias.alias_name
    db.delete(alias)
    record(
        db, actor_admin_user_id=current_user.id, action="domain.alias.remove",
        target_type="domain", target_id=str(domain.id),
        details={"alias": alias_name},
        source_ip=client_ip(request),
    )
    return _redir(msg=f"Usunięto alias logowania {alias_name}.")
