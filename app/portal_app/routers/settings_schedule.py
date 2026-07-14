from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, SyncScheduleConfig
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(
    prefix="/admin/settings/schedule",
    tags=["settings-schedule"],
    dependencies=[Depends(require_setup_complete)],
)

# Praktyczne presety (minuty) pokazywane jako szybki wybór.
PRESETS = [15, 30, 60, 120, 240, 360, 720, 1440]


def _get_or_create(db: Session) -> SyncScheduleConfig:
    cfg = db.query(SyncScheduleConfig).first()
    if cfg is None:
        cfg = SyncScheduleConfig(interval_minutes=60)
        db.add(cfg)
        db.flush()
    return cfg


@router.get("")
def schedule_page(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    return templates.TemplateResponse(
        request,
        "settings/schedule.html",
        {"active": "settings", "current_user": current_user, "cfg": cfg,
         "presets": PRESETS, "saved": request.query_params.get("saved")},
    )


@router.post("")
def save_schedule(
    request: Request,
    interval_minutes: int = Form(60),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    cfg = _get_or_create(db)
    # Rozsądne widełki: min 5 minut (żeby nie zajechać źródeł), max 7 dni.
    cfg.interval_minutes = max(5, min(interval_minutes, 60 * 24 * 7))
    db.add(cfg)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="sync_schedule.update",
        target_type="sync_schedule_config",
        target_id=str(cfg.id),
        details={"interval_minutes": cfg.interval_minutes},
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/settings/schedule?saved=1", status_code=303)
