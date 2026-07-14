from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, Vm2Connection
from ..services import system_update_vm1, vm2_client
from ..services.audit_service import record
from ..templating import templates

router = APIRouter(
    prefix="/admin/settings/updates",
    tags=["settings-updates"],
    dependencies=[Depends(require_setup_complete)],
)


def _vm2_updates(db: Session) -> dict | None:
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        return None
    try:
        return vm2_client.get_system_updates(conn)
    except Exception as exc:  # noqa: BLE001 — brak łączności nie może wywalić strony
        return {"error": str(exc)}


@router.get("")
def updates_page(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    try:
        vm1 = system_update_vm1.get_updates()
    except Exception as exc:  # noqa: BLE001
        vm1 = {"error": str(exc)}
    vm2 = _vm2_updates(db)
    return templates.TemplateResponse(
        request,
        "settings/updates.html",
        {"active": "settings", "current_user": current_user, "vm1": vm1, "vm2": vm2,
         "result": request.session.pop("update_result", None)},
    )


@router.post("/vm1")
def apply_vm1(
    request: Request,
    mode: str = Form("security"),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    security_only = mode != "all"
    result = system_update_vm1.apply(security_only=security_only)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="system.update.vm1",
        target_type="system",
        target_id="vm1",
        details={"security_only": security_only, "reboot_needed": result["reboot_needed"], "healthy": result["healthy"]},
        source_ip=client_ip(request),
    )
    request.session["update_result"] = {"host": "VM1 (portal)", **result}
    return RedirectResponse("/admin/settings/updates", status_code=303)


@router.post("/vm2")
def apply_vm2(
    request: Request,
    mode: str = Form("security"),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        return RedirectResponse("/admin/settings/updates", status_code=303)
    security_only = mode != "all"
    result = vm2_client.system_update(conn, security_only=security_only)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="system.update.vm2",
        target_type="system",
        target_id="vm2",
        details={"security_only": security_only, "reboot_needed": result.get("reboot_needed"),
                 "health_check": result.get("health_check")},
        source_ip=client_ip(request),
    )
    request.session["update_result"] = {
        "host": "VM2 (serwer poczty)",
        "output_tail": result.get("dnf_output_tail", ""),
        "reboot_needed": result.get("reboot_needed"),
        "healthy": result.get("health_check", {}).get("healthy"),
        "security_only": result.get("security_only", security_only),
    }
    return RedirectResponse("/admin/settings/updates", status_code=303)
