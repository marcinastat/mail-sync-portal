#!/usr/bin/env bash
# VM2 — krok 45: rspamd (analiza phishingu / podejrzanych linków) w trybie
# OFFLINE — nie jako milter SMTP, tylko do skanowania zarchiwizowanej poczty
# przez rspamc (skrypt vm2-rspamd-scan.sh). valkey = backend redis-kompatybilny.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-45-rspamd"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"

# --- Repo rspamd (oficjalne, dla el10 nie ma go w EPEL) ----------------------
cat > /etc/yum.repos.d/rspamd.repo <<'EOF'
[rspamd]
name=Rspamd stable repository
baseurl=https://rspamd.com/rpm-stable/centos-10/$basearch/
enabled=1
gpgcheck=1
gpgkey=https://rspamd.com/rpm-stable/gpg.key
EOF

pkg_install_idempotent valkey rspamd

# valkey (redis) na localhost — backend rspamd.
systemctl enable --now valkey

# rspamd: wskaż redis/valkey. Reszta domyślnej konfiguracji (moduł phishing,
# url reputation, RBL) jest wystarczająca do skanu offline.
mkdir -p /etc/rspamd/local.d
render_template "$REPO_ROOT/templates/rspamd/redis.conf.tmpl" /etc/rspamd/local.d/redis.conf
systemctl enable --now rspamd
systemctl restart rspamd

# --- Skan maildirów rspamd (offline, przyrostowy) ----------------------------
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-rspamd-scan.sh" /usr/local/sbin/vm2-rspamd-scan.sh
install -m 0755 -o root -g root "$REPO_ROOT/vm2_api/bin/vm2-rspamd-parse.py" /usr/local/sbin/vm2-rspamd-parse.py
install -d -m 0750 -o root -g root /var/lib/vm2-scan
# Zasiej marker, żeby pierwszy przebieg nie ruszał całego backlogu (28k+ maili
# przez rspamc byłoby ciężkie). Backlog można przeskanować ręcznie:
#   sudo /usr/local/sbin/vm2-rspamd-scan.sh full
[[ -f /var/lib/vm2-scan/.last-rspamd-scan ]] || touch /var/lib/vm2-scan/.last-rspamd-scan

install -D -m 0644 "$REPO_ROOT/templates/systemd/rspamd-maildir-scan.service.tmpl" /etc/systemd/system/rspamd-maildir-scan.service
install -D -m 0644 "$REPO_ROOT/templates/systemd/rspamd-maildir-scan.timer.tmpl" /etc/systemd/system/rspamd-maildir-scan.timer
systemctl daemon-reload
systemctl enable --now rspamd-maildir-scan.timer

log_info "rspamd zainstalowany (offline). Skan phishingu przyrostowy co 60 min; pelny na zadanie: vm2-rspamd-scan.sh full."
mark_step_done "$STEP_NAME"
