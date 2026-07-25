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

# wget potrzebne do pobierania po HTTP (force_wget w user.conf) — Rocky Minimal
# go nie ma. curl jest już z pakietów bazowych (00-preflight).
pkg_install_idempotent clamav-unofficial-sigs wget

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
# Marker pierwszego pobrania = urlhaus.ndb (dostarcza je unofficial-sigs po HTTPS).
# phish.ndb pochodzi teraz z pobieracza HTTPS SaneSecurity, więc nie nadaje się
# tu na marker.
if [[ ! -f /var/lib/clamav/urlhaus.ndb ]]; then
    log_info "Pierwsze pobranie sygnatur unofficial (--force, HTTP; może potrwać kilka minut)..."
    # Twardy timeout, żeby przy problemach z siecią krok nie wisiał w nieskończoność
    # (jest nie-krytyczny — SaneSecurity to dodatkowe sygnatury; ClamAV core i rspamd
    # działają niezależnie). Timer i tak ponowi później.
    timeout 900 /usr/sbin/clamav-unofficial-sigs.sh --force \
        || log_warn "Pierwsze pobranie sygnatur nie powiodło się lub przekroczyło limit czasu — pomijam, timer spróbuje ponownie (Ustawienia i tak nie zależą od tego kroku)."
fi

systemctl enable --now clamav-unofficial-sigs.timer

# --- SaneSecurity po HTTPS (własny pobieracz, omija rsync/873) ----------------
# clamav-unofficial-sigs ciągnie SaneSecurity tylko rsynciem; my pobieramy je po
# HTTPS z weryfikacją GPG (w user.conf enable_sanesecurity="no", żeby narzędzie
# nie próbowało rsynca). Reszta darmowych providerów (URLhaus/interServer/LMD)
# idzie dalej przez unofficial-sigs po HTTPS.
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-sanesecurity-http.sh" /usr/local/sbin/vm2-sanesecurity-http.sh
install -d -m 0750 -o root -g root /var/lib/vm2-sanesecurity
install -D -m 0644 "$REPO_ROOT/templates/systemd/vm2-sanesecurity-http.service.tmpl" /etc/systemd/system/vm2-sanesecurity-http.service
install -D -m 0644 "$REPO_ROOT/templates/systemd/vm2-sanesecurity-http.timer.tmpl" /etc/systemd/system/vm2-sanesecurity-http.timer
systemctl daemon-reload
log_info "Pierwsze pobranie SaneSecurity po HTTPS (weryfikacja GPG; kilka minut)..."
timeout 900 /usr/local/sbin/vm2-sanesecurity-http.sh \
    || log_warn "Pobranie SaneSecurity po HTTPS nie w pełni się powiodło — timer spróbuje ponownie."
systemctl enable --now vm2-sanesecurity-http.timer

log_info "Sygnatury ClamAV: SaneSecurity po HTTPS (GPG) + URLhaus/interServer/LMD po HTTPS. Odswiezanie przez timery."
mark_step_done "$STEP_NAME"
