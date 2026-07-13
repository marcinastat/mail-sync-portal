#!/usr/bin/env bash
# VM2 — krok 70: końcowa weryfikacja, że wszystkie usługi żyją.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-70-finalize"
require_root
step_done "$STEP_NAME"
load_install_conf

UNITS=(firewalld "postgresql-${PGDG_MAJOR_VERSION}" postfix dovecot clamd@scan clamav-milter@scan clamav-maildir-scan.timer vm2-disk-check.timer vm2-provisioning-api)
FAILED=0
for unit in "${UNITS[@]}"; do
    if systemctl is-active --quiet "$unit"; then
        log_info "OK: $unit aktywny."
    else
        log_warn "PROBLEM: $unit NIE jest aktywny (systemctl status $unit)."
        FAILED=1
    fi
done

if ! mountpoint -q /var/mail/vhosts; then
    log_warn "PROBLEM: /var/mail/vhosts nie jest zamontowanym dyskiem (scripts/vm2/25-mail-disk.sh)."
    FAILED=1
fi

if [[ "$FAILED" -eq 1 ]]; then
    die "Co najmniej jedna usługa/dysk nie działa poprawnie — sprawdź logi przed przejściem do konfiguracji VM1."
fi

log_info "VM2 gotowe. API provisioningu nasłuchuje na porcie ${VM2_API_PORT} (mTLS, tylko z ${VM1_IP})."
mark_step_done "$STEP_NAME"
