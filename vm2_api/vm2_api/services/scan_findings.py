"""Odczyt wykryć skanów (ClamAV + rspamd) z /var/lib/vm2-scan/findings.jsonl.
Skrypty skanujące (root) DOPISUJĄ tam po jednym JSON-ie na linię; API tylko
CZYTA (plik jest group-readable dla vm2-api). Każde wykrycie dostaje monotoniczne
`id` = numer linii, żeby VM1 mógł pytać „co nowego od id"."""

import json
from email import policy
from email.parser import BytesParser
from pathlib import Path

FINDINGS_FILE = Path("/var/lib/vm2-scan/findings.jsonl")


def _email_headers(path: str) -> dict:
    """Nagłówki maila (Subject/From/Date) — żeby raport wskazywał KTÓRY mail.
    Czytamy tylko nagłówki (do pustej linii); MIME-encoded words dekoduje
    policy.default. Plik mógł zostać usunięty — wtedy pusto."""
    try:
        head = b""
        with open(path, "rb") as fh:
            for line in fh:
                if line in (b"\r\n", b"\n"):
                    break
                head += line
                if len(head) > 65536:
                    break
        msg = BytesParser(policy=policy.default).parsebytes(head)
        def h(name):
            v = msg[name]
            return str(v) if v else None
        return {"subject": h("subject"), "from": h("from"), "date": h("date")}
    except Exception:
        return {}


def _read_all() -> list[dict]:
    if not FINDINGS_FILE.exists():
        return []
    out = []
    with FINDINGS_FILE.open(encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            row["id"] = i
            out.append(row)
    return out


def get_findings(since_id: int = 0, limit: int = 100) -> dict:
    rows = _read_all()
    max_id = rows[-1]["id"] if rows else 0
    new_rows = [r for r in rows if r["id"] > since_id]
    # Podsumowanie po silniku i wadze (do kafelka w panelu).
    by_engine: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for r in rows:
        by_engine[r.get("engine", "?")] = by_engine.get(r.get("engine", "?"), 0) + 1
        by_severity[r.get("severity", "?")] = by_severity.get(r.get("severity", "?"), 0) + 1
    # Najnowsze najpierw, przycięte do limitu; wzbogacone o nagłówki maila.
    recent = list(reversed(rows))[:limit]
    new = list(reversed(new_rows))[:limit]
    for r in recent:
        r.update(_email_headers(r.get("path", "")))
    for r in new:
        r.update(_email_headers(r.get("path", "")))
    return {
        "total": len(rows),
        "max_id": max_id,
        "new_count": len(new_rows),
        "new": new,
        "recent": recent,
        "by_engine": by_engine,
        "by_severity": by_severity,
    }
