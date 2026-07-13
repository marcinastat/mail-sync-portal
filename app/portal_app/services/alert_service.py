import json
import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from ..models import AlertChannel

logger = logging.getLogger("portal.alerts")

# Zewnętrzny relay SMTP dla alertów e-mail (VM1 nie ma własnego MTA — poczta
# systemowa portalu jest logicznie odrębna od zsynchronizowanych skrzynek na
# VM2). Admin uzupełnia ten plik ręcznie; jeśli brak, alerty e-mail są
# pomijane z ostrzeżeniem w logu (webhooki działają niezależnie od tego pliku).
SMTP_RELAY_CONFIG = Path("/etc/portal/alert-smtp.conf")


def _load_smtp_relay() -> dict | None:
    if not SMTP_RELAY_CONFIG.exists():
        return None
    try:
        return json.loads(SMTP_RELAY_CONFIG.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Nie udało się wczytać %s: %s", SMTP_RELAY_CONFIG, exc)
        return None


def _send_email(to_address: str, subject: str, body: str) -> None:
    relay = _load_smtp_relay()
    if relay is None:
        logger.warning("Brak konfiguracji SMTP relay (%s) — pomijam alert e-mail do %s.", SMTP_RELAY_CONFIG, to_address)
        return
    msg = EmailMessage()
    msg["From"] = relay["from_address"]
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(relay["host"], relay.get("port", 587), timeout=15) as smtp:
        smtp.starttls()
        if relay.get("username"):
            smtp.login(relay["username"], relay["password"])
        smtp.send_message(msg)


def _send_webhook(url: str, event: str, details: dict) -> None:
    with httpx.Client(timeout=10.0) as client:
        client.post(url, json={"event": event, "details": details})


def dispatch(db: Session, *, event: str, subject: str, details: dict) -> None:
    channels = db.query(AlertChannel).filter(AlertChannel.is_active.is_(True)).all()
    for channel in channels:
        if event not in channel.events.split(","):
            continue
        try:
            if channel.channel_type == "email":
                _send_email(channel.target, subject, json.dumps(details, indent=2, default=str))
            elif channel.channel_type == "webhook":
                _send_webhook(channel.target, event, details)
        except Exception:
            logger.exception("Nie udało się wysłać alertu %s przez kanał %s (%s)", event, channel.id, channel.channel_type)
