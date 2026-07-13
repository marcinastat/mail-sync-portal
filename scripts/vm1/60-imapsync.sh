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

IMAPSYNC_TAG="${IMAPSYNC_GIT_TAG:-v2.267}"
IMAPSYNC_BIN="/usr/local/bin/imapsync"

if ! rpm -q epel-release >/dev/null 2>&1; then
    pkg_install_idempotent epel-release
fi

pkg_install_idempotent perl perl-Mail-IMAPClient perl-IO-Socket-SSL perl-Digest-MD5 \
    perl-Digest-HMAC perl-Term-ReadKey perl-File-Copy-Recursive perl-Data-Uniqid \
    perl-Unicode-String perl-Authen-NTLM perl-JSON-WebToken perl-File-Tail \
    perl-Test-Pod perl-Test-Pod-Coverage perl-Sys-MemInfo || \
    log_warn "Część pakietów Perl mogła nie zainstalować się z EPEL — imapsync zgłosi brakujące moduły przy pierwszym uruchomieniu."

if [[ ! -x "$IMAPSYNC_BIN" ]]; then
    log_info "Pobieram imapsync ${IMAPSYNC_TAG}..."
    curl -fsSL -o "$IMAPSYNC_BIN" \
        "https://raw.githubusercontent.com/imapsync/imapsync/${IMAPSYNC_TAG}/imapsync"
    chmod 0755 "$IMAPSYNC_BIN"
fi

"$IMAPSYNC_BIN" --version || log_warn "imapsync --version nie powiodło się — sprawdź brakujące moduły Perl (cpan/dnf)."

log_info "imapsync gotowe pod ${IMAPSYNC_BIN} (wersja przypięta: ${IMAPSYNC_TAG})."
mark_step_done "$STEP_NAME"
