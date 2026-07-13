#!/usr/bin/env bash
# VM2 — krok 40: ClamAV — clamd (skanowanie), freshclam (definicje), milter
# (obrona w głąb dla ewentualnego SMTP) + okresowe skanowanie maildirów
# (pokrywa pocztę dopisaną przez imapsync).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-40-clamav"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
export CLAMAV_FRESHCLAM_INTERVAL_MIN="${CLAMAV_FRESHCLAM_INTERVAL_MIN:-60}"

if ! rpm -q epel-release >/dev/null 2>&1; then
    pkg_install_idempotent epel-release
fi
pkg_install_idempotent clamav clamav-update clamav-server clamav-server-systemd clamav-milter clamav-milter-systemd

mkdir -p /var/log/clamav /run/clamd.scan /run/clamav-milter
chown clamscan:clamscan /var/log/clamav /run/clamd.scan 2>/dev/null || true

render_template "$REPO_ROOT/templates/clamav/freshclam.conf.tmpl" /etc/freshclam.conf
render_template "$REPO_ROOT/templates/clamav/clamd.scan.conf.tmpl" /etc/clamd.d/scan.conf
render_template "$REPO_ROOT/templates/clamav/clamav-milter.conf.tmpl" /etc/mail/clamav-milter.conf

if [[ ! -f /var/lib/clamav/main.cvd && ! -f /var/lib/clamav/main.cld ]]; then
    log_info "Pobieram wstępne definicje wirusów (freshclam)..."
    freshclam || log_warn "Wstępny freshclam nie powiódł się — sprawdź łączność wychodzącą do database.clamav.net; freshclam.timer spróbuje ponownie."
fi

systemctl enable --now clamd@scan
systemctl enable --now clamav-milter@scan 2>/dev/null || systemctl enable --now clamav-milter

install -D -m 0644 "$REPO_ROOT/templates/systemd/clamav-maildir-scan.service.tmpl" /etc/systemd/system/clamav-maildir-scan.service
render_template "$REPO_ROOT/templates/systemd/clamav-maildir-scan.timer.tmpl" /etc/systemd/system/clamav-maildir-scan.timer '$CLAMAV_FRESHCLAM_INTERVAL_MIN'
systemctl daemon-reload
systemctl enable --now clamav-maildir-scan.timer
systemctl enable --now freshclam 2>/dev/null || true

log_info "ClamAV skonfigurowany: clamd + milter (obrona w głąb) + okresowe skanowanie /var/mail/vhosts co ${CLAMAV_FRESHCLAM_INTERVAL_MIN}min."
mark_step_done "$STEP_NAME"
