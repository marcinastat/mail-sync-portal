#!/usr/bin/env bash
# Aktualizacja portalu na TEJ maszynie — jedno polecenie dla każdej instalacji
# (także u klienta, bez kontaktu z dostawcą). Rola (VM1/VM2) jest wykrywana po
# tym, co zainstalowano. KOLEJNOŚĆ: najpierw VM2, potem VM1.
#
#   bash scripts/update.sh           — pełny przebieg
#   bash scripts/update.sh --check   — kontrola + informacja, czy jest nowy kod (BEZ zmian)
#   bash scripts/update.sh --force   — także gdy w plikach repo są lokalne zmiany (trafią do kopii)
#
# Przebieg: kontrola wstępna → kopia katalogu repo (/root/repo-backup-*) →
# pobranie kodu (git fetch + reset --hard: działa też dla klonów sprzed zmiany
# historii repo i kopii bez .git; install.conf i ca/ są poza gitem i zostają) →
# uruchomienie NOWEJ wersji tego skryptu (--after-fetch — ten przełącznik musi
# zostać w kolejnych wersjach) → wdrożenie (50-*.sh) → jednorazowe migracje →
# weryfikacja. Pakiety systemu i Roundcube aktualizuje się potem z panelu.
#
# Stan ostatniego przebiegu: /var/lib/portal-update/last-run (key=value),
# pełny log: /var/log/portal-update/. Nowe jednorazowe kroki migracji dopisuj
# w run_migrations() — każdy MUSI być idempotentny.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/guards.sh"

REPO_ROOT="$(repo_root)"
REPO_URL="https://github.com/marcinastat/mail-sync-portal.git"
LOG_DIR="/var/log/portal-update"
STATE_FILE="/var/lib/portal-update/last-run"
KEEP_REPO_BACKUPS=5

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
        busy="$(runuser -u postgres -- psql -d portal_db -tAc \
            "SELECT count(*) FROM system_update_runs WHERE status='running'" 2>/dev/null || echo 0)"
        [[ "${busy//[[:space:]]/}" == "0" ]] \
            || die "W panelu trwa aktualizacja (systemu lub Roundcube) — poczekaj, aż się skończy."
        busy="$(runuser -u postgres -- psql -d portal_db -tAc \
            "SELECT count(*) FROM job_runs WHERE status='running'" 2>/dev/null || echo 0)"
        [[ "${busy//[[:space:]]/}" == "0" ]] \
            || log_warn "Trwa synchronizacja skrzynek — restart workera ją przerwie, a portal wznowi ją automatycznie."
    fi

    if [[ -d "$REPO_ROOT/.git" ]]; then
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
        log_info "Kod jest aktualny (${local_head:0:7}). Pełny przebieg i tak sprawdzi wdrożenie i migracje."
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

verify() {
    STEP="weryfikacja"
    local bad=0 u code target
    if [[ "$ROLE" == vm2 ]]; then
        for u in "postgresql-${PGDG_MAJOR_VERSION}" dovecot postfix vm2-provisioning-api; do
            if systemctl is-active --quiet "$u"; then log_info "OK    $u"; else log_error "FAIL  $u"; bad=1; fi
        done
    else
        bash "$REPO_ROOT/scripts/vm1/health-check.sh" || bad=1
        target="$(runuser -u postgres -- psql -d portal_db -tAc \
            "SELECT vm2_host||':'||vm2_api_port FROM vm2_connection WHERE vm2_host IS NOT NULL LIMIT 1" 2>/dev/null || true)"
        if [[ -n "${target// /}" ]]; then
            code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
                --cert /etc/portal/vm1-client/client.crt --key /etc/portal/vm1-client/client.key \
                --cacert /etc/portal/vm1-client/ca.crt "https://${target// /}/health" || true)"
            case "$code" in
                200) log_info "Połączenie VM1 → VM2 (mTLS): OK" ;;
                403) log_error "VM2 odrzuca adres VM1 (403) — runbook: zmiana adresu IP VM1."; bad=1 ;;
                *)   log_error "VM2 nieosiągalna (kod ${code:-brak}) — sprawdź VM2 i sieć."; bad=1 ;;
            esac
        fi
    fi
    if dnf update --assumeno 2>&1 | grep -q 'Problem'; then
        log_warn "dnf zgłasza konflikt pakietów — aktualizacja systemu w trybie „wszystkie” się nie uda. Sprawdź: dnf update --assumeno"
    fi
    return "$bad"
}

next_steps() {
    log_info "------------------------------------------------------------------------"
    if [[ "$ROLE" == vm2 ]]; then
        log_info "VM2 zaktualizowana. TERAZ uruchom to samo na VM1: bash <katalog-repo>/scripts/update.sh"
    else
        log_info "VM1 zaktualizowana. Dalej w panelu (Ustawienia → Aktualizacje systemu):"
        log_info "  1. VM2: „Wszystkie aktualizacje” → Zainstaluj; restart, jeśli wymagany."
        log_info "  2. VM1: to samo (restart VM1 = panel niedostępny 1–2 min)."
        log_info "  3. Roundcube (webmail): „Zaktualizuj Roundcube do …”, jeśli dostępna aktualizacja."
    fi
}

main() {
    require_root
    local mode=run phase=1 arg
    for arg in "$@"; do
        case "$arg" in
            --check)       mode=check ;;
            --force)       FORCE=1 ;;
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
        install -d -m 0700 "$LOG_DIR"
        UPDATE_LOG="$LOG_DIR/update-${ROLE}-$(date '+%Y%m%d-%H%M%S').log"
        export UPDATE_LOG
        exec > >(umask 077; tee -a "$UPDATE_LOG") 2>&1
        set_state running "kontrola wstępna"
        preflight
        backup_repo
        set_state running "pobranie kodu"
        fetch_code
        # Dalej NOWA wersja skryptu (mogła dojść nowa logika/migracje). Wyjście
        # zostaje w tym samym tee (deskryptory przechodzą przez exec).
        exec bash "$REPO_ROOT/scripts/update.sh" --after-fetch
    fi

    set_state running "wdrożenie"
    deploy
    set_state running "migracje"
    run_migrations
    set_state running "weryfikacja"
    if verify; then
        set_state success "zakończono"
        log_info "Aktualizacja kodu ${ROLE^^} zakończona powodzeniem. Log: $UPDATE_LOG"
        next_steps
    else
        fail "Weryfikacja po aktualizacji zgłosiła problem (szczegóły powyżej)"
    fi
}

# Całość w funkcji + exit w tej samej linii: bash wczytuje plik przyrostowo, a
# fetch_code podmienia go w trakcie — tak nic z nowej wersji nie zostanie
# doczytane do starego przebiegu.
{ main "$@"; exit; }
