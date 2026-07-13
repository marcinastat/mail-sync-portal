#!/usr/bin/env bash
# VM1 — krok 40: php-fpm + Roundcube (wersja z install.conf), config.inc.php
# wskazany na roundcube_db (Faza 4) i VM2 Dovecot/Postfix (Faza 2).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-40-roundcube"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
RC_VERSION="${ROUNDCUBE_VERSION:?ROUNDCUBE_VERSION musi być ustawione}"
RC_ROOT="/var/www/roundcube"
DB_PASS_FILE="/etc/portal/secrets/vm1-roundcube-db.pass"
DES_KEY_FILE="/etc/portal/secrets/vm1-roundcube-des.key"

[[ -f "$DB_PASS_FILE" ]] || die "Brak $DB_PASS_FILE — uruchom najpierw scripts/vm1/20-postgresql.sh"

pkg_install_idempotent php-fpm php-cli php-common php-json php-xml php-mbstring \
    php-intl php-pdo php-pgsql php-gd php-zip php-curl php-opcache php-sodium

if [[ ! -d "$RC_ROOT/public_html" ]]; then
    log_info "Pobieram Roundcube ${RC_VERSION}..."
    TMP_TARBALL="$(mktemp)"
    curl -fsSL -o "$TMP_TARBALL" \
        "https://github.com/roundcube/roundcubemail/releases/download/${RC_VERSION}/roundcubemail-${RC_VERSION}-complete.tar.gz"
    mkdir -p "$RC_ROOT"
    tar -xzf "$TMP_TARBALL" -C "$RC_ROOT" --strip-components=1
    rm -f "$TMP_TARBALL"
fi

id roundcube >/dev/null 2>&1 || useradd --system --home-dir "$RC_ROOT" --shell /sbin/nologin roundcube
chown -R roundcube:roundcube "$RC_ROOT"
mkdir -p /var/log/roundcube
chown roundcube:roundcube /var/log/roundcube

# Placeholder logo skina — config.inc.php ustawia skin_logo na
# images/portal-logo.png; branding admina nadpisze go później przez
# apply-branding.sh. Bez placeholdera (zanim admin skonfiguruje branding)
# Roundcube pokazywałby zepsuty obrazek. Używamy stockowego thumbnail.png
# skina (prawdziwy PNG), jeśli własny plik jeszcze nie istnieje.
RC_SKIN_LOGO="$RC_ROOT/skins/elastic/images/portal-logo.png"
if [[ ! -f "$RC_SKIN_LOGO" && -f "$RC_ROOT/skins/elastic/thumbnail.png" ]]; then
    install -m 0644 -o roundcube -g roundcube "$RC_ROOT/skins/elastic/thumbnail.png" "$RC_SKIN_LOGO"
fi

ensure_secret_file "$DES_KEY_FILE" 18  # base64(18 bajtów) daje 24 znaki wymagane przez Roundcube

export ROUNDCUBE_DB_PASSWORD ROUNDCUBE_DES_KEY VM2_HOSTNAME
ROUNDCUBE_DB_PASSWORD="$(cat "$DB_PASS_FILE")"
ROUNDCUBE_DES_KEY="$(cat "$DES_KEY_FILE")"

render_template "$REPO_ROOT/templates/roundcube/config.inc.php.tmpl" "$RC_ROOT/config/config.inc.php" \
    '$ROUNDCUBE_DB_PASSWORD $VM2_HOSTNAME $ROUNDCUBE_DES_KEY'
chmod 0640 "$RC_ROOT/config/config.inc.php"
chgrp roundcube "$RC_ROOT/config/config.inc.php"

# --- Schemat bazy (jednorazowo) -------------------------------------------------
SCHEMA_MARKER="/var/lib/portal-install/.steps/vm1-roundcube-db-schema"
if [[ ! -f "$SCHEMA_MARKER" ]]; then
    PGPASSWORD="$ROUNDCUBE_DB_PASSWORD" psql -h 127.0.0.1 -U roundcube_app -d roundcube_db \
        -v ON_ERROR_STOP=1 -f "$RC_ROOT/SQL/postgres.initial.sql"
    mark_step_done "vm1-roundcube-db-schema"
fi

# --- php-fpm pool ----------------------------------------------------------------
cat > /etc/php-fpm.d/roundcube.conf <<'PHPFPM'
[roundcube]
user = roundcube
group = roundcube
listen = /run/php-fpm/roundcube.sock
listen.owner = nginx
listen.group = nginx
listen.mode = 0660
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 4
php_admin_value[error_log] = /var/log/roundcube/php-fpm-error.log
php_admin_flag[log_errors] = on
PHPFPM
mkdir -p /run/php-fpm

if command -v setsebool >/dev/null 2>&1; then
    setsebool -P httpd_can_network_connect on || true
fi

systemctl enable --now php-fpm
systemctl restart php-fpm

nginx -t && systemctl reload nginx || log_warn "nginx -t nie przeszło — sprawdź konfigurację (Faza 4)."

log_info "Roundcube ${RC_VERSION} zainstalowane pod $RC_ROOT (IMAP/SMTP -> ${VM2_HOSTNAME})."
mark_step_done "$STEP_NAME"
