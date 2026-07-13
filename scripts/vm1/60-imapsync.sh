#!/usr/bin/env bash
# VM1 — krok 60: zależności Perl + imapsync (silnik synchronizacji, wywoływany
# przez portal_app/services/imapsync_runner.py z twardą allowlistą flag).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-60-imapsync"
require_root
step_done "$STEP_NAME"
load_install_conf

# Tag w repo imapsync/imapsync ma format "imapsync-X.Y.Z" (NIE "vX.Y.Z") —
# potwierdzone wprost przez GitHub API, najnowszy dostępny tag na dziś.
IMAPSYNC_TAG="${IMAPSYNC_GIT_TAG:-imapsync-2.229}"
IMAPSYNC_BIN="/usr/local/bin/imapsync"

if ! rpm -q epel-release >/dev/null 2>&1; then
    pkg_install_idempotent epel-release
fi

# EPEL10 jest bardzo świeże i nie ma jeszcze portów wielu starszych modułów
# Perl (w tym kluczowego Mail::IMAPClient) — instalujemy z dnf co dostępne,
# a resztę (w tym to, co krytyczne) dobieramy przez cpanm. gcc/perl-devel są
# potrzebne, bo część modułów ma komponenty XS (kompilowane).
pkg_install_idempotent perl perl-App-cpanminus gcc perl-devel make \
    perl-IO-Socket-SSL perl-Digest-MD5 perl-Digest-HMAC \
    perl-File-Copy-Recursive perl-Unicode-String perl-Sys-MemInfo || true

# Pełna lista wynika wprost z `grep '^use [A-Z]' imapsync-2.229` — to
# WSZYSTKO, czego skrypt potrzebuje żeby się w ogóle skompilować (moduły
# rdzenia Perla jak Carp/Cwd/POSIX pomięte, bo są zawsze dostępne). Każdy
# brakujący powodował BEGIN failed--compilation aborted przy kolejnym z rzędu
# uruchomieniu — teraz instalujemy komplet za jednym razem.
cpanm --notest --quiet \
    Mail::IMAPClient Encode::IMAPUTF7 IO::Socket::INET6 IO::Tee \
    Readonly Regexp::Common Term::ReadKey File::Tail Compress::Zlib \
    || die "Nie udało się zainstalować wymaganych modułów Perl przez cpanm — imapsync nie będzie działać."

# Używane tylko przez opcjonalne funkcje imapsync (NTLM/OAuth2/uniqid),
# nieużywane przy naszym modelu auth samym hasłem — best-effort.
cpanm --notest --quiet Data::Uniqid Authen::NTLM JSON::WebToken 2>/dev/null \
    || log_warn "Część opcjonalnych modułów Perl (NTLM/OAuth2) nie zainstalowała się — nieużywane przy auth samym hasłem, można pominąć."

if [[ ! -x "$IMAPSYNC_BIN" ]]; then
    log_info "Pobieram imapsync ${IMAPSYNC_TAG}..."
    curl -fsSL -o "$IMAPSYNC_BIN" \
        "https://raw.githubusercontent.com/imapsync/imapsync/${IMAPSYNC_TAG}/imapsync"
    chmod 0755 "$IMAPSYNC_BIN"
fi

"$IMAPSYNC_BIN" --version || die "imapsync --version nie powiodło się — sprawdź brakujące moduły Perl powyżej."

log_info "imapsync gotowe pod ${IMAPSYNC_BIN} (wersja przypięta: ${IMAPSYNC_TAG})."
mark_step_done "$STEP_NAME"
