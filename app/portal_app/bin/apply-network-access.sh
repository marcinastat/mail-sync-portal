#!/usr/bin/env bash
# Instaluje wyrenderowane przez portal include'y stref dostępu (allow/deny) do
# /etc/portal/nginx/, testuje konfigurację nginx i przeładowuje ją. Jeśli
# `nginx -t` nie przejdzie — przywraca poprzednie pliki i kończy błędem, żeby
# literówka w CIDR NIGDY nie zostawiła nginx w stanie nie do uruchomienia.
# Uruchamiane jako root wyłącznie przez portal-app (sudoers.d/portal-app), bez
# argumentów (zawsze ten sam staging), spójnie z apply-branding.sh.
set -euo pipefail

STAGE_DIR="/var/lib/portal-app/network-stage"
TARGET_DIR="/etc/portal/nginx"
FILES=(admin-access.conf webmail-access.conf)

mkdir -p "$TARGET_DIR"
backup="$(mktemp -d)"
trap 'rm -rf "$backup"' EXIT

# Kopia zapasowa obecnych plików (do rollbacku).
for f in "${FILES[@]}"; do
    [[ -f "$TARGET_DIR/$f" ]] && cp -a "$TARGET_DIR/$f" "$backup/$f"
done

# Instalacja nowych.
for f in "${FILES[@]}"; do
    if [[ -f "$STAGE_DIR/$f" ]]; then
        install -m 0644 -o root -g root "$STAGE_DIR/$f" "$TARGET_DIR/$f"
    fi
done

# Test + reload, z rollbackiem przy błędzie.
if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "apply-network-access: zastosowano nowe strefy dostępu"
else
    echo "apply-network-access: nginx -t NIE przeszedł — przywracam poprzednią konfigurację" >&2
    for f in "${FILES[@]}"; do
        if [[ -f "$backup/$f" ]]; then
            cp -a "$backup/$f" "$TARGET_DIR/$f"
        else
            rm -f "$TARGET_DIR/$f"
        fi
    done
    nginx -t 2>/dev/null && systemctl reload nginx || true
    exit 1
fi
