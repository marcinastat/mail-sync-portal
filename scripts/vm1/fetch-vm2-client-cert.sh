#!/usr/bin/env bash
# VM1 — opcjonalny skrypt: pobiera certyfikat kliencki mTLS (wygenerowany
# przez scripts/vm2/50-provisioning-api.sh NA VM2) i instaluje go lokalnie
# pod /etc/portal/vm1-client/ — dokładnie tam, gdzie oczekuje go kreator
# pierwszego uruchomienia (krok 4, test połączenia z VM2).
#
# Wymaga wcześniejszego uruchomienia scripts/vm1/sync-to-vm2.sh (używa tego
# samego klucza SSH) ORAZ scripts/vm2/50-provisioning-api.sh już wykonanego
# na VM2 (inaczej pliki certów tam jeszcze nie istnieją).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_root
load_install_conf

: "${VM2_IP:?VM2_IP musi być ustawione w install.conf}"

SSH_KEY="/root/.ssh/portal_deploy_ed25519"
REMOTE_USER="${VM2_SSH_USER:-root}"
REMOTE_PATH="${VM2_REMOTE_REPO_PATH:-/root/mail-sync-portal}"
LOCAL_DIR="/etc/portal/vm1-client"

[[ -f "$SSH_KEY" ]] || die "Brak $SSH_KEY — uruchom najpierw scripts/vm1/sync-to-vm2.sh."

mkdir -p "$LOCAL_DIR"

for pair in "vm1-client.crt:client.crt" "vm1-client.key:client.key" "ca.crt:ca.crt"; do
    remote_name="${pair%%:*}"
    local_name="${pair##*:}"
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
        "${REMOTE_USER}@${VM2_IP}:${REMOTE_PATH}/ca/${remote_name}" "$LOCAL_DIR/${local_name}" \
        || die "Nie udało się pobrać ${remote_name} z VM2:${REMOTE_PATH}/ca/ — czy scripts/vm2/50-provisioning-api.sh już tam się wykonał?"
done

# Te pliki czyta proces portal-app (aplikacja /admin) w runtime, żeby zestawić
# mTLS do VM2 — musi więc być ich właścicielem, inaczej dostaje
# PermissionError na client.key (obserwowane na kroku 4 kreatora). Katalog
# 0750 portal-app, klucz 0600 portal-app — nikt poza aplikacją (i rootem) go
# nie odczyta.
if id portal-app >/dev/null 2>&1; then
    chown -R portal-app:portal-app "$LOCAL_DIR"
    chmod 0750 "$LOCAL_DIR"
fi
chmod 0600 "$LOCAL_DIR/client.key"
chmod 0640 "$LOCAL_DIR/client.crt" "$LOCAL_DIR/ca.crt"

log_info "Certyfikat kliencki mTLS zainstalowany w $LOCAL_DIR — krok 4 kreatora (/admin/setup) powinien teraz przejść test połączenia z VM2."
