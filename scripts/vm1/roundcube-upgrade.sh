#!/usr/bin/env bash
# VM1 — aktualizacja Roundcube. Roundcube jest instalowany z tarballa
# (40-roundcube.sh), więc aktualizacje systemu (dnf / panel) go NIE obejmują.
# Narzędzie jest powtarzalne na KAŻDEJ instalacji portalu — nic tu nie zależy
# od konkretnej maszyny (adresy, hosty); wszystko wynika z układu instalacji.
#
#   roundcube-upgrade.sh check                — wersje + kontrola wstępna, BEZ zmian
#   roundcube-upgrade.sh upgrade [wersja]     — domyślnie najnowsza w tej samej gałęzi (np. 1.7.x)
#   roundcube-upgrade.sh list                 — kopie zapasowe
#   roundcube-upgrade.sh rollback <katalog>   — przywrócenie plików + bazy z kopii
#   roundcube-upgrade.sh status               — panel: wersje jako key=value (bez zmian)
#   roundcube-upgrade.sh upgrade-panel        — panel: upgrade w gałęzi, poza piaskownicą workera
#
# Panel woła kopię zainstalowaną przez 50-portal-app.sh w /opt/portal-app/bin
# (+ biblioteki w /opt/portal-app/lib, root-owned) — wyłącznie dwa ostatnie tryby
# (sudoers bez argumentów dowolnych: tylko gałąź bieżąca, auto-rollback zawsze).
#
# Bezpieczniki: podpis GPG paczki (lib/roundcube.sh); kopia plików i roundcube_db
# PRZED zmianą; webmail zatrzymany na czas podmiany (bez pół-zaktualizowanego
# kodu w obsłudze); test po aktualizacji i AUTOMATYCZNY rollback, gdy nie przejdzie
# (NO_AUTO_ROLLBACK=1 wyłącza). Zmiana gałęzi (np. 1.6 -> 1.7) tylko świadomie:
# ALLOW_BRANCH_CHANGE=1, po lekturze UPGRADING w informacjach o wydaniu.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../lib/roundcube.sh"

RC_ROOT="/var/www/roundcube"
RC_DB="roundcube_db"
BACKUP_ROOT="/var/backups/roundcube"
KEEP_BACKUPS=3
LOCK_FILE="/run/roundcube-upgrade.lock"
# Pliki z sekretami w drzewie Roundcube — chown -R po aktualizacji by im zmienił
# właściciela, więc zapamiętujemy i odtwarzamy ich uprawnienia.
SECRET_FILES=(config/config.inc.php plugins/portal_sso/config.inc.php)
RELEASES_API="https://api.github.com/repos/roundcube/roundcubemail/releases?per_page=50"
# Cache listy wydań dla trybu status (panel pyta przy każdym wejściu na stronę,
# a GitHub API bez tokenu ma limit 60 zapytań/h na adres).
RELEASES_CACHE="/run/roundcube-releases.cache"
PANEL_OUT="/run/roundcube-upgrade-panel.out"

# pg_dump/pg_restore z PGDG (gdyby alternatives nie dały ich w PATH). `|| true`:
# bez katalogu PGDG ls pada, a pod set -e + pipefail skrypt kończyłby się po cichu.
PATH="$PATH:$(ls -d /usr/pgsql-*/bin 2>/dev/null | sort -V | tail -1 || true)"

# Pusto, gdy pliku nie ma. `|| true` jest KLUCZOWE: verify() woła to po instalacji —
# bez niego brak pliku zakończyłby skrypt po cichu (set -e) ZAMIAST auto-rollbacku.
installed_version() {
    sed -n "s/.*define('RCMAIL_VERSION', '\([^']*\)').*/\1/p" \
        "$RC_ROOT/program/include/iniset.php" 2>/dev/null | head -1 || true
}

branch_of() { cut -d. -f1,2 <<<"$1"; }

# Stabilne wydania (bez rc/beta), rosnąco. Pusto, gdy GitHub API niedostępne.
# Argument "cached": użyj listy sprzed < 15 min (tryb status).
stable_releases() {
    if [[ "${1:-}" == "cached" && -s "$RELEASES_CACHE" && -n "$(find "$RELEASES_CACHE" -mmin -15 2>/dev/null)" ]]; then
        cat "$RELEASES_CACHE"; return 0
    fi
    local list
    list="$(curl -fsSL --max-time 30 "$RELEASES_API" 2>/dev/null \
        | grep -o '"tag_name": *"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/' \
        | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V || true)"
    if [[ -n "$list" ]]; then printf '%s\n' "$list" 2>/dev/null > "$RELEASES_CACHE" || true; fi
    printf '%s\n' "$list"
}

# Najnowsze wydanie w gałęzi wersji $1 (np. 1.7.2 -> najnowsze 1.7.x) z listy $2.
latest_in_branch() {
    grep -E "^$(branch_of "$1" | sed 's/\./\\./')\.[0-9]+$" <<<"$2" | tail -1 || true
}

# Kontrola wstępna — nic nie zmienia. Kończy skrypt (die), gdy aktualizacja
# nie może się bezpiecznie udać.
preflight() {
    [[ -f "$RC_ROOT/program/include/iniset.php" ]] || die "Brak instalacji Roundcube w $RC_ROOT."
    [[ -n "$(installed_version)" ]] || die "Nie da się odczytać wersji Roundcube z $RC_ROOT/program/include/iniset.php."
    id roundcube >/dev/null 2>&1 || die "Brak użytkownika systemowego roundcube."
    local bin
    for bin in php curl tar pg_dump pg_restore; do
        command -v "$bin" >/dev/null 2>&1 || die "Brak narzędzia: $bin."
    done
    local db_bytes
    db_bytes="$(runuser -u postgres -- psql -tAc "SELECT pg_database_size('$RC_DB')" 2>/dev/null || true)"
    [[ "$db_bytes" =~ ^[0-9]+$ ]] || die "Brak dostępu do bazy $RC_DB jako postgres."
    local need_kb avail_kb
    need_kb=$(( $(du -sk "$RC_ROOT" | cut -f1) + db_bytes / 1024 + 300 * 1024 ))
    avail_kb="$(df -Pk /var | awk 'NR==2 {print $4}')"
    (( avail_kb > need_kb )) || die "Za mało miejsca na /var: wolne ${avail_kb} KB, potrzeba ~${need_kb} KB (kopia + paczka)."
    log_info "Kontrola wstępna OK: Roundcube $(installed_version), baza $((db_bytes / 1024 / 1024)) MB, wolne na /var $((avail_kb / 1024)) MB."
}

# Rozruch Roundcube z CLI: config + rdzeń + wtyczki + zapytanie do bazy.
# Niezależny od stref dostępu nginx (te mogą odrzucać 127.0.0.1).
cli_selftest() {
    (cd "$RC_ROOT" && runuser -u roundcube -- php -r '
        define("INSTALL_PATH", getcwd() . "/");
        require INSTALL_PATH . "program/include/clisetup.php";
        $rc = rcmail::get_instance();
        $db = $rc->get_dbh();
        $db->query("SELECT 1");
        if ($db->is_error()) { fwrite(STDERR, "DB: " . $db->is_error() . "\n"); exit(1); }
        echo "OK " . RCMAIL_VERSION . " wtyczki: " . implode(",", $rc->plugins->loaded_plugins()) . "\n";
    ')
}

verify() {
    local want="$1" got out code
    got="$(installed_version)"
    [[ "$got" == "$want" ]] || { log_error "Wersja po aktualizacji: '$got' (oczekiwano $want)."; return 1; }
    systemctl is-active --quiet php-fpm || { log_error "php-fpm nie działa po restarcie."; return 1; }
    out="$(cli_selftest 2>&1)" || { log_error "Test rozruchu Roundcube nie przeszedł: $out"; return 1; }
    log_info "Test rozruchu: $out"
    code="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 20 https://127.0.0.1/ || true)"
    case "$code" in
        200) log_info "Strona logowania webmaila: HTTP 200." ;;
        403) log_warn "HTTP 403 z 127.0.0.1 — strefy dostępu nginx nie wpuszczają localhosta; sprawdź logowanie w przeglądarce." ;;
        *)   log_error "Strona logowania webmaila: HTTP ${code:-brak odpowiedzi}."; return 1 ;;
    esac
}

# Ustawia BACKUP_DIR (globalnie — log_info pisze na stdout, więc bez $(...)).
make_backup() {
    local cur="$1"
    BACKUP_DIR="$BACKUP_ROOT/$(date '+%Y%m%d-%H%M%S')-$cur"
    install -d -m 0700 "$BACKUP_ROOT" "$BACKUP_DIR"
    log_info "Kopia zapasowa → $BACKUP_DIR"
    tar -czf "$BACKUP_DIR/files.tar.gz" -C "$(dirname "$RC_ROOT")" "$(basename "$RC_ROOT")"
    runuser -u postgres -- pg_dump -Fc "$RC_DB" > "$BACKUP_DIR/db.dump"
    echo "$cur" > "$BACKUP_DIR/VERSION"
    echo "backup_path=$BACKUP_DIR"   # dla panelu (parsowane przez services/roundcube_update.py)
}

prune_backups() {
    local old
    old="$(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) || true)"
    [[ -n "$old" ]] && xargs -r rm -rf -- <<<"$old"
    return 0
}

do_rollback() {
    local dir="${1%/}" ts
    [[ -f "$dir/files.tar.gz" && -f "$dir/db.dump" ]] || die "To nie jest kopia Roundcube (brak files.tar.gz / db.dump): $dir"
    ts="$(date '+%Y%m%d-%H%M%S')"
    log_info "Przywracam Roundcube $(cat "$dir/VERSION" 2>/dev/null) z $dir ..."
    systemctl stop php-fpm || true
    if [[ -d "$RC_ROOT" ]]; then mv "$RC_ROOT" "${RC_ROOT}.failed-$ts"; fi
    tar -xzf "$dir/files.tar.gz" -C "$(dirname "$RC_ROOT")"   # root: zachowuje właścicieli i prawa
    if command -v restorecon >/dev/null 2>&1; then restorecon -R "$RC_ROOT" || true; fi
    runuser -u postgres -- pg_restore --clean --if-exists -d "$RC_DB" "$dir/db.dump" \
        || log_warn "pg_restore zgłosił ostrzeżenia — sprawdź logowanie do webmaila."
    systemctl start php-fpm
    log_info "Przywrócono Roundcube $(installed_version). Stan sprzed przywrócenia: ${RC_ROOT}.failed-$ts (usuń po sprawdzeniu)."
}

fail_upgrade() {
    local reason="$1"
    if [[ "${NO_AUTO_ROLLBACK:-0}" == "1" ]]; then
        systemctl start php-fpm || true
        die "Aktualizacja NIEUDANA: $reason. Auto-rollback wyłączony — przywróć: $0 rollback $BACKUP_DIR"
    fi
    log_error "Aktualizacja NIEUDANA: $reason — automatyczny rollback."
    do_rollback "$BACKUP_DIR"
    die "Aktualizacja nieudana ($reason); przywrócono poprzednią wersję. Log: $BACKUP_DIR/upgrade.log"
}

do_check() {
    preflight
    local cur releases in_branch newest
    cur="$(installed_version)"
    releases="$(stable_releases)"
    [[ -n "$releases" ]] || die "Nie udało się pobrać listy wydań z GitHub (brak internetu?)."
    in_branch="$(latest_in_branch "$cur" "$releases")"
    newest="$(tail -1 <<<"$releases")"
    log_info "Zainstalowana: $cur | najnowsza w gałęzi $(branch_of "$cur"): ${in_branch:-?} | najnowsza ogółem: $newest"
    if [[ -n "$in_branch" && "$in_branch" != "$cur" ]]; then
        log_info "Dostępna aktualizacja $cur → $in_branch. Uruchom: $0 upgrade"
    else
        log_info "Roundcube jest aktualny w swojej gałęzi."
    fi
    if [[ "$(branch_of "$newest")" != "$(branch_of "$cur")" ]]; then
        log_info "Istnieje nowsza gałąź ($newest) — zmiana gałęzi tylko świadomie (ALLOW_BRANCH_CHANGE=1, patrz runbook)."
    fi
}

do_upgrade() {
    local target="${1:-}" cur work
    exec 9>"$LOCK_FILE"
    flock -n 9 || die "Inna aktualizacja Roundcube już trwa."
    preflight
    cur="$(installed_version)"

    if [[ -z "$target" ]]; then
        target="$(latest_in_branch "$cur" "$(stable_releases)")"
        [[ -n "$target" ]] || die "Nie udało się ustalić najnowszej wersji (GitHub API) — podaj ją jawnie: $0 upgrade 1.7.5"
    fi
    [[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Nieprawidłowa wersja: '$target' (oczekiwano np. 1.7.5)."
    if [[ "$target" == "$cur" ]]; then
        log_info "Roundcube $cur jest już zainstalowany — nic do zrobienia."; return 0
    fi
    [[ "$(printf '%s\n%s\n' "$cur" "$target" | sort -V | tail -1)" == "$target" ]] \
        || die "Wersja $target jest starsza niż zainstalowana $cur — do cofania służy: $0 rollback <kopia>."
    if [[ "$(branch_of "$cur")" != "$(branch_of "$target")" && "${ALLOW_BRANCH_CHANGE:-0}" != "1" ]]; then
        die "Zmiana gałęzi $(branch_of "$cur") → $(branch_of "$target"). Przeczytaj UPGRADING w informacjach o wydaniu i uruchom z ALLOW_BRANCH_CHANGE=1."
    fi

    # installto.sh używa rsync; gpg do weryfikacji podpisu. dnf tylko gdy brakuje —
    # nie blokujemy się o lock dnf trwającej aktualizacji systemu.
    command -v rsync >/dev/null 2>&1 && command -v gpg >/dev/null 2>&1 \
        || pkg_install_idempotent rsync gnupg2
    work="$(mktemp -d -p /var/tmp roundcube-upgrade.XXXXXX)"
    # Ścieżka rozwinięta TERAZ ("..."): pułapka EXIT odpala się po wyjściu z
    # funkcji, gdy lokalnej zmiennej $work już nie ma.
    trap "rm -rf '$work'" EXIT
    rc_fetch_verified "$target" "$work/rc.tar.gz"
    mkdir "$work/src"
    tar -xzf "$work/rc.tar.gz" -C "$work/src" --strip-components=1

    make_backup "$cur"
    local f saved=()
    for f in "${SECRET_FILES[@]}"; do
        [[ -f "$RC_ROOT/$f" ]] && saved+=("$f|$(stat -c '%U:%G|%a' "$RC_ROOT/$f")")
    done

    log_info "Zatrzymuję webmail (php-fpm) i instaluję Roundcube $target w miejsce $cur ..."
    systemctl stop php-fpm
    # update.sh (wołany przez installto.sh) ZAWSZE kończy się kodem 0 — o sukcesie
    # aktualizacji schematu bazy świadczy wyłącznie ten komunikat w wyjściu.
    if ! php "$work/src/bin/installto.sh" -y "$RC_ROOT" >"$BACKUP_DIR/upgrade.log" 2>&1; then
        fail_upgrade "installto.sh zakończył się błędem"
    fi
    grep -q "This instance of Roundcube is up-to-date" "$BACKUP_DIR/upgrade.log" \
        || fail_upgrade "aktualizacja schematu bazy nie potwierdziła sukcesu"

    chown -R roundcube:roundcube "$RC_ROOT"
    local entry path owner mode
    for entry in "${saved[@]}"; do
        IFS='|' read -r path owner mode <<<"$entry"
        chown "$owner" "$RC_ROOT/$path" && chmod "$mode" "$RC_ROOT/$path"
    done
    if command -v restorecon >/dev/null 2>&1; then restorecon -R "$RC_ROOT" || true; fi
    systemctl start php-fpm

    verify "$target" || fail_upgrade "test po aktualizacji nie przeszedł"

    local conf
    conf="$(repo_root)/config/install.conf"
    if [[ -f "$conf" ]]; then
        sed -i "s/^ROUNDCUBE_VERSION=.*/ROUNDCUBE_VERSION=\"$target\"/" "$conf"
    fi
    prune_backups
    log_info "Roundcube zaktualizowany: $cur → $target. Kopia: $BACKUP_DIR (cofnięcie: $0 rollback $BACKUP_DIR)."
}

do_status() {
    local cur releases
    cur="$(installed_version)"
    [[ -n "$cur" ]] || die "Nie da się odczytać wersji Roundcube z $RC_ROOT."
    releases="$(stable_releases cached)"
    echo "installed=$cur"
    echo "latest_branch=$(latest_in_branch "$cur" "$releases")"
    echo "latest=$(tail -1 <<<"$releases")"
}

# Z panelu helper startuje w piaskownicy portal-workera (ProtectSystem=full:
# /usr i /etc tylko do odczytu) — właściwą aktualizację uruchamiamy jako
# transient unit POZA nią (ten sam wzorzec co dnf w apply-system-update.sh).
# Wynik przez plik pod stałą ścieżką + cat (nie --pipe). Środowisko transient
# unitu jest czyste: zawsze najnowsza w TEJ SAMEJ gałęzi, z auto-rollbackiem.
do_upgrade_panel() {
    if [[ "${RC_UPGRADE_ONHOST:-0}" == "1" ]]; then
        do_upgrade ""
        return
    fi
    local rc=0
    /usr/bin/systemd-run --quiet --wait --collect --setenv=RC_UPGRADE_ONHOST=1 \
        -p "StandardOutput=truncate:$PANEL_OUT" -p "StandardError=inherit" \
        "$(readlink -f "${BASH_SOURCE[0]}")" upgrade-panel || rc=$?
    cat "$PANEL_OUT" 2>/dev/null || true
    return "$rc"
}

do_list() {
    local d
    ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | while read -r d; do
        printf '%s  (wersja %s)\n' "${d%/}" "$(cat "$d/VERSION" 2>/dev/null || echo '?')"
    done || log_info "Brak kopii w $BACKUP_ROOT."
}

require_root
case "${1:-}" in
    check)    do_check ;;
    upgrade)  do_upgrade "${2:-}" ;;
    list)     do_list ;;
    rollback) [[ -n "${2:-}" ]] || die "Podaj katalog kopii (zobacz: $0 list)."
              exec 9>"$LOCK_FILE"; flock -n 9 || die "Trwa aktualizacja Roundcube."
              do_rollback "$2" ;;
    status)        do_status ;;
    upgrade-panel) do_upgrade_panel ;;
    *) echo "Użycie: $0 check | upgrade [wersja] | list | rollback <katalog-kopii>" >&2; exit 2 ;;
esac
