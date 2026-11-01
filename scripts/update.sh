#!/usr/bin/env bash
# Aktualizacja APLIKACJI portalu (kod VM1 / API VM2) na TEJ maszynie — jedno
# polecenie na VM, dla każdej instalacji (także starszej i u klienta, bez
# kontaktu z dostawcą). Rola (VM1/VM2) jest wykrywana po tym, co zainstalowano.
# KOLEJNOŚĆ: najpierw VM2, potem VM1. Pakiety systemu i Roundcube aktualizuje
# się z panelu (Ustawienia → Aktualizacje systemu); stamtąd można też uruchomić
# ten skrypt na obu VM naraz (przycisk „Aktualizuj aplikację”).
#
# Jedno polecenie (działa też na instalacjach, które jeszcze nie mają tego skryptu):
#   curl -fsSL https://raw.githubusercontent.com/marcinastat/mail-sync-portal/master/scripts/update.sh \
#        -o /root/portal-update.sh && bash /root/portal-update.sh
#
# Przełączniki:
#   --check      kontrola + informacja, czy jest nowy kod (BEZ zmian)
#   --force      także gdy w plikach repo są lokalne zmiany (trafią do kopii)
#
# Przebieg: [tryb samodzielny: znalezienie katalogu instalacji → kopia → pobranie
# kodu → przekazanie sterowania wersji z repo] → kontrola wstępna → kopia
# katalogu repo → pobranie kodu (git fetch + reset --hard; install.conf i ca/
# są poza gitem i zostają) → NOWA wersja tego skryptu (--after-fetch; przełącznik
# musi zostać w kolejnych wersjach) → wdrożenie (50-*.sh) → jednorazowe migracje
# → weryfikacja.
#
# Stan ostatniego przebiegu: /var/lib/portal-update/last-run (key=value),
# pełny log: /var/log/portal-update/. Nowe jednorazowe kroki migracji dopisuj
# w run_migrations() — każdy MUSI być idempotentny.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="https://github.com/marcinastat/mail-sync-portal.git"
LOG_DIR="/var/log/portal-update"
STATE_FILE="/var/lib/portal-update/last-run"
KEEP_REPO_BACKUPS=5

# W repozytorium: pełne biblioteki. Pobrany pojedynczo (curl) — tryb samodzielny,
# który tylko przygotowuje katalog instalacji i oddaje sterowanie jego kopii.
if [[ -f "$SCRIPT_DIR/lib/common.sh" && -f "$SCRIPT_DIR/lib/guards.sh" ]]; then
    STANDALONE=0
    source "$SCRIPT_DIR/lib/common.sh"
    source "$SCRIPT_DIR/lib/guards.sh"
    REPO_ROOT="$(repo_root)"
else
    STANDALONE=1
fi

# ================================================================================
# Tryb samodzielny (bez bibliotek — skrypt pobrany poza repozytorium)
# ================================================================================

bs_log() { printf '[%s] %-5s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" "$2"; }
bs_die() { bs_log ERROR "$1" >&2; exit 1; }

# Katalog repozytorium tej instalacji. VM2: ten z CA identycznym z wdrożonym
# (bywają dwa katalogi z różnymi CA — zły zerwałby mTLS). VM1: ten z install.conf
# i skryptami VM1. PORTAL_REPO=<katalog> wymusza wybór.
bs_find_repo() {
    local role="$1" fp f cands=()
    if [[ -n "${PORTAL_REPO:-}" ]]; then echo "${PORTAL_REPO%/}"; return 0; fi
    if [[ "$role" == vm2 ]]; then
        fp="$(openssl x509 -noout -fingerprint -sha256 -in /etc/portal/vm2-api/ca.crt 2>/dev/null)" \
            || bs_die "Brak /etc/portal/vm2-api/ca.crt — instalacja VM2 niekompletna; skontaktuj się z dostawcą."
        while read -r f; do
            [[ "$(openssl x509 -noout -fingerprint -sha256 -in "$f" 2>/dev/null)" == "$fp" ]] && cands+=("${f%/ca/ca.crt}")
        done < <(find / -xdev -maxdepth 4 -path '*/ca/ca.crt' 2>/dev/null)
        [[ ${#cands[@]} -gt 0 ]] \
            || bs_die "Nie znaleziono katalogu repo z CA wdrożonym na tej VM2. NIE instaluj od nowa — skontaktuj się z dostawcą."
        echo "${cands[0]}"   # kilka z tym samym CA — każdy jest dobry
    else
        while read -r f; do
            f="${f%/config/install.conf}"
            [[ -f "$f/scripts/vm1/50-portal-app.sh" ]] && cands+=("$f")
        done < <(find / -xdev -maxdepth 4 -path '*/config/install.conf' 2>/dev/null)
        case ${#cands[@]} in
            0) bs_die "Nie znaleziono katalogu repo (z config/install.conf) na tej VM1." ;;
            1) echo "${cands[0]}" ;;
            *) bs_die "Kilka katalogów repo: ${cands[*]} — wskaż właściwy: PORTAL_REPO=<katalog> bash $0" ;;
        esac
    fi
}

bootstrap_main() {
    [[ "$(id -u)" -eq 0 ]] || bs_die "Uruchom jako root."
    local role repo arg check=0 force=0 changes
    for arg in "$@"; do
        case "$arg" in --check) check=1 ;; --force) force=1 ;; esac
    done
    if [[ -d /opt/vm2-api ]]; then role=vm2
    elif [[ -d /opt/portal-app ]]; then role=vm1
    else bs_die "Nie rozpoznano maszyny (brak /opt/portal-app i /opt/vm2-api) — to nie jest zainstalowany portal."
    fi
    repo="$(bs_find_repo "$role")"
    bs_log INFO "Maszyna: ${role^^}, katalog instalacji: $repo"

    if [[ "$check" == 1 ]]; then
        if [[ -f "$repo/scripts/update.sh" ]]; then exec bash "$repo/scripts/update.sh" "$@"; fi
        bs_log INFO "Katalog nie ma jeszcze scripts/update.sh — pełny przebieg pobierze aktualny kod. Nic nie zmieniono."
        exit 0
    fi

    install -d -m 0700 "$LOG_DIR"
    UPDATE_LOG="$LOG_DIR/update-${role}-$(date '+%Y%m%d-%H%M%S').log"
    export UPDATE_LOG
    exec > >(umask 077; tee -a "$UPDATE_LOG") 2>&1

    if [[ -d "$repo/.git" ]]; then
        changes="$(git -c safe.directory="$repo" -C "$repo" status --porcelain --untracked-files=no 2>/dev/null || true)"
        if [[ -n "$changes" && "$force" != 1 ]]; then
            printf '%s\n' "$changes"
            bs_die "Lokalne zmiany w plikach repo (powyżej) zostałyby nadpisane. Jeśli nie są potrzebne: bash $0 --force $*"
        fi
    fi
    curl -fsS --max-time 15 -o /dev/null https://github.com || bs_die "Brak dostępu do github.com — aktualizacja wymaga internetu."

    UPDATE_REPO_BACKUP="/root/repo-backup-${role}-$(date '+%Y%m%d-%H%M%S').tar.gz"
    (umask 077; tar -czf "$UPDATE_REPO_BACKUP" -C "$(dirname "$repo")" "$(basename "$repo")")
    export UPDATE_REPO_BACKUP
    bs_log INFO "Kopia katalogu repo: $UPDATE_REPO_BACKUP"

    command -v git >/dev/null 2>&1 || dnf install -y git
    local gr=(git -c safe.directory="$repo" -C "$repo")
    if [[ ! -d "$repo/.git" ]]; then
        bs_log INFO "Katalog bez .git (kopia z sync-to-vm2) — zamieniam go w klon repozytorium."
        "${gr[@]}" init -q
    fi
    "${gr[@]}" remote get-url origin >/dev/null 2>&1 || "${gr[@]}" remote add origin "$REPO_URL"
    "${gr[@]}" fetch -q origin master || bs_die "git fetch nie powiódł się."
    "${gr[@]}" reset -q --hard origin/master || bs_die "git reset nie powiódł się."
    bs_log INFO "Kod: $("${gr[@]}" log --oneline -1)"

    # Kod już najnowszy, kopia zrobiona — wersja z repo pomija te kroki.
    export UPDATE_FETCHED=1
    exec bash "$repo/scripts/update.sh" "$@"
}

# ================================================================================
# Tryb pełny (w repozytorium)
# ================================================================================

# git z safe.directory: katalog repo bywa własnością innego użytkownika niż root.
g() { git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" "$@"; }

set_state() {   # set_state <state> <krok>
    install -d -m 0755 "$(dirname "$STATE_FILE")"
    printf 'state=%s\nstep=%s\nrole=%s\nlog=%s\nupdated=%s\n' \
        "$1" "$2" "${ROLE:-?}" "${UPDATE_LOG:-}" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$STATE_FILE"
}

fail() {
    set_state failed "${STEP:-?}"
    die "$* — log: ${UPDATE_LOG:-brak}. Kopia repo: ${UPDATE_REPO_BACKUP:-brak}. W razie wątpliwości: snapshot obu VM."
}

# Każde wyjście z błędem (także die z bezpieczników) zostawia state=failed —
# żeby plik stanu nie wisiał na „running”. Pułapka nie odpala się przy exec.
on_exit() {
    local rc=$?
    if [[ $rc -ne 0 && -f "$STATE_FILE" ]] && grep -q '^state=running' "$STATE_FILE"; then
        set_state failed "${STEP:-?}"
    fi
}

detect_role() {
    if [[ -d /opt/vm2-api || -f "$VM2_TLS_DIR/ca.crt" ]]; then echo vm2
    elif [[ -d /opt/portal-app ]]; then echo vm1
    else die "Nie rozpoznano maszyny (brak /opt/portal-app i /opt/vm2-api) — to nie jest zainstalowany portal."
    fi
}

# --- Faza 1: przed pobraniem kodu -----------------------------------------------

preflight() {
    STEP="kontrola wstępna"
    log_info "Maszyna: ${ROLE^^}, katalog repo: $REPO_ROOT"
    curl -fsS --max-time 15 -o /dev/null https://github.com \
        || die "Brak dostępu do github.com — aktualizacja wymaga internetu."
    if [[ "$ROLE" == vm2 ]]; then guard_vm2_deploy "$REPO_ROOT"; else guard_vm1_deploy; fi

    if [[ "$ROLE" == vm1 ]]; then
        local busy
        # Kolejka, nie system_update_runs: wpis przebiegu potrafi zostać „running”
        # po restarcie workera (sprząta go reaper) — nie może blokować wdrożenia.
        busy="$(runuser -u postgres -- psql -d portal_db -tAc \
            "SELECT count(*) FROM job_queue WHERE job_type='system_update' AND status IN ('queued','running')" 2>/dev/null || echo 0)"
        [[ "${busy//[[:space:]]/}" == "0" ]] \
            || die "W panelu trwa aktualizacja (systemu lub Roundcube) — poczekaj, aż się skończy."
        busy="$(runuser -u postgres -- psql -d portal_db -tAc \
            "SELECT count(*) FROM job_runs WHERE status='running'" 2>/dev/null || echo 0)"
        [[ "${busy//[[:space:]]/}" == "0" ]] \
            || log_warn "Trwa synchronizacja skrzynek — restart workera ją przerwie, a portal wznowi ją automatycznie."
    fi

    if [[ -d "$REPO_ROOT/.git" && "${UPDATE_FETCHED:-0}" != 1 ]]; then
        local changes
        changes="$(g status --porcelain --untracked-files=no 2>/dev/null || true)"
        if [[ -n "$changes" ]]; then
            log_warn "Lokalne zmiany w plikach repo (zostaną nadpisane nowym kodem):"
            printf '%s\n' "$changes"
            [[ "${FORCE:-0}" == 1 ]] \
                || die "Przerwano. Jeśli te zmiany nie są potrzebne, uruchom z --force (kopia katalogu i tak powstanie)."
        fi
    fi
}

show_pending() {
    local local_head remote_head
    remote_head="$(git ls-remote "$REPO_URL" refs/heads/master 2>/dev/null | cut -f1 || true)"
    local_head="$(g rev-parse HEAD 2>/dev/null || true)"
    [[ -n "$remote_head" ]] || die "Nie udało się odczytać wersji kodu z GitHub."
    if [[ "$local_head" == "$remote_head" ]]; then
        log_info "Kod jest aktualny (${local_head:0:7})."
    elif [[ -z "$local_head" ]]; then
        log_info "Katalog nie jest klonem git (kopia z sync-to-vm2) — pełny przebieg zamieni go w klon i pobierze kod ${remote_head:0:7}."
    else
        log_info "Dostępny nowszy kod: lokalnie ${local_head:0:7}, GitHub ${remote_head:0:7}."
    fi
}

backup_repo() {
    STEP="kopia katalogu repo"
    UPDATE_REPO_BACKUP="/root/repo-backup-${ROLE}-$(date '+%Y%m%d-%H%M%S').tar.gz"
    (umask 077; tar -czf "$UPDATE_REPO_BACKUP" -C "$(dirname "$REPO_ROOT")" "$(basename "$REPO_ROOT")")
    export UPDATE_REPO_BACKUP
    log_info "Kopia katalogu repo (z install.conf$([[ "$ROLE" == vm2 ]] && echo ' i CA')): $UPDATE_REPO_BACKUP"
}

prune_repo_backups() {
    ls -1t /root/repo-backup-"${ROLE}"-*.tar.gz 2>/dev/null | tail -n +$((KEEP_REPO_BACKUPS + 1)) \
        | xargs -r rm -f -- || true
}

fetch_code() {
    STEP="pobranie kodu"
    if [[ ! -d "$REPO_ROOT/.git" ]]; then
        log_info "Katalog bez .git (kopia z sync-to-vm2) — zamieniam go w klon repozytorium."
        g init -q
    fi
    g remote get-url origin >/dev/null 2>&1 || g remote add origin "$REPO_URL"
    g fetch -q origin master || fail "git fetch nie powiódł się"
    g reset -q --hard origin/master || fail "git reset nie powiódł się"
    log_info "Kod: $(g log --oneline -1)"
}

# --- Faza 2: nowy kod -------------------------------------------------------------

deploy() {
    STEP="wdrożenie"
    if [[ "$ROLE" == vm2 ]]; then
        FORCE_REAPPLY=1 bash "$REPO_ROOT/scripts/vm2/50-provisioning-api.sh" || fail "Wdrożenie VM2 (50-provisioning-api.sh) nie powiodło się"
    else
        FORCE_REAPPLY=1 bash "$REPO_ROOT/scripts/vm1/50-portal-app.sh" || fail "Wdrożenie VM1 (50-portal-app.sh) nie powiodło się"
    fi
}

# Jednorazowe migracje istniejących instalacji — każda idempotentna.
run_migrations() {
    STEP="migracje"
    # 2026-11: PostgreSQL bez versionlock (gałąź trzyma nazwa pakietu
    # postgresqlNN-*, wydania poprawkowe to łatki bezpieczeństwa).
    local locked p
    locked="$(dnf -q versionlock list 2>/dev/null | grep '^postgresql' | sed 's/-[0-9]*:.*//' || true)"
    for p in $locked; do
        dnf -q versionlock delete "$p" </dev/null >/dev/null 2>&1 || log_warn "Nie udało się zdjąć blokady: $p"
    done
    [[ -z "$locked" ]] || log_info "Zdjęto blokadę wersji PostgreSQL: $(xargs <<<"$locked")"
}

# Test VM1 → VM2 (mTLS). Ponawiany do ~3 min — VM2 mogła się właśnie restartować.
check_vm2_link() {
    local target code i
    target="$(runuser -u postgres -- psql -d portal_db -tAc \
        "SELECT vm2_host||':'||vm2_api_port FROM vm2_connection WHERE vm2_host IS NOT NULL LIMIT 1" 2>/dev/null || true)"
    target="${target//[[:space:]]/}"
    [[ -n "$target" ]] || { log_warn "Brak skonfigurowanego połączenia z VM2 — pomijam test."; return 0; }
    for i in $(seq 1 18); do
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
            --cert /etc/portal/vm1-client/client.crt --key /etc/portal/vm1-client/client.key \
            --cacert /etc/portal/vm1-client/ca.crt "https://$target/health" || true)"
        case "$code" in
            200) log_info "Połączenie VM1 → VM2 (mTLS): OK"; return 0 ;;
            403) log_error "VM2 odrzuca adres VM1 (403) — runbook: zmiana adresu IP VM1."; return 1 ;;
        esac
        [[ $i -eq 1 ]] && log_info "VM2 jeszcze nie odpowiada (kod ${code:-brak}) — czekam do 3 min (mogła się restartować)..."
        sleep 10
    done
    log_error "VM2 nieosiągalna (kod ${code:-brak}) — sprawdź VM2 i sieć."
    return 1
}

verify() {
    STEP="weryfikacja"
    local bad=0 u
    if [[ "$ROLE" == vm2 ]]; then
        for u in "postgresql-${PGDG_MAJOR_VERSION}" dovecot postfix vm2-provisioning-api; do
            if systemctl is-active --quiet "$u"; then log_info "OK    $u"; else log_error "FAIL  $u"; bad=1; fi
        done
    else
        bash "$REPO_ROOT/scripts/vm1/health-check.sh" || bad=1
        check_vm2_link || bad=1
    fi
    return "$bad"
}

finish() {
    set_state success "zakończono"
    log_info "------------------------------------------------------------------------"
    log_info "Aktualizacja aplikacji ${ROLE^^} zakończona powodzeniem. Log: $UPDATE_LOG"
    if [[ "$ROLE" == vm2 ]]; then
        log_info "Następny krok: to samo polecenie na VM1."
    else
        log_info "Następny krok: panel → Ustawienia → Aktualizacje systemu (pakiety VM2/VM1, Roundcube)."
    fi
}

main() {
    require_root
    local mode=run phase=1 arg pass=()
    FORCE=0
    for arg in "$@"; do
        case "$arg" in
            --check)       mode=check ;;
            --force)       FORCE=1; pass+=("$arg") ;;
            --after-fetch) phase=2 ;;
            *) echo "Użycie: $0 [--check] [--force]" >&2; exit 2 ;;
        esac
    done
    load_install_conf
    ROLE="$(detect_role)"
    command -v git >/dev/null 2>&1 || {
        [[ "$mode" == check ]] && die "Brak git — pełny przebieg go doinstaluje."
        pkg_install_idempotent git
    }

    if [[ "$mode" == check ]]; then
        preflight
        show_pending
        log_info "Kontrola zakończona — nic nie zmieniono."
        return 0
    fi

    trap on_exit EXIT
    if [[ "$phase" == 1 ]]; then
        if [[ -z "${UPDATE_LOG:-}" ]]; then
            install -d -m 0700 "$LOG_DIR"
            UPDATE_LOG="$LOG_DIR/update-${ROLE}-$(date '+%Y%m%d-%H%M%S').log"
            export UPDATE_LOG
            exec > >(umask 077; tee -a "$UPDATE_LOG") 2>&1
        fi
        set_state running "kontrola wstępna"
        preflight
        if [[ "${UPDATE_FETCHED:-0}" != 1 ]]; then
            backup_repo
            set_state running "pobranie kodu"
            fetch_code
            # Dalej NOWA wersja skryptu (mogła dojść nowa logika/migracje). Wyjście
            # zostaje w tym samym tee (deskryptory przechodzą przez exec).
            exec bash "$REPO_ROOT/scripts/update.sh" --after-fetch "${pass[@]}"
        fi
    fi

    prune_repo_backups
    set_state running "wdrożenie"
    deploy
    set_state running "migracje"
    run_migrations
    set_state running "weryfikacja"
    verify || fail "Weryfikacja po wdrożeniu kodu zgłosiła problem (szczegóły powyżej)"
    finish
}

# Całość w funkcjach + exit w tej samej linii: bash wczytuje plik przyrostowo, a
# pobranie kodu podmienia go w trakcie — nic z nowej wersji nie zostanie
# doczytane do starego przebiegu.
{ if [[ "$STANDALONE" == 1 ]]; then bootstrap_main "$@"; else main "$@"; fi; exit; }
