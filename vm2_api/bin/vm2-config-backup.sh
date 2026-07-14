#!/usr/bin/env bash
# Kopia zapasowa configów VM2 robiona PRZED aktualizacją systemu. Uruchamiane
# jako root przez vm2-api (sudoers), bez wolnych argumentów. Wypisuje na stdout
# "backup_path=..." (parsowane przez services/system_control.py).
#
# Usługa vm2-api działa pod ProtectSystem=strict (/var read-only w jej
# namespace), więc samo utworzenie pliku by padło. Dlatego mkdir+tar robimy
# jako transient unit przez systemd-run — POZA sandboxem (na hoście /var jest
# zapisywalne) — identyczny wzorzec jak vm2-dnf.sh.
set -uo pipefail

BACKUP_ROOT="/var/lib/vm2-config-backups"
# Tylko pliki konfiguracyjne (małe) — NIE maildiry ani bazy.
PATHS="/etc/postfix /etc/dovecot /etc/clamd.d /etc/mail /etc/sudoers.d \
/etc/systemd/system/vm2-provisioning-api.service"

ts="$(date +%Y%m%d-%H%M%S)"
out_dir="${BACKUP_ROOT}/${ts}"

# Konstruowana komenda używa WYŁĄCZNIE stałych ścieżek i wygenerowanego znacznika
# czasu — brak jakiegokolwiek wejścia od użytkownika, więc bezpieczna.
/usr/bin/systemd-run --quiet --wait --collect -p "StandardError=journal" \
    /bin/bash -c "
        mkdir -p '${out_dir}'
        pgconf=\$(find /var/lib/pgsql/17/data -maxdepth 1 -name '*.conf' 2>/dev/null)
        tar czf '${out_dir}/configs.tar.gz' --ignore-failed-read ${PATHS} \$pgconf 2>/dev/null || true
        ls -1dt ${BACKUP_ROOT}/*/ 2>/dev/null | tail -n +11 | xargs -r rm -rf
    "
echo "backup_path=${out_dir}"
