#!/usr/bin/env bash
# Kontrole wstępne (preflight) wspólne dla VM1 i VM2.
# Źródłuj po common.sh: source ".../lib/checks.sh"

check_os_rocky10() {
    if [[ ! -f /etc/os-release ]]; then
        die "Brak /etc/os-release — nie mogę zweryfikować systemu operacyjnego."
    fi
    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${ID:-}" != "rocky" ]]; then
        die "Oczekiwano Rocky Linux, wykryto: ${ID:-nieznany} ${VERSION_ID:-}"
    fi
    local major="${VERSION_ID%%.*}"
    if [[ "$major" != "10" ]]; then
        die "Oczekiwano Rocky Linux 10.x, wykryto: ${VERSION_ID:-nieznany}"
    fi
    log_info "System operacyjny: Rocky Linux $VERSION_ID — OK."
}

check_disk_space_gb() {
    local path="$1" min_gb="$2"
    local avail_kb
    avail_kb="$(df --output=avail -k "$path" | tail -n1 | tr -d ' ')"
    local avail_gb=$(( avail_kb / 1024 / 1024 ))
    if (( avail_gb < min_gb )); then
        die "Za mało miejsca na $path: ${avail_gb}GB dostępne, wymagane ${min_gb}GB."
    fi
    log_info "Miejsce na $path: ${avail_gb}GB dostępne (wymagane ${min_gb}GB) — OK."
}

check_outbound_connectivity() {
    local host="$1"
    if ! curl --silent --head --max-time 5 "https://$host" >/dev/null 2>&1; then
        log_warn "Brak połączenia wychodzącego do $host — jeśli OUTBOUND_INTERNET_ACCESS=true w install.conf, sprawdź firewall/DNS."
        return 1
    fi
    log_info "Połączenie wychodzące do $host — OK."
}

check_selinux_enforcing() {
    if command -v getenforce >/dev/null 2>&1; then
        local mode
        mode="$(getenforce)"
        if [[ "$mode" != "Enforcing" ]]; then
            log_warn "SELinux nie jest w trybie Enforcing (aktualnie: $mode). Plan zakłada enforcing — nie wyłączamy SELinuksa jako obejścia problemów."
        else
            log_info "SELinux: Enforcing — OK."
        fi
    fi
}
