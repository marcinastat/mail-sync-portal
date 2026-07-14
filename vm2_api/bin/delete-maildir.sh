#!/usr/bin/env bash
# Kasuje DOKŁADNIE JEDEN maildir skrzynki: /var/mail/vhosts/<domena>/<local_part>.
# Uruchamiane jako root wyłącznie przez vm2-api (sudoers.d/vm2-api), po tym jak
# API usunęło rekord z mail_db. Argumenty są ściśle walidowane — żadnych
# metaznaków powłoki, żadnego path-traversal — więc mimo wieloznacznika w
# sudoers (delete-maildir.sh *) nie da się wskazać ścieżki poza korzeniem poczty.
set -euo pipefail

MAIL_ROOT="/var/mail/vhosts"
domain="${1:-}"
local_part="${2:-}"

# Dozwolone tylko: litery, cyfry, kropka, myślnik, podkreślenie. To wyklucza
# "/", "..", spacje i wszelkie metaznaki — nie da się uciec z MAIL_ROOT.
valid='^[A-Za-z0-9._-]+$'
if [[ ! "$domain" =~ $valid ]] || [[ ! "$local_part" =~ $valid ]]; then
    echo "delete-maildir: niedozwolone znaki w argumencie" >&2
    exit 2
fi
# Dodatkowa bariera: kropka na początku (np. samo "..") jest zabroniona.
if [[ "$domain" == .* ]] || [[ "$local_part" == .* ]]; then
    echo "delete-maildir: argument nie może zaczynać się od kropki" >&2
    exit 2
fi

target="$MAIL_ROOT/$domain/$local_part"

# Realpath MUSI pozostać wewnątrz MAIL_ROOT (obrona w głąb, gdyby powyższe
# przeoczyło jakiś przypadek). Jeśli katalog nie istnieje — to nie błąd
# (skrzynka mogła nigdy się nie zalogować i Dovecot nie utworzył Maildira).
if [[ ! -e "$target" ]]; then
    echo "delete-maildir: brak katalogu $target (pomijam)"
    exit 0
fi
resolved="$(readlink -f "$target")"
case "$resolved" in
    "$MAIL_ROOT"/*) : ;;
    *) echo "delete-maildir: ścieżka poza $MAIL_ROOT — odmawiam" >&2; exit 3 ;;
esac

rm -rf -- "$resolved"
echo "delete-maildir: usunięto $resolved"
