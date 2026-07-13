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
LOGO_SRC="/opt/portal-app/portal_app/static/branding/logo.png"
# Roundcube serwuje skin_logo TYLKO z wnętrza katalogu skina (przez static.php
# z walidacją realpath) — ścieżka nginx /admin/static/... jest przez Roundcube
# przepisywana na nieistniejące static.php/skins/elastic/... i daje zepsuty
# obrazek. Dlatego kopiujemy logo do skina; config.inc.php ma skin_logo
# ustawione na 'images/portal-logo.png' (względne do skina).
RC_SKIN_LOGO="/var/www/roundcube/skins/elastic/images/portal-logo.png"

for name in 404 429 500; do
    src="$STAGE_DIR/${name}.html"
    if [[ -f "$src" ]]; then
        install -m 0644 -o root -g root "$src" "$TARGET_DIR/${name}.html"
    fi
done

if [[ -f "$LOGO_SRC" && -d "$(dirname "$RC_SKIN_LOGO")" ]]; then
    install -m 0644 -o roundcube -g roundcube "$LOGO_SRC" "$RC_SKIN_LOGO"
fi

# Dynamiczna konfiguracja Roundcube (product_name + logo jako data: URI) —
# wyrenderowana przez branding_renderer do stagingu, instalowana tu do
# /etc/portal/ (root), skąd config.inc.php ją include'uje. Data: URI omija
# problem z rozwiązywaniem skin_logo przez static.php.
RC_BRANDING_STAGE="$STAGE_DIR/roundcube-branding.php"
RC_BRANDING_TARGET="/etc/portal/roundcube-branding.php"
if [[ -f "$RC_BRANDING_STAGE" ]]; then
    install -m 0644 -o root -g root "$RC_BRANDING_STAGE" "$RC_BRANDING_TARGET"
fi

systemctl reload nginx
