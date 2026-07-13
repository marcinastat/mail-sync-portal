#!/usr/bin/env bash
# VM1 — krok 70: jail.d/*.conf + filter.d/*.conf dla sshd/portal-admin-auth/roundcube-auth/nginx-limit-req.
# Status: STUB — implementacja w Fazie 9 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-70-fail2ban-jails"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 9). Zobacz docs/technical/build-status.md."
