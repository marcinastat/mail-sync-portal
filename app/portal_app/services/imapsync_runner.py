import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import IMAPSYNC_LOG_DIR

IMAPSYNC_BIN = "/usr/local/bin/imapsync"

# Allowlista argv — TO JEST jedyne miejsce, gdzie budowane jest wywołanie
# imapsync. Flagi mutujące/kasujące na hoście 1 (źródle) — --delete1,
# --expunge1, --delete1duplicates i inne warianty *1 — CELOWO nie istnieją
# nigdzie w tym module. Nie ma ścieżki w kodzie (ani przez UI, ani przez
# konfigurację), która mogłaby je dodać do argv. Host 1 jest też zawsze
# otwierany w trybie tylko-do-odczytu na poziomie logiki: nie wysyłamy nic
# poza --host1/--user1/--passfile1 i parametrami odczytu (--folder, --maxage).


class ImapsyncSafetyError(RuntimeError):
    """Nigdy nie powinno się zdarzyć — zabezpieczenie przed regresją w kodzie."""


_FORBIDDEN_SOURCE_FLAGS = re.compile(r"^--(delete1|expunge1|delete1duplicates|search1|noexpunge1)\b")


def _write_passfile(password: str, tmp_dir: Path) -> Path:
    tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = tmp_dir / f"passfile-{uuid.uuid4()}"
    path.write_text(password, encoding="utf-8")
    path.chmod(0o600)
    return path


def build_argv(
    *,
    source_host: str,
    source_port: int,
    source_user: str,
    source_passfile: Path,
    dest_host: str,
    dest_port: int,
    dest_user: str,
    dest_passfile: Path,
    days_back: int,
    preserve_folder_structure: bool,
    delete_on_dest_when_missing_from_source: bool,
    dry_run: bool = False,
) -> list[str]:
    argv = [
        IMAPSYNC_BIN,
        "--host1", source_host,
        "--port1", str(source_port),
        "--user1", source_user,
        "--passfile1", str(source_passfile),
        "--ssl1",
        "--host2", dest_host,
        "--port2", str(dest_port),
        "--user2", dest_user,
        "--passfile2", str(dest_passfile),
        "--ssl2",
        # imapsync domyślnie tworzy własny katalog LOG_imapsync/ w bieżącym
        # katalogu roboczym — a worker działa z CWD=/opt/portal-app (read-only
        # pod ProtectSystem) i pada z "Read-only file system". Przechwytujemy
        # całe stdout/stderr do własnego pliku (run_sync niżej), więc własne
        # logowanie imapsync jest zbędne — wyłączamy je (--nolog), a operacje
        # tymczasowe kierujemy do /tmp (PrivateTmp=true daje zapisywalny, prywatny /tmp).
        "--nolog",
        "--tmpdir", "/tmp",
        "--automap" if preserve_folder_structure else "--no-automap",
    ]
    # --maxage OGRANICZA synchronizację do wiadomości młodszych niż N dni.
    # days_back <= 0 oznacza "synchronizuj WSZYSTKO, bez limitu wieku" — wtedy
    # w ogóle nie dodajemy --maxage. (Wcześniej domyślne 365 cicho pomijało
    # starsze maile: skrzynka 1027 wiadomości -> tylko 485 zsynchronizowanych.)
    if days_back and days_back > 0:
        argv += ["--maxage", str(days_back)]
    if delete_on_dest_when_missing_from_source:
        # Jedyna flaga kasująca w całym module — dotyczy WYŁĄCZNIE hosta 2
        # (docelowy, VM2) i tylko gdy admin świadomie to włączył (domyślnie
        # wyłączone, wymaga potwierdzenia w UI — patrz routers/mailboxes.py).
        argv.append("--delete2")
    if dry_run:
        argv.append("--dry")

    for flag in argv:
        if _FORBIDDEN_SOURCE_FLAGS.match(flag):
            raise ImapsyncSafetyError(f"Wykryto zabronioną flagę mutującą źródło: {flag}")

    return argv


def run_sync(
    *,
    mailbox_id: int,
    source_host: str,
    source_port: int,
    source_user: str,
    source_password: str,
    dest_host: str,
    dest_port: int,
    dest_user: str,
    dest_password: str,
    days_back: int,
    preserve_folder_structure: bool,
    delete_on_dest_when_missing_from_source: bool,
    dry_run: bool = False,
    tmp_dir: Path = Path("/run/portal-app/imapsync"),
) -> dict:
    source_passfile = _write_passfile(source_password, tmp_dir)
    dest_passfile = _write_passfile(dest_password, tmp_dir)
    try:
        argv = build_argv(
            source_host=source_host,
            source_port=source_port,
            source_user=source_user,
            source_passfile=source_passfile,
            dest_host=dest_host,
            dest_port=dest_port,
            dest_user=dest_user,
            dest_passfile=dest_passfile,
            days_back=days_back,
            preserve_folder_structure=preserve_folder_structure,
            delete_on_dest_when_missing_from_source=delete_on_dest_when_missing_from_source,
            dry_run=dry_run,
        )
        result = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
    finally:
        source_passfile.unlink(missing_ok=True)
        dest_passfile.unlink(missing_ok=True)

    IMAPSYNC_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = IMAPSYNC_LOG_DIR / f"mailbox-{mailbox_id}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log"
    log_path.write_text(result.stdout + "\n--- stderr ---\n" + result.stderr, encoding="utf-8")

    return {
        "returncode": result.returncode,
        "log_path": str(log_path),
        "stats": _parse_stats(result.stdout),
    }


# Wzorce dopasowane do rzeczywistego formatu podsumowania imapsync 2.229
# (potwierdzone na żywym logu). "Folders synced : 7/7 synced" niesie i
# zsynchronizowane, i całkowite; "Messages transferred : 486" itd.
_STATS_SINGLE = {
    "messages_transferred": re.compile(r"Messages transferred\s*:\s*(\d+)"),
    "bytes_transferred": re.compile(r"Total bytes transferred\s*:\s*(\d+)"),
    # "all 486 identified messages in host1 are on host2" — najpewniejsze
    # źródło liczby wiadomości na źródle w tej wersji imapsync.
    "messages_total": re.compile(r"all (\d+) identified messages in host1"),
    # Rozmiar skrzynki źródłowej (host1) w bajtach — wymaga braku
    # --nofoldersizes. Format imapsync 2.229 (potwierdzony na żywym logu):
    #   "Host1 Total size:               7750159 bytes (7.391 MiB)"
    "source_bytes": re.compile(r"Host1 Total size:\s*(\d+)"),
    "dest_bytes_reported": re.compile(r"Host2 Total size:\s*(\d+)"),
}
_STATS_FOLDERS = re.compile(r"Folders synced\s*:\s*(\d+)\s*/\s*(\d+)")
# Suma po WSZYSTKICH folderach host1 (źródło) — prawdziwa liczba wiadomości na
# skrzynce źródłowej, niezależna od --maxage. Linie w stylu:
#   "Host1: folder [INBOX] has 1027 messages in total (mentioned by SELECT)"
_STATS_HOST1_FOLDER_TOTAL = re.compile(r"Host1: folder \[.*?\] has (\d+) messages in total")


def _parse_stats(stdout: str) -> dict:
    """imapsync wypisuje podsumowanie w formacie tekstowym pod koniec logu —
    parsowanie jest best-effort (brakujące pola zostają na 0), bo dokładny
    format może się różnić między wersjami; surowy log jest zawsze zachowany
    do ręcznej weryfikacji (job_runs.imapsync_log_path)."""
    stats = {"messages_transferred": 0, "bytes_transferred": 0, "messages_total": 0,
             "folders_synced": 0, "folders_total": 0, "source_messages_total": 0,
             "source_bytes": 0, "dest_bytes_reported": 0}
    for key, pattern in _STATS_SINGLE.items():
        match = pattern.search(stdout)
        if match:
            stats[key] = int(match.group(1))
    folders = _STATS_FOLDERS.search(stdout)
    if folders:
        stats["folders_synced"] = int(folders.group(1))
        stats["folders_total"] = int(folders.group(2))
    source_totals = _STATS_HOST1_FOLDER_TOTAL.findall(stdout)
    if source_totals:
        stats["source_messages_total"] = sum(int(n) for n in source_totals)
    return stats
