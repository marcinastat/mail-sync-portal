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
    result = _run(["/usr/bin/sudo", "-n", "/usr/bin/clamdscan", "--ping", "1", "-c", CLAMD_CONF], timeout=10)
    return result.returncode == 0


def last_defs_update() -> datetime | None:
    newest = None
    for candidate in ["/var/lib/clamav/daily.cld", "/var/lib/clamav/daily.cvd", *_MAIN_DB_CANDIDATES]:
        path = Path(candidate)
        if path.exists():
            ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if newest is None or ts > newest:
                newest = ts
    return newest


def defs_version() -> dict:
    """Wersja silnika i sygnatur ClamAV z `clamdscan --version`.
    Format: 'ClamAV <engine>/<sig_version>/<data_bazy>'."""
    result = _run(["/usr/bin/sudo", "-n", "/usr/bin/clamdscan", "--version", "-c", CLAMD_CONF], timeout=10)
    engine = sig = None
    line = (result.stdout or "").strip().splitlines()[0] if result.stdout.strip() else ""
    parts = line.split("/")
    if parts and parts[0].startswith("ClamAV"):
        engine = parts[0].replace("ClamAV", "").strip() or None
    if len(parts) >= 2 and parts[1].strip().isdigit():
        sig = int(parts[1].strip())
    return {"engine_version": engine, "defs_version": sig}


def get_status() -> dict:
    updated = last_defs_update()
    ver = defs_version()
    age_hours = None
    current = None
    if updated is not None:
        age_hours = round((datetime.now(timezone.utc) - updated).total_seconds() / 3600, 1)
        # freshclam odświeża definicje regularnie (Checks 24/dobę) — jeśli
        # ostatnia aktualizacja jest młodsza niż 48h, uznajemy bazy za aktualne.
        current = age_hours < 48
    return {
        "clamd_alive": clamd_alive(),
        "last_defs_update": updated,
        "engine_version": ver["engine_version"],
        "defs_version": ver["defs_version"],
        "defs_age_hours": age_hours,
        "defs_current": current,
    }


def update_defs() -> dict:
    result = _run(["/usr/bin/sudo", "-n", "-u", "clamscan", "/usr/bin/freshclam"], timeout=300)
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
        ["/usr/bin/sudo", "-n", "/usr/bin/clamdscan", "--fdpass", "--multiscan", "-c", CLAMD_CONF, str(target)],
        timeout=600,
    )
    infected = result.returncode == 1
    return {
        "infected": infected,
        "returncode": result.returncode,
        "summary_tail": result.stdout[-2000:],
    }
