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

pkg_install_idempotent python3.12 python3.12-devel gcc sudo libffi-devel

if ! id portal-app >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /sbin/nologin --create-home portal-app
fi

mkdir -p "$APP_DIR"
rsync -a --delete --exclude '__pycache__' --exclude '.venv' --exclude 'tests' "$REPO_ROOT/app/" "$APP_DIR/"
chown -R portal-app:portal-app "$APP_DIR"

if [[ ! -d "$APP_DIR/venv" ]]; then
    sudo -u portal-app python3.12 -m venv "$APP_DIR/venv"
fi
sudo -u portal-app "$APP_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u portal-app "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

mkdir -p /var/log/portal /var/log/portal/imapsync /var/lib/portal-app /var/lib/portal-app/branding-stage /run/portal-import
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
render_template "$REPO_ROOT/templates/sudoers/portal-app.tmpl" /etc/sudoers.d/portal-app
chmod 0440 /etc/sudoers.d/portal-app
visudo -cf /etc/sudoers.d/portal-app || die "Wygenerowany plik sudoers jest niepoprawny składniowo — przerywam."

# --- Migracje bazy -------------------------------------------------------------
sudo -u portal-app bash -c "cd '$APP_DIR' && venv/bin/alembic upgrade head"

# --- systemd unit ----------------------------------------------------------------
export PGDG_MAJOR_VERSION
render_template "$REPO_ROOT/templates/systemd/portal-gunicorn.service.tmpl" /etc/systemd/system/portal-gunicorn.service '$PGDG_MAJOR_VERSION'
systemctl daemon-reload
systemctl enable --now portal-gunicorn

nginx -t && systemctl reload nginx || log_warn "nginx -t nie przeszło po starcie portal-gunicorn — sprawdź konfigurację."

log_info "portal_app uruchomiony (gunicorn na /run/portal-app/gunicorn.sock). Kreator pierwszego uruchomienia: https://${VM1_HOSTNAME}/admin/setup"
mark_step_done "$STEP_NAME"
