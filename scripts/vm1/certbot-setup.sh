#!/usr/bin/env bash
# VM1 — opcjonalny skrypt (NIE część stałej sekwencji 00-90): włącza certbot
# w trybie DNS-01. VM1 nie jest internet-facing, więc HTTP-01 nie zadziała —
# patrz docs/technical/tls-lifecycle.md. Uruchom ręcznie, gdy CERTBOT_DNS_PROVIDER
# i CERTBOT_DNS_CREDENTIALS_FILE są uzupełnione w config/install.conf.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_root
load_install_conf

: "${CERTBOT_DNS_PROVIDER:?Uzupełnij CERTBOT_DNS_PROVIDER w install.conf (np. cloudflare, route53)}"
: "${CERTBOT_DNS_CREDENTIALS_FILE:?Uzupełnij CERTBOT_DNS_CREDENTIALS_FILE w install.conf}"
: "${CERTBOT_EMAIL:?Uzupełnij CERTBOT_EMAIL w install.conf}"
[[ -f "$CERTBOT_DNS_CREDENTIALS_FILE" ]] || die "Plik poświadczeń DNS nie istnieje: $CERTBOT_DNS_CREDENTIALS_FILE"

REPO_ROOT="$(repo_root)"

if ! rpm -q epel-release >/dev/null 2>&1; then
    pkg_install_idempotent epel-release
fi
pkg_install_idempotent certbot "python3-certbot-dns-${CERTBOT_DNS_PROVIDER}"

chmod 0600 "$CERTBOT_DNS_CREDENTIALS_FILE"

mkdir -p /etc/letsencrypt/renewal-hooks/deploy
install -m 0755 "$REPO_ROOT/templates/certbot/deploy-hook.sh.tmpl" /etc/letsencrypt/renewal-hooks/deploy/portal-activate.sh

certbot certonly \
    --non-interactive --agree-tos --email "$CERTBOT_EMAIL" \
    --authenticator "dns-${CERTBOT_DNS_PROVIDER}" \
    --dns-${CERTBOT_DNS_PROVIDER}-credentials "$CERTBOT_DNS_CREDENTIALS_FILE" \
    -d "$VM1_HOSTNAME"

# Pakiet certbot na Rocky/EPEL włącza własny timer odnowień (certbot-renew.timer).
systemctl enable --now certbot-renew.timer 2>/dev/null || true

log_info "certbot skonfigurowany (DNS-01, dostawca: ${CERTBOT_DNS_PROVIDER}). Certyfikat aktywowany przez deploy-hook po pierwszym udanym wystawieniu."
log_info "Ustaw TLS_MODE=certbot w config/install.conf, żeby dokumentacja/dashboard odzwierciedlały ten tryb."
