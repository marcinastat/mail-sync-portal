#!/usr/bin/env bash
# VM1 — krok 50: venv, pip install portal_app, alembic upgrade, jednostki systemd
# (gunicorn, worker, scheduler.timer), klucz szyfrowania sekretów przez systemd-creds.
# Status: STUB — implementacja w Fazie 6 planu (docs/technical/architecture.md).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-50-portal-app"
require_root
step_done "$STEP_NAME"
load_install_conf

die "Krok '$STEP_NAME' nie jest jeszcze zaimplementowany (Faza 6). Zobacz docs/technical/build-status.md."
