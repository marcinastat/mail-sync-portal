#!/usr/bin/env bash
# VM2 — krok 60: firewalld — 143/993/8443 tylko z VM1_IP (install.conf), reguły idempotentne.
# Status: STUB — implementacja w Fazie 2/3 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-60-firewall-rules"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 2/3). Zobacz docs/technical/build-status.md."
