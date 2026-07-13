#!/usr/bin/env bash
# VM1 — krok 60: zależności Perl + imapsync (wersja przypięta w install.conf).
# Status: STUB — implementacja w Fazie 8 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-60-imapsync"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 8). Zobacz docs/technical/build-status.md."
