#!/usr/bin/env bash
# Uruchamiane jako root wyłącznie przez portal-app (sudoers.d/portal-app).
# Przełącza /etc/portal/tls/active/* na wskazane źródło TYLKO jeśli `nginx -t`
# przechodzi po przełączeniu; w razie błędu przywraca poprzedni cel symlinka
# i kończy się niezerowym kodem — nginx nigdy nie zostaje z niepoprawnym TLS.
#
# Użycie: apply-tls.sh <manual|certbot|selfsigned>
set -euo pipefail

MODE="${1:?Użycie: apply-tls.sh <manual|certbot|selfsigned>}"
TLS_ROOT="/etc/portal/tls"
ACTIVE_DIR="$TLS_ROOT/active"

case "$MODE" in
    manual)
        SOURCE_DIR="$TLS_ROOT/manual"
        STAGE_DIR="/var/lib/portal-app/tls-stage"
        [[ -f "$STAGE_DIR/fullchain.pem" && -f "$STAGE_DIR/privkey.pem" ]] || { echo "Brak wystagowanych plików w $STAGE_DIR" >&2; exit 1; }
        mkdir -p "$SOURCE_DIR"
        install -m 0644 "$STAGE_DIR/fullchain.pem" "$SOURCE_DIR/fullchain.pem"
        install -m 0600 "$STAGE_DIR/privkey.pem" "$SOURCE_DIR/privkey.pem"
        shred -u "$STAGE_DIR/fullchain.pem" "$STAGE_DIR/privkey.pem"
        ;;
    certbot)   SOURCE_DIR="$TLS_ROOT/certbot" ;;
    selfsigned) SOURCE_DIR="$TLS_ROOT/selfsigned" ;;
    *) echo "Nieznany tryb: $MODE" >&2; exit 1 ;;
esac

[[ -f "$SOURCE_DIR/fullchain.pem" && -f "$SOURCE_DIR/privkey.pem" ]] || { echo "Brak plików w $SOURCE_DIR" >&2; exit 1; }

PREV_FULLCHAIN_TARGET="$(readlink "$ACTIVE_DIR/fullchain.pem" 2>/dev/null || true)"
PREV_PRIVKEY_TARGET="$(readlink "$ACTIVE_DIR/privkey.pem" 2>/dev/null || true)"

ln -sf "../$(basename "$SOURCE_DIR")/fullchain.pem" "$ACTIVE_DIR/fullchain.pem"
ln -sf "../$(basename "$SOURCE_DIR")/privkey.pem" "$ACTIVE_DIR/privkey.pem"

if nginx -t; then
    systemctl reload nginx
    echo "TLS przełączony na tryb: $MODE"
else
    echo "nginx -t nie przeszło po przełączeniu na $MODE — wycofuję." >&2
    if [[ -n "$PREV_FULLCHAIN_TARGET" ]]; then
        ln -sf "$PREV_FULLCHAIN_TARGET" "$ACTIVE_DIR/fullchain.pem"
        ln -sf "$PREV_PRIVKEY_TARGET" "$ACTIVE_DIR/privkey.pem"
        nginx -t && systemctl reload nginx
    fi
    exit 1
fi
