#!/usr/bin/env bash
# VM2 — krok 60: firewalld — 143/993 (Dovecot) + 8443 (provisioning API) tylko
# z IP VM1. Reguły idempotentne (firewalld sam ignoruje duplikaty rich rules
# przy --add-rich-rule, ale sprawdzamy jawnie żeby log był czytelny).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-60-firewall-rules"
require_root
step_done "$STEP_NAME"
load_install_conf

: "${VM1_IP:?VM1_IP musi być ustawione w install.conf}"

pkg_install_idempotent firewalld
systemctl enable --now firewalld

add_rich_rule() {
    local rule="$1"
    if ! firewall-cmd --permanent --query-rich-rule="$rule" >/dev/null 2>&1; then
        firewall-cmd --permanent --add-rich-rule="$rule"
        log_info "Dodano regułę firewalld: $rule"
    else
        log_info "Reguła już istnieje, pomijam: $rule"
    fi
}

# KOLEJNOŚĆ JEST KRYTYCZNA — patrz obszerny komentarz w
# scripts/vm1/80-firewall-rules.sh: --add-rich-rule bez --zone= trafia do
# AKTUALNEJ domyślnej strefy w chwili wywołania. Strefę trzeba przełączyć
# na "drop" ZANIM dodamy reguły, inaczej wylądują w nieużywanej strefie
# "public" i SSH/porty zostaną odcięte całkowicie mimo poprawnych reguł.
firewall-cmd --set-default-zone=drop

# Domyślnie odrzucaj wszystko poza SSH z podsieci admina (VM2 też jest
# administrowana zdalnie po SSH z tej samej podsieci co VM1).
add_rich_rule "rule family='ipv4' source address='${ADMIN_SUBNET_CIDR}' service name='ssh' accept"
add_rich_rule "rule family='ipv4' source address='${VM1_IP}/32' port port='143' protocol='tcp' accept"
add_rich_rule "rule family='ipv4' source address='${VM1_IP}/32' port port='993' protocol='tcp' accept"
add_rich_rule "rule family='ipv4' source address='${VM1_IP}/32' port port='587' protocol='tcp' accept"
add_rich_rule "rule family='ipv4' source address='${VM1_IP}/32' port port='${VM2_API_PORT}' protocol='tcp' accept"

firewall-cmd --reload

log_info "Firewalld VM2 skonfigurowany (domyślna polityka: drop)."
mark_step_done "$STEP_NAME"
