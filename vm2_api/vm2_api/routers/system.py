import psycopg
from fastapi import APIRouter, Depends, Request

from ..audit import insert_audit_log
from ..auth.ip_allowlist import require_vm1_ip
from ..db import get_conn
from ..schemas import SystemRebootRequest, SystemUpdateResult
from ..services import system_control

router = APIRouter(prefix="/system", tags=["system"])


@router.post("/update", response_model=SystemUpdateResult)
def system_update(
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    result = system_control.run_dnf_update()
    insert_audit_log(
        conn,
        actor=actor,
        action="system.update",
        target_type=None,
        target_id=None,
        details={"reboot_needed": result["reboot_needed"], "health_check": result["health_check"]},
        source_ip=request.client.host if request.client else None,
    )
    return result


@router.post("/reboot", status_code=202)
def system_reboot(
    body: SystemRebootRequest,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    system_control.reboot(body.confirm_token)
    insert_audit_log(
        conn,
        actor=actor,
        action="system.reboot",
        target_type=None,
        target_id=None,
        details={},
        source_ip=request.client.host if request.client else None,
    )
    return {"status": "reboot_scheduled"}
