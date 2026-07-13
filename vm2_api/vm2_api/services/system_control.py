import secrets
import subprocess
import time

from fastapi import HTTPException, status

from ..config import get_settings

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


def run_health_check() -> dict:
    results = {}
    for unit in _HEALTH_UNITS:
        result = _run(["/usr/bin/systemctl", "is-active", unit], timeout=10)
        results[unit] = result.stdout.strip() == "active"
    return {"units": results, "healthy": all(results.values())}


def _reboot_pending() -> bool:
    result = _run(["/usr/bin/needs-restarting", "-r"], timeout=15)
    # needs-restarting -r zwraca 1 jeśli wymagany reboot, 0 jeśli nie.
    return result.returncode == 1


def run_dnf_update() -> dict:
    result = _run(["/usr/bin/sudo", "-n", "/usr/bin/dnf", "-y", "update"], timeout=1800)
    if result.returncode != 0:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"dnf update zakończył się błędem: {result.stderr[-1000:]}",
        )
    health = run_health_check()
    reboot_needed = _reboot_pending()
    token = None
    if reboot_needed:
        token = secrets.token_urlsafe(32)
        settings = get_settings()
        _pending_reboot_token[token] = time.monotonic() + settings.system_update_confirm_ttl_seconds
    return {
        "dnf_output_tail": result.stdout[-3000:],
        "health_check": health,
        "reboot_needed": reboot_needed,
        "reboot_confirm_token": token,
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
