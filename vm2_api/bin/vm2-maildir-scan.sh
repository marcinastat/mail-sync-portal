#!/usr/bin/env bash
# Skan maildirów ClamAV na VM2 — INKREMENTALNY (tylko poczta dopisana od
# ostatniego przebiegu) albo PEŁNY (nocny). Wcześniej skanowano CAŁE 21 GB co
# godzinę (~42 min/przebieg) → maszyna praktycznie bez przerwy re-skanowała to
# samo. Teraz przyrost = sekundy. Wykryte zagrożenia trafiają do findings.jsonl
# (konsumowane przez API VM2 → panel/alerty).
#
#   vm2-maildir-scan.sh              # inkrementalny (domyślny)
#   vm2-maildir-scan.sh full         # pełny (nocny)
set -uo pipefail

MODE="${1:-incremental}"
SCAN_ROOT="/var/mail/vhosts"
STATE_DIR="/var/lib/vm2-scan"
MARKER="${STATE_DIR}/.last-maildir-scan"
LOG="/var/log/clamav/maildir-scan.log"
FINDINGS="${STATE_DIR}/findings.jsonl"
CLAMD_CONF="/etc/clamd.d/scan.conf"

mkdir -p "$STATE_DIR"
ts_now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
EMITTER="/usr/local/sbin/vm2-emit-finding.py"

# --- Zbuduj listę plików do skanu --------------------------------------------
LIST="$(mktemp)"
trap 'rm -f "$LIST" "$OUT" 2>/dev/null' EXIT
if [[ "$MODE" == "full" || ! -f "$MARKER" ]]; then
    find "$SCAN_ROOT" -type f > "$LIST" 2>/dev/null
    SCAN_KIND="pełny"
else
    find "$SCAN_ROOT" -type f -newer "$MARKER" > "$LIST" 2>/dev/null
    SCAN_KIND="inkrementalny"
fi

COUNT="$(wc -l < "$LIST" | tr -d ' ')"
echo "$(ts_now) start skan ${SCAN_KIND}: ${COUNT} plików" >> "$LOG"
if [[ "$COUNT" -eq 0 ]]; then
    echo "$(ts_now) nic nowego do skanu" >> "$LOG"
    touch "$MARKER"
    exit 0
fi

# --- Skan przez clamd (fdpass, tylko zainfekowane w wyjściu) ------------------
OUT="$(mktemp)"
# --multiscan tylko dla pełnego (wiele plików); MaxThreads w scan.conf i tak ogranicza.
MS=()
[[ "$MODE" == "full" ]] && MS=(--multiscan)
clamdscan --config-file="$CLAMD_CONF" --fdpass --infected "${MS[@]}" --file-list="$LIST" >"$OUT" 2>&1
rc=$?
cat "$OUT" >> "$LOG"

# --- Wyłap wykrycia: linie "<ścieżka>: <Sygnatura> FOUND" --------------------
FOUND=0
while IFS= read -r line; do
    case "$line" in
        *": "*" FOUND")
            fpath="${line%%: *}"
            sig="${line#*: }"; sig="${sig% FOUND}"
            # Emiter (root) czyta+dekoduje nagłówki maila i dopisuje finding.
            FSIG="$sig" FENGINE="clamav" FSEV="malware" python3.12 "$EMITTER" "$fpath" >> "$FINDINGS"
            FOUND=$((FOUND+1))
            ;;
    esac
done < "$OUT"

# findings.jsonl musi być czytelne dla API (vm2-api) — panel je pobiera.
chgrp vm2-api "$FINDINGS" 2>/dev/null || true
chmod 0640 "$FINDINGS" 2>/dev/null || true

echo "$(ts_now) koniec skan ${SCAN_KIND}: wykryto ${FOUND}, rc=${rc}" >> "$LOG"
# Marker przesuwamy tylko po udanym skanie (rc 0=czysto, 1=znaleziono) — rc>=2
# to błąd, wtedy NIE przesuwamy, żeby następny przebieg spróbował ponownie.
if [[ "$rc" -le 1 ]]; then touch "$MARKER"; fi
exit 0
