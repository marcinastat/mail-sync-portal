"""Przełącznik funkcji „Otwórz w Roundcube" (SSO admina). Domyślnie WYŁĄCZONA."""

from sqlalchemy.orm import Session

from ..models import WebmailSsoConfig


def get_or_create(db: Session) -> WebmailSsoConfig:
    cfg = db.query(WebmailSsoConfig).first()
    if cfg is None:
        cfg = WebmailSsoConfig(enabled=False)
        db.add(cfg)
        db.flush()
    return cfg


def is_enabled(db: Session) -> bool:
    cfg = db.query(WebmailSsoConfig).first()
    return bool(cfg and cfg.enabled)
