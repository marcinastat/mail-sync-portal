#!/usr/bin/env bash
# Narzędzie ratunkowe (konsola VM1) — ustawia nowe hasło konta admina PANELU,
# gdy admin je zapomniał. Uruchamiać jako root bezpośrednio na maszynie (SSH/
# lokalnie). NIE jest wołane przez aplikację. TOTP pozostaje nietknięte.
#
#   portal-admin-password.sh --list                 — pokaż loginy adminów
#   portal-admin-password.sh <login>                — ustaw hasło (pyta 2x, ukryte)
#   portal-admin-password.sh <login> --random       — wygeneruj losowe i pokaż raz
#
# Hasło jest hashowane TYM SAMYM argon2 co logowanie (helper w venv aplikacji),
# uruchamianym jako portal-app; hasło idzie przez POTOK (stdin), nie przez argv
# ani env — nie wycieka do `ps`.
set -uo pipefail

APP_DIR="/opt/portal-app"
VENV_PY="$APP_DIR/venv/bin/python"
HELPER="$APP_DIR/bin/set-admin-password.py"
SERVICE_USER="portal-app"

if [[ $EUID -ne 0 ]]; then
    echo "Uruchom jako root (sudo $0 ...)." >&2
    exit 1
fi
[[ -x "$VENV_PY" ]] || { echo "Nie znaleziono venv aplikacji ($VENV_PY)." >&2; exit 1; }
[[ -f "$HELPER" ]]  || { echo "Nie znaleziono helpera ($HELPER)." >&2; exit 1; }

usage() { grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

run_helper() {  # $1 = hasło; przekazywane STDIN-em
    local user="$1" pw="$2"
    printf '%s' "$pw" | runuser -u "$SERVICE_USER" -- env PORTAL_USER="$user" "$VENV_PY" "$HELPER"
}

case "${1:-}" in
    -h|--help|"") usage 0 ;;
    --list)
        runuser -u "$SERVICE_USER" -- env PORTAL_LIST=1 "$VENV_PY" "$HELPER"
        exit $?
        ;;
esac

username="$1"
mode="${2:-prompt}"

if [[ "$mode" == "--random" ]]; then
    newpw="Tmp-$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 12)"
    run_helper "$username" "$newpw" || exit $?
    echo "Wygenerowane hasło (pokazane tylko teraz): $newpw"
    echo "Zaloguj się i zmień je w panelu: Ustawienia → Użytkownicy → Moje hasło."
    exit 0
fi

read -r -s -p "Nowe hasło dla '$username': " p1; echo
read -r -s -p "Powtórz nowe hasło: " p2; echo
if [[ "$p1" != "$p2" ]]; then echo "Hasła nie są identyczne — anulowano." >&2; exit 1; fi
if [[ ${#p1} -lt 10 ]]; then echo "Hasło musi mieć co najmniej 10 znaków — anulowano." >&2; exit 1; fi
run_helper "$username" "$p1" || exit $?
echo "Gotowe. Zaloguj się nowym hasłem (TOTP bez zmian)."
