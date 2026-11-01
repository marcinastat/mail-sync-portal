#!/usr/bin/env bash
# Pobieranie Roundcube z weryfikacją podpisu GPG — wspólne dla instalacji
# (scripts/vm1/40-roundcube.sh) i aktualizacji (scripts/vm1/roundcube-upgrade.sh).
# Kotwicą zaufania jest PRZYPIĘTY odcisk klucza głównego „Roundcube Developers”
# (ID 41C4F7D5, roundcube.net/download): sam klucz pobieramy po HTTPS, ale
# akceptujemy wyłącznie podpis złożony tym kluczem (lub jego podkluczem).
# Wymaga wcześniejszego `source common.sh` (die/log_*).

RC_SIGNING_FPR="F3E4C04BB3DB5D4215C45F7F5AB2BAA141C4F7D5"
RC_PUBKEY_URL="https://roundcube.net/download/pubkey.asc"

# rc_fetch_verified <wersja> <plik_docelowy.tar.gz>
# Pobiera roundcubemail-<wersja>-complete.tar.gz (+ .asc) i weryfikuje podpis.
# Przy błędzie pobierania lub podpisu kasuje plik i kończy skrypt (die).
rc_fetch_verified() {
    local version="$1" out="$2" url gnupg_home status
    url="https://github.com/roundcube/roundcubemail/releases/download/${version}/roundcubemail-${version}-complete.tar.gz"
    gnupg_home="$(mktemp -d)"

    if ! curl -fsSL -o "$out" "$url" || ! curl -fsSL -o "${out}.asc" "${url}.asc" \
        || ! curl -fsSL -o "$gnupg_home/pubkey.asc" "$RC_PUBKEY_URL"; then
        rm -rf "$gnupg_home"; rm -f "$out" "${out}.asc"
        die "Nie udało się pobrać Roundcube ${version} (tarball, podpis lub klucz) — sprawdź wersję i dostęp do internetu."
    fi

    # Osobny, tymczasowy keyring — nie dotykamy keyringu roota.
    gpg --homedir "$gnupg_home" --batch --quiet --import "$gnupg_home/pubkey.asc" 2>/dev/null || true
    status="$(gpg --homedir "$gnupg_home" --batch --status-fd 1 --verify "${out}.asc" "$out" 2>/dev/null || true)"
    gpgconf --homedir "$gnupg_home" --kill all >/dev/null 2>&1 || true
    rm -rf "$gnupg_home"

    # VALIDSIG niesie odcisk klucza podpisującego, a na końcu odcisk klucza
    # GŁÓWNEGO — grep łapie oba przypadki (podpis kluczem głównym lub podkluczem).
    if ! grep -q "^\[GNUPG:\] VALIDSIG .*${RC_SIGNING_FPR}" <<<"$status"; then
        rm -f "$out" "${out}.asc"
        die "Podpis GPG Roundcube ${version} NIEPOPRAWNY lub złożony innym kluczem niż ${RC_SIGNING_FPR} — przerywam."
    fi
    rm -f "${out}.asc"
    log_info "Roundcube ${version}: podpis GPG poprawny (klucz ${RC_SIGNING_FPR})."
}
