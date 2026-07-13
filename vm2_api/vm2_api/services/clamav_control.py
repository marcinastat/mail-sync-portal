import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status

from ..config import get_settings

# Wszystkie wywołania subprocess używają stałej listy argumentów — nigdy
# konkatenacji stringów z danych wejściowych — żeby wykluczyć iniekcję poleceń.

CLAMD_CONF = "/etc/clamd.d/scan.conf"
_MAIN_DB_CANDIDATES = ["/var/lib/clamav/main.cvd", "/var/lib/clamav/main.cld"]


def _run(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def clamd_alive() -> bool:
    result = _run(["/usr/bin/clamdscan", "--ping", "1", "-c", CLAMD_CONF], timeout=10)
    return result.returncode == 0


def last_defs_update() -> datetime | None:
    for candidate in _MAIN_DB_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return None


def get_status() -> dict:
    return {
        "clamd_alive": clamd_alive(),
        "last_defs_update": last_defs_update(),
    }


def update_defs() -> dict:
    result = _run(["/usr/bin/freshclam"], timeout=300)
    if result.returncode not in (0, 1):  # freshclam zwraca 1 gdy bazy już aktualne
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"freshclam zakończył się błędem: {result.stderr[-500:]}",
        )
    return {"stdout_tail": result.stdout[-2000:], "last_defs_update": last_defs_update()}


def _mailbox_maildir_path(domain_name: str, local_part: str) -> Path:
    settings = get_settings()
    base = settings.maildir_base.resolve()
    target = (base / domain_name / local_part).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nieprawidłowa ścieżka skrzynki.")
    return target


def scan_mailbox(domain_name: str, local_part: str) -> dict:
    target = _mailbox_maildir_path(domain_name, local_part)
    if not target.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Katalog skrzynki jeszcze nie istnieje (brak dostarczonej poczty).")
    result = _run(
        ["/usr/bin/clamdscan", "--fdpass", "--multiscan", "-c", CLAMD_CONF, str(target)],
        timeout=600,
    )
    infected = result.returncode == 1
    return {
        "infected": infected,
        "returncode": result.returncode,
        "summary_tail": result.stdout[-2000:],
    }
