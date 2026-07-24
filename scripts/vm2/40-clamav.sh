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

mkdir -p /var/log/clamav /run/clamd.scan /run/clamav-milter /run/clamav /var/lib/clamav
# Pakiet EPEL domyślnie zakłada właściciela clamupdate:clamupdate dla
# /var/lib/clamav, ale nasza konfiguracja (freshclam.conf: DatabaseOwner
# clamscan; clamd.scan.conf: User clamscan) świadomie używa jednego,
# spójnego konta clamscan dla wszystkiego — bez tego chowna freshclam nie
# może zapisać baz (obserwowany błąd: "Can't create freshclam.dat").
chown -R clamscan:clamscan /var/log/clamav /run/clamd.scan /run/clamav /var/lib/clamav 2>/dev/null || true

# /run jest tmpfs — czyszczony przy każdym reboocie. Bez reguły tmpfiles.d
# /run/clamav (gdzie freshclam.conf każe zapisywać PidFile) po restarcie VM
# by nie istniał i clamav-freshclam.service padałby z "No such file or
# directory" tak samo jak teraz, dopóki ktoś ręcznie nie doda go z powrotem.
cat > /etc/tmpfiles.d/clamav-freshclam.conf <<'EOF'
d /run/clamav 0755 clamscan clamscan -
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/clamav-freshclam.conf

# freshclam 1.4.3 w trybie demona przy pierwszym starcie próbuje lchown()
# na UpdateLogFile ZANIM go utworzy, jeśli plik jeszcze nie istnieje —
# kończy się "lchown ... failed ... No such file or directory" i wyjściem
# 9. Tworzymy plik z wyprzedzeniem, żeby obejść tę kolejność.
touch /var/log/clamav/freshclam.log
chown clamscan:clamscan /var/log/clamav/freshclam.log
# 0755 nie wystarcza — clamilt (proces miltera, patrz niżej) potrzebuje
# zapisu do /var/log/clamav jako suplementarny członek grupy clamscan, a
# grupowe uprawnienia domyślne (r-x) na to nie pozwalają.
chmod 0770 /var/log/clamav

# Stockowa jednostka RPM clamav-milter.service wymusza User=clamilt (nie
# clamscan) i zdejmuje prawie wszystkie capability (CAP_KILL only) — więc to
# clamilt, nie clamscan, faktycznie uruchamia milter i potrzebuje:
#   - grupy postfix, żeby ustawić grupę gniazda miltera na postfix
#     (MilterSocketGroup postfix w clamav-milter.conf)
#   - grupy clamscan, żeby odczytać/zapisać gniazdo clamd (ClamdSocket,
#     /run/clamd.scan/clamd.sock należy do clamscan:clamscan, mode 0660)
usermod -aG postfix,clamscan clamilt

render_template "$REPO_ROOT/templates/clamav/freshclam.conf.tmpl" /etc/freshclam.conf
render_template "$REPO_ROOT/templates/clamav/clamd.scan.conf.tmpl" /etc/clamd.d/scan.conf
render_template "$REPO_ROOT/templates/clamav/clamav-milter.conf.tmpl" /etc/mail/clamav-milter.conf

if [[ ! -f /var/lib/clamav/main.cvd && ! -f /var/lib/clamav/main.cld ]]; then
    log_info "Pobieram wstępne definicje wirusów (freshclam)..."
    freshclam || log_warn "Wstępny freshclam nie powiódł się — sprawdź łączność wychodzącą do database.clamav.net; freshclam.timer spróbuje ponownie."
fi

# reset-failed: jeśli poprzednie uruchomienie tego skryptu nie powiodło się
# (np. przez brak uprawnień do /var/lib/clamav, patrz wyżej), systemd mógł
# wejść w start-limit-hit i odmawiać restartu mimo poprawionej przyczyny.
systemctl reset-failed clamd@scan.service clamav-milter@scan.service clamav-milter.service clamav-freshclam.service 2>/dev/null || true

# Stary plik pid po nieudanym/przerwanym starcie bywa root:root (proces
# docelowo działa jako clamilt — patrz komentarz przy usermod wyżej) i
# blokuje kolejny start ("Can't save PID in file ..."); bezpieczne do
# usunięcia, systemd i tak śledzi proces po swoim cgroup, nie po tym pliku.
rm -f /run/clamav-milter/clamav-milter.pid

systemctl enable --now clamd@scan
# Milter (ścieżka SMTP) jest WYŁĄCZONY: poczta na VM2 wchodzi przez imapsync
# (IMAP APPEND), nie przez SMTP, więc milter nic nie skanuje, a wisiał jako
# `failed`. Pokrycie zapewnia skan maildirów (niżej). Gdyby kiedyś doszła
# realna ścieżka SMTP — włączyć ponownie clamav-milter@scan.
systemctl disable --now clamav-milter@scan clamav-milter 2>/dev/null || true
systemctl reset-failed clamav-milter@scan.service clamav-milter.service 2>/dev/null || true

# Skan maildirów: INKREMENTALNY co interwał (tani — tylko przyrost) + PEŁNY nocny.
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-maildir-scan.sh" /usr/local/sbin/vm2-maildir-scan.sh
install -d -m 0750 -o root -g root /var/lib/vm2-scan
# Zasiej marker, żeby PIERWSZY skan przyrostowy nie ruszał całych 21 GB (backlog
# pokrył już wcześniejszy skan; pełne przeskanowanie z NOWYMI opcjami zrobi
# nocny fullscan). Bez tego pierwszy przebieg trwałby ~42 min.
[[ -f /var/lib/vm2-scan/.last-maildir-scan ]] || touch /var/lib/vm2-scan/.last-maildir-scan
install -D -m 0644 "$REPO_ROOT/templates/systemd/clamav-maildir-scan.service.tmpl" /etc/systemd/system/clamav-maildir-scan.service
render_template "$REPO_ROOT/templates/systemd/clamav-maildir-scan.timer.tmpl" /etc/systemd/system/clamav-maildir-scan.timer '$CLAMAV_FRESHCLAM_INTERVAL_MIN'
install -D -m 0644 "$REPO_ROOT/templates/systemd/clamav-maildir-fullscan.service.tmpl" /etc/systemd/system/clamav-maildir-fullscan.service
install -D -m 0644 "$REPO_ROOT/templates/systemd/clamav-maildir-fullscan.timer.tmpl" /etc/systemd/system/clamav-maildir-fullscan.timer
systemctl daemon-reload
systemctl enable --now clamav-maildir-scan.timer clamav-maildir-fullscan.timer
# Nazwa jednostki to clamav-freshclam (nie "freshclam") — działa w trybie
# demona (freshclam -d), respektując "Checks 24" z freshclam.conf.
systemctl enable --now clamav-freshclam

log_info "ClamAV skonfigurowany: clamd + milter (obrona w głąb) + okresowe skanowanie /var/mail/vhosts co ${CLAMAV_FRESHCLAM_INTERVAL_MIN}min."
mark_step_done "$STEP_NAME"
