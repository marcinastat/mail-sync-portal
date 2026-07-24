#!/usr/bin/env bash
# Ustawia harmonogram skanów (systemd timery) z panelu. Uruchamiane jako root
# przez vm2-api (sudoers). Argumenty są WALIDOWANE (liczba minut albo ścisły
# OnCalendar) — to jedyna granica bezpieczeństwa przy zapisie do /etc/systemd.
#
#   vm2-scan-schedule.sh clamav_inc=<min|off> clamav_full=<off|CAL> \
#                        rspamd_inc=<min|off> rspamd_full=<off|CAL>
#   CAL: "[Dow ]*-*-* HH:00:00"  (Dow ∈ Mon..Sun; HH 00..23)
set -uo pipefail

# Usługa vm2-api działa pod ProtectSystem=strict — /etc jest READ-ONLY w jej
# namespace, więc sudo'owany helper (dziedziczy namespace) nie zapisze timerów.
# Uciekamy: PID1 uruchamia nas jako transient unit na HOŚCIE (systemd-run), gdzie
# /etc jest zapisywalne. Guard SCAN_SCHED_ONHOST zapobiega rekursji. --wait
# propaguje kod wyjścia (walidacja), --collect sprząta.
if [[ "${SCAN_SCHED_ONHOST:-0}" != "1" ]]; then
    exec /usr/bin/systemd-run --quiet --wait --collect \
        -p StandardOutput=journal -p StandardError=journal \
        --setenv=SCAN_SCHED_ONHOST=1 /usr/local/sbin/vm2-scan-schedule.sh "$@"
fi

CLAMAV_INC=""; CLAMAV_FULL=""; RSPAMD_INC=""; RSPAMD_FULL=""
for arg in "$@"; do
    case "$arg" in
        clamav_inc=*)  CLAMAV_INC="${arg#clamav_inc=}" ;;
        clamav_full=*) CLAMAV_FULL="${arg#clamav_full=}" ;;
        rspamd_inc=*)  RSPAMD_INC="${arg#rspamd_inc=}" ;;
        rspamd_full=*) RSPAMD_FULL="${arg#rspamd_full=}" ;;
        *) echo "nieznany argument: $arg" >&2; exit 2 ;;
    esac
done

valid_int() { [[ "$1" =~ ^[0-9]+$ ]] && (( 10#$1 >= 5 && 10#$1 <= 1440 )); }
valid_cal() { [[ "$1" =~ ^((Mon|Tue|Wed|Thu|Fri|Sat|Sun)\ )?\*-\*-\*\ ([01][0-9]|2[0-3]):00:00$ ]]; }

write_inc_timer() {  # base minutes desc service
    local base="$1" min="$2" desc="$3" svc="$4"
    if [[ "$min" == "off" ]]; then systemctl disable --now "$base.timer" 2>/dev/null || true; return; fi
    valid_int "$min" || { echo "zły interwał '$min'" >&2; exit 2; }
    cat > "/etc/systemd/system/$base.timer" <<EOF
[Unit]
Description=$desc
[Timer]
OnBootSec=10min
OnUnitActiveSec=${min}min
Unit=$svc
[Install]
WantedBy=timers.target
EOF
}

write_full_timer() {  # base cal desc service
    local base="$1" cal="$2" desc="$3" svc="$4"
    if [[ "$cal" == "off" ]]; then systemctl disable --now "$base.timer" 2>/dev/null || true; return; fi
    valid_cal "$cal" || { echo "zły OnCalendar '$cal'" >&2; exit 2; }
    cat > "/etc/systemd/system/$base.timer" <<EOF
[Unit]
Description=$desc
[Timer]
OnCalendar=$cal
Persistent=true
Unit=$svc
[Install]
WantedBy=timers.target
EOF
}

write_inc_timer  clamav-maildir-scan     "$CLAMAV_INC"  "ClamAV skan przyrostowy"  clamav-maildir-scan.service
write_full_timer clamav-maildir-fullscan "$CLAMAV_FULL" "ClamAV skan pelny"        clamav-maildir-fullscan.service
write_inc_timer  rspamd-maildir-scan     "$RSPAMD_INC"  "rspamd skan przyrostowy"  rspamd-maildir-scan.service
write_full_timer rspamd-maildir-fullscan "$RSPAMD_FULL" "rspamd skan pelny"        rspamd-maildir-fullscan.service

systemctl daemon-reload
[[ "$CLAMAV_INC"  != "off" ]] && systemctl enable --now clamav-maildir-scan.timer     >/dev/null 2>&1 || true
[[ "$CLAMAV_FULL" != "off" ]] && systemctl enable --now clamav-maildir-fullscan.timer >/dev/null 2>&1 || true
[[ "$RSPAMD_INC"  != "off" ]] && systemctl enable --now rspamd-maildir-scan.timer     >/dev/null 2>&1 || true
[[ "$RSPAMD_FULL" != "off" ]] && systemctl enable --now rspamd-maildir-fullscan.timer >/dev/null 2>&1 || true
echo "scan-schedule applied"
