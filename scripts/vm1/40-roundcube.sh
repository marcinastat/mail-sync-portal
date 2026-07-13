#!/usr/bin/env bash
# VM1 — krok 40: php-fpm + Roundcube 1.7.x, config.inc.php wskazany na roundcube_db i VM2 Dovecot.
# Status: STUB — implementacja w Fazie 5 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-40-roundcube"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 5). Zobacz docs/technical/build-status.md."
