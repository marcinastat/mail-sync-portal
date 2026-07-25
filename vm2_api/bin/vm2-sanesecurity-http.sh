#!/usr/bin/env bash
# Pobieracz sygnatur SaneSecurity po HTTPS (omija rsync/873, który bywa
# zablokowany na wychodzącym ruchu). Każda baza jest WERYFIKOWANA podpisem GPG
# SaneSecurity i testowana clamscanem przed instalacją do /var/lib/clamav; na
# koniec clamd jest przeładowywany. Uruchamiane jako root (timer/instalator).
#
# Dlaczego własny skrypt: clamav-unofficial-sigs pobiera SaneSecurity WYŁĄCZNIE
# przez rsync (rsync:// na sztywno) — nie ma tam ścieżki HTTP. URLhaus/interServer/
# LinuxMalwareDetect mają URL-e https i te idą przez force_wget w unofficial-sigs.
set -uo pipefail

MIRRORS=("https://mirror.rollernet.us/sanesecurity" "https://ftp.swin.edu.au/sanesecurity")
GPG_KEY_URL="https://www.sanesecurity.com/publickey.gpg"
CLAM_DB="/var/lib/clamav"
WORK="/var/lib/vm2-sanesecurity"
GPG_HOME="$WORK/gpg"
CLAMD_CONF="/etc/clamd.d/scan.conf"
LOG="/var/log/clamav/sanesecurity-http.log"

# Zestaw baz SaneSecurity: REQUIRED + LOW + MEDIUM (zgodnie z domyślami
# clamav-unofficial-sigs). Bazy HIGH (foxhole_all*, foxhole_mail, winnow_phish_
# complete) POMIJAMY — bywają fałszywie dodatnie. Nieistniejące na mirrorze są
# pomijane (np. wycofane) bez błędu.
DBS=(
    sanesecurity.ftm sigwhitelist.ign2
    blurl.ndb junk.ndb jurlbl.ndb malwarehash.hsb phish.ndb rogue.hdb scam.ndb
    spamattach.hdb spamimg.hdb foxhole_filename.cdb foxhole_generic.cdb
    winnow_bad_cw.hdb winnow_extended_malware.hdb winnow_malware_links.ndb
    winnow_malware.hdb winnow_phish_complete_url.ndb winnow.attachments.hdb
    badmacro.ndb jurlbla.ndb lott.ndb shelter.ldb spam.ldb spear.ndb spearl.ndb
    foxhole_js.cdb foxhole_js.ndb winnow_extended_malware_links.ndb
    winnow_spam_complete.ndb winnow.complex.patterns.ldb MiscreantPunch099-Low.ldb
)

mkdir -p "$WORK" "$GPG_HOME"; chmod 700 "$GPG_HOME"
ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) $*" >> "$LOG"; }

# --- 1. Klucz GPG SaneSecurity (raz) ------------------------------------------
if [[ ! -f "$GPG_HOME/imported" ]]; then
    if curl -fsS --max-time 30 "$GPG_KEY_URL" -o "$WORK/publickey.gpg" \
        && gpg --homedir "$GPG_HOME" --import "$WORK/publickey.gpg" 2>/dev/null; then
        touch "$GPG_HOME/imported"
    else
        log "BŁĄD: nie udało się pobrać/zaimportować klucza GPG SaneSecurity"
        exit 1
    fi
fi

fetch() {  # $1=nazwa -> pobiera $1 i $1.sig do WORK z pierwszego działającego mirrora
    local f="$1" m
    for m in "${MIRRORS[@]}"; do
        if curl -fsS --max-time 180 "$m/$f" -o "$WORK/$f.new" \
            && curl -fsS --max-time 60 "$m/$f.sig" -o "$WORK/$f.sig.new"; then
            return 0
        fi
    done
    return 1
}

EMPTY="$WORK/.scan-test"; : > "$EMPTY"
changed=0; failed=0; skipped=0
log "start pobierania SaneSecurity po HTTPS (${#DBS[@]} baz)"

for db in "${DBS[@]}"; do
    if ! fetch "$db"; then
        rm -f "$WORK/$db.new" "$WORK/$db.sig.new"
        skipped=$((skipped+1)); continue      # brak na mirrorze / wycofana — pomijamy
    fi
    # Weryfikacja podpisu GPG — DOWÓD autentyczności (klucz SaneSecurity).
    if ! gpg --homedir "$GPG_HOME" --trust-model always --verify "$WORK/$db.sig.new" "$WORK/$db.new" 2>/dev/null; then
        log "GPG FAIL: $db — pomijam (możliwa podmiana/uszkodzenie)"
        rm -f "$WORK/$db.new" "$WORK/$db.sig.new"; failed=$((failed+1)); continue
    fi
    # Test integralności clamscanem (poza .ftm/.ign2 — nie ładują się samodzielnie).
    case "$db" in
        *.ftm|*.ign2) : ;;
        *)
            if ! clamscan --quiet -d "$WORK/$db.new" "$EMPTY" >/dev/null 2>&1; then
                rc=$?
                if [[ "$rc" -ge 2 ]]; then
                    log "clamscan integralność BŁĄD: $db (rc=$rc) — pomijam"
                    rm -f "$WORK/$db.new" "$WORK/$db.sig.new"; failed=$((failed+1)); continue
                fi
            fi
            ;;
    esac
    # Instaluj tylko, jeśli się zmieniła (oszczędza reload).
    if ! cmp -s "$WORK/$db.new" "$CLAM_DB/$db" 2>/dev/null; then
        install -m 0644 -o clamscan -g clamscan "$WORK/$db.new" "$CLAM_DB/$db"
        changed=$((changed+1))
    fi
    rm -f "$WORK/$db.new" "$WORK/$db.sig.new"
done

log "koniec: zaktualizowane=$changed, błędy=$failed, pominięte=$skipped"

if [[ "$changed" -gt 0 ]]; then
    clamdscan --reload -c "$CLAMD_CONF" >/dev/null 2>&1 \
        || systemctl reload clamd@scan >/dev/null 2>&1 || true
    log "przeładowano clamd (zmienione bazy: $changed)"
fi
exit 0
