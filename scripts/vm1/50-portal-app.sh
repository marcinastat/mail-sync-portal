#!/usr/bin/env bash
# VM1 — krok 50: venv, portal_app (FastAPI+Gunicorn), alembic upgrade,
# sekrety (SECRET_KEY, klucz szyfrowania haseł) zaszyfrowane przez
# systemd-creds i dostarczane usłudze wyłącznie przez LoadCredentialEncrypted=
# (nigdy jako plaintext na dysku) — patrz docs/technical/architecture.md.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-50-portal-app"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
APP_DIR="/opt/portal-app"
CREDS_DIR="/etc/portal/creds"
DB_PASS_FILE="/etc/portal/secrets/vm1-portal-db.pass"
[[ -f "$DB_PASS_FILE" ]] || die "Brak $DB_PASS_FILE — uruchom najpierw scripts/vm1/20-postgresql.sh"

command -v systemd-creds >/dev/null 2>&1 || die "systemd-creds niedostępne — wymagany systemd >= 250 (Rocky 10 go ma domyślnie)."

pkg_install_idempotent python3.12 python3.12-devel gcc sudo libffi-devel checkpolicy policycoreutils-python-utils

if ! id portal-app >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /sbin/nologin --create-home portal-app
fi

# portal_app czyta DB_PASS_FILE w runtime jako user portal-app (alembic
# teraz, gunicorn/worker/scheduler później) — nie jako root. Domyślne
# uprawnienia z 10-base-hardening.sh (katalog 0700 root, plik 0600 root)
# blokują to całkowicie (obserwowane: PermissionError w alembic env.py).
# Otwieramy tylko dostęp do TEGO JEDNEGO pliku; reszta /etc/portal/secrets
# zostaje nietknięta (0700, root-only — czytana wyłącznie przy renderowaniu
# configów jako root, np. Roundcube w scripts/vm1/40-roundcube.sh).
chmod 0711 /etc/portal/secrets
chown portal-app:portal-app "$DB_PASS_FILE"
chmod 0600 "$DB_PASS_FILE"

mkdir -p "$APP_DIR"
# "venv" (bez kropki) - patrz komentarz w scripts/vm2/50-provisioning-api.sh
# o tym samym błędzie (rsync --delete próbujący skasować cały virtualenv).
# portal_app/static/branding/ WYKLUCZONE z --delete: tam ląduje logo wgrane
# przez admina (nie ma go w repo), a bez wykluczenia rsync --delete kasowałby
# je przy każdym redeployu — obserwowane: znikające logo brandingu.
rsync -a --delete --exclude '__pycache__' --exclude 'venv' --exclude 'tests' \
    --exclude 'portal_app/static/branding' "$REPO_ROOT/app/" "$APP_DIR/"
rsync -a --delete "$REPO_ROOT/docs/" "$APP_DIR/docs/"
chown -R portal-app:portal-app "$APP_DIR"

if [[ ! -d "$APP_DIR/venv" ]]; then
    sudo -u portal-app python3.12 -m venv "$APP_DIR/venv"
fi
sudo -u portal-app "$APP_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u portal-app "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

mkdir -p /var/log/portal /var/log/portal/imapsync /var/log/portal/system-updates /var/lib/portal-app /var/lib/portal-app/branding-stage /run/portal-import
chown -R portal-app:portal-app /var/log/portal /var/lib/portal-app /run/portal-import

# --- Sekrety: generowane raz, natychmiast szyfrowane przez systemd-creds, ----
# plaintext shredowany. Ponowne uruchomienie skryptu NIE regeneruje kluczy
# (byłoby to nieodwracalne dla już zaszyfrowanych haseł w bazie).
mkdir -p "$CREDS_DIR"
if [[ ! -f "$CREDS_DIR/portal-secret-key.cred" ]]; then
    TMP_SECRET="$(mktemp)"
    openssl rand -base64 48 > "$TMP_SECRET"
    systemd-creds encrypt --name=portal-secret-key "$TMP_SECRET" "$CREDS_DIR/portal-secret-key.cred"
    shred -u "$TMP_SECRET"
    log_info "Wygenerowano i zaszyfrowano SECRET_KEY sesji aplikacji."
fi
if [[ ! -f "$CREDS_DIR/portal-credential-key.cred" ]]; then
    TMP_KEY="$(mktemp)"
    sudo -u portal-app "$APP_DIR/venv/bin/python" -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > "$TMP_KEY"
    systemd-creds encrypt --name=portal-credential-key "$TMP_KEY" "$CREDS_DIR/portal-credential-key.cred"
    shred -u "$TMP_KEY"
    log_info "Wygenerowano i zaszyfrowano klucz szyfrowania haseł źródłowych."
fi
chmod 0600 "$CREDS_DIR"/*.cred
chown root:root "$CREDS_DIR"/*.cred

# --- sudoers.d (branding -> apply-branding.sh jako root) ----------------------
install -D -m 0700 -o root -g root "$APP_DIR/portal_app/bin/apply-branding.sh" "$APP_DIR/bin/apply-branding.sh"
install -D -m 0700 -o root -g root "$APP_DIR/portal_app/bin/apply-tls.sh" "$APP_DIR/bin/apply-tls.sh"
install -D -m 0700 -o root -g root "$APP_DIR/portal_app/bin/apply-network-access.sh" "$APP_DIR/bin/apply-network-access.sh"
# Helper aktualizacji systemu (wołany fazami przez portal-worker) — root-owned
# 0700, POZA katalogami zapisywalnymi dla konta usługi (brak eskalacji).
install -D -m 0700 -o root -g root "$APP_DIR/portal_app/bin/apply-system-update.sh" "$APP_DIR/bin/apply-system-update.sh"
# Narzędzie ratunkowe na konsolę (przywraca kopię configów sprzed aktualizacji).
install -m 0700 -o root -g root "$APP_DIR/portal_app/bin/portal-config-recovery.sh" /usr/local/sbin/portal-config-recovery.sh
# Narzędzie konsolowe: reset hasła admina panelu (gdy zapomniane). Wrapper w
# /usr/local/sbin (root, 0700); pomocnik pythonowy w /opt/portal-app/bin
# (uruchamiany jako portal-app przez runuser, musi być czytelny dla usługi).
install -m 0700 -o root -g root "$APP_DIR/portal_app/bin/portal-admin-password.sh" /usr/local/sbin/portal-admin-password.sh
install -D -m 0755 -o root -g root "$APP_DIR/portal_app/bin/set-admin-password.py" "$APP_DIR/bin/set-admin-password.py"
# Katalog na kopie konfiguracji robione przed aktualizacją (retencja w helperze).
install -d -m 0700 -o root -g root /var/lib/portal-config-backups
# needs-restarting (dnf-utils) — bez niego reboot-check nie potrafi rzetelnie
# stwierdzić, czy restart jest wymagany (raportowałby "unknown", nie zgaduje "yes").
pkg_install_idempotent dnf-utils
render_template "$REPO_ROOT/templates/sudoers/portal-app.tmpl" /etc/sudoers.d/portal-app
chmod 0440 /etc/sudoers.d/portal-app
visudo -cf /etc/sudoers.d/portal-app || die "Wygenerowany plik sudoers jest niepoprawny składniowo — przerywam."

# --- Migracje bazy -------------------------------------------------------------
sudo -u portal-app bash -c "cd '$APP_DIR' && venv/bin/alembic upgrade head"

mkdir -p /run/portal-app/imapsync /run/portal-import
chown -R portal-app:portal-app /run/portal-app /run/portal-import

# RuntimeDirectoryMode=0750 (portal-gunicorn.service.tmpl) oznacza, że tylko
# grupa portal-app może wejść do /run/portal-app — nginx działa jako
# osobny user "nginx" (templates/nginx/nginx.conf.tmpl), więc bez dopisania
# go do tej grupy dostaje zwykłe DAC "Permission denied" przy connect() do
# gunicorn.sock, niezależnie od etykiety SELinux (patrz fcontext niżej —
# to dwa NIEZALEŻNE warunki, oba muszą być spełnione).
if id nginx >/dev/null 2>&1; then
    usermod -aG portal-app nginx
fi

# nginx (domena SELinux httpd_t) musi się połączyć z gniazdem Unix Gunicorna
# w /run/portal-app/ — bez etykiety httpd_var_run_t dostaje AVC denied na
# connectto (ten sam rodzaj problemu co /run/nginx.pid w scripts/vm1/30-nginx.sh).
# Reguła jest trwała (semanage), więc systemd sam nada właściwą etykietę przy
# każdym tworzeniu RuntimeDirectory=portal-app (katalog jest na tmpfs).
if command -v semanage >/dev/null 2>&1; then
    semanage fcontext -a -t httpd_var_run_t "/run/portal-app(/.*)?" 2>/dev/null \
        || semanage fcontext -m -t httpd_var_run_t "/run/portal-app(/.*)?" 2>/dev/null || true
fi

# Etykieta pliku (wyżej) NIE wystarcza — SELinux osobno sprawdza "connectto"
# między DOMENAMI procesów dla klasy unix_stream_socket: httpd_t (nginx) ->
# unconfined_service_t (Gunicorn, generyczna domena usług systemd). Bez tego
# modułu połączenie kończy się "Permission denied" mimo poprawnych etykiet
# pliku i uprawnień DAC — potwierdzone wprost na działającym środowisku
# (AVC: denied { connectto }, tclass=unix_stream_socket).
if command -v checkmodule >/dev/null 2>&1 && command -v semodule_package >/dev/null 2>&1; then
    SELINUX_BUILD_DIR="$(mktemp -d)"
    checkmodule -M -m -o "$SELINUX_BUILD_DIR/portal_nginx_gunicorn.mod" \
        "$REPO_ROOT/templates/selinux/portal_nginx_gunicorn.te"
    semodule_package -o "$SELINUX_BUILD_DIR/portal_nginx_gunicorn.pp" \
        -m "$SELINUX_BUILD_DIR/portal_nginx_gunicorn.mod"
    semodule -i "$SELINUX_BUILD_DIR/portal_nginx_gunicorn.pp"
    rm -rf "$SELINUX_BUILD_DIR"
    log_info "Zainstalowano moduł SELinux portal_nginx_gunicorn (connectto httpd_t -> unconfined_service_t)."
else
    log_warn "Brak checkmodule/semodule_package (pakiet checkpolicy) — nginx może nie połączyć się z Gunicornem pod SELinux enforcing."
fi

# --- systemd units -----------------------------------------------------------------
export PGDG_MAJOR_VERSION
render_template "$REPO_ROOT/templates/systemd/portal-gunicorn.service.tmpl" /etc/systemd/system/portal-gunicorn.service '$PGDG_MAJOR_VERSION'
render_template "$REPO_ROOT/templates/systemd/portal-worker.service.tmpl" /etc/systemd/system/portal-worker.service '$PGDG_MAJOR_VERSION'
render_template "$REPO_ROOT/templates/systemd/portal-scheduler.service.tmpl" /etc/systemd/system/portal-scheduler.service '$PGDG_MAJOR_VERSION'
render_template "$REPO_ROOT/templates/systemd/portal-scheduler.timer.tmpl" /etc/systemd/system/portal-scheduler.timer
render_template "$REPO_ROOT/templates/systemd/portal-audit-verify.service.tmpl" /etc/systemd/system/portal-audit-verify.service '$PGDG_MAJOR_VERSION'
render_template "$REPO_ROOT/templates/systemd/portal-audit-verify.timer.tmpl" /etc/systemd/system/portal-audit-verify.timer
render_template "$REPO_ROOT/templates/systemd/portal-environment-check.service.tmpl" /etc/systemd/system/portal-environment-check.service '$PGDG_MAJOR_VERSION'
render_template "$REPO_ROOT/templates/systemd/portal-environment-check.timer.tmpl" /etc/systemd/system/portal-environment-check.timer
systemctl daemon-reload
systemctl enable portal-gunicorn portal-worker portal-scheduler.timer portal-audit-verify.timer portal-environment-check.timer
systemctl start portal-scheduler.timer portal-audit-verify.timer portal-environment-check.timer
# restart (nie enable --now): procesy Python wczytują kod do pamięci przy
# starcie, a systemd czyta unit przy (re)starcie — po rsyncu nowego kodu i
# re-renderze unitów działające procesy trzeba faktycznie zrestartować, żeby
# zmiany weszły w życie (enable --now nie rusza już działającej usługi).
systemctl restart portal-gunicorn portal-worker

nginx -t && systemctl reload nginx || log_warn "nginx -t nie przeszło po starcie portal-gunicorn — sprawdź konfigurację."

log_info "portal_app uruchomiony (gunicorn na /run/portal-app/gunicorn.sock). Kreator pierwszego uruchomienia: https://${VM1_HOSTNAME}/admin/setup"
mark_step_done "$STEP_NAME"
