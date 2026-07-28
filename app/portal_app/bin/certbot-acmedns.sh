#!/usr/bin/env bash
# VM1 — wystawia certyfikat Let's Encrypt przez acme-dns (DNS-01) i przełącza
# nginx na nowy cert. Uruchamiany jako root: przez portal-app (sudoers, z panelu)
# albo ręcznie na konsoli. NIE wymaga wystawiania serwera do internetu.
#
# certbot pisze /etc/letsencrypt, /var/log/letsencrypt i uruchamia deploy-hook —
# a usługa portal-app działa w sandboxie (ProtectSystem=full, /etc read-only),
# więc certbota (i dnf) odpalamy jako transient unit przez systemd-run, POZA
# namespace usługi (ten sam wzorzec co vm2-dnf.sh na VM2). Konto acme-dns i host
# bierzemy z /etc/portal/secrets/acmedns.json (zapisuje je portal przy rejestracji).
set -uo pipefail

CREDS=/etc/portal/secrets/acmedns.json
AUTH_HOOK=/usr/local/sbin/acmedns-auth-hook.sh
DEPLOY_HOOK=/etc/letsencrypt/renewal-hooks/deploy/portal-activate.sh

[[ -f "$CREDS" ]]      || { echo "Brak $CREDS — najpierw zarejestruj acme-dns w panelu." >&2; exit 1; }
[[ -x "$AUTH_HOOK" ]]  || { echo "Brak auth-hooka $AUTH_HOOK." >&2; exit 1; }
[[ -f "$DEPLOY_HOOK" ]]|| { echo "Brak deploy-hooka $DEPLOY_HOOK (reinstaluj scripts/vm1/50-portal-app.sh)." >&2; exit 1; }

HOST="$(/usr/bin/python3 -c "import json;print(json.load(open('$CREDS'))['hostname'])")" || exit 1
[[ -n "$HOST" ]] || { echo "Pusty host w $CREDS." >&2; exit 1; }

# systemd-run: uruchom polecenie na HOŚCIE (poza sandboxem usługi). --wait blokuje
# do zakończenia, kod wyjścia jest propagowany; wyjście leci do journala.
run() { /usr/bin/systemd-run --quiet --wait --collect -p StandardOutput=journal -p StandardError=journal "$@"; }

# certbot obecny? (Rocky Minimal go nie ma)
if ! command -v certbot >/dev/null 2>&1; then
    echo "Instaluję certbot..."
    run /usr/bin/dnf install -y certbot || { echo "Instalacja certbota nie powiodła się." >&2; exit 1; }
fi

echo "Wystawiam certyfikat dla ${HOST} przez acme-dns (DNS-01)..."
run /usr/bin/certbot certonly \
    --non-interactive --agree-tos --register-unsafely-without-email \
    --manual --preferred-challenges dns \
    --manual-auth-hook "$AUTH_HOOK" \
    --manual-cleanup-hook /bin/true \
    --deploy-hook "$DEPLOY_HOOK" \
    -d "$HOST"
rc=$?
if [[ $rc -ne 0 ]]; then
    echo "certbot zakończył się błędem (kod $rc). Sprawdź: journalctl -t certbot / /var/log/letsencrypt." >&2
    exit $rc
fi

# certbot na Rocky/EPEL włącza własny timer odnowień (odnowienie użyje tego samego
# auth-hooka i deploy-hooka zapisanych w konfiguracji renewal).
run /usr/bin/systemctl enable --now certbot-renew.timer >/dev/null 2>&1 || true

echo "Gotowe: certyfikat ${HOST} wystawiony i aktywowany (deploy-hook przełączył nginx)."
