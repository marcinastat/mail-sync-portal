#!/usr/bin/env bash
# Uruchamia dnf POZA namespace usługi vm2-api (ProtectSystem=strict blokuje
# zapis do /usr,/var) przez systemd-run jako transient unit. Wynik dnf trafia do
# pliku tymczasowego, który następnie zwykłym `cat` wypisujemy na stdout — dzięki
# temu finalna dostawa do wołającego to normalny potok, a nie przekazywanie fd
# przez D-Bus (systemd-run --pipe gubi output, gdy wołającym jest długo działający
# proces asyncio uvicorna). Uruchamiane jako root przez vm2-api (sudoers),
# z JEDNYM z ustalonych trybów — bez wolnych argumentów.
set -uo pipefail

mode="${1:-}"
case "$mode" in
    check-security)   args=(-q check-update --security) ;;
    check-all)        args=(-q check-update) ;;
    updateinfo)       args=(-q updateinfo summary --available) ;;
    update-security)  args=(-y --security update) ;;
    update-all)       args=(-y update) ;;
    *) echo "vm2-dnf: nieznany tryb '$mode'" >&2; exit 2 ;;
esac

# WAŻNE: helper działa w namespace usługi vm2-api, gdzie /run jest READ-ONLY
# (ProtectSystem=strict) — NIE możemy tu utworzyć pliku (mktemp by padł). Ale
# transient unit systemd-run działa na HOŚCIE (poza sandboxem), gdzie /run jest
# zapisywalny, a namespace ma read-only WIDOK tego samego /run. Dlatego to
# transient unit tworzy/zapisuje plik pod STAŁĄ ścieżką, a helper tylko go CZYTA.
out="/run/vm2-dnf-${mode}.out"
# StandardOutput=truncate: nadpisuje plik przy każdym uruchomieniu (nie narasta).
/usr/bin/systemd-run --quiet --wait --collect \
    -p "StandardOutput=truncate:$out" -p "StandardError=journal" \
    /usr/bin/dnf "${args[@]}"
rc=$?
cat "$out" 2>/dev/null
exit "$rc"
