from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from ..templating import templates
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, AlertChannel
from ..services.audit_service import record

router = APIRouter(prefix="/admin/settings/alerts", tags=["settings-alerts"], dependencies=[Depends(require_setup_complete)])

AVAILABLE_EVENTS = ["sync_failed", "av_infected", "cert_expiring", "vm2_unhealthy", "audit_integrity_failed", "disk_low_space", "domain_pool_quota"]


@router.get("")
def list_channels(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    channels = db.query(AlertChannel).all()
    return templates.TemplateResponse(
        request,
        "settings/alerts.html",
        {"active": "settings", "current_user": current_user, "channels": channels, "available_events": AVAILABLE_EVENTS},
    )


@router.post("")
async def create_channel(
    request: Request,
    channel_type: str = Form(...),
    target: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    form = await request.form()
    events = [v for k, v in form.multi_items() if k == "events"]
    channel = AlertChannel(channel_type=channel_type, target=target, events=",".join(events) or "sync_failed")
    db.add(channel)
    db.flush()
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="alert_channel.create",
        target_type="alert_channel",
        target_id=str(channel.id),
        details={"channel_type": channel_type, "events": events},
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/settings/alerts", status_code=303)


@router.post("/{channel_id}/deactivate")
def deactivate_channel(
    channel_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    channel = db.get(AlertChannel, channel_id)
    if channel:
        channel.is_active = False
        db.add(channel)
        record(
            db,
            actor_admin_user_id=current_user.id,
            action="alert_channel.deactivate",
            target_type="alert_channel",
            target_id=str(channel_id),
            source_ip=client_ip(request),
        )
    return RedirectResponse("/admin/settings/alerts", status_code=303)
