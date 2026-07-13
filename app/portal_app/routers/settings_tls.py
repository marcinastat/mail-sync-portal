from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, TlsConfig
from ..services import tls_manager
from ..services.audit_service import record

router = APIRouter(prefix="/admin/settings/tls", tags=["settings-tls"], dependencies=[Depends(require_setup_complete)])
templates = Jinja2Templates(directory="portal_app/templates")


def _get_config(db: Session) -> TlsConfig:
    config = db.query(TlsConfig).first()
    if config is None:
        config = TlsConfig()
        db.add(config)
        db.flush()
    return config


@router.get("")
def show(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    config = _get_config(db)
    return templates.TemplateResponse(
        request, "settings/tls.html", {"active": "settings", "current_user": current_user, "config": config}
    )


@router.post("/manual")
def apply_manual(
    request: Request,
    cert_pem: str = Form(...),
    key_pem: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    config = _get_config(db)
    try:
        tls_manager.validate_and_stage(cert_pem, key_pem)
        tls_manager.switch_mode("manual")
    except tls_manager.TlsValidationError as exc:
        return templates.TemplateResponse(
            request, "settings/tls.html", {"active": "settings", "current_user": current_user, "config": config, "error": str(exc)}, status_code=400
        )

    from datetime import datetime, timezone

    config.mode = "manual"
    config.manual_uploaded_at = datetime.now(timezone.utc)
    db.add(config)
    record(db, actor_admin_user_id=current_user.id, action="tls.switch_manual", source_ip=client_ip(request))
    return RedirectResponse("/admin/settings/tls", status_code=303)


@router.post("/selfsigned")
def revert_selfsigned(
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    config = _get_config(db)
    try:
        tls_manager.switch_mode("selfsigned")
    except tls_manager.TlsValidationError as exc:
        return templates.TemplateResponse(
            request, "settings/tls.html", {"active": "settings", "current_user": current_user, "config": config, "error": str(exc)}, status_code=400
        )
    config.mode = "selfsigned"
    db.add(config)
    record(db, actor_admin_user_id=current_user.id, action="tls.switch_selfsigned", source_ip=client_ip(request))
    return RedirectResponse("/admin/settings/tls", status_code=303)
