import psycopg
from fastapi import APIRouter, Depends, Request

from ..audit import insert_audit_log
from ..auth.ip_allowlist import require_vm1_ip
from ..db import get_conn
from ..schemas import AvScanRequest
from ..services import clamav_control

router = APIRouter(prefix="/av", tags=["av"])


@router.get("/status")
def av_status(actor: str = Depends(require_vm1_ip)):
    return clamav_control.get_status()


@router.post("/scan")
def av_scan(
    body: AvScanRequest,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    result = clamav_control.scan_mailbox(body.domain, body.local_part)
    insert_audit_log(
        conn,
        actor=actor,
        action="av.scan",
        target_type="mailbox",
        target_id=f"{body.local_part}@{body.domain}",
        details={"infected": result["infected"]},
        source_ip=request.client.host if request.client else None,
    )
    return result


@router.post("/update-defs")
def av_update_defs(
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    result = clamav_control.update_defs()
    insert_audit_log(
        conn,
        actor=actor,
        action="av.update_defs",
        target_type=None,
        target_id=None,
        details={"last_defs_update": str(result["last_defs_update"])},
        source_ip=request.client.host if request.client else None,
    )
    return result
