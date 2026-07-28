#!/usr/bin/env bash
# Narzędzie ratunkowe (konsola VM1) — RESETUJE TOTP konta admina PANELU, gdy
# admin stracił authenticator. Uruchamiać jako root bezpośrednio na maszynie
# (SSH/lokalnie). NIE jest wołane przez aplikację.
#
# Po co osobno od resetu hasła: samo zresetowanie hasła NIE odblokowuje kogoś,
# kto stracił też telefon/authenticator — logowanie nadal żąda TOTP. Ten skrypt
# kasuje sparowanie TOTP, więc przy następnym logowaniu admin paruje je od nowa
# (dostaje świeży QR i NOWE kody odzyskiwania). Zwykle używać RAZEM z
# portal-admin-password.sh, gdy admin zapomniał hasła i zgubił authenticator.
#
#   portal-admin-totp-reset.sh --list          — pokaż adminów + status TOTP
#   portal-admin-totp-reset.sh <login>         — zresetuj TOTP (pyta o potwierdzenie)
#
# Operacja jest audytowana (auth.totp_reset_console) w append-only audit logu.
set -uo pipefail

APP_DIR="/opt/portal-app"
VENV_PY="$APP_DIR/venv/bin/python"
HELPER="$APP_DIR/bin/set-admin-totp.py"
SERVICE_USER="portal-app"

if [[ $EUID -ne 0 ]]; then
    echo "Uruchom jako root (sudo $0 ...)." >&2
    exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "Nie znaleziono venv aplikacji ($VENV_PY)." >&2; exit 1; }
[[ -f "$HELPER" ]]  || { echo "Nie znaleziono helpera ($HELPER)." >&2; exit 1; }

usage() { grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

case "${1:-}" in
    -h|--help|"") usage 0 ;;
    --list)
        runuser -u "$SERVICE_USER" -- env PORTAL_LIST=1 "$VENV_PY" "$HELPER"
        exit $?
        ;;
esac

username="$1"

read -r -p "Zresetować TOTP admina '$username'? Przy następnym logowaniu sparuje od nowa [t/N]: " ans
case "${ans,,}" in
    t|tak|y|yes) ;;
    *) echo "Anulowano."; exit 1 ;;
esac

runuser -u "$SERVICE_USER" -- env PORTAL_USER="$username" "$VENV_PY" "$HELPER" || exit $?
echo "Wskazówka: jeśli admin zapomniał też hasła, ustaw je: portal-admin-password.sh '$username'."
