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

# fail2ban jest w EPEL, nie w bazowych repo Rocky.
if ! rpm -q epel-release >/dev/null 2>&1; then
    pkg_install_idempotent epel-release
fi

pkg_install_idempotent firewalld fail2ban policycoreutils-python-utils
systemctl enable --now firewalld
# Jaile własne (portal-admin-auth, roundcube-auth, nginx-limit-req) dochodzą
# w Fazie 9 — na razie fail2ban startuje z domyślnym jailem sshd.
systemctl enable --now fail2ban

mkdir -p /etc/portal/secrets
chmod 0700 /etc/portal/secrets

# --- Utwardzenie SSH: tylko klucze (root wyłącznie kluczem) -------------------
# ZABEZPIECZENIE: instalujemy TYLKO jeśli root ma już wgrany klucz publiczny —
# inaczej wyłączenie logowania hasłem odcięłoby dostęp do świeżej maszyny.
REPO_ROOT="$(repo_root)"
if [[ -s /root/.ssh/authorized_keys ]]; then
    install -m 0600 -o root -g root "$REPO_ROOT/templates/ssh/00-portal-hardening.conf" /etc/ssh/sshd_config.d/00-portal-hardening.conf
    if sshd -t; then
        systemctl reload sshd
        log_info "SSH utwardzony: tylko klucze, root prohibit-password."
    else
        rm -f /etc/ssh/sshd_config.d/00-portal-hardening.conf
        log_warn "sshd -t nie przeszedł po dodaniu hardeningu SSH — cofnięto zmianę."
    fi
else
    log_warn "Pomijam utwardzenie SSH: brak /root/.ssh/authorized_keys (najpierw wgraj klucz roota, inaczej stracisz dostęp)."
fi

log_info "Hardening bazowy VM1 zakończony (firewalld/fail2ban zainstalowane, reguły w kolejnych krokach)."
mark_step_done "$STEP_NAME"
