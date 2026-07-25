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

# reboot-check: nie dnf, lecz needs-restarting — ale ono też jest z rodziny dnf
# (inicjalizuje /var/log/dnf.log, w namespace usługi vm2-api read-only przez
# ProtectSystem=strict), więc bezpośrednio pada z "Config error: Read-only file
# system: /var/log/dnf.log" i MYLĄCO zwraca exit 1 — nieodróżnialne od prawdziwego
# "reboot needed" (to dawało wieczny fałszywy badge "wymagany restart"). Dlatego
# uruchamiamy je jak dnf: transient unit systemd-run POZA sandboxem. Zwracamy jawny
# token i ROZRÓŻNIAMY kody wyjścia (0/1/inne), NIE zgadując "yes" przy błędzie/braku
# binarki (ten sam wzorzec co VM1 apply-system-update.sh reboot-check).
if [[ "$mode" == "reboot-check" ]]; then
    if ! command -v needs-restarting >/dev/null 2>&1; then
        echo "reboot_needed=unknown"; exit 0
    fi
    /usr/bin/systemd-run --quiet --wait --collect \
        -p "StandardOutput=null" -p "StandardError=journal" \
        /usr/bin/needs-restarting -r
    case $? in
        0) echo "reboot_needed=no" ;;
        1) echo "reboot_needed=yes" ;;
        *) echo "reboot_needed=unknown" ;;
    esac
    exit 0
fi

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
