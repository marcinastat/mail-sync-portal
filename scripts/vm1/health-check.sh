#!/usr/bin/env bash
# VM1 — health-check ręczny, do uruchomienia po każdym `dnf update` (VM1 nie
# ma odpowiednika VM2 provisioning API, więc nie ma automatycznego
# health-checka po aktualizacji — patrz docs/technical/runbooks/post-update-checklist.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
load_install_conf

UNITS=(firewalld "postgresql-${PGDG_MAJOR_VERSION}" nginx php-fpm portal-gunicorn portal-worker portal-scheduler.timer portal-audit-verify.timer fail2ban)
FAILED=0
for unit in "${UNITS[@]}"; do
    if systemctl is-active --quiet "$unit"; then
        echo "OK    $unit"
    else
        echo "FAIL  $unit"
        FAILED=1
    fi
done

if [[ "$FAILED" -eq 1 ]]; then
    echo
    echo "Co najmniej jedna usługa nie działa. Sprawdź: systemctl status <usługa>, journalctl -u <usługa>."
    exit 1
fi

echo
echo "Wszystkie usługi VM1 aktywne."
