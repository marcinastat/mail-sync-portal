from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, BrandingConfig
from ..services import branding_renderer
from ..services.audit_service import record

router = APIRouter(prefix="/admin/settings/branding", tags=["settings-branding"], dependencies=[Depends(require_setup_complete)])
templates = Jinja2Templates(directory="portal_app/templates")


def _get_branding(db: Session) -> BrandingConfig:
    branding = db.query(BrandingConfig).first()
    if branding is None:
        branding = BrandingConfig()
        db.add(branding)
        db.flush()
    return branding


@router.get("")
def show(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    branding = _get_branding(db)
    return templates.TemplateResponse(
        request,
        "settings/branding.html",
        {"active": "settings", "current_user": current_user, "branding": branding},
    )


@router.post("")
def save(
    request: Request,
    product_name: str = Form(...),
    primary_color: str = Form("#2563eb"),
    secondary_color: str = Form("#1e293b"),
    accent_color: str = Form("#f59e0b"),
    logo: UploadFile | None = None,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    branding = _get_branding(db)
    branding.product_name = product_name.strip() or "Portal Poczty"
    branding.primary_color = primary_color
    branding.secondary_color = secondary_color
    branding.accent_color = accent_color
    if logo is not None and logo.filename:
        branding.logo_path = branding_renderer.save_logo(logo.file.read())
    branding.generated_at = datetime.now(timezone.utc)
    db.add(branding)
    db.flush()

    # render_all jest best-effort dla części nginx/roundcube (nie wywala
    # zapisu ustawień, jeśli helper zawiedzie — motyw panelu i tak się zapisze).
    branding_renderer.render_all(branding)

    record(
        db,
        actor_admin_user_id=current_user.id,
        action="branding.update",
        details={"product_name": branding.product_name, "logo_changed": bool(logo and logo.filename)},
        source_ip=client_ip(request),
    )
    return templates.TemplateResponse(
        request,
        "settings/branding.html",
        {"active": "settings", "current_user": current_user, "branding": branding, "saved": True},
    )
