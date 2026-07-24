#!/usr/bin/env bash
# Skan poczty rspamd na VM2 (offline, przez rspamc) — analiza PHISHINGU i
# podejrzanych linków. Skanuje tylko przyrost od ostatniego przebiegu (własny
# marker). Zapisuje wykrycia phishingowe do findings.jsonl (ten sam, co ClamAV).
# CELOWO nie zapisujemy zwykłego spamu (stare newslettery = szum) — tylko
# sygnały phishingu / odrzucenia, zgodnie z intencją: „linki do dziwnych stron".
#
#   vm2-rspamd-scan.sh              # inkrementalny
#   vm2-rspamd-scan.sh full         # pełny (na żądanie; ciężki)
set -uo pipefail

MODE="${1:-incremental}"
SCAN_ROOT="/var/mail/vhosts"
STATE_DIR="/var/lib/vm2-scan"
MARKER="${STATE_DIR}/.last-rspamd-scan"
LOG="/var/log/clamav/rspamd-scan.log"
FINDINGS="${STATE_DIR}/findings.jsonl"

mkdir -p "$STATE_DIR"
ts_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

LIST="$(mktemp)"; trap 'rm -f "$LIST"' EXIT
if [[ "$MODE" == "full" || ! -f "$MARKER" ]]; then
    find "$SCAN_ROOT" -type f -path '*/cur/*' -o -type f -path '*/new/*' > "$LIST" 2>/dev/null
else
    find "$SCAN_ROOT" \( -path '*/cur/*' -o -path '*/new/*' \) -type f -newer "$MARKER" > "$LIST" 2>/dev/null
fi
COUNT="$(wc -l < "$LIST" | tr -d ' ')"
echo "$(ts_now) rspamd start: ${COUNT} plików (${MODE})" >> "$LOG"
if [[ "$COUNT" -eq 0 ]]; then touch "$MARKER"; exit 0; fi

PARSER="/usr/local/sbin/vm2-rspamd-parse.py"
while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    # rspamc -j (JSON: score/action/symbols) na stdin parsera; parser emituje
    # linię findings TYLKO dla phishingu/odrzucenia. FPATH przekazuje ścieżkę.
    /usr/bin/rspamc -j -t 20 symbols < "$f" 2>/dev/null \
        | FPATH="$f" python3.12 "$PARSER" >> "$FINDINGS" || true
done < "$LIST"

chgrp vm2-api "$FINDINGS" 2>/dev/null || true
chmod 0640 "$FINDINGS" 2>/dev/null || true
echo "$(ts_now) rspamd koniec (${MODE})" >> "$LOG"
touch "$MARKER"
exit 0
