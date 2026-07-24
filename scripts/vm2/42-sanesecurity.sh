#!/usr/bin/env bash
# VM2 — krok 42: SaneSecurity (i inne DARMOWE) sygnatury dla ClamAV przez
# clamav-unofficial-sigs (EPEL). Podnosi wykrywalność zagrożeń MAILOWYCH
# (phishing/scam/złośliwe dokumenty/URL) bez nowego demona — te same clamd/skan.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-42-sanesecurity"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"

pkg_install_idempotent clamav-unofficial-sigs

# Konfiguracja pod nasze clamd (clamscan / /var/lib/clamav / gniazdo skanu).
render_template "$REPO_ROOT/templates/clamav/clamav-unofficial-sigs-user.conf.tmpl" \
    /etc/clamav-unofficial-sigs/user.conf

# Katalogi robocze narzędzia domyślnie należą do clamupdate; my używamy clamscan.
chown -R clamscan:clamscan /var/lib/clamav-unofficial-sigs /var/log/clamav-unofficial-sigs 2>/dev/null || true

# Podwójny mechanizm (cron.d + timer) prowadziłby do dublowanych pobrań →
# usuwamy cron.d, zostawiamy systemd timer (czystszy, respektuje cooldown).
rm -f /etc/cron.d/clamav-unofficial-sigs

# Pierwsze pobranie: --force omija wbudowany cooldown (anty-hammer). Robimy je
# TYLKO gdy sygnatur jeszcze nie ma — inaczej częste --force mogłoby skończyć
# się blokadą IP na mirrorze. Kolejne odświeżenia robi timer (bez --force).
if [[ ! -f /var/lib/clamav/phish.ndb ]]; then
    log_info "Pierwsze pobranie sygnatur unofficial (--force, może potrwać kilka minut)..."
    /usr/sbin/clamav-unofficial-sigs.sh --force || log_warn "Pierwsze pobranie sygnatur nie w pełni się powiodło — timer spróbuje ponownie."
fi

systemctl enable --now clamav-unofficial-sigs.timer

log_info "SaneSecurity/URLhaus + darmowe sygnatury ClamAV skonfigurowane. Odswiezanie przez clamav-unofficial-sigs.timer."
mark_step_done "$STEP_NAME"
