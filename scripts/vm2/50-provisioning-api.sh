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

# API czyta hasło do bazy w runtime jako user vm2-api (config.py:get_settings).
# Plik generuje 20-postgresql.sh jako 0600 root — bez tego vm2-api dostaje
# PermissionError i usługa w ogóle nie startuje. Otwieramy dostęp tylko do
# tego jednego pliku (reszta /etc/portal/secrets zostaje root-only, jest
# czytana wyłącznie jako root przy renderowaniu configów Postfix/Dovecot).
DB_PASS_FILE="/etc/portal/secrets/vm2-mail-db.pass"
if [[ -f "$DB_PASS_FILE" ]]; then
    chmod 0711 /etc/portal/secrets
    chown vm2-api:vm2-api "$DB_PASS_FILE"
    chmod 0600 "$DB_PASS_FILE"
fi

mkdir -p "$APP_DIR"
# Katalog virtualenv nazywa się "venv" (bez kropki, patrz niżej) — exclude
# musi się z nim zgadzać, inaczej rsync --delete przy każdym uruchomieniu
# próbuje skasować cały venv (i częściowo się wywala na __pycache__, które
# jest osobno wykluczone, więc nie da się go dowiązać do rmdir — obserwowane
# "cannot delete non-empty directory").
rsync -a --delete --exclude '__pycache__' --exclude 'venv' "$REPO_ROOT/vm2_api/" "$APP_DIR/"
chown -R vm2-api:vm2-api "$APP_DIR"

if [[ ! -d "$APP_DIR/venv" ]]; then
    sudo -u vm2-api python3.12 -m venv "$APP_DIR/venv"
fi
sudo -u vm2-api "$APP_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u vm2-api "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# --- mTLS: CA + certyfikat serwera (API) + certyfikat kliencki (dla VM1) ------
# Oba certyfikaty MUSZĄ powstać tutaj — CA żyje tylko na VM2. Wcześniej ten
# skrypt generował tylko cert serwera i tylko *twierdził* w logu, że cert
# kliencki jest gotowy (realny błąd, poprawione).
mtls_setup_vm2_server "$REPO_ROOT/ca" "$VM2_HOSTNAME" "$VM2_IP"
mtls_setup_vm1_client "$REPO_ROOT/ca"
mkdir -p "$TLS_DIR"
install -m 0640 -o vm2-api -g vm2-api "$REPO_ROOT/ca/vm2-server.crt" "$TLS_DIR/server.crt"
install -m 0600 -o vm2-api -g vm2-api "$REPO_ROOT/ca/vm2-server.key" "$TLS_DIR/server.key"
install -m 0640 -o vm2-api -g vm2-api "$REPO_ROOT/ca/ca.crt" "$TLS_DIR/ca.crt"

log_info "Certyfikat kliencki dla VM1 gotowy w $REPO_ROOT/ca/vm1-client.{crt,key} (+ $REPO_ROOT/ca/ca.crt) — skopiuj oba na VM1 do /etc/portal/vm1-client/{client.crt,client.key,ca.crt}. Możesz użyć scripts/vm1/fetch-vm2-client-cert.sh (patrz INSTALL.md)."

# --- root-owned helpery uruchamiane przez vm2-api przez sudo -----------------
# MUSZĄ leżeć poza /opt/vm2-api (własność vm2-api) — inaczej konto usługi mogłoby
# nadpisać skrypt uruchamiany jako root i eskalować uprawnienia. Stąd /usr/local/sbin.
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/delete-maildir.sh" /usr/local/sbin/vm2-delete-maildir.sh
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-dnf.sh" /usr/local/sbin/vm2-dnf.sh
# Kopia configów przed aktualizacją + narzędzie ratunkowe na konsolę.
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-config-backup.sh" /usr/local/sbin/vm2-config-backup.sh
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-config-recovery.sh" /usr/local/sbin/vm2-config-recovery.sh
install -d -m 0700 -o root -g root /var/lib/vm2-config-backups
# Katalog na trwałe logi aktualizacji systemu (pełne wyjście dnf) — zapisywalny
# przez usługę (ReadWritePaths w unicie).
install -d -m 0750 -o vm2-api -g vm2-api /var/log/vm2-api

# --- sudoers.d (jedyna realna granica uprawnień, patrz komentarz w unicie) ----
# vm2-api.tmpl jest statyczny (brak ${VAR}), więc render_template go tylko kopiuje.
render_template "$REPO_ROOT/templates/sudoers/vm2-api.tmpl" /etc/sudoers.d/vm2-api
chmod 0440 /etc/sudoers.d/vm2-api
visudo -cf /etc/sudoers.d/vm2-api || die "Wygenerowany plik sudoers jest niepoprawny składniowo — przerywam."

# --- systemd unit --------------------------------------------------------------
export PGDG_MAJOR_VERSION VM1_IP VM2_API_PORT
render_template "$REPO_ROOT/templates/systemd/vm2-provisioning-api.service.tmpl" /etc/systemd/system/vm2-provisioning-api.service '$PGDG_MAJOR_VERSION $VM1_IP $VM2_API_PORT'
systemctl daemon-reload
systemctl enable vm2-provisioning-api
# restart, nie tylko enable --now: uvicorn wczytuje certyfikat serwera do
# pamięci przy starcie, więc po regeneracji certów (np. zmiana SAN/IP)
# działający proces nadal serwowałby stary cert. restart jest bezpieczny —
# API jest bezstanowe poza tokenem reboota, który i tak jest efemeryczny.
systemctl restart vm2-provisioning-api

log_info "VM2 provisioning API uruchomione na porcie ${VM2_API_PORT} (mTLS, dostęp tylko z ${VM1_IP})."
mark_step_done "$STEP_NAME"
