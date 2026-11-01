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

# --- Bezpieczniki ponownego wdrożenia (PRZED jakąkolwiek zmianą) -----------------
# CA mTLS żyje w katalogu repo ($REPO_ROOT/ca, poza gitem). Instalacja mogła iść
# z klonu git albo z kopii wgranej sync-to-vm2.sh (INSTALL.md, opcje A/B) — na
# jednej maszynie bywają OBA katalogi z RÓŻNYMI CA. Uruchomienie z niewłaściwego
# wystawiłoby cert serwera obcym (lub nowym) CA: VM1 przestałaby ufać VM2 i panel
# straciłby połączenie. Gdy CA jest już wdrożone, wymagamy, by repo miało to samo.
if [[ -f "$TLS_DIR/ca.crt" ]]; then
    deployed_ca="$(openssl x509 -noout -fingerprint -sha256 -in "$TLS_DIR/ca.crt")"
    repo_ca="$(openssl x509 -noout -fingerprint -sha256 -in "$REPO_ROOT/ca/ca.crt" 2>/dev/null || true)"
    if [[ "$deployed_ca" != "$repo_ca" ]]; then
        match=""
        while read -r cand; do
            if [[ "$(openssl x509 -noout -fingerprint -sha256 -in "$cand" 2>/dev/null)" == "$deployed_ca" ]]; then
                match="${cand%/ca/ca.crt}"; break
            fi
        done < <(find / -xdev -maxdepth 4 -path '*/ca/ca.crt' 2>/dev/null)
        if [[ -n "$match" ]]; then
            hint="Uruchom skrypt z katalogu: $match"
        else
            hint="Nie znaleziono kopii repo z wdrożonym CA — nie generuj nowego, skontaktuj się z dostawcą."
        fi
        die "Katalog $REPO_ROOT ma INNE CA niż wdrożone w $TLS_DIR — przerywam, nic nie zmieniono (inaczej panel straciłby połączenie z VM2). $hint"
    fi
fi
# VM2_IP trafia do SAN certyfikatu serwera — musi być adresem TEJ maszyny.
if [[ -n "${VM2_IP:-}" ]] && ! hostname -I | tr ' ' '\n' | grep -qxF "$VM2_IP"; then
    die "VM2_IP=$VM2_IP w install.conf nie jest adresem tej maszyny ($(hostname -I | xargs)). Popraw config/install.conf (runbook: zmiana adresu IP VM2)."
fi
# VM1_IP trafia do allowlisty API. Różnica względem wdrożonej wartości to albo
# nieaktualny install.conf (panel dostałby 403), albo realna zmiana IP VM1.
if [[ -f /etc/systemd/system/vm2-provisioning-api.service ]]; then
    deployed_vm1="$(sed -n 's/^Environment=VM2_API_ALLOWED_CLIENT_IP=//p' /etc/systemd/system/vm2-provisioning-api.service)"
    if [[ -n "$deployed_vm1" && "$deployed_vm1" != "$VM1_IP" && "${ALLOW_VM1_IP_CHANGE:-0}" != "1" ]]; then
        die "VM1_IP=$VM1_IP w install.conf różni się od wdrożonego ($deployed_vm1). Jeśli install.conf jest nieaktualny — popraw go. Jeśli VM1 naprawdę zmieniła adres — runbook: zmiana adresu IP VM1 (albo ALLOW_VM1_IP_CHANGE=1)."
    fi
fi

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
# Harmonogram skanów sterowany z panelu (przepisuje systemd timery).
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-scan-schedule.sh" /usr/local/sbin/vm2-scan-schedule.sh
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-fail2ban-status.sh" /usr/local/sbin/vm2-fail2ban-status.sh
install -d -m 0700 -o root -g root /var/lib/vm2-config-backups
# API (vm2-api) czyta wykrycia skanów z /var/lib/vm2-scan/findings.jsonl —
# katalog tworzy 40-clamav.sh (root:root); tu dokładamy grupę vm2-api do odczytu.
if [[ -d /var/lib/vm2-scan ]]; then chgrp vm2-api /var/lib/vm2-scan && chmod 0750 /var/lib/vm2-scan; fi
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
