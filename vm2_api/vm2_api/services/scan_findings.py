"""Odczyt wykryć skanów (ClamAV + rspamd) z /var/lib/vm2-scan/findings.jsonl.
Skrypty skanujące (root) DOPISUJĄ tam po jednym JSON-ie na linię; API tylko
CZYTA (plik jest group-readable dla vm2-api). Każde wykrycie dostaje monotoniczne
`id` = numer linii, żeby VM1 mógł pytać „co nowego od id"."""

import json
from pathlib import Path

FINDINGS_FILE = Path("/var/lib/vm2-scan/findings.jsonl")

# Nagłówki maila (Subject/From/Date) są ZAPISYWANE PRZY WYKRYCIU przez skaner
# (root, ma dostęp do maildirów 0600) — patrz vm2-emit-finding.py / rspamd-parse.
# API tylko je serwuje; nie czyta plików poczty (konto vm2-api i tak nie ma do
# nich uprawnień, a plik mógł zniknąć).


# Kanoniczna waga liczona z silnika+sygnatury (patrz classify) — NIE ze
# zapisanego pola "severity". Dzięki temu dashboard pokazuje REALNE zagrożenia,
# a spam/heurystyki są osobno, i obejmuje to też historyczne wpisy bez rescanu.
# Kolejność = ważność (malanie): malware > suspicious > spam > bulk.
_SEVERITY_RANK = {"malware": 3, "suspicious": 2, "spam": 1, "bulk": 0}


def classify(engine: str, signature: str) -> str:
    """Waga wykrycia:
      - malware    — OFICJALNA sygnatura ClamAV (Win.*, Email.Phishing.*, ...) =
                     realne zagrożenie.
      - suspicious — heurystyka ClamAV (Heuristics.*) lub SaneSecurity
                     (*.UNOFFICIAL): advisory, możliwe false-positive.
      - spam       — rspamd z akcją 'reject' (pewny spam).
      - bulk       — rspamd 'add header'/'PHISHING'/... (otagowana poczta masowa;
                     dominują newslettery/marketing — NIE zagrożenie).
    rspamd to skaner SPAMU, więc nigdy nie jest 'malware'/'phishing' twardo."""
    sig = signature or ""
    if engine == "rspamd":
        return "spam" if sig.lower().startswith("reject") else "bulk"
    if sig.startswith("Heuristics.") or sig.endswith(".UNOFFICIAL"):
        return "suspicious"
    return "malware"


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
            # Nadpisz wagę kanoniczną klasyfikacją (stored 'severity' był mylący:
            # rspamd 'phishing', wszystko clamav 'malware').
            row["severity"] = classify(row.get("engine", ""), row.get("signature", ""))
            out.append(row)
    return out


def _rank(row: dict) -> int:
    return _SEVERITY_RANK.get(row.get("severity", "bulk"), 0)


def get_findings(since_id: int = 0, limit: int = 100) -> dict:
    rows = _read_all()
    max_id = rows[-1]["id"] if rows else 0
    new_rows = [r for r in rows if r["id"] > since_id]

    by_engine: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for r in rows:
        by_engine[r.get("engine", "?")] = by_engine.get(r.get("engine", "?"), 0) + 1
        by_severity[r["severity"]] = by_severity.get(r["severity"], 0) + 1

    # Do listy "recent"/"new" pokazujemy NAJWAŻNIEJSZE najpierw (malware/suspicious
    # przed spamem), a przy równej wadze — najnowsze. Bez tego 8 pokazanych wierszy
    # to zwykle same tagi spamu i realne trafienia giną.
    def _key(r):
        return (_rank(r), r["id"])

    recent = sorted(rows, key=_key, reverse=True)[:limit]
    new = sorted(new_rows, key=_key, reverse=True)[:limit]

    # "threats" = realne zagrożenia (malware) — nagłówkowa liczba na dashboard.
    threats = by_severity.get("malware", 0)
    review = by_severity.get("suspicious", 0)
    spam_reject = by_severity.get("spam", 0)
    spam_bulk = by_severity.get("bulk", 0)

    return {
        "total": len(rows),
        "max_id": max_id,
        "new_count": len(new_rows),
        "new": new,
        "recent": recent,
        "by_engine": by_engine,
        "by_severity": by_severity,
        "threats": threats,
        "review": review,
        "spam_reject": spam_reject,
        "spam_bulk": spam_bulk,
    }
