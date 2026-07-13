import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..models import AuditLog

_CHAIN_LOCK_KEY = "portal_audit_log_chain"
_GENESIS_HASH = "genesis"


def record(
    session: Session,
    *,
    actor_admin_user_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    source_ip: str | None = None,
) -> AuditLog:
    """Dopisuje wpis w tej samej transakcji co właściwa zmiana (caller
    commituje oba naraz — jeśli audit się nie powiedzie, całość jest wycofana).
    pg_advisory_xact_lock serializuje łańcuch hashy między współbieżnymi
    requestami/workerami."""
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _CHAIN_LOCK_KEY})
    last = session.query(AuditLog).order_by(AuditLog.id.desc()).first()
    prev_hash = last.row_hash if last else _GENESIS_HASH

    occurred_at = datetime.now(timezone.utc)
    payload = {
        "occurred_at": occurred_at.isoformat(),
        "actor_admin_user_id": actor_admin_user_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "details": details or {},
        "source_ip": source_ip,
        "prev_hash": prev_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    row_hash = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()

    entry = AuditLog(
        occurred_at=occurred_at,
        actor_admin_user_id=actor_admin_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
        source_ip=source_ip,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    session.add(entry)
    session.flush()
    return entry


def verify_chain(session: Session) -> tuple[bool, int | None]:
    prev_hash = _GENESIS_HASH
    for row in session.query(AuditLog).order_by(AuditLog.id.asc()).yield_per(500):
        payload = {
            "occurred_at": row.occurred_at.isoformat(),
            "actor_admin_user_id": row.actor_admin_user_id,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "details": row.details,
            "source_ip": row.source_ip,
            "prev_hash": prev_hash,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        expected = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()
        if row.prev_hash != prev_hash or row.row_hash != expected:
            return False, row.id
        prev_hash = row.row_hash
    return True, None
