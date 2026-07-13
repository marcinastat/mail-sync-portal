#!/usr/bin/env bash
# VM1 — krok 90: końcowa weryfikacja usług, zapis podsieci admina do odczytu
# przez kreator pierwszego uruchomienia, wypisanie URL.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-90-finalize"
require_root
step_done "$STEP_NAME"
load_install_conf

mkdir -p /etc/portal
echo -n "${ADMIN_SUBNET_CIDR}" > /etc/portal/admin-subnet-cidr
chmod 0644 /etc/portal/admin-subnet-cidr

UNITS=(firewalld "postgresql-${PGDG_MAJOR_VERSION}" nginx php-fpm portal-gunicorn fail2ban)
FAILED=0
for unit in "${UNITS[@]}"; do
    if systemctl is-active --quiet "$unit"; then
        log_info "OK: $unit aktywny."
    else
        log_warn "PROBLEM: $unit NIE jest aktywny (systemctl status $unit)."
        FAILED=1
    fi
done

if [[ "$FAILED" -eq 1 ]]; then
    die "Co najmniej jedna usługa nie działa — sprawdź logi (fail2ban jaile konfigurowane w Fazie 9, może jeszcze nie istnieć na tym etapie)."
fi

log_info "VM1 gotowe. Otwórz https://${VM1_HOSTNAME}/admin/setup aby dokończyć konfigurację (kreator pierwszego uruchomienia)."
mark_step_done "$STEP_NAME"
