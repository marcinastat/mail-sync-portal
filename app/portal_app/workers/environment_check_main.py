import logging
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509

from ..db import session_scope
from ..models import Vm2Connection
from ..services import vm2_client
from ..services.alert_service import dispatch as dispatch_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("portal.environment_check")

ACTIVE_CERT_PATH = Path("/etc/portal/tls/active/fullchain.pem")
CERT_EXPIRY_WARNING_DAYS = 30


def _check_cert_expiry(db) -> None:
    if not ACTIVE_CERT_PATH.exists():
        return
    cert = x509.load_pem_x509_certificate(ACTIVE_CERT_PATH.read_bytes())
    days_left = (cert.not_valid_after_utc - datetime.now(timezone.utc)).days
    if days_left <= CERT_EXPIRY_WARNING_DAYS:
        dispatch_alert(
            db,
            event="cert_expiring",
            subject=f"Certyfikat TLS VM1 wygasa za {days_left} dni",
            details={"days_left": days_left, "not_valid_after": str(cert.not_valid_after_utc)},
        )


def _check_vm2(db) -> None:
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        return
    try:
        health = vm2_client.check_health(conn)
        conn.last_health_check_at = datetime.now(timezone.utc)
        conn.last_health_check_ok = bool(health.get("healthy"))
        db.add(conn)
        if not health.get("healthy"):
            dispatch_alert(db, event="vm2_unhealthy", subject="VM2: health-check nieudany", details=health)
    except vm2_client.Vm2ApiError as exc:
        conn.last_health_check_ok = False
        db.add(conn)
        dispatch_alert(db, event="vm2_unhealthy", subject="VM2: brak połączenia", details={"error": str(exc)})
        return

    try:
        av = vm2_client.av_status(conn)
        if not av.get("clamd_alive"):
            dispatch_alert(db, event="av_infected", subject="VM2: ClamAV (clamd) nie działa", details=av)
    except vm2_client.Vm2ApiError as exc:
        logger.warning("Nie udało się sprawdzić statusu AV na VM2: %s", exc)


def run_once() -> None:
    with session_scope() as db:
        _check_cert_expiry(db)
        _check_vm2(db)


if __name__ == "__main__":
    run_once()
