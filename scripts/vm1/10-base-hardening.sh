#!/usr/bin/env bash
# VM1 — krok 10: hardening bazowy — pakiety firewalld/fail2ban (reguły/jaile
# konfigurowane w późniejszych krokach 70/80), weryfikacja SELinux.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../lib/checks.sh"

STEP_NAME="vm1-10-base-hardening"
require_root
step_done "$STEP_NAME"
load_install_conf

check_selinux_enforcing

pkg_install_idempotent firewalld fail2ban policycoreutils-python-utils
systemctl enable --now firewalld
# Jaile własne (portal-admin-auth, roundcube-auth, nginx-limit-req) dochodzą
# w Fazie 9 — na razie fail2ban startuje z domyślnym jailem sshd.
systemctl enable --now fail2ban

mkdir -p /etc/portal/secrets
chmod 0700 /etc/portal/secrets

log_info "Hardening bazowy VM1 zakończony (firewalld/fail2ban zainstalowane, reguły w kolejnych krokach)."
mark_step_done "$STEP_NAME"
