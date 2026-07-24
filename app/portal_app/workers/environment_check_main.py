import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from sqlalchemy import func

from ..db import session_scope
from ..models import Domain, Mailbox, Vm2Connection, WebmailSsoToken
from ..services import vm2_client
from ..services.alert_service import dispatch as dispatch_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("portal.environment_check")

ACTIVE_CERT_PATH = Path("/etc/portal/tls/active/fullchain.pem")
CERT_EXPIRY_WARNING_DAYS = 30
DISK_USAGE_WARNING_PERCENT = 85


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

    try:
        disk = vm2_client.disk_usage(conn)
        for label, key in (("systemowy (/)", "os_disk"), ("pocztowy (/var/mail/vhosts)", "mail_disk")):
            usage = disk.get(key, {})
            percent = usage.get("used_percent", 0)
            if percent >= DISK_USAGE_WARNING_PERCENT:
                dispatch_alert(
                    db,
                    event="disk_low_space",
                    subject=f"VM2: dysk {label} zajęty w {percent}%",
                    details=usage,
                )
    except vm2_client.Vm2ApiError as exc:
        logger.warning("Nie udało się sprawdzić zajętości dysków VM2: %s", exc)


DOMAIN_POOL_WARNING_PERCENT = 90


def _check_domain_pools(db) -> None:
    """WSPÓLNA PULA na domenę: sumujemy zajętość docelową skrzynek
    (dest_bytes, cache z doveadm) i porównujemy z total_quota_mb. Alert przy
    przekroczeniu progu ostrzegawczego. Czysto aplikacyjne — bez XFS/Dovecota."""
    usage = dict(
        db.query(Mailbox.domain_id, func.coalesce(func.sum(Mailbox.dest_bytes), 0))
        .group_by(Mailbox.domain_id)
        .all()
    )
    domains = db.query(Domain).filter(Domain.total_quota_mb > 0).all()
    for d in domains:
        limit_bytes = d.total_quota_mb * 1048576
        used = usage.get(d.id, 0)
        percent = round(used / limit_bytes * 100, 1) if limit_bytes else 0
        if percent >= DOMAIN_POOL_WARNING_PERCENT:
            dispatch_alert(
                db,
                event="domain_pool_quota",
                subject=f"Domena {d.source_domain}: wspólna pula zajęta w {percent}%",
                details={
                    "domain": d.source_domain,
                    "used_bytes": used,
                    "limit_mb": d.total_quota_mb,
                    "used_percent": percent,
                    "exceeded": percent >= 100,
                },
            )


def _prune_sso_tokens(db) -> None:
    """Sprząta jednorazowe tokeny „Otwórz w Roundcube": zużyte lub wygasłe.
    TTL to ~60 s, więc trzymanie ich po fakcie nic nie daje. Zostawiamy krótki
    zapas (1 dzień) na wypadek diagnostyki/korelacji z audytem."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    deleted = (
        db.query(WebmailSsoToken)
        .filter((WebmailSsoToken.used_at.isnot(None)) | (WebmailSsoToken.expires_at < cutoff))
        .delete(synchronize_session=False)
    )
    if deleted:
        logger.info("Usunięto %d zużytych/wygasłych tokenów SSO webmaila.", deleted)


def run_once() -> None:
    with session_scope() as db:
        _check_cert_expiry(db)
        _check_vm2(db)
        _check_domain_pools(db)
        _prune_sso_tokens(db)


if __name__ == "__main__":
    run_once()
