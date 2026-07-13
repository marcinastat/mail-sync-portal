#!/usr/bin/env bash
# VM2 — krok 50: vm2_api (FastAPI, mTLS) jako systemd service pod dedykowanym
# kontem, z wąskim sudoers.d dla operacji uprzywilejowanych.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../lib/mtls.sh"

STEP_NAME="vm2-50-provisioning-api"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
APP_DIR="/opt/vm2-api"
TLS_DIR="/etc/portal/vm2-api"

pkg_install_idempotent python3.12 python3.12-devel gcc sudo dnf-utils

if ! id vm2-api >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /sbin/nologin --create-home vm2-api
fi

mkdir -p "$APP_DIR"
rsync -a --delete --exclude '__pycache__' --exclude '.venv' "$REPO_ROOT/vm2_api/" "$APP_DIR/"
chown -R vm2-api:vm2-api "$APP_DIR"

if [[ ! -d "$APP_DIR/venv" ]]; then
    sudo -u vm2-api python3.12 -m venv "$APP_DIR/venv"
fi
sudo -u vm2-api "$APP_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u vm2-api "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# --- mTLS: certyfikat serwera dla API (CA generowane przez lib/mtls.sh) -------
mtls_setup_vm2_server "$REPO_ROOT/ca" "$VM2_HOSTNAME"
mkdir -p "$TLS_DIR"
install -m 0640 -o vm2-api -g vm2-api "$REPO_ROOT/ca/vm2-server.crt" "$TLS_DIR/server.crt"
install -m 0600 -o vm2-api -g vm2-api "$REPO_ROOT/ca/vm2-server.key" "$TLS_DIR/server.key"
install -m 0640 -o vm2-api -g vm2-api "$REPO_ROOT/ca/ca.crt" "$TLS_DIR/ca.crt"

log_info "Certyfikat kliencki dla VM1 gotowy w $REPO_ROOT/ca/vm1-client.{crt,key} — skopiuj go bezpiecznie na VM1 (np. scp przez tunel administracyjny), NIE przez sieć publiczną."

# --- sudoers.d (jedyna realna granica uprawnień, patrz komentarz w unicie) ----
# vm2-api.tmpl jest statyczny (brak ${VAR}), więc render_template go tylko kopiuje.
render_template "$REPO_ROOT/templates/sudoers/vm2-api.tmpl" /etc/sudoers.d/vm2-api
chmod 0440 /etc/sudoers.d/vm2-api
visudo -cf /etc/sudoers.d/vm2-api || die "Wygenerowany plik sudoers jest niepoprawny składniowo — przerywam."

# --- systemd unit --------------------------------------------------------------
export PGDG_MAJOR_VERSION VM1_IP VM2_API_PORT
render_template "$REPO_ROOT/templates/systemd/vm2-provisioning-api.service.tmpl" /etc/systemd/system/vm2-provisioning-api.service '$PGDG_MAJOR_VERSION $VM1_IP $VM2_API_PORT'
systemctl daemon-reload
systemctl enable --now vm2-provisioning-api

log_info "VM2 provisioning API uruchomione na porcie ${VM2_API_PORT} (mTLS, dostęp tylko z ${VM1_IP})."
mark_step_done "$STEP_NAME"
