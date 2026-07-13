#!/usr/bin/env bash
# VM1 — krok 30: nginx z repo nginx.org, TLS offload, self-signed 10-letni
# cert domyślnie. Certyfikat aktywny jest zawsze pod /etc/portal/tls/active/
# (symlinki) — przełączanie trybu TLS (Faza 9/11) tylko podmienia symlinki
# i przeładowuje nginx, nigdy nie edytuje konfiguracji server bloku.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-30-nginx"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
export NGINX_REPO_STREAM="${NGINX_REPO_STREAM:-stable}"
export VM1_HOSTNAME

if [[ ! -f /etc/yum.repos.d/nginx.repo ]]; then
    render_template "$REPO_ROOT/templates/nginx/nginx-repo.tmpl" /etc/yum.repos.d/nginx.repo '$NGINX_REPO_STREAM'
fi
rpmkeys --import https://nginx.org/keys/nginx_signing.key 2>/dev/null || true

pkg_install_idempotent nginx

# --- TLS: self-signed 10 lat + struktura active/ dla przyszłych przełączeń ---
TLS_ROOT="/etc/portal/tls"
mkdir -p "$TLS_ROOT/selfsigned" "$TLS_ROOT/manual" "$TLS_ROOT/certbot"
if [[ ! -f "$TLS_ROOT/selfsigned/privkey.pem" ]]; then
    openssl req -x509 -new -nodes -sha256 -days "${TLS_SELFSIGNED_DAYS:-3650}" \
        -subj "/CN=${VM1_HOSTNAME}" \
        -keyout "$TLS_ROOT/selfsigned/privkey.pem" \
        -out "$TLS_ROOT/selfsigned/fullchain.pem"
    chmod 0600 "$TLS_ROOT/selfsigned/privkey.pem"
    log_info "Wygenerowano self-signed certyfikat (10 lat) dla ${VM1_HOSTNAME}."
fi

mkdir -p "$TLS_ROOT/active"
if [[ ! -e "$TLS_ROOT/active/fullchain.pem" ]]; then
    ln -sf "../selfsigned/fullchain.pem" "$TLS_ROOT/active/fullchain.pem"
    ln -sf "../selfsigned/privkey.pem" "$TLS_ROOT/active/privkey.pem"
    log_info "Aktywny TLS: self-signed (domyślnie). Zmiana trybu — patrz docs/technical/tls-lifecycle.md."
fi

# --- Strony błędów (placeholder — nadpisywane przez branding_renderer w Fazie 6) ---
mkdir -p /var/www/errors
install -m 0644 "$REPO_ROOT/templates/nginx/error-pages/404.html" /var/www/errors/404.html
install -m 0644 "$REPO_ROOT/templates/nginx/error-pages/429.html" /var/www/errors/429.html
install -m 0644 "$REPO_ROOT/templates/nginx/error-pages/500.html" /var/www/errors/500.html

# --- Konfiguracja ---------------------------------------------------------------
render_template "$REPO_ROOT/templates/nginx/nginx.conf.tmpl" /etc/nginx/nginx.conf
render_template "$REPO_ROOT/templates/nginx/admin.conf.tmpl" /etc/nginx/conf.d/admin.conf '$VM1_HOSTNAME'

nginx -t || die "Konfiguracja nginx nie przechodzi walidacji (nginx -t) — sprawdź logi powyżej."

if command -v setsebool >/dev/null 2>&1; then
    setsebool -P httpd_can_network_connect on || true
fi

systemctl enable --now nginx
systemctl reload nginx

pkg_install_idempotent python3-dnf-plugin-versionlock
dnf versionlock add nginx 2>/dev/null || true

log_info "nginx skonfigurowany (TLS: self-signed 10 lat, / -> Roundcube [Faza 5], /admin -> portal_app [Faza 6])."
mark_step_done "$STEP_NAME"
