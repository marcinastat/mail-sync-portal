"""Aktualizacje systemu VM1 (host portalu).

Liczenie dostępnych łatek (`check_updates`) nie wymaga roota poza dostępem do
cache dnf (idzie przez sudo, bo konto portal-app go nie ma) i jest szybkie —
wołane z żądania web (AJAX „czekadełko").

Samo zastosowanie aktualizacji jest DŁUGIE i idzie przez portal-worker w tle,
fazami: backup → dnf → health → reboot-check. Każda faza to osobne wywołanie
wąskiego root-helpera apply-system-update.sh (sudoers), żeby modal w panelu
pokazywał postęp. Nigdy nie wołać apply/_run z żądania web — gunicorn zabiłby
workera po --timeout, a to była pierwotna przyczyna „aktualizacja nie działa"."""

import subprocess

HELPER = "/opt/portal-app/bin/apply-system-update.sh"


def _count_packages(argv: list[str]) -> int:
    """Liczy pakiety w wyjściu `dnf check-update`. Kody 0/100 to nie błąd
    (100 = są aktualizacje, 0 = brak). Uruchamiane przez sudo — konto portal-app
    nie ma dostępu do systemowego cache dnf."""
    res = subprocess.run(["/usr/bin/sudo", "-n", *argv], capture_output=True, text=True, timeout=180)
    if res.returncode not in (0, 100):
        return 0
    count = 0
    for line in res.stdout.splitlines():
        line = line.rstrip()
        if not line or line.startswith((" ", "Obsoleting", "Last metadata", "Security:")):
            continue
        parts = line.split()
        if len(parts) >= 3 and "." in parts[0]:
            count += 1
    return count


def check_updates() -> dict:
    """Ile łatek czeka (security + wszystkie) i czy wymagany reboot. Szybkie,
    wołane z AJAX po załadowaniu strony (żeby render nie czekał na dnf)."""
    security = _count_packages(["/usr/bin/dnf", "-q", "check-update", "--security"])
    total = _count_packages(["/usr/bin/dnf", "-q", "check-update"])
    return {"security_count": security, "total_count": total, "reboot_needed": check_reboot()}


def _helper(*args: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/sudo", "-n", HELPER, *args], capture_output=True, text=True, timeout=timeout)


def run_backup() -> dict:
    """Kopia configów przed aktualizacją. Zwraca ścieżkę kopii + wyjście."""
    res = _helper("backup", timeout=300)
    backup_path = None
    for line in res.stdout.splitlines():
        if line.startswith("backup_path="):
            backup_path = line.split("=", 1)[1].strip()
    return {"output": res.stdout + res.stderr, "backup_path": backup_path, "ok": res.returncode == 0}


def run_dnf(security_only: bool = True) -> dict:
    res = _helper("update", "security" if security_only else "all", timeout=1800)
    return {"output": res.stdout + res.stderr, "ok": res.returncode == 0}


def run_health() -> dict:
    res = _helper("health", timeout=120)
    return {"output": res.stdout, "healthy": res.returncode == 0}


def check_reboot() -> bool | None:
    """True/False = wymagany/niewymagany; None = nie wiadomo (brak
    needs-restarting). NIGDY nie zgadujemy „yes" przy braku narzędzia."""
    res = _helper("reboot-check", timeout=60)
    out = res.stdout.strip()
    if "reboot_needed=yes" in out:
        return True
    if "reboot_needed=no" in out:
        return False
    return None


def trigger_reboot() -> None:
    """Odroczony restart VM1. Fire-and-forget — nie czekamy (maszyna zaraz
    zniknie). Wołane z osobnego, świadomego przycisku w panelu."""
    subprocess.Popen(["/usr/bin/sudo", "-n", HELPER, "reboot"])
