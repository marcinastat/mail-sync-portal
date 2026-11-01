#!/usr/bin/env bash
# Bezpieczniki ponownego wdrożenia — wspólne dla scripts/update.sh (sprawdza
# PRZED pobraniem kodu) i 50-provisioning-api.sh (PRZED jakąkolwiek zmianą).
# Wymagają wcześniejszego `source common.sh` i `load_install_conf`.

VM2_TLS_DIR="/etc/portal/vm2-api"
VM2_API_UNIT="/etc/systemd/system/vm2-provisioning-api.service"

# Kończy (die), gdy ponowne wdrożenie VM2 z katalogu repo $1 zepsułoby mTLS
# albo adresy. Nic nie zmienia.
guard_vm2_deploy() {
    local repo="$1" deployed_ca repo_ca match="" cand hint deployed_vm1
    # CA mTLS żyje w katalogu repo ($repo/ca, poza gitem). Instalacja mogła iść
    # z klonu git albo z kopii wgranej sync-to-vm2.sh (INSTALL.md, opcje A/B) —
    # na jednej maszynie bywają OBA katalogi z RÓŻNYMI CA. Wdrożenie z
    # niewłaściwego wystawiłoby cert serwera obcym (lub nowym) CA: VM1 przestałaby
    # ufać VM2 i panel straciłby połączenie.
    if [[ -f "$VM2_TLS_DIR/ca.crt" ]]; then
        deployed_ca="$(openssl x509 -noout -fingerprint -sha256 -in "$VM2_TLS_DIR/ca.crt")"
        repo_ca="$(openssl x509 -noout -fingerprint -sha256 -in "$repo/ca/ca.crt" 2>/dev/null || true)"
        if [[ "$deployed_ca" != "$repo_ca" ]]; then
            while read -r cand; do
                if [[ "$(openssl x509 -noout -fingerprint -sha256 -in "$cand" 2>/dev/null)" == "$deployed_ca" ]]; then
                    match="${cand%/ca/ca.crt}"; break
                fi
            done < <(find "${CA_SEARCH_ROOT:-/}" -xdev -maxdepth 4 -path '*/ca/ca.crt' 2>/dev/null)
            if [[ -n "$match" ]]; then
                hint="Uruchom z katalogu: $match"
            else
                hint="Nie znaleziono kopii repo z wdrożonym CA — nie generuj nowego, skontaktuj się z dostawcą."
            fi
            die "Katalog $repo ma INNE CA niż wdrożone w $VM2_TLS_DIR — przerywam, nic nie zmieniono (inaczej panel straciłby połączenie z VM2). $hint"
        fi
    fi
    # VM2_IP trafia do SAN certyfikatu serwera — musi być adresem TEJ maszyny.
    # Porównanie w [[ ]], nie `hostname -I | grep -q` (pod pipefail SIGPIPE potrafi
    # dać fałszywy wynik).
    if [[ -n "${VM2_IP:-}" && " $(hostname -I) " != *" $VM2_IP "* ]]; then
        die "VM2_IP=$VM2_IP w install.conf nie jest adresem tej maszyny ($(hostname -I | xargs)). Popraw $repo/config/install.conf (runbook: zmiana adresu IP VM2)."
    fi
    # VM1_IP trafia do allowlisty API. Różnica względem wdrożonej wartości to albo
    # nieaktualny install.conf (panel dostałby 403), albo realna zmiana IP VM1.
    if [[ -f "$VM2_API_UNIT" ]]; then
        deployed_vm1="$(sed -n 's/^Environment=VM2_API_ALLOWED_CLIENT_IP=//p' "$VM2_API_UNIT")"
        if [[ -n "$deployed_vm1" && "$deployed_vm1" != "$VM1_IP" && "${ALLOW_VM1_IP_CHANGE:-0}" != "1" ]]; then
            die "VM1_IP=$VM1_IP w install.conf różni się od wdrożonego ($deployed_vm1). Jeśli install.conf jest nieaktualny — popraw go. Jeśli VM1 naprawdę zmieniła adres — runbook: zmiana adresu IP VM1 (albo ALLOW_VM1_IP_CHANGE=1)."
        fi
    fi
}

# VM1: adresy z install.conf nie trafiają do wdrażanych tu plików (50-portal-app),
# więc rozjazd to tylko ostrzeżenie — ale zwykle oznacza, że zmienił się adres.
guard_vm1_deploy() {
    local resolved
    if [[ -n "${VM1_IP:-}" && " $(hostname -I) " != *" $VM1_IP "* ]]; then
        log_warn "VM1_IP=$VM1_IP w install.conf nie jest adresem tej maszyny ($(hostname -I | xargs)) — jeśli VM1 zmieniła adres, patrz runbook: zmiana adresu IP VM1."
    fi
    resolved="$(getent hosts "${VM2_HOSTNAME:-}" 2>/dev/null | awk '{print $1; exit}' || true)"
    if [[ -n "${VM2_IP:-}" && -n "$resolved" && "$resolved" != "$VM2_IP" ]]; then
        log_warn "VM2_HOSTNAME=$VM2_HOSTNAME wskazuje na $resolved (/etc/hosts), a install.conf ma VM2_IP=$VM2_IP — sprawdź, który adres jest aktualny (runbook: zmiana adresu IP VM2)."
    fi
}
