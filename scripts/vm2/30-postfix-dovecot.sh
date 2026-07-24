#!/usr/bin/env bash
# VM2 — krok 30: Postfix (virtual mailbox domains, LMTP->Dovecot) + Dovecot
# (IMAP/IMAPS, SQL passdb/userdb backed by mail_db). Tylko dostarczanie
# lokalne — patrz komentarz w templates/postfix/main.cf.tmpl.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-30-postfix-dovecot"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
DB_PASS_FILE="/etc/portal/secrets/vm2-mail-db.pass"
[[ -f "$DB_PASS_FILE" ]] || die "Brak $DB_PASS_FILE — uruchom najpierw scripts/vm2/20-postgresql.sh"
export MAIL_DB_PASSWORD
MAIL_DB_PASSWORD="$(cat "$DB_PASS_FILE")"
export VM2_HOSTNAME

mountpoint -q /var/mail/vhosts || die "/var/mail/vhosts nie jest zamontowanym dyskiem — uruchom najpierw scripts/vm2/25-mail-disk.sh (VM2 wymaga osobnego dysku na pocztę)."

pkg_install_idempotent postfix dovecot dovecot-pgsql postfix-pgsql

# --- Użytkownik systemowy dla skrzynek wirtualnych --------------------------
if ! id vmail >/dev/null 2>&1; then
    groupadd -g 5000 vmail
    useradd -u 5000 -g vmail -d /var/mail/vhosts -s /sbin/nologin -c "Virtual mail user" vmail
fi
mkdir -p /var/mail/vhosts
chown vmail:vmail /var/mail/vhosts
chmod 0750 /var/mail/vhosts

# --- Certyfikat TLS dla Dovecot (self-signed, 10 lat, ruch tylko wewnętrzny) --
DOVECOT_TLS_DIR="/etc/pki/dovecot"
export DOVECOT_TLS_CERT="$DOVECOT_TLS_DIR/dovecot.crt"
export DOVECOT_TLS_KEY="$DOVECOT_TLS_DIR/dovecot.key"
mkdir -p "$DOVECOT_TLS_DIR"
if [[ ! -f "$DOVECOT_TLS_KEY" ]]; then
    openssl req -x509 -new -nodes -sha256 -days 3650 \
        -subj "/CN=${VM2_HOSTNAME}" \
        -keyout "$DOVECOT_TLS_KEY" -out "$DOVECOT_TLS_CERT"
    chmod 0600 "$DOVECOT_TLS_KEY"
fi

# --- Postfix -----------------------------------------------------------------
render_template "$REPO_ROOT/templates/postfix/main.cf.tmpl" /etc/postfix/main.cf '$VM2_HOSTNAME $DOVECOT_TLS_CERT $DOVECOT_TLS_KEY'
render_template "$REPO_ROOT/templates/postfix/pgsql-virtual-mailbox-domains.cf.tmpl" /etc/postfix/pgsql-virtual-mailbox-domains.cf '$MAIL_DB_PASSWORD'
render_template "$REPO_ROOT/templates/postfix/pgsql-virtual-mailbox-maps.cf.tmpl" /etc/postfix/pgsql-virtual-mailbox-maps.cf '$MAIL_DB_PASSWORD'
chmod 0640 /etc/postfix/pgsql-virtual-mailbox-*.cf
chgrp postfix /etc/postfix/pgsql-virtual-mailbox-*.cf

# Usługa "submission" (587, SASL przez Dovecot) — pozwala Roundcube na VM1
# faktycznie wysyłać/odpowiadać na pocztę ze zsynchronizowanych skrzynek.
# Dopisywana raz do domyślnego master.cf pakietu (nie nadpisujemy całego
# pliku, żeby nie replikować reszty stockowej konfiguracji Postfiksa).
if ! grep -q '^submission inet' /etc/postfix/master.cf; then
    cat >> /etc/postfix/master.cf <<'MASTERCF'

submission inet n       -       n       -       -       smtpd
  -o syslog_name=postfix/submission
  -o smtpd_tls_security_level=encrypt
  -o smtpd_sasl_auth_enable=yes
  -o smtpd_sasl_type=dovecot
  -o smtpd_sasl_path=private/auth
  -o smtpd_relay_restrictions=permit_sasl_authenticated,reject
  -o smtpd_recipient_restrictions=permit_sasl_authenticated,reject
  -o milter_macro_daemon_name=ORIGINATING
MASTERCF
    log_info "Dodano usługę submission (587) do /etc/postfix/master.cf."
fi

# --- Dovecot -------------------------------------------------------------------
render_template "$REPO_ROOT/templates/dovecot/dovecot-sql.conf.ext.tmpl" /etc/dovecot/dovecot-sql.conf.ext '$MAIL_DB_PASSWORD'
chmod 0640 /etc/dovecot/dovecot-sql.conf.ext
chgrp dovecot /etc/dovecot/dovecot-sql.conf.ext

render_template "$REPO_ROOT/templates/dovecot/10-mail.conf.tmpl" /etc/dovecot/conf.d/10-mail.conf
render_template "$REPO_ROOT/templates/dovecot/10-master.conf.tmpl" /etc/dovecot/conf.d/10-master.conf
render_template "$REPO_ROOT/templates/dovecot/10-ssl.conf.tmpl" /etc/dovecot/conf.d/10-ssl.conf '$DOVECOT_TLS_CERT $DOVECOT_TLS_KEY'
render_template "$REPO_ROOT/templates/dovecot/10-auth.conf.tmpl" /etc/dovecot/conf.d/10-auth.conf

# --- Master user (impersonacja z panelu: „Otwórz w Roundcube") ----------------
# Hasło mastera generujemy RAZ i trzymamy jako plaintext w /etc/portal/secrets
# (root 0600). VM1 pobiera je fetch-skryptem (scripts/vm1/55-webmail-sso.sh),
# żeby wtyczka Roundcube mogła logować się jako master. Plik master-users trzyma
# tylko HASH (SHA512-CRYPT) — regenerowany z sekretu przy każdym uruchomieniu.
MASTER_USER="portaladmin"
MASTER_PASS_FILE="/etc/portal/secrets/dovecot-master.pass"
ensure_secret_file "$MASTER_PASS_FILE" 24
MASTER_HASH="$(doveadm pw -s SHA512-CRYPT -p "$(cat "$MASTER_PASS_FILE")")"
printf '%s:%s\n' "$MASTER_USER" "$MASTER_HASH" > /etc/dovecot/master-users
chmod 0640 /etc/dovecot/master-users
chgrp dovecot /etc/dovecot/master-users
render_template "$REPO_ROOT/templates/dovecot/20-master-user.conf.tmpl" /etc/dovecot/conf.d/20-master-user.conf

# SELinux: pozwól Postfiksowi łączyć się z Postgresem po TCP i Dovecotowi
# czytać/pisać w /var/mail/vhosts poza domyślną etykietą.
if command -v setsebool >/dev/null 2>&1; then
    setsebool -P postfix_can_network_connect_db on || true
fi
if command -v semanage >/dev/null 2>&1; then
    semanage fcontext -a -t mail_spool_t "/var/mail/vhosts(/.*)?" 2>/dev/null || true
    restorecon -R /var/mail/vhosts || true
fi

systemctl enable --now postfix dovecot
systemctl restart postfix dovecot

log_info "Postfix + Dovecot skonfigurowane (domeny wirtualne z mail_db)."
mark_step_done "$STEP_NAME"
