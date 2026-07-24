from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, ScanScheduleConfig, Vm2Connection
from ..services import vm2_client
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(
    prefix="/admin/settings/scanning",
    tags=["settings-scanning"],
    dependencies=[Depends(require_setup_complete)],
)

_MODES = ["off", "daily", "weekly"]


def _get_or_create(db: Session) -> ScanScheduleConfig:
    cfg = db.query(ScanScheduleConfig).first()
    if cfg is None:
        cfg = ScanScheduleConfig()
        db.add(cfg)
        db.flush()
    return cfg


def _payload(cfg: ScanScheduleConfig) -> dict:
    return {
        "clamav_incremental_minutes": cfg.clamav_incremental_minutes,
        "clamav_full_mode": cfg.clamav_full_mode,
        "clamav_full_dow": cfg.clamav_full_dow,
        "clamav_full_hour": cfg.clamav_full_hour,
        "rspamd_incremental_minutes": cfg.rspamd_incremental_minutes,
        "rspamd_full_mode": cfg.rspamd_full_mode,
        "rspamd_full_dow": cfg.rspamd_full_dow,
        "rspamd_full_hour": cfg.rspamd_full_hour,
    }


@router.get("")
def scanning_page(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    cfg = _get_or_create(db)
    return templates.TemplateResponse(
        request, "settings/scanning.html",
        {"active": "settings", "current_user": current_user, "cfg": cfg,
         "saved": request.query_params.get("saved"), "error": request.session.pop("scan_error", None)},
    )


@router.post("")
def save_scanning(
    request: Request,
    clamav_incremental_minutes: int = Form(60),
    clamav_full_mode: str = Form("daily"),
    clamav_full_dow: int = Form(6),
    clamav_full_hour: int = Form(3),
    rspamd_incremental_minutes: int = Form(60),
    rspamd_full_mode: str = Form("off"),
    rspamd_full_dow: int = Form(6),
    rspamd_full_hour: int = Form(4),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    cfg = _get_or_create(db)
    cfg.clamav_incremental_minutes = max(0, clamav_incremental_minutes)
    cfg.clamav_full_mode = clamav_full_mode if clamav_full_mode in _MODES else "daily"
    cfg.clamav_full_dow = max(0, min(6, clamav_full_dow))
    cfg.clamav_full_hour = max(0, min(23, clamav_full_hour))
    cfg.rspamd_incremental_minutes = max(0, rspamd_incremental_minutes)
    cfg.rspamd_full_mode = rspamd_full_mode if rspamd_full_mode in _MODES else "off"
    cfg.rspamd_full_dow = max(0, min(6, rspamd_full_dow))
    cfg.rspamd_full_hour = max(0, min(23, rspamd_full_hour))
    db.add(cfg)
    db.flush()
    record(
        db, actor_admin_user_id=current_user.id, action="scan_schedule.update",
        target_type="setting", target_id="scan_schedule", details=_payload(cfg),
        source_ip=client_ip(request),
    )
    # Wypchnij do VM2 (przepisuje timery). Zapis lokalny zostaje niezależnie od
    # łączności — przy błędzie pokazujemy komunikat, konfigurację można ponowić.
    conn = db.query(Vm2Connection).first()
    if conn is not None and conn.vm2_host:
        try:
            vm2_client.set_scan_schedule(conn, _payload(cfg))
        except vm2_client.Vm2ApiError as exc:
            request.session["scan_error"] = f"Zapisano lokalnie, ale nie udało się zastosować na VM2: {exc}"
            return RedirectResponse("/admin/settings/scanning", status_code=303)
    return RedirectResponse("/admin/settings/scanning?saved=1", status_code=303)
