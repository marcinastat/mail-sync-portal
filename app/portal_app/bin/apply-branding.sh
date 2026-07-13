#!/usr/bin/env bash
# Uruchamiane jako root wyłącznie przez portal-app (sudoers.d/portal-app,
# patrz templates/sudoers/portal-app.tmpl). Kopiuje wyrenderowane przez
# services/branding_renderer.py strony błędów ze stagingu (zapisywalnego
# przez portal-app) do /var/www/errors (root/nginx) i przeładowuje nginx.
# Argumentów nie przyjmuje celowo — zawsze operuje na tym samym stałym
# katalogu stagingu, żeby sudoers mógł dopuścić komendę bez parametrów.
set -euo pipefail

STAGE_DIR="/var/lib/portal-app/branding-stage"
TARGET_DIR="/var/www/errors"

for name in 404 429 500; do
    src="$STAGE_DIR/${name}.html"
    if [[ -f "$src" ]]; then
        install -m 0644 -o root -g root "$src" "$TARGET_DIR/${name}.html"
    fi
done

systemctl reload nginx
