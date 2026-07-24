import os
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone

from fastapi import HTTPException, status

from ..config import get_settings

_LOG_DIR = "/var/log/vm2-api/system-updates"

# Stały argv wszędzie — zero konkatenacji stringów z danych wejściowych.
# Konto serwisowe vm2-api ma wąski sudoers.d ograniczony dokładnie do tych
# komend (patrz scripts/vm2/50-provisioning-api.sh).

_HEALTH_UNITS = ["postgresql-17", "dovecot", "postfix", "clamd@scan", "vm2-provisioning-api"]

# Token potwierdzający reboot — trzymany w pamięci procesu. Usługa musi
# działać z dokładnie jednym workerem (patrz systemd unit), inaczej token
# wydany przez jeden proces nie byłby widoczny w drugim.
_pending_reboot_token: dict[str, float] = {}


def _run(argv: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


# Usługa działa pod ProtectSystem=strict — dnf uruchomiony bezpośrednio (nawet
# przez sudo) dziedziczy namespace i nie ma zapisu do /usr, /var/cache, /var/log
# ("Read-only file system: /var/log/dnf.log"). Root-helper vm2-dnf.sh uruchamia
# dnf jako transient unit (systemd-run, POZA sandboxem) i zwraca jego wynik przez
# plik + cat — patrz komentarz w bin/vm2-dnf.sh (bezpośrednie systemd-run --pipe
# gubi output, gdy wołającym jest asyncio uvicorna).
_DNF_HELPER = "/usr/local/sbin/vm2-dnf.sh"
_BACKUP_HELPER = "/usr/local/sbin/vm2-config-backup.sh"


def _dnf(mode: str, timeout: int) -> subprocess.CompletedProcess:
    return _run(["/usr/bin/sudo", "-n", _DNF_HELPER, mode], timeout=timeout)


def _config_backup() -> str | None:
    """Kopia configów VM2 przed aktualizacją (przez root-helper, systemd-run
    escape). Zwraca ścieżkę kopii albo None (backup best-effort — jego brak nie
    blokuje aktualizacji, ale jest widoczny w wyniku)."""
    try:
        res = _run(["/usr/bin/sudo", "-n", _BACKUP_HELPER], timeout=300)
    except Exception:
        return None
    for line in res.stdout.splitlines():
        if line.startswith("backup_path="):
            return line.split("=", 1)[1].strip()
    return None


def run_health_check() -> dict:
    results = {}
    for unit in _HEALTH_UNITS:
        result = _run(["/usr/bin/systemctl", "is-active", unit], timeout=10)
        results[unit] = result.stdout.strip() == "active"
    return {"units": results, "healthy": all(results.values())}


def _reboot_pending() -> bool:
    result = _run(["/usr/bin/sudo", "-n", "/usr/bin/needs-restarting", "-r"], timeout=15)
    # needs-restarting -r zwraca 1 jeśli wymagany reboot, 0 jeśli nie.
    return result.returncode == 1


def get_available_updates() -> dict:
    """Ile aktualizacji czeka, ze szczególnym uwzględnieniem BEZPIECZEŃSTWA.
    Nie wymaga roota (czyta metadane z cache dnf). `check-update` zwraca kod 100
    gdy są aktualizacje, 0 gdy brak — obu NIE traktujemy jako błąd."""
    sec = _dnf("check-security", timeout=180)
    security_packages = []
    if sec.returncode in (0, 100):
        for line in sec.stdout.splitlines():
            line = line.rstrip()
            # Linie pakietów to "nazwa.arch   wersja   repo"; pomijamy puste,
            # nagłówki i sekcję Obsoleting.
            if not line or line.startswith((" ", "Obsoleting", "Last metadata", "Security:")):
                continue
            parts = line.split()
            if len(parts) >= 3 and "." in parts[0]:
                security_packages.append(parts[0])

    allpkgs = _dnf("check-all", timeout=180)
    all_count = 0
    if allpkgs.returncode in (0, 100):
        for line in allpkgs.stdout.splitlines():
            line = line.rstrip()
            if not line or line.startswith((" ", "Obsoleting", "Last metadata")):
                continue
            parts = line.split()
            if len(parts) >= 3 and "." in parts[0]:
                all_count += 1

    summary = _dnf("updateinfo", timeout=180)
    return {
        "security_count": len(security_packages),
        "security_packages": sorted(set(security_packages))[:100],
        "total_count": all_count,
        "summary_text": summary.stdout.strip()[:2000],
        "reboot_needed": _reboot_pending(),
    }


def _write_log(mode: str, backup_path, output: str, health: dict, reboot_needed) -> str | None:
    """Trwały log aktualizacji NA VM2 (pełne wyjście). /var/log/vm2-api jest w
    ReadWritePaths usługi. Best-effort — błąd zapisu nie wywraca aktualizacji."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = f"{_LOG_DIR}/vm2-{mode}-{ts}.log"
        header = (
            f"# Aktualizacja systemu VM2 (tryb: {mode})\n"
            f"# czas: {ts} UTC  usługi_ok: {health.get('healthy')}  reboot: {reboot_needed}\n"
            f"# kopia configów: {backup_path}\n{'-' * 72}\n"
        )
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(header + (output or ""))
        return path
    except OSError:
        return None


def run_dnf_update(security_only: bool = True) -> dict:
    # Domyślnie TYLKO łatki bezpieczeństwa (--security) — świadomie unikamy
    # pełnego `dnf update`, który mógłby przeskoczyć wersje i coś rozłożyć.
    # Pełny update jest możliwy, ale tylko na wyraźne żądanie (security_only=False).
    # Najpierw kopia configów — żeby po nieudanej aktualizacji dało się je
    # przywrócić narzędziem konsolowym vm2-config-recovery.sh.
    mode = "security" if security_only else "all"
    backup_path = _config_backup()
    result = _dnf("update-security" if security_only else "update-all", timeout=1800)
    health = run_health_check() if result.returncode == 0 else {"healthy": False, "units": {}}
    full_output = (result.stdout or "") + (result.stderr or "")
    # Log piszemy ZAWSZE (także przy błędzie dnf) — żeby VM2 miała trwały ślad.
    log_path = _write_log(mode, backup_path, full_output, health, _reboot_pending() if result.returncode == 0 else None)
    if result.returncode != 0:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"dnf update zakończył się błędem (log na VM2: {log_path}): {result.stderr[-1000:]}",
        )
    reboot_needed = _reboot_pending()
    token = None
    if reboot_needed:
        token = secrets.token_urlsafe(32)
        settings = get_settings()
        _pending_reboot_token[token] = time.monotonic() + settings.system_update_confirm_ttl_seconds
    return {
        "dnf_output_tail": full_output[-200000:],
        "health_check": health,
        "reboot_needed": reboot_needed,
        "reboot_confirm_token": token,
        "security_only": security_only,
        "backup_path": backup_path,
        "log_path": log_path,
    }


def _usage_dict(path) -> dict:
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round(usage.used / usage.total * 100, 1),
    }


def get_disk_usage() -> dict:
    """VM2 ma dwa dyski (wymóg architektury — patrz scripts/vm2/25-mail-disk.sh):
    systemowy (/) i dedykowany na pocztę (maildir_base). Raportujemy oba
    osobno, żeby dało się odróżnić "system się zapycha" od "poczta się zapycha"."""
    settings = get_settings()
    return {
        "os_disk": _usage_dict("/"),
        "mail_disk": _usage_dict(settings.maildir_base),
    }


def reboot(confirm_token: str) -> None:
    expiry = _pending_reboot_token.get(confirm_token)
    if expiry is None or expiry < time.monotonic():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Token potwierdzający reboot jest nieprawidłowy lub wygasł — najpierw wywołaj POST /system/update.",
        )
    del _pending_reboot_token[confirm_token]
    subprocess.Popen(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "reboot"])
