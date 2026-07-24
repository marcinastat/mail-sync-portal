"""Status antispamu rspamd (do kafelka w panelu). Wszystko czytelne dla konta
vm2-api bez sudo: systemctl is-active, rspamadm --version, rspamc stat, mtime map."""

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RSPAMD_LIB = Path("/var/lib/rspamd")


def _run(argv: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _alive() -> bool:
    try:
        return _run(["/usr/bin/systemctl", "is-active", "rspamd"]).stdout.strip() == "active"
    except Exception:
        return False


def _version() -> str | None:
    try:
        out = _run(["/usr/bin/rspamadm", "--version"]).stdout.strip()
        m = re.search(r"(\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def _scanned() -> int | None:
    try:
        out = _run(["/usr/bin/rspamc", "stat"], timeout=8).stdout
        m = re.search(r"Messages scanned:\s*(\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _maps_updated() -> datetime | None:
    """Najświeższy plik w /var/lib/rspamd = ostatnia aktualizacja map/reguł
    rspamd (RBL/URL/phishing). Odpowiednik „definicji" dla antispamu."""
    try:
        newest = None
        for p in RSPAMD_LIB.iterdir():
            try:
                ts = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if newest is None or ts > newest:
                newest = ts
        return newest
    except Exception:
        return None


def get_status() -> dict:
    updated = _maps_updated()
    age_hours = None
    if updated is not None:
        age_hours = round((datetime.now(timezone.utc) - updated).total_seconds() / 3600, 1)
    return {
        "alive": _alive(),
        "version": _version(),
        "messages_scanned": _scanned(),
        "maps_updated": updated,
        "maps_age_hours": age_hours,
    }
