from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from ..deps import require_login, require_setup_complete
from ..models import AdminUser

router = APIRouter(prefix="/admin/settings", tags=["settings"], dependencies=[Depends(require_setup_complete)])
templates = Jinja2Templates(directory="portal_app/templates")


@router.get("")
def settings_index(request: Request, current_user: AdminUser = Depends(require_login)):
    return templates.TemplateResponse(
        request, "settings/index.html", {"active": "settings", "current_user": current_user}
    )
