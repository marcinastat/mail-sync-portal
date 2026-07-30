#!/usr/bin/env bash
# Read-only status fail2ban do panelu (Raporty). Root-owned; wywoływany przez
# vm2-api przez sudo (bez argumentów). Wypisuje SUROWE wyjście fail2ban-client
# (ogólny status + per-jail) — parsowanie po stronie aplikacji
# (vm2_api endpoint /fail2ban/status). NIC nie modyfikuje: żadnego ban/unban/set.
set -uo pipefail

if ! command -v fail2ban-client >/dev/null 2>&1; then
    echo "STATE not-installed"; exit 0
fi
if ! systemctl is-active --quiet fail2ban; then
    echo "STATE inactive"; exit 0
fi
echo "STATE active"

jails="$(fail2ban-client status 2>/dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr ',' ' ')"
for j in $jails; do
    j="$(printf '%s' "$j" | tr -d '[:space:]')"
    [ -z "$j" ] && continue
    echo "=== JAIL $j ==="
    fail2ban-client status "$j" 2>/dev/null
done
