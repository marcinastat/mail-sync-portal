from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from ..templating import templates
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser
from ..services.audit_service import record
from ..services.throttle_service import get_global_policy

router = APIRouter(prefix="/admin/settings/throttle", tags=["settings-throttle"], dependencies=[Depends(require_setup_complete)])


@router.get("")
def show(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    policy = get_global_policy(db)
    return templates.TemplateResponse(
        request, "settings/throttle.html", {"active": "settings", "current_user": current_user, "policy": policy}
    )


@router.post("")
def update(
    request: Request,
    max_connections_per_minute: int = Form(...),
    max_connections_per_hour: int = Form(...),
    max_connections_per_day: int = Form(...),
    max_bandwidth_kbps: int = Form(0),
    concurrent_job_limit: int = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    policy = get_global_policy(db)
    policy.max_connections_per_minute = max_connections_per_minute
    policy.max_connections_per_hour = max_connections_per_hour
    policy.max_connections_per_day = max_connections_per_day
    policy.max_bandwidth_kbps = max_bandwidth_kbps
    policy.concurrent_job_limit = concurrent_job_limit
    db.add(policy)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="throttle_policy.update",
        details={
            "max_connections_per_minute": max_connections_per_minute,
            "max_connections_per_hour": max_connections_per_hour,
            "max_connections_per_day": max_connections_per_day,
            "concurrent_job_limit": concurrent_job_limit,
        },
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/settings/throttle", status_code=303)
