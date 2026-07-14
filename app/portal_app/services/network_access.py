"""Strefy dostępowe sieci: osobne listy dozwolonych CIDR dla panelu /admin i dla
webmaila Roundcube, egzekwowane w nginx (allow/deny per location). Portal renderuje
dwa pliki include do stagingu, a wąski helper (sudo, root) instaluje je do
/etc/portal/nginx/, testuje `nginx -t` i przeładowuje nginx — z automatycznym
wycofaniem, jeśli konfiguracja jest błędna (żeby literówka w CIDR nie wywaliła nginx)."""

import ipaddress
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("portal.network_access")

_STAGE_DIR = Path("/var/lib/portal-app/network-stage")
_APPLY_HELPER = "/opt/portal-app/bin/apply-network-access.sh"

# Nazwy plików muszą się zgadzać z include'ami w templates/nginx/admin.conf.tmpl
_ADMIN_FILE = "admin-access.conf"
_WEBMAIL_FILE = "webmail-access.conf"


def parse_cidrs(raw: str) -> tuple[list[str], list[str]]:
    """Rozbija tekst (linie / przecinki / spacje) na znormalizowane CIDR-y.
    Zwraca (poprawne, błędne). Pojedynczy adres bez maski jest akceptowany
    (ipaddress dopisze /32 lub /128)."""
    valid: list[str] = []
    invalid: list[str] = []
    tokens = [t.strip() for chunk in raw.splitlines() for t in chunk.replace(",", " ").split()]
    for token in tokens:
        if not token:
            continue
        try:
            net = ipaddress.ip_network(token, strict=False)
            valid.append(str(net))
        except ValueError:
            invalid.append(token)
    return valid, invalid


def _render_include(networks: list[str], label: str) -> str:
    if not networks:
        # Pusta lista = brak dodatkowego ograniczenia poza firewalld. Świadomie
        # NIE piszemy "deny all", żeby nie odciąć wszystkich przez pomyłkę.
        return f"# {label}: brak ograniczenia sieci (obowiązuje tylko firewalld)\n"
    lines = [f"# {label}: dozwolone tylko poniższe sieci"]
    lines += [f"allow {cidr};" for cidr in networks]
    lines.append("deny all;")
    return "\n".join(lines) + "\n"


def render_and_apply(admin_networks: list[str], webmail_networks: list[str]) -> None:
    """Zapisuje include'y do stagingu i uruchamia helper (sudo) instalujący je
    do /etc/portal/nginx/ + `nginx -t` + reload z rollbackiem. Rzuca wyjątkiem,
    jeśli helper zwróci błąd (np. nginx -t nie przeszedł) — router pokaże to
    adminowi i NIE zapisze zmiany jako 'applied'."""
    _STAGE_DIR.mkdir(parents=True, exist_ok=True)
    (_STAGE_DIR / _ADMIN_FILE).write_text(_render_include(admin_networks, "Panel /admin"), encoding="utf-8")
    (_STAGE_DIR / _WEBMAIL_FILE).write_text(_render_include(webmail_networks, "Webmail Roundcube"), encoding="utf-8")

    result = subprocess.run(
        ["/usr/bin/sudo", "-n", _APPLY_HELPER],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        logger.error("apply-network-access.sh nie powiodło się: %s", result.stderr.strip())
        raise RuntimeError(
            "Nginx odrzucił nową konfigurację stref dostępu (przywrócono poprzednią). "
            "Sprawdź poprawność wpisanych sieci."
        )
