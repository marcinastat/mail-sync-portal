#!/usr/bin/env bash
# Biblioteka wspólna dla wszystkich skryptów instalacyjnych VM1/VM2.
# Źródłuj tak: source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"

set -euo pipefail

STEPS_DIR="/var/lib/portal-install/.steps"
LOG_TAG="portal-install"

log() {
    local level="$1"; shift
    printf '[%s] %-5s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$level" "$*"
    logger -t "$LOG_TAG" -- "$level: $*" 2>/dev/null || true
}

log_info()  { log "INFO"  "$@"; }
log_warn()  { log "WARN"  "$@"; }
log_error() { log "ERROR" "$@" >&2; }
die()       { log_error "$@"; exit 1; }

require_root() {
    if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
        die "Ten skrypt musi być uruchomiony jako root (sudo)."
    fi
}

# Wczytuje config/install.conf (musi istnieć — nie mamy sensownych domyślnych
# wartości dla adresów sieciowych, więc nie kontynuujemy bez jawnej konfiguracji).
load_install_conf() {
    local repo_root
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    local conf_file="${INSTALL_CONF:-$repo_root/config/install.conf}"
    if [[ ! -f "$conf_file" ]]; then
        die "Brak pliku konfiguracyjnego: $conf_file (skopiuj z config/install.conf.example i uzupełnij)"
    fi
    # shellcheck disable=SC1090
    source "$conf_file"
    : "${ADMIN_SUBNET_CIDR:?ADMIN_SUBNET_CIDR musi być ustawione w install.conf}"
}

# --- Idempotencja bez Ansible ------------------------------------------------
# Każdy numerowany skrypt wywołuje step_done na starcie; jeśli krok był już
# wykonany, skrypt kończy się natychmiast (exit 0), chyba że FORCE_REAPPLY=1.
step_done() {
    local name="$1"
    mkdir -p "$STEPS_DIR"
    if [[ -f "$STEPS_DIR/$name" && "${FORCE_REAPPLY:-0}" != "1" ]]; then
        log_info "Krok '$name' już wykonany — pomijam (FORCE_REAPPLY=1 wymusza ponowne uruchomienie)."
        exit 0
    fi
}

mark_step_done() {
    local name="$1"
    mkdir -p "$STEPS_DIR"
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "$STEPS_DIR/$name"
    log_info "Krok '$name' oznaczony jako wykonany."
}

pkg_install_idempotent() {
    # dnf install -y jest naturalnie idempotentny — cienki wrapper dla spójnego logowania.
    log_info "Instaluję pakiety: $*"
    dnf install -y "$@"
}

# Renderuje szablon do pliku docelowego. Trzeci argument to jawna lista
# zmiennych do podstawienia (np. '$VM1_HOSTNAME $VM2_IP'), przekazywana
# wprost do envsubst jako whitelist. To NIE jest opcjonalne dla szablonów
# zawierających $ inne niż nasze (nginx/postfix/dovecot mają własną,
# bardzo podobną składnię $zmienna) — envsubst bez whitelisty podstawiłby
# pusty string za KAŻDĄ nierozpoznaną zmienną środowiskową, cicho psując
# konfigurację (np. $remote_addr w nginx). Pusty/pominięty trzeci argument
# oznacza "nie podstawiaj niczego, tylko skopiuj".
# Jeśli plik docelowy istnieje i różni się od ostatnio wyrenderowanej wersji
# (a nie tylko od nowego szablonu), robi kopię zapasową zamiast cicho nadpisywać
# ręczne zmiany administratora.
render_template() {
    local template_path="$1" target_path="$2" vars="${3:-}"
    local rendered_marker="${target_path}.rendered-sha256"
    local tmp_rendered
    tmp_rendered="$(mktemp)"
    trap 'rm -f "$tmp_rendered"' RETURN

    if [[ -n "$vars" ]]; then
        envsubst "$vars" < "$template_path" > "$tmp_rendered"
    else
        cp "$template_path" "$tmp_rendered"
    fi
    local new_sha
    new_sha="$(sha256sum "$tmp_rendered" | awk '{print $1}')"

    if [[ -f "$target_path" ]]; then
        local current_sha
        current_sha="$(sha256sum "$target_path" | awk '{print $1}')"
        local last_rendered_sha=""
        [[ -f "$rendered_marker" ]] && last_rendered_sha="$(cat "$rendered_marker")"

        if [[ "$current_sha" != "$last_rendered_sha" ]]; then
            local backup_path
            backup_path="${target_path}.bak-$(date -u '+%Y%m%d%H%M%S')"
            log_warn "Plik $target_path był ręcznie zmieniony od ostatniego renderu — kopia zapasowa w $backup_path zamiast cichego nadpisania."
            cp -a "$target_path" "$backup_path"
        fi
    fi

    install -D -m 0644 "$tmp_rendered" "$target_path"
    sha256sum "$target_path" | awk '{print $1}' > "$rendered_marker"
    log_info "Wyrenderowano $template_path -> $target_path"
}

backup_file() {
    local path="$1"
    if [[ -f "$path" ]]; then
        cp -a "$path" "${path}.bak-$(date -u '+%Y%m%d%H%M%S')"
    fi
}

# Generuje losowy sekret i zapisuje go do pliku root:root 0600, jeśli plik
# jeszcze nie istnieje (nie nadpisuje istniejących sekretów przy ponownym
# uruchomieniu skryptu — idempotencja).
ensure_secret_file() {
    local path="$1" length="${2:-32}"
    mkdir -p "$(dirname "$path")"
    if [[ ! -f "$path" ]]; then
        openssl rand -base64 "$length" | tr -d '\n' > "$path"
        chmod 0600 "$path"
        log_info "Wygenerowano nowy sekret: $path"
    fi
}

repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}
