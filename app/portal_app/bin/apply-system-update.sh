#!/usr/bin/env bash
# Multi-komendowy helper aktualizacji systemu VM1, uruchamiany jako root przez
# portal-app (sudoers.d/portal-app) z JEDNĄ z ustalonych komend — bez wolnych
# argumentów. Orkiestruje go portal-worker (background job), więc każda faza to
# osobne wywołanie: dzięki temu modal w panelu pokazuje postęp krok-po-kroku.
#
# Komendy:
#   backup                 — kopia zapasowa configów przed aktualizacją
#   update security|all    — dnf update (domyślnie tylko łatki bezpieczeństwa)
#   health                 — health-check kluczowych usług (exit 1 = coś padło)
#   reboot-check           — czy wymagany restart (reboot_needed=yes|no|unknown)
#   reboot                 — zaplanuj restart (osobny, świadomy przycisk w UI)
set -uo pipefail

BACKUP_ROOT="/var/lib/portal-config-backups"
# Configi warte kopii PRZED aktualizacją (tylko pliki konfiguracyjne — małe;
# NIE całe bazy/maildiry). Nieistniejące ścieżki tar po prostu pomija.
BACKUP_PATHS=(
    /etc/nginx
    /etc/portal
    /etc/sudoers.d
    /etc/fail2ban
    /etc/php-fpm.d
    /etc/systemd/system/portal-gunicorn.service
    /etc/systemd/system/portal-worker.service
    /etc/systemd/system/portal-scheduler.service
)
HEALTH_UNITS=(postgresql-17 nginx portal-gunicorn portal-worker php-fpm fail2ban)

cmd="${1:-}"

do_backup() {
    local ts dir
    ts="$(date +%Y%m%d-%H%M%S)"
    dir="${BACKUP_ROOT}/${ts}"
    mkdir -p "$dir"
    # PG trzyma configi w katalogu danych — bierzemy tylko *.conf (nie dane).
    local pg_conf=()
    if [[ -d /var/lib/pgsql/17/data ]]; then
        mapfile -t pg_conf < <(find /var/lib/pgsql/17/data -maxdepth 1 -name '*.conf' 2>/dev/null)
    fi
    tar czf "${dir}/configs.tar.gz" --ignore-failed-read \
        "${BACKUP_PATHS[@]}" "${pg_conf[@]}" 2>/dev/null || true
    # Zapamiętaj listę usług i ich stan (do porównania po aktualizacji).
    systemctl is-enabled "${HEALTH_UNITS[@]}" > "${dir}/units-enabled.txt" 2>&1 || true
    echo "backup_path=${dir}"
    du -sh "$dir" 2>/dev/null | awk '{print "backup_size="$1}'
    # Retencja: zostaw 10 najnowszych kopii.
    ls -1dt "${BACKUP_ROOT}"/*/ 2>/dev/null | tail -n +11 | xargs -r rm -rf
}

do_update() {
    local mode="${1:-security}" args
    case "$mode" in
        security) args=(-y --security update) ;;
        all)      args=(-y update) ;;
        *) echo "apply-system-update: nieznany tryb '$mode' (dozwolone: security|all)" >&2; exit 2 ;;
    esac
    echo "=== dnf ${args[*]} ==="
    # Helper dziedziczy namespace usługi (ProtectSystem=full -> /usr read-only),
    # więc bezpośredni dnf nie zainstalowałby pakietów. Uruchamiamy dnf jako
    # transient unit przez systemd-run — POZA sandboxem usługi. Wynik przez plik
    # + cat (nie --pipe: fd-passing bywa zawodne spod długo działającej usługi).
    local dnf_out="/run/portal-dnf-${mode}.out"
    /usr/bin/systemd-run --quiet --wait --collect \
        -p "StandardOutput=truncate:$dnf_out" -p "StandardError=journal" \
        /usr/bin/dnf "${args[@]}"
    local rc=$?
    # Pełne wyjście (nie ostatnie 6 KB) — trafia do logu na VMce i do panelu.
    tail -c 200000 "$dnf_out" 2>/dev/null
    exit $rc
}

do_health() {
    echo "=== health-check kluczowych usług ==="
    local rc=0 state
    for unit in "${HEALTH_UNITS[@]}"; do
        state="$(systemctl is-active "$unit" 2>/dev/null || true)"
        printf '%-20s %s\n' "$unit" "$state"
        [[ "$state" == "active" ]] || rc=1
    done
    exit $rc
}

do_reboot_check() {
    # needs-restarting -r: exit 0 = brak potrzeby, 1 = wymagany reboot.
    # Gdy binarki brak (dnf-utils nie zainstalowane) — NIE zgadujemy "yes"
    # (to był bug: każdy nie-zerowy kod, w tym 127="command not found",
    # raportował "wymagany reboot" na zawsze, także po reboocie).
    if ! command -v needs-restarting >/dev/null 2>&1; then
        echo "reboot_needed=unknown"
        exit 0
    fi
    needs-restarting -r >/dev/null 2>&1
    case $? in
        0) echo "reboot_needed=no" ;;
        1) echo "reboot_needed=yes" ;;
        *) echo "reboot_needed=unknown" ;;
    esac
}

do_reboot() {
    echo "reboot_scheduled"
    # Odroczony restart, żeby odpowiedź HTTP zdążyła się zwrócić do panelu.
    /usr/bin/systemd-run --quiet --on-active=3 /usr/bin/systemctl reboot
}

case "$cmd" in
    backup)       do_backup ;;
    update)       do_update "${2:-security}" ;;
    health)       do_health ;;
    reboot-check) do_reboot_check ;;
    reboot)       do_reboot ;;
    *) echo "apply-system-update: nieznana komenda '$cmd'" >&2; exit 2 ;;
esac
