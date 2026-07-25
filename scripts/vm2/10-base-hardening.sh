#!/usr/bin/env bash
# VM2 — krok 10: hardening bazowy — pakiety firewalld/fail2ban + katalog na
# sekrety. SELinux weryfikuje 00-preflight; reguły firewalld ORAZ utwardzenie
# SSH (root tylko kluczem, użytkownicy hasłem) idą w kroku 60-firewall-rules.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../lib/checks.sh"

STEP_NAME="vm2-10-base-hardening"
require_root
step_done "$STEP_NAME"
load_install_conf

check_selinux_enforcing

# fail2ban jest w EPEL, nie w bazowych repo Rocky. firewalld instalujemy już tu
# (reguły dokłada krok 60). policycoreutils-python-utils = semanage dla modułów
# SELinux w kolejnych krokach (Dovecot/mail-spool).
if ! rpm -q epel-release >/dev/null 2>&1; then
    pkg_install_idempotent epel-release
fi
pkg_install_idempotent firewalld fail2ban policycoreutils-python-utils
systemctl enable --now firewalld
# fail2ban startuje z domyślnym jailem sshd (obrona przed brute-force logowania
# hasłem — zwykli użytkownicy mogą się logować hasłem, patrz polityka SSH w 60).
systemctl enable --now fail2ban || log_warn "fail2ban nie wystartował — sprawdź 'journalctl -u fail2ban'."

# Katalog na sekrety (hasła DB itd.) — tworzą je kolejne kroki (np. 20-postgresql
# zapisuje tu vm2-mail-db.pass), więc musi istnieć wcześniej.
mkdir -p /etc/portal/secrets
chmod 0700 /etc/portal/secrets

log_info "Hardening bazowy VM2 zakończony (firewalld/fail2ban zainstalowane, /etc/portal/secrets utworzony; reguły i SSH w kroku 60)."
mark_step_done "$STEP_NAME"
