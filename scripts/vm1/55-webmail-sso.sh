#!/usr/bin/env bash
# VM1 — krok 55: „Otwórz w Roundcube" (SSO admina do skrzynki bez hasła).
# Wtyczka portal_sso loguje jako MASTER USER Dovecota, waliduje jednorazowy token
# (portal_db.webmail_sso_tokens) i sprawdza IP wobec sieci admina.
#
# Wymaga: 50-portal-app.sh (migracja 0014 tworzy tabelę tokenów) oraz na VM2
# 30-postfix-dovecot.sh (generuje hasło mastera). Pobiera to hasło z VM2 tym
# samym kluczem SSH co sync-to-vm2.sh / fetch-vm2-client-cert.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-55-webmail-sso"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
RC_ROOT="/var/www/roundcube"
PLUGIN_DIR="$RC_ROOT/plugins/portal_sso"
: "${VM2_IP:?VM2_IP musi być ustawione w install.conf}"

[[ -d "$RC_ROOT" ]] || die "Brak $RC_ROOT — uruchom najpierw scripts/vm1/40-roundcube.sh."

# --- 1. Hasło mastera z VM2 ---------------------------------------------------
# Trzy ścieżki: (a) plik już podłożony ręcznie — użyj go; (b) jest klucz deploy
# (sync-to-vm2.sh) — pobierz przez scp; (c) brak obu — jasna instrukcja.
SSH_KEY="/root/.ssh/portal_deploy_ed25519"
REMOTE_USER="${VM2_SSH_USER:-root}"
MASTER_PASS_FILE="/etc/portal/secrets/dovecot-master.pass"
mkdir -p /etc/portal/secrets
if [[ -f "$MASTER_PASS_FILE" ]]; then
    log_info "Używam istniejącego $MASTER_PASS_FILE (pominięto pobieranie z VM2)."
elif [[ -f "$SSH_KEY" ]]; then
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
        "${REMOTE_USER}@${VM2_IP}:/etc/portal/secrets/dovecot-master.pass" "$MASTER_PASS_FILE" \
        || die "Nie udało się pobrać hasła mastera z VM2 — czy scripts/vm2/30-postfix-dovecot.sh już się tam wykonał?"
else
    die "Brak $MASTER_PASS_FILE i brak klucza deploy $SSH_KEY. Skopiuj hasło mastera z VM2 (/etc/portal/secrets/dovecot-master.pass) na VM1 do tej samej ścieżki i uruchom ponownie."
fi
chmod 0600 "$MASTER_PASS_FILE"
SSO_MASTER_PASSWORD="$(cat "$MASTER_PASS_FILE")"

# --- 2. Rola DB dla wtyczki (wąskie uprawnienia na tabelę tokenów) ------------
SSO_DB_PASS_FILE="/etc/portal/secrets/vm1-roundcube-sso-db.pass"
ensure_secret_file "$SSO_DB_PASS_FILE" 24
SSO_DB_PASSWORD="$(cat "$SSO_DB_PASS_FILE")"

# Tabela musi już istnieć (migracja 0014). Rola: tylko SELECT/UPDATE na niej.
sudo -u postgres psql -v ON_ERROR_STOP=1 -d portal_db <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'roundcube_sso') THEN
    CREATE ROLE roundcube_sso LOGIN PASSWORD '${SSO_DB_PASSWORD}';
  ELSE
    ALTER ROLE roundcube_sso LOGIN PASSWORD '${SSO_DB_PASSWORD}';
  END IF;
END
\$\$;
GRANT CONNECT ON DATABASE portal_db TO roundcube_sso;
GRANT USAGE ON SCHEMA public TO roundcube_sso;
GRANT SELECT, UPDATE ON webmail_sso_tokens TO roundcube_sso;
SQL

# --- 3. Pliki wtyczki ---------------------------------------------------------
mkdir -p "$PLUGIN_DIR"
install -m 0644 "$REPO_ROOT/templates/roundcube/plugins/portal_sso/portal_sso.php" "$PLUGIN_DIR/portal_sso.php"

# --- 4. Config wtyczki (SEKRETY) ----------------------------------------------
export SSO_DB_PASSWORD SSO_MASTER_PASSWORD
render_template "$REPO_ROOT/templates/roundcube/portal_sso.config.inc.php.tmpl" "$PLUGIN_DIR/config.inc.php" \
    '$SSO_DB_PASSWORD $SSO_MASTER_PASSWORD'
chmod 0640 "$PLUGIN_DIR/config.inc.php"
chown root:roundcube "$PLUGIN_DIR/config.inc.php"
chown -R roundcube:roundcube "$PLUGIN_DIR/portal_sso.php"

# --- 5. Włącz wtyczkę w configu Roundcube (jeśli 40 nie odświeżone) -----------
RC_CFG="$RC_ROOT/config/config.inc.php"
if [[ -f "$RC_CFG" ]] && ! grep -q "portal_sso" "$RC_CFG"; then
    log_warn "config.inc.php nie zawiera portal_sso - uruchom ponownie scripts/vm1/40-roundcube.sh z FORCE_REAPPLY=1, aby dodac wtyczke do listy plugins."
fi

# SELinux: etykiety pod RC_ROOT + php-fpm łączy się z Postgresem (portal_db).
if command -v restorecon >/dev/null 2>&1; then
    restorecon -R "$PLUGIN_DIR" || true
fi
if command -v setsebool >/dev/null 2>&1; then
    setsebool -P httpd_can_network_connect_db on || true
fi

systemctl restart php-fpm

log_info "Wtyczka portal_sso zainstalowana - Otworz w Roundcube z panelu loguje jako master user, audytowane, tylko z sieci admina."
mark_step_done "$STEP_NAME"
