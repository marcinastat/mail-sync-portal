"""Aktualizacje systemu VM1 (host portalu). Liczenie dostępnych łatek nie
wymaga roota (czyta cache dnf); zastosowanie idzie przez wąski helper root
apply-system-update.sh (sudoers). Domyślnie tylko łatki bezpieczeństwa."""

import subprocess


def _count_packages(argv: list[str]) -> int:
    """Liczy pakiety w wyjściu `dnf check-update`. Kody 0/100 to nie błąd
    (100 = są aktualizacje, 0 = brak)."""
    res = subprocess.run(argv, capture_output=True, text=True, timeout=180)
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


def get_updates() -> dict:
    security = _count_packages(["/usr/bin/dnf", "-q", "check-update", "--security"])
    total = _count_packages(["/usr/bin/dnf", "-q", "check-update"])
    return {"security_count": security, "total_count": total}


def apply(security_only: bool = True) -> dict:
    """Uruchamia helper (sudo) i zwraca ogon logu + czy potrzebny reboot + czy
    wszystkie kluczowe usługi zostały aktywne po aktualizacji."""
    mode = "security" if security_only else "all"
    res = subprocess.run(
        ["/usr/bin/sudo", "-n", "/opt/portal-app/bin/apply-system-update.sh", mode],
        capture_output=True, text=True, timeout=1800,
    )
    out = res.stdout
    reboot_needed = "reboot_needed=yes" in out
    # returncode helpera != 0 oznacza, że któraś usługa nie wróciła jako active.
    return {
        "output_tail": out[-3000:],
        "reboot_needed": reboot_needed,
        "healthy": res.returncode == 0,
        "security_only": security_only,
    }
