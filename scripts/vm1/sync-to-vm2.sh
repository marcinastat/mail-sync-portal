#!/usr/bin/env bash
# VM1 — opcjonalny skrypt (NIE część stałej sekwencji 00-90): generuje klucz
# SSH na VM1 (jeśli brak), wypycha go na VM2 (poprosi o hasło roota VM2
# JEDEN raz, potem już nie), synchronizuje TO repozytorium (ten sam checkout
# co na VM1) na VM2 przez rsync po SSH.
#
# Po zakończeniu skrypty scripts/vm2/*.sh nadal uruchamia się RĘCZNIE, po
# kolei, NA VM2 — ten skrypt tylko przygotowuje tam kopię repo, nic więcej
# (świadomie, żeby nie wykonywać zdalnie kroków wymagających interwencji,
# np. wyboru dysku pocztowego przy niejednoznaczności).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_root
load_install_conf

: "${VM2_IP:?VM2_IP musi być ustawione w install.conf}"

REPO_ROOT="$(repo_root)"
SSH_KEY="/root/.ssh/portal_deploy_ed25519"
REMOTE_USER="${VM2_SSH_USER:-root}"
REMOTE_PATH="${VM2_REMOTE_REPO_PATH:-/root/mail-sync-portal}"

install_base_prereqs

if [[ ! -f "$SSH_KEY" ]]; then
    log_info "Generuję klucz SSH do wdrożeń VM1 -> VM2 ($SSH_KEY)..."
    ssh-keygen -t ed25519 -N "" -f "$SSH_KEY" -C "portal-vm1-deploy" >/dev/null
fi

if ! ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=5 \
        "${REMOTE_USER}@${VM2_IP}" true 2>/dev/null; then
    log_info "Klucz jeszcze nie jest autoryzowany na VM2 — podaj hasło roota VM2, gdy zapyta (jednorazowo)."
    if command -v ssh-copy-id >/dev/null 2>&1; then
        ssh-copy-id -i "${SSH_KEY}.pub" -o StrictHostKeyChecking=accept-new "${REMOTE_USER}@${VM2_IP}"
    else
        # ssh-copy-id bywa niedostępne na czystym minimal — fallback bez niego.
        cat "${SSH_KEY}.pub" | ssh -o StrictHostKeyChecking=accept-new "${REMOTE_USER}@${VM2_IP}" \
            'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys'
    fi
else
    log_info "Klucz SSH już autoryzowany na VM2 — pomijam ssh-copy-id."
fi

log_info "Synchronizuję repozytorium na VM2:${REMOTE_PATH} ..."
rsync -az --delete \
    -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new" \
    --exclude '.git' \
    --exclude 'ca' \
    --exclude 'config/install.conf.bak-*' \
    "$REPO_ROOT/" "${REMOTE_USER}@${VM2_IP}:${REMOTE_PATH}/"

log_info "Gotowe. Na VM2:"
log_info "  ssh -i $SSH_KEY ${REMOTE_USER}@${VM2_IP}"
log_info "  cd ${REMOTE_PATH} && sudo scripts/vm2/00-preflight.sh   # i dalej po kolei"
log_info "Uruchom ten skrypt ponownie po każdej zmianie w repo na VM1, żeby zsynchronizować VM2 (rsync --delete, bezpieczne do wielokrotnego użycia)."
