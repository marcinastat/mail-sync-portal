#!/usr/bin/env bash
# VM2 — krok 25: wykrywa dedykowany dysk na pocztę (osobny od dysku
# systemowego), formatuje go (TYLKO jeśli jest zupełnie pusty), dodaje do
# /etc/fstab przez UUID i montuje pod /var/mail/vhosts — miejsce, którego
# oczekują Postfix/Dovecot (scripts/vm2/30-postfix-dovecot.sh) i ClamAV
# (scripts/vm2/40-clamav.sh). Instaluje też lokalny monitoring zajętości obu
# dysków (systemd timer, niezależny od tego, czy VM1 odpytuje VM2).
#
# Bezpieczeństwo: skrypt NIGDY nie formatuje dysku, który ma już jakikolwiek
# ślad partycji/systemu plików, i NIGDY nie rusza dysku systemowego. Jeśli
# wykrycie jest niejednoznaczne, przerywa z czytelnym błędem zamiast zgadywać.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-25-mail-disk"
require_root
load_install_conf

REPO_ROOT="$(repo_root)"
MAIL_MOUNT="/var/mail/vhosts"

# Celowo NIE używamy step_done() (znacznik pliku) jako jedynej bramki
# idempotencji dla formatowania/montowania — dla operacji na dysku liczy się
# rzeczywisty stan systemu (np. po odtworzeniu VM ze snapshotu marker mógłby
# istnieć, a dysk nie być realnie zamontowany).
if mountpoint -q "$MAIL_MOUNT"; then
    log_info "$MAIL_MOUNT już jest punktem montowania — pomijam formatowanie/montowanie (idempotentne)."
else
    pkg_install_idempotent xfsprogs util-linux

    # --- Wybór urządzenia -------------------------------------------------------
    if [[ -n "${VM2_MAIL_DISK:-}" ]]; then
        MAIL_DISK="${VM2_MAIL_DISK#/dev/}"
        log_info "VM2_MAIL_DISK ustawione jawnie w install.conf: /dev/$MAIL_DISK"
    else
        root_source="$(findmnt -no SOURCE /)"
        os_disks="$(lsblk -no NAME,TYPE -s "$root_source" 2>/dev/null | awk '$2=="disk"{print $1}' | sort -u)"
        all_disks="$(lsblk -dn -o NAME,TYPE | awk '$2=="disk"{print $1}' | sort -u)"
        candidate_disks="$(comm -23 <(echo "$all_disks") <(echo "$os_disks"))"

        candidate_count="$(echo "$candidate_disks" | grep -c . || true)"
        if [[ "$candidate_count" -eq 0 ]]; then
            die "Nie znaleziono drugiego dysku (poza systemowym: $os_disks). Wymóg: VM2 musi mieć osobny dysk na pocztę. Dodaj dysk do VM i uruchom ten skrypt ponownie, albo ustaw VM2_MAIL_DISK w install.conf."
        elif [[ "$candidate_count" -gt 1 ]]; then
            die "Znaleziono więcej niż jeden dysk poza systemowym ($candidate_disks) — niejednoznaczne. Ustaw jawnie VM2_MAIL_DISK=/dev/<nazwa> w config/install.conf i uruchom ponownie."
        fi
        MAIL_DISK="$candidate_disks"
    fi

    MAIL_DEVICE="/dev/${MAIL_DISK}"
    [[ -b "$MAIL_DEVICE" ]] || die "Urządzenie $MAIL_DEVICE nie istnieje."

    # --- Bezpieczeństwo: formatuj TYLKO jeśli dysk jest zupełnie pusty ---------
    existing_fstype="$(lsblk -no FSTYPE "$MAIL_DEVICE" | tr -d '[:space:]')"
    existing_parttable="$(lsblk -no PTTYPE "$MAIL_DEVICE" | tr -d '[:space:]')"
    child_count="$(lsblk -no NAME "$MAIL_DEVICE" | tail -n +2 | grep -c . || true)"

    if [[ -n "$existing_fstype" || -n "$existing_parttable" || "$child_count" -gt 0 ]]; then
        die "$MAIL_DEVICE nie jest pusty (fstype='$existing_fstype', parttable='$existing_parttable', partycje=$child_count) — NIE formatuję istniejących danych. Jeśli to zamierzony, już przygotowany dysk na pocztę, zamontuj go ręcznie pod $MAIL_MOUNT, dodaj wpis do /etc/fstab i uruchom ten skrypt ponownie (wykryje istniejący mountpoint i przejdzie dalej)."
    fi

    log_info "Formatuję pusty dysk $MAIL_DEVICE jako XFS (miejsce na pocztę VM2)..."
    mkfs.xfs -L mailvhosts "$MAIL_DEVICE"

    DISK_UUID="$(blkid -s UUID -o value "$MAIL_DEVICE")"
    [[ -n "$DISK_UUID" ]] || die "Nie udało się odczytać UUID dla $MAIL_DEVICE po sformatowaniu."

    mkdir -p "$MAIL_MOUNT"

    FSTAB_LINE="UUID=${DISK_UUID}  ${MAIL_MOUNT}  xfs  defaults,nofail  0  2"
    if ! grep -qF "$DISK_UUID" /etc/fstab; then
        backup_file /etc/fstab
        echo "$FSTAB_LINE" >> /etc/fstab
        log_info "Dodano wpis do /etc/fstab: $FSTAB_LINE"
    fi

    mount "$MAIL_MOUNT"
    mountpoint -q "$MAIL_MOUNT" || die "Montowanie $MAIL_MOUNT nie powiodło się mimo wpisu w fstab."

    log_info "Dysk pocztowy $MAIL_DEVICE zamontowany pod $MAIL_MOUNT (UUID=$DISK_UUID)."
fi

# --- Lokalny monitoring obu dysków (niezależny od VM1) --------------------------
export DISK_USAGE_WARNING_PERCENT="${DISK_USAGE_WARNING_PERCENT:-85}"
render_template "$REPO_ROOT/templates/monitoring/vm2-disk-check.sh.tmpl" /usr/local/sbin/vm2-disk-check.sh '$DISK_USAGE_WARNING_PERCENT'
chmod 0755 /usr/local/sbin/vm2-disk-check.sh
install -m 0644 "$REPO_ROOT/templates/systemd/vm2-disk-check.service.tmpl" /etc/systemd/system/vm2-disk-check.service
install -m 0644 "$REPO_ROOT/templates/systemd/vm2-disk-check.timer.tmpl" /etc/systemd/system/vm2-disk-check.timer
systemctl daemon-reload
systemctl enable --now vm2-disk-check.timer

log_info "Monitoring dysków VM2 aktywny (próg ostrzeżenia: ${DISK_USAGE_WARNING_PERCENT}%, journalctl -u vm2-disk-check)."
mark_step_done "$STEP_NAME"
