#!/usr/bin/env bash
# Aktualizacja APLIKACJI z panelu — root-helper (sudoers: tylko check/start/status,
# bez argumentów). Ten sam plik na obu VM:
#   VM1 → /opt/portal-app/bin/portal-app-update.sh  (woła go panel)
#   VM2 → /usr/local/sbin/vm2-app-update.sh          (woła go vm2-api)
#
#   check   — wersja kodu w katalogu instalacji i na GitHub (key=value)
#   start   — aktualizacja w tle jako transient unit: update.sh restartuje usługę,
#             która helpera wywołała, więc nie może być jej procesem potomnym.
#             VM2: scripts/update.sh. VM1: run-all = najpierw VM2 (przez API mTLS),
#             potem VM1 — ta sama kolejność co w procedurze ręcznej.
#   status  — stan ostatniego przebiegu (key=value) + ogon logu po linii ---log---
#   run-all / run-local — wewnętrzne (VM1 / VM2): uruchamia je `start` jako
#             transient unit, nie sudoers
#
# Katalog instalacji zapisują 50-portal-app.sh / 50-provisioning-api.sh w
# /etc/portal/repo-path; kod z niego wykonujemy jako root, więc musi należeć do roota.
set -uo pipefail

UNIT="portal-app-update"
REPO_PATH_FILE="/etc/portal/repo-path"
STATE_DIR="/var/lib/portal-update"
LOG_DIR="/var/log/portal-update"
REPO_URL="https://github.com/marcinastat/mail-sync-portal.git"
VM2_WAIT_SECONDS=1800

if [[ -d /opt/vm2-api ]]; then ROLE=vm2; else ROLE=vm1; fi
# VM2: stan zapisuje sam update.sh. VM1: stan całej operacji (VM2 + VM1).
if [[ "$ROLE" == vm2 ]]; then STATE_FILE="$STATE_DIR/last-run"; else STATE_FILE="$STATE_DIR/app-run"; fi

err() { echo "error=$*"; exit 3; }

load_repo() {
    REPO="$(cat "$REPO_PATH_FILE" 2>/dev/null || true)"
    [[ -n "$REPO" && -f "$REPO/scripts/update.sh" ]] \
        || err "Brak zapisanego katalogu instalacji — zaktualizuj tę maszynę raz z konsoli (scripts/update.sh)."
    [[ "$(stat -c %U "$REPO")" == root && "$(stat -c %U "$REPO/scripts/update.sh")" == root ]] \
        || err "Katalog $REPO nie należy do roota — odmawiam uruchomienia z panelu."
}

write_state() {   # <state> <krok>
    install -d -m 0755 "$STATE_DIR"
    printf 'state=%s\nstep=%s\nrole=%s\nstarted=%s\nlog=%s\nupdated=%s\n' "$1" "$2" "$ROLE" \
        "${RUN_STARTED:-}" "${RUN_LOG:-}" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$STATE_FILE"
}

do_check() {
    load_repo
    local g=(git -c safe.directory="$REPO" -C "$REPO")
    echo "local=$("${g[@]}" rev-parse HEAD 2>/dev/null || true)"
    echo "local_date=$("${g[@]}" log -1 --format=%cI 2>/dev/null || true)"
    echo "local_subject=$("${g[@]}" log -1 --format=%s 2>/dev/null | cut -c1-120 || true)"
    echo "remote=$(timeout 20 git ls-remote "$REPO_URL" refs/heads/master 2>/dev/null | cut -f1 || true)"
}

do_start() {
    load_repo
    systemctl is-active --quiet "$UNIT" && err "Aktualizacja aplikacji już trwa."
    RUN_STARTED="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    if [[ "$ROLE" == vm2 ]]; then
        # Wywołujący vm2-api działa pod ProtectSystem=strict (/var tylko do odczytu),
        # więc stan zapisujemy dopiero w transient unicie (run-local, poza piaskownicą).
        systemd-run --quiet --unit="$UNIT" --collect --setenv=RUN_STARTED="$RUN_STARTED" \
            -p StandardOutput=null -p StandardError=null \
            "$(readlink -f "${BASH_SOURCE[0]}")" run-local || err "Nie udało się uruchomić aktualizacji (systemd-run)."
    else
        # VM1: wywołujący (gunicorn) ma ProtectSystem=full — /var zapisywalny, więc
        # stan „running” zapisujemy od razu (panel widzi go przy pierwszym odczycie).
        install -d -m 0700 "$LOG_DIR"
        RUN_LOG="$LOG_DIR/app-run-$(date '+%Y%m%d-%H%M%S').log"
        write_state running start
        systemd-run --quiet --unit="$UNIT" --collect \
            --setenv=RUN_LOG="$RUN_LOG" --setenv=RUN_STARTED="$RUN_STARTED" \
            -p StandardOutput="append:$RUN_LOG" -p StandardError=inherit \
            "$(readlink -f "${BASH_SOURCE[0]}")" run-all || err "Nie udało się uruchomić aktualizacji (systemd-run)."
    fi
    echo "started=1"
}

do_status() {
    local active=no log
    systemctl is-active --quiet "$UNIT" && active=yes
    if [[ -f "$STATE_FILE" ]]; then cat "$STATE_FILE"; else echo "state=none"; fi
    echo "active=$active"
    log="$(sed -n 's/^log=//p' "$STATE_FILE" 2>/dev/null || true)"
    echo "---log---"
    if [[ -n "$log" && -f "$log" ]]; then tail -n 200 "$log"; fi
    return 0
}

# --- VM2: przebieg w transient unicie ---------------------------------------------

do_run_local() {
    [[ -n "${INVOCATION_ID:-}" ]] || err "run-local uruchamia wyłącznie tryb start (jako transient unit)."
    load_repo
    # Stan „running” od razu — inaczej odpytujący (VM1) widziałby stan
    # POPRZEDNIEGO przebiegu, zanim update.sh zapisze własny.
    write_state running start
    exec /bin/bash "$REPO/scripts/update.sh"
}

# --- VM1: cała operacja (VM2, potem VM1) -----------------------------------------

say() { printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }

vm2_json_field() {   # <json> <pole> — pusto, gdy brak/niepoprawny JSON
    python3 -c 'import json,sys
try:
    v = json.loads(sys.argv[1]).get(sys.argv[2])
except Exception:
    v = None
print("" if v is None else (str(v).lower() if isinstance(v, bool) else v))' "$1" "$2" 2>/dev/null || true
}

do_run_all() {
    [[ -n "${INVOCATION_ID:-}" ]] || err "run-all uruchamia wyłącznie tryb start (jako transient unit)."
    load_repo
    local target code body state active tmp deadline
    local tls=(--cert /etc/portal/vm1-client/client.crt --key /etc/portal/vm1-client/client.key
               --cacert /etc/portal/vm1-client/ca.crt)
    target="$(runuser -u postgres -- psql -d portal_db -tAc \
        "SELECT vm2_host||':'||vm2_api_port FROM vm2_connection WHERE vm2_host IS NOT NULL LIMIT 1" 2>/dev/null | tr -d '[:space:]')"

    write_state running vm2
    if [[ -z "$target" ]]; then
        say "Brak skonfigurowanego połączenia z VM2 — pomijam VM2."
    else
        say "### VM2 ($target): uruchamiam aktualizację aplikacji..."
        tmp="$(mktemp)"
        code="$(curl -s -o "$tmp" -w '%{http_code}' --max-time 30 "${tls[@]}" -X POST "https://$target/system/app-update" || true)"
        case "$code" in
            200|409) [[ "$code" == 409 ]] && say "Na VM2 aktualizacja już trwa — czekam na jej wynik." ;;
            404) say "VM2 ma starszą wersję bez aktualizacji z panelu — zaktualizuj VM2 raz z konsoli (scripts/update.sh), potem ponów."
                 rm -f "$tmp"; write_state failed vm2; exit 1 ;;
            *)   say "VM2 nie przyjęła żądania (HTTP ${code:-brak}): $(head -c 500 "$tmp")"
                 rm -f "$tmp"; write_state failed vm2; exit 1 ;;
        esac
        rm -f "$tmp"
        deadline=$(( $(date +%s) + VM2_WAIT_SECONDS ))
        sleep 5
        while :; do
            # W trakcie VM2 restartuje swoje API — chwilowe błędy połączenia są normalne.
            body="$(curl -s --max-time 15 "${tls[@]}" "https://$target/system/app-update/status" || true)"
            state="$(vm2_json_field "$body" state)"
            active="$(vm2_json_field "$body" active)"
            if [[ -n "$state" && "$active" == false && "$state" != running ]]; then break; fi
            if (( $(date +%s) > deadline )); then
                say "VM2 nie skończyła w ciągu $((VM2_WAIT_SECONDS / 60)) min — przerywam (sprawdź VM2)."
                write_state failed vm2; exit 1
            fi
            sleep 10
        done
        say "--- log VM2 (ogon) ---"
        vm2_json_field "$body" log_tail | tail -n 40
        say "--- koniec logu VM2 ---"
        if [[ "$state" != success ]]; then
            say "Aktualizacja VM2 NIEUDANA (stan: $state) — VM1 nie była aktualizowana."
            write_state failed vm2; exit 1
        fi
        say "VM2 zaktualizowana."
    fi

    write_state running vm1
    say "### VM1: aktualizacja aplikacji (panel zrestartuje się na chwilę — okno wznowi odczyt)..."
    if bash "$REPO/scripts/update.sh"; then
        write_state success done
        say "Aktualizacja aplikacji zakończona powodzeniem na obu maszynach."
    else
        write_state failed vm1
        say "Aktualizacja VM1 NIEUDANA — szczegóły powyżej."
        exit 1
    fi
}

main() {
    case "${1:-}" in
        check)   do_check ;;
        start)   do_start ;;
        status)  do_status ;;
        run-all)   [[ "$ROLE" == vm1 ]] || err "run-all tylko na VM1."; do_run_all ;;
        run-local) [[ "$ROLE" == vm2 ]] || err "run-local tylko na VM2."; do_run_local ;;
        *) echo "Użycie: $0 check|start|status" >&2; exit 2 ;;
    esac
}

# Całość w funkcji + exit: run-all trwa minuty, a wdrożenie VM1 podmienia ten
# plik w trakcie — bash nie doczyta nic z nowej wersji do bieżącego przebiegu.
{ main "$@"; exit; }
