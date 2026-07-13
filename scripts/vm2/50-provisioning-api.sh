#!/usr/bin/env bash
# VM2 — krok 50: venv, vm2_api, jednostka systemd (mTLS, port 8443 z install.conf),
# instalacja certyfikatu serwera wystawionego przez lib/mtls.sh.
# Status: STUB — implementacja w Fazie 3 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-50-provisioning-api"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 3). Zobacz docs/technical/build-status.md."
