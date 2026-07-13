#!/usr/bin/env bash
# VM1 — krok 90: włącza/startuje usługi, ustawia instance_state.first_run_required=true,
# wypisuje URL kreatora pierwszego uruchomienia.
# Status: STUB — implementacja w Fazie 6 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-90-finalize"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 6). Zobacz docs/technical/build-status.md."
