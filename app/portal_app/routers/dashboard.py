from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..deps import get_db, require_login, require_setup_complete
from ..models import AdminUser, BrandingConfig

router = APIRouter(prefix="/admin", tags=["dashboard"])
templates = Jinja2Templates(directory="portal_app/templates")


@router.get("/", dependencies=[Depends(require_setup_complete)])
def dashboard(
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    branding = db.query(BrandingConfig).first()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"active": "dashboard", "current_user": current_user, "branding": branding},
    )
