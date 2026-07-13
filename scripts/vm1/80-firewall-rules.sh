#!/usr/bin/env bash
# VM1 — krok 80: firewalld — 22/443 tylko z ADMIN_SUBNET_CIDR, domyślna
# polityka drop. Wychodzące połączenia (do VM2, zewnętrznych IMAP, repo
# pakietów) nie są ograniczane przez firewalld (INPUT/FORWARD, nie OUTPUT).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-80-firewall-rules"
require_root
step_done "$STEP_NAME"
load_install_conf

: "${ADMIN_SUBNET_CIDR:?ADMIN_SUBNET_CIDR musi być ustawione w install.conf}"

add_rich_rule() {
    local rule="$1"
    if ! firewall-cmd --permanent --query-rich-rule="$rule" >/dev/null 2>&1; then
        firewall-cmd --permanent --add-rich-rule="$rule"
        log_info "Dodano regułę firewalld: $rule"
    else
        log_info "Reguła już istnieje, pomijam: $rule"
    fi
}

add_rich_rule "rule family='ipv4' source address='${ADMIN_SUBNET_CIDR}' service name='ssh' accept"
add_rich_rule "rule family='ipv4' source address='${ADMIN_SUBNET_CIDR}' port port='443' protocol='tcp' accept"

firewall-cmd --set-default-zone=drop
firewall-cmd --reload

log_info "Firewalld VM1 skonfigurowany: 22/443 tylko z ${ADMIN_SUBNET_CIDR}, reszta domyślnie odrzucana."
mark_step_done "$STEP_NAME"
