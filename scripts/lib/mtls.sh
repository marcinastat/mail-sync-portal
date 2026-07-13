#!/usr/bin/env bash
# Generowanie lokalnego CA + certyfikatów mTLS dla kanału
# VM1 (klient) <-> VM2 provisioning API (serwer).
#
# Wynik ląduje w ca/ w katalogu repo — ten katalog NIGDY nie jest commitowany
# (patrz .gitignore) i musi zostać bezpiecznie skopiowany na obie VM po
# wygenerowaniu (np. scp przez tunel administracyjny, nie przez sieć publiczną).
#
# Źródłuj po common.sh.

MTLS_CA_DIR_DEFAULT() {
    local repo_root
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    echo "$repo_root/ca"
}

mtls_generate_ca() {
    local ca_dir="${1:-$(MTLS_CA_DIR_DEFAULT)}"
    mkdir -p "$ca_dir"
    if [[ -f "$ca_dir/ca.key" ]]; then
        log_info "CA już istnieje w $ca_dir — pomijam generowanie (usuń ręcznie, jeśli potrzebna rotacja)."
        return 0
    fi
    log_info "Generuję lokalne CA w $ca_dir ..."
    openssl genrsa -out "$ca_dir/ca.key" 4096
    chmod 0600 "$ca_dir/ca.key"
    openssl req -x509 -new -nodes -key "$ca_dir/ca.key" -sha256 -days 3650 \
        -subj "/CN=portal-internal-ca" \
        -out "$ca_dir/ca.crt"
    log_info "CA wygenerowane: $ca_dir/ca.crt (ważne 10 lat)."
}

# mtls_issue_cert <ca_dir> <cn> <out_prefix> [san]
# Wystawia certyfikat podpisany lokalnym CA. Użyj CN="vm1-portal-client" dla
# klienta (aplikacja VM1) i CN=<VM2_HOSTNAME> dla serwera (provisioning API).
# Opcjonalny [san] (np. "DNS:mail.example.internal,IP:10.0.0.20") jest KONIECZNY
# dla certyfikatu serwera — nowoczesna weryfikacja TLS (Python/httpx, którego
# używa aplikacja VM1) wymaga subjectAltName i NIE akceptuje samego CN.
mtls_issue_cert() {
    local ca_dir="$1" cn="$2" out_prefix="$3" san="${4:-}"
    openssl genrsa -out "${out_prefix}.key" 2048
    chmod 0600 "${out_prefix}.key"
    openssl req -new -key "${out_prefix}.key" -subj "/CN=${cn}" -out "${out_prefix}.csr"

    local ext_args=() ext_file=""
    if [[ -n "$san" ]]; then
        ext_file="$(mktemp)"
        printf 'subjectAltName=%s\n' "$san" > "$ext_file"
        ext_args=(-extfile "$ext_file")
    fi
    openssl x509 -req -in "${out_prefix}.csr" \
        -CA "$ca_dir/ca.crt" -CAkey "$ca_dir/ca.key" -CAcreateserial \
        -out "${out_prefix}.crt" -days 825 -sha256 "${ext_args[@]}"
    rm -f "${out_prefix}.csr"
    [[ -n "$ext_file" ]] && rm -f "$ext_file"
    log_info "Wystawiono certyfikat CN=$cn${san:+ (SAN: $san)} -> ${out_prefix}.crt / ${out_prefix}.key"
}

mtls_setup_vm1_client() {
    local ca_dir="${1:-$(MTLS_CA_DIR_DEFAULT)}"
    mtls_generate_ca "$ca_dir"
    mtls_issue_cert "$ca_dir" "vm1-portal-client" "$ca_dir/vm1-client"
}

mtls_setup_vm2_server() {
    local ca_dir="${1:-$(MTLS_CA_DIR_DEFAULT)}" vm2_hostname="$2" vm2_ip="${3:-}"
    mtls_generate_ca "$ca_dir"
    # SAN musi objąć zarówno nazwę hosta, jak i IP — w kreatorze admin poda
    # zwykle IP (brak wewnętrznego DNS), a httpx weryfikuje adres, z którym
    # faktycznie się łączy, względem SAN. Bez IP w SAN test połączenia z VM2
    # pada z błędem weryfikacji certyfikatu mimo poprawnego mTLS.
    local san="DNS:${vm2_hostname}"
    [[ -n "$vm2_ip" ]] && san="${san},IP:${vm2_ip}"
    mtls_issue_cert "$ca_dir" "$vm2_hostname" "$ca_dir/vm2-server" "$san"
}
