import time

import psycopg
from fastapi import APIRouter, Depends, Request

from ..audit import insert_audit_log
from ..auth.ip_allowlist import require_vm1_ip
from ..db import get_conn
from ..schemas import AvScanRequest
from ..services import clamav_control, rspamd_control, scan_findings

router = APIRouter(prefix="/av", tags=["av"])

# Cache statusu AV: get_status odpala serię podprocesów do clamd/rspamd
# (clamdscan --version, rspamc stat, systemctl...), co potrafi trwać kilka sekund,
# gdy demon akurat obsługuje skan. Kafelek na pulpicie doładowuje się przy KAŻDYM
# wejściu — bez cache serwer był niepotrzebnie odpytywany za każdym razem. Status
# jest informacyjny (nie musi być co do sekundy świeży), więc trzymamy go krótko.
_STATUS_TTL = 60.0
_status_cache: dict = {"at": 0.0, "data": None}


@router.get("/status")
def av_status(actor: str = Depends(require_vm1_ip)):
    now = time.monotonic()
    cached = _status_cache["data"]
    if cached is not None and (now - _status_cache["at"]) < _STATUS_TTL:
        return cached
    status = clamav_control.get_status()
    status["rspamd"] = rspamd_control.get_status()  # status antispamu do panelu
    _status_cache["at"] = now
    _status_cache["data"] = status
    return status


@router.get("/findings")
def av_findings(since_id: int = 0, limit: int = 100, actor: str = Depends(require_vm1_ip)):
    """Wykrycia skanów (ClamAV + rspamd). `since_id` do wykrywania NOWYCH
    (alerty). Panel pokazuje `recent`, worker alertuje na `new`."""
    return scan_findings.get_findings(since_id=since_id, limit=limit)


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
