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

REPO_ROOT="$(repo_root)"

# fail2ban jest w EPEL, nie w bazowych repo Rocky. firewalld instalujemy już tu
# (reguły dokłada krok 60). policycoreutils-python-utils = semanage dla modułów
# SELinux w kolejnych krokach (Dovecot/mail-spool).
if ! rpm -q epel-release >/dev/null 2>&1; then
    pkg_install_idempotent epel-release
fi
pkg_install_idempotent firewalld fail2ban policycoreutils-python-utils
systemctl enable --now firewalld

# fail2ban 1.x NIE włącza żadnego jaila domyślnie — bez własnego jail.d SSH nie
# jest chroniony (obserwowane: `fail2ban-client status` = 0 jaili). Instalujemy
# jail sshd (backend=systemd, bo Minimal nie ma /var/log/secure) PRZED startem,
# żeby usługa od razu wstała z aktywnym jailem. Restart (nie tylko enable --now),
# bo przy re-runie działający fail2ban nie przeładowałby nowej konfiguracji.
install -D -m 0644 "$REPO_ROOT/templates/fail2ban/jail-vm2.conf" /etc/fail2ban/jail.d/vm2.conf
systemctl enable fail2ban
systemctl restart fail2ban || log_warn "fail2ban nie wystartował — sprawdź 'journalctl -u fail2ban' i 'fail2ban-client -d'."

# Katalog na sekrety (hasła DB itd.) — tworzą je kolejne kroki (np. 20-postgresql
# zapisuje tu vm2-mail-db.pass), więc musi istnieć wcześniej.
mkdir -p /etc/portal/secrets
chmod 0700 /etc/portal/secrets

log_info "Hardening bazowy VM2 zakończony (firewalld + fail2ban z jailem sshd, /etc/portal/secrets utworzony; reguły firewalld i SSH w kroku 60)."
mark_step_done "$STEP_NAME"
