#!/usr/bin/env bash
# VM1 — krok 20: PostgreSQL z repo PGDG (roundcube_db + portal_db, role per-DB).
# Status: STUB — implementacja w Fazie 4 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-20-postgresql"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 4). Zobacz docs/technical/build-status.md."
