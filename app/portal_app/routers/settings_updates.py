from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, JobQueue, SystemUpdateRun, Vm2Connection
from ..services import system_update_vm1, vm2_client
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(
    prefix="/admin/settings/updates",
    tags=["settings-updates"],
    dependencies=[Depends(require_setup_complete)],
)


def _running_run(db: Session, host: str) -> SystemUpdateRun | None:
    return (
        db.query(SystemUpdateRun)
        .filter(SystemUpdateRun.host == host, SystemUpdateRun.status == "running")
        .order_by(SystemUpdateRun.id.desc())
        .first()
    )


def _last_run(db: Session, host: str) -> SystemUpdateRun | None:
    return (
        db.query(SystemUpdateRun)
        .filter(SystemUpdateRun.host == host)
        .order_by(SystemUpdateRun.id.desc())
        .first()
    )


def _run_json(run: SystemUpdateRun) -> dict:
    return {
        "id": run.id,
        "host": run.host,
        "mode": run.mode,
        "status": run.status,
        "phase": run.phase,
        "output": run.output or "",
        "reboot_needed": run.reboot_needed,
        "healthy": run.healthy,
        "backup_path": run.backup_path,
        "log_path": run.log_path,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.get("")
def updates_page(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    conn = db.query(Vm2Connection).first()
    vm2_configured = conn is not None and bool(conn.vm2_host)
    # Strona renderuje się NATYCHMIAST — liczba dostępnych łatek dociąga się
    # AJAX-em (/vm1/check, /vm2/check), żeby dnf-owe pobieranie metadanych nie
    # blokowało renderu ("czekadełko" na froncie).
    return templates.TemplateResponse(
        request,
        "settings/updates.html",
        {
            "active": "settings",
            "current_user": current_user,
            "vm2_configured": vm2_configured,
            "vm1_running": _running_run(db, "vm1"),
            "vm2_running": _running_run(db, "vm2"),
            "vm1_last": _last_run(db, "vm1"),
            "vm2_last": _last_run(db, "vm2"),
        },
    )


@router.get("/vm1/check")
def check_vm1(current_user: AdminUser = Depends(require_login)):
    try:
        return system_update_vm1.check_updates()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.get("/vm2/check")
def check_vm2(current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        return {"error": "Brak skonfigurowanego połączenia z VM2."}
    try:
        return vm2_client.get_system_updates(conn)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _start_run(db: Session, request: Request, current_user: AdminUser, host: str, mode: str) -> dict:
    mode = "all" if mode == "all" else "security"
    existing = _running_run(db, host)
    if existing is not None:
        return {"run_id": existing.id, "already_running": True}
    run = SystemUpdateRun(host=host, mode=mode, status="running", phase="queued",
                          actor_admin_user_id=current_user.id)
    db.add(run)
    db.flush()
    db.add(JobQueue(
        job_type="system_update",
        payload={"run_id": run.id, "host": host, "mode": mode},
        status="queued",
        priority=10,
        run_after=datetime.now(timezone.utc),
        max_attempts=1,  # aktualizacji NIE ponawiamy automatycznie
    ))
    record(
        db,
        actor_admin_user_id=current_user.id,
        action=f"system.update.{host}.start",
        target_type="system",
        target_id=host,
        details={"mode": mode, "run_id": run.id},
        source_ip=client_ip(request),
    )
    return {"run_id": run.id, "already_running": False}


@router.post("/vm1")
def apply_vm1(
    request: Request,
    mode: str = Form("security"),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    return _start_run(db, request, current_user, "vm1", mode)


@router.post("/vm2")
def apply_vm2(
    request: Request,
    mode: str = Form("security"),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        raise HTTPException(400, "Brak skonfigurowanego połączenia z VM2.")
    return _start_run(db, request, current_user, "vm2", mode)


@router.get("/run/{run_id}")
def run_status(run_id: int, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    run = db.get(SystemUpdateRun, run_id)
    if run is None:
        raise HTTPException(404, "Nie ma takiego przebiegu aktualizacji.")
    return _run_json(run)


@router.post("/vm1/reboot")
def reboot_vm1(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="system.reboot.vm1",
        target_type="system",
        target_id="vm1",
        details={},
        source_ip=client_ip(request),
    )
    system_update_vm1.trigger_reboot()
    return {"status": "reboot_scheduled"}


@router.post("/vm2/reboot")
def reboot_vm2(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        raise HTTPException(400, "Brak skonfigurowanego połączenia z VM2.")
    # Token potwierdzający pochodzi z ostatniej aktualizacji VM2 (API VM2 wydaje
    # go tylko, gdy reboot jest realnie potrzebny; ma krótki TTL). Jeśli wygasł —
    # trzeba ponowić aktualizację, żeby dostać świeży token.
    last = (
        db.query(SystemUpdateRun)
        .filter(SystemUpdateRun.host == "vm2", SystemUpdateRun.reboot_token.isnot(None))
        .order_by(SystemUpdateRun.id.desc())
        .first()
    )
    if last is None or not last.reboot_token:
        raise HTTPException(400, "Brak ważnego tokenu restartu VM2 — uruchom ponownie aktualizację VM2.")
    try:
        vm2_client.system_reboot(conn, last.reboot_token)
    except vm2_client.Vm2ApiError as exc:
        raise HTTPException(400, f"Restart VM2 nie powiódł się (token mógł wygasnąć): {exc}")
    last.reboot_token = None  # jednorazowy
    db.add(last)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="system.reboot.vm2",
        target_type="system",
        target_id="vm2",
        details={},
        source_ip=client_ip(request),
    )
    return {"status": "reboot_scheduled"}
