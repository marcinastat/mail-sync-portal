#!/usr/bin/env bash
# VM2 — krok 00: kontrole wstępne (OS, miejsce na dysku, łączność).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../lib/checks.sh
source "$SCRIPT_DIR/../lib/checks.sh"

STEP_NAME="vm2-00-preflight"
require_root
step_done "$STEP_NAME"
load_install_conf

install_base_prereqs

check_os_rocky10
check_disk_space_gb "/" 20
check_disk_space_gb "/var" 20
check_selinux_enforcing

if [[ "${OUTBOUND_INTERNET_ACCESS:-true}" == "true" ]]; then
    check_outbound_connectivity "download.postgresql.org" || true
    check_outbound_connectivity "database.clamav.net" || true
fi

log_info "Preflight VM2 zakończony pomyślnie."
mark_step_done "$STEP_NAME"
