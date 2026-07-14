#!/usr/bin/env bash
# Narzędzie ratunkowe (konsola VM1) — przywraca kopię configów zrobioną przez
# panel PRZED aktualizacją systemu. Uruchamiać jako root bezpośrednio z konsoli,
# gdy po aktualizacji coś się rozjechało. NIE jest wołane przez aplikację.
#
#   portal-config-recovery.sh list                 — pokaż dostępne kopie
#   portal-config-recovery.sh show   <timestamp>   — pokaż zawartość kopii
#   portal-config-recovery.sh restore <timestamp>  — przywróć kopię (z potwierdzeniem)
set -uo pipefail

BACKUP_ROOT="/var/lib/portal-config-backups"
HEALTH_UNITS=(postgresql-17 nginx portal-gunicorn portal-worker php-fpm fail2ban)

if [[ $EUID -ne 0 ]]; then
    echo "Uruchom jako root (sudo $0 ...)." >&2
    exit 1
fi

usage() { grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

cmd_list() {
    if [[ ! -d "$BACKUP_ROOT" ]] || [[ -z "$(ls -A "$BACKUP_ROOT" 2>/dev/null)" ]]; then
        echo "Brak kopii w $BACKUP_ROOT (żadna aktualizacja nie została jeszcze uruchomiona z panelu)."
        return 0
    fi
    echo "Dostępne kopie konfiguracji (najnowsze u góry):"
    printf '%-20s %-8s %s\n' "ZNACZNIK" "ROZMIAR" "UTWORZONO"
    for d in $(ls -1dt "${BACKUP_ROOT}"/*/ 2>/dev/null); do
        local ts size when
        ts="$(basename "$d")"
        size="$(du -sh "$d" 2>/dev/null | awk '{print $1}')"
        when="$(stat -c '%y' "$d" 2>/dev/null | cut -d. -f1)"
        printf '%-20s %-8s %s\n' "$ts" "$size" "$when"
    done
}

cmd_show() {
    local ts="$1" arc="${BACKUP_ROOT}/$1/configs.tar.gz"
    [[ -f "$arc" ]] || { echo "Nie ma kopii '$ts' (archiwum $arc)." >&2; exit 1; }
    echo "Zawartość kopii $ts:"
    tar tzf "$arc"
}

cmd_restore() {
    local ts="$1" arc="${BACKUP_ROOT}/$1/configs.tar.gz"
    [[ -f "$arc" ]] || { echo "Nie ma kopii '$ts' (archiwum $arc)." >&2; exit 1; }
    echo "UWAGA: przywrócę pliki konfiguracyjne z kopii $ts, nadpisując bieżące."
    read -r -p "Wpisz dokładnie znacznik kopii, aby potwierdzić: " confirm
    [[ "$confirm" == "$ts" ]] || { echo "Anulowano (znacznik się nie zgadza)."; exit 1; }

    # Najpierw awaryjna kopia BIEŻĄCEGO stanu (żeby dało się cofnąć restore).
    local safety="${BACKUP_ROOT}/pre-restore-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$safety"
    tar czf "${safety}/configs.tar.gz" --ignore-failed-read \
        -T <(tar tzf "$arc" | sed 's#^#/#') 2>/dev/null || true
    echo "Bieżący stan zapisany do $safety (na wypadek gdyby restore pogorszył)."

    tar xzf "$arc" -C / && echo "Pliki przywrócone."
    systemctl daemon-reload
    echo "Restartuję usługi..."
    systemctl restart "${HEALTH_UNITS[@]}" 2>/dev/null || true
    echo "=== stan usług po przywróceniu ==="
    for u in "${HEALTH_UNITS[@]}"; do
        printf '%-20s %s\n' "$u" "$(systemctl is-active "$u" 2>/dev/null || echo '?')"
    done
    echo "Gotowe. Jeśli nadal są problemy — rozważ restart maszyny."
}

case "${1:-}" in
    list)    cmd_list ;;
    show)    [[ $# -ge 2 ]] || usage 1; cmd_show "$2" ;;
    restore) [[ $# -ge 2 ]] || usage 1; cmd_restore "$2" ;;
    -h|--help|"") usage 0 ;;
    *) echo "Nieznana komenda: $1" >&2; usage 1 ;;
esac
