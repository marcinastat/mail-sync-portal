from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser
from ..services import webmail_sso
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(
    prefix="/admin/settings/webmail",
    tags=["settings-webmail"],
    dependencies=[Depends(require_setup_complete)],
)


@router.get("")
def webmail_page(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    cfg = webmail_sso.get_or_create(db)
    return templates.TemplateResponse(
        request,
        "settings/webmail.html",
        {"active": "settings", "current_user": current_user, "cfg": cfg,
         "saved": request.query_params.get("saved")},
    )


@router.post("")
def save_webmail(
    request: Request,
    enabled: bool = Form(False),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    cfg = webmail_sso.get_or_create(db)
    cfg.enabled = enabled
    db.add(cfg)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="webmail_sso.toggle",
        target_type="setting",
        target_id="webmail_sso",
        details={"enabled": enabled},
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/settings/webmail?saved=1", status_code=303)
