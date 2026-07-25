#!/usr/bin/env bash
# VM2 — krok 10: hardening bazowy (firewalld baseline, SELinux check).
# Status: STUB — implementacja w Fazie 2 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-10-base-hardening"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 2). Zobacz docs/technical/build-status.md."
