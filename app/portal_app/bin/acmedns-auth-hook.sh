#!/usr/bin/env bash
# certbot manual auth-hook dla acme-dns. certbot ustawia w środowisku
# $CERTBOT_DOMAIN i $CERTBOT_VALIDATION — wysyłamy walidacyjny TXT do serwera
# acme-dns (konto z /etc/portal/secrets/acmedns.json, zapisane przez portal przy
# rejestracji). Let's Encrypt odpytuje potem _acme-challenge.<host>, które CNAME
# wskazuje na acme-dns, więc widzi ten TXT. Cleanup nie jest potrzebny —
# acme-dns trzyma tylko dwa ostatnie TXT i sam je rotuje.
set -uo pipefail

CREDS=/etc/portal/secrets/acmedns.json
[[ -f "$CREDS" ]] || { echo "acmedns-auth-hook: brak $CREDS" >&2; exit 1; }

get() { /usr/bin/python3 -c "import json;print(json.load(open('$CREDS'))['$1'])"; }
SERVER="$(get server)"; USER="$(get username)"; KEY="$(get password)"; SUB="$(get subdomain)"

curl -sS -X POST "${SERVER%/}/update" \
    -H "X-Api-User: $USER" -H "X-Api-Key: $KEY" -H "Content-Type: application/json" \
    --data "{\"subdomain\":\"$SUB\",\"txt\":\"${CERTBOT_VALIDATION}\"}" >/dev/null \
    || { echo "acmedns-auth-hook: aktualizacja TXT w acme-dns nie powiodła się" >&2; exit 1; }

# acme-dns aktualizuje się natychmiast; krótka pauza na wszelki wypadek.
sleep 3
