#!/usr/bin/env bash
# VM1 — krok 70: jaile fail2ban dla admin-auth (portal_app), roundcube-auth
# i nginx-limit-req (eskalacja powtarzalnych 429 do bana). sshd zostaje przy
# domyślnym filtrze fail2ban.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-70-fail2ban-jails"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"

install -m 0644 "$REPO_ROOT/templates/fail2ban/filter-portal-admin-auth.conf" /etc/fail2ban/filter.d/portal-admin-auth.conf
install -m 0644 "$REPO_ROOT/templates/fail2ban/filter-roundcube-auth.conf" /etc/fail2ban/filter.d/roundcube-auth.conf
install -m 0644 "$REPO_ROOT/templates/fail2ban/filter-nginx-limit-req.conf" /etc/fail2ban/filter.d/nginx-limit-req.conf
render_template "$REPO_ROOT/templates/fail2ban/jail-portal.conf.tmpl" /etc/fail2ban/jail.d/portal.conf

touch /var/log/portal/auth.log
chown portal-app:portal-app /var/log/portal/auth.log 2>/dev/null || true

# fail2ban odmawia startu w ogóle (nie tylko pomija jail), jeśli logpath
# jakiegokolwiek skonfigurowanego jaila nie istnieje — obserwowane: "Have not
# found any log file for roundcube-auth jail", cały fail2ban.service pada.
# Roundcube tworzy ten plik dopiero przy pierwszej próbie logowania.
touch /var/log/roundcube/userlogins
chown roundcube:roundcube /var/log/roundcube/userlogins 2>/dev/null || true

systemctl restart fail2ban
sleep 1
systemctl is-active --quiet fail2ban || die "fail2ban nie wystartował — sprawdź journalctl -xeu fail2ban."
fail2ban-client status | grep -q portal-admin-auth || log_warn "portal-admin-auth nie widoczne w fail2ban-client status — sprawdź /var/log/fail2ban.log"

log_info "fail2ban jaile skonfigurowane: sshd, portal-admin-auth, roundcube-auth, nginx-limit-req."
mark_step_done "$STEP_NAME"
