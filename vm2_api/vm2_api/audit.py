import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import psycopg

# Zapis do audit_log dzieje się w TEJ SAMEJ transakcji co właściwa zmiana
# (caller commituje oba naraz) — jeśli zapis audytowy się nie powiedzie,
# cała operacja jest wycofywana. pg_advisory_xact_lock serializuje łańcuch
# hashy między współbieżnymi requestami, żeby prev_hash zawsze wskazywał na
# faktycznie poprzedni wiersz.

_CHAIN_LOCK_KEY = "vm2_audit_log_chain"
_GENESIS_HASH = "genesis"


def insert_audit_log(
    conn: psycopg.Connection,
    *,
    actor: str,
    action: str,
    target_type: str | None,
    target_id: str | None,
    details: dict[str, Any],
    source_ip: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (_CHAIN_LOCK_KEY,))
        cur.execute("SELECT row_hash FROM audit_log ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        prev_hash = row["row_hash"] if row else _GENESIS_HASH

        occurred_at = datetime.now(timezone.utc)
        payload = {
            "occurred_at": occurred_at.isoformat(),
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details,
            "source_ip": source_ip,
            "prev_hash": prev_hash,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        row_hash = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()

        cur.execute(
            """
            INSERT INTO audit_log
                (occurred_at, actor, action, target_type, target_id, details, source_ip, prev_hash, row_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                occurred_at,
                actor,
                action,
                target_type,
                target_id,
                json.dumps(details),
                source_ip,
                prev_hash,
                row_hash,
            ),
        )


def verify_chain(conn: psycopg.Connection) -> tuple[bool, int | None]:
    """Przelicza cały łańcuch od zera; zwraca (ok, id pierwszego złamanego wiersza)."""
    prev_hash = _GENESIS_HASH
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, occurred_at, actor, action, target_type, target_id, details,
                      source_ip, prev_hash, row_hash
               FROM audit_log ORDER BY id ASC"""
        )
        for row in cur:
            payload = {
                "occurred_at": row["occurred_at"].isoformat(),
                "actor": row["actor"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "details": row["details"],
                "source_ip": str(row["source_ip"]) if row["source_ip"] else None,
                "prev_hash": prev_hash,
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
            expected = hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()
            if row["prev_hash"] != prev_hash or row["row_hash"] != expected:
                return False, row["id"]
            prev_hash = row["row_hash"]
    return True, None
