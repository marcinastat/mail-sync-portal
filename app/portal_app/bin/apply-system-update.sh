#!/usr/bin/env bash
# Aktualizacja systemu VM1 uruchamiana z portalu. Domyślnie TYLKO łatki
# bezpieczeństwa (dnf --security update) — świadomie unikamy pełnego update,
# który mógłby przeskoczyć wersje major (Postgres/nginx mają versionlock, ale
# reszta nie). Pełny update tylko na jawne żądanie: argument "all".
# Uruchamiane jako root wyłącznie przez portal-app (sudoers.d/portal-app),
# z JEDNYM z dwóch dozwolonych argumentów: "security" | "all".
set -euo pipefail

mode="${1:-security}"
case "$mode" in
    security) args=(-y --security update) ;;
    all)      args=(-y update) ;;
    *) echo "apply-system-update: nieznany tryb '$mode' (dozwolone: security|all)" >&2; exit 2 ;;
esac

echo "=== dnf ${args[*]} ==="
/usr/bin/dnf "${args[@]}" 2>&1 | tail -c 4000

echo "=== health-check kluczowych usług ==="
rc=0
for unit in postgresql-17 nginx portal-gunicorn portal-worker php-fpm fail2ban; do
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    printf '%-20s %s\n' "$unit" "$state"
    [[ "$state" == "active" ]] || rc=1
done

echo "=== reboot wymagany? ==="
if /usr/bin/needs-restarting -r >/dev/null 2>&1; then
    echo "reboot_needed=no"
else
    echo "reboot_needed=yes"
fi

exit $rc
