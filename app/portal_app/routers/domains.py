from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, Domain
from ..services.audit_service import record

router = APIRouter(prefix="/admin/domains", tags=["domains"], dependencies=[Depends(require_setup_complete)])
templates = Jinja2Templates(directory="portal_app/templates")


@router.get("")
def list_domains(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    domains = db.query(Domain).order_by(Domain.source_domain).all()
    return templates.TemplateResponse(
        request, "domains/list.html", {"active": "domains", "current_user": current_user, "domains": domains}
    )


@router.post("/{domain_id}")
def update_domain(
    domain_id: int,
    request: Request,
    destination_domain: str = Form(...),
    source_imap_host: str = Form(...),
    source_imap_port: int = Form(993),
    is_active: bool = Form(False),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    domain = db.get(Domain, domain_id)
    if domain:
        domain.destination_domain = destination_domain
        domain.source_imap_host = source_imap_host
        domain.source_imap_port = source_imap_port
        domain.is_active = is_active
        db.add(domain)
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
                "is_active": is_active,
            },
            source_ip=client_ip(request),
        )
    return RedirectResponse("/admin/domains", status_code=303)
