#!/usr/bin/env bash
# VM2 — krok 20: PostgreSQL z repo PGDG, baza mail_db + rola aplikacyjna, schemat.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm2-20-postgresql"
require_root
step_done "$STEP_NAME"
load_install_conf

REPO_ROOT="$(repo_root)"
PG_VER="${PGDG_MAJOR_VERSION:?PGDG_MAJOR_VERSION musi być ustawione}"
PG_BIN_DIR="/usr/pgsql-${PG_VER}/bin"
SECRETS_DIR="/etc/portal/secrets"
DB_PASS_FILE="$SECRETS_DIR/vm2-mail-db.pass"

if ! rpm -q pgdg-redhat-repo >/dev/null 2>&1; then
    log_info "Dodaję repozytorium PGDG..."
    dnf install -y "https://download.postgresql.org/pub/repos/yum/reporpms/EL-10-x86_64/pgdg-redhat-repo-latest.noarch.rpm"
fi

dnf -qy module disable postgresql 2>/dev/null || true
pkg_install_idempotent "postgresql${PG_VER}-server" "postgresql${PG_VER}-contrib"

if [[ ! -f "/var/lib/pgsql/${PG_VER}/data/PG_VERSION" ]]; then
    log_info "Inicjalizuję klaster PostgreSQL ${PG_VER}..."
    "$PG_BIN_DIR/postgresql-${PG_VER}-setup" initdb
fi

PG_DATA_DIR="/var/lib/pgsql/${PG_VER}/data"
sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost'/" "$PG_DATA_DIR/postgresql.conf"

if ! grep -q "^host    mail_db " "$PG_DATA_DIR/pg_hba.conf" 2>/dev/null; then
    echo "host    mail_db    mail_app    127.0.0.1/32    md5" >> "$PG_DATA_DIR/pg_hba.conf"
fi

systemctl enable --now "postgresql-${PG_VER}"

ensure_secret_file "$DB_PASS_FILE" 32
chown root:root "$DB_PASS_FILE"
DB_PASS="$(cat "$DB_PASS_FILE")"

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mail_app') THEN
        CREATE ROLE mail_app LOGIN PASSWORD '${DB_PASS}';
    ELSE
        ALTER ROLE mail_app WITH PASSWORD '${DB_PASS}';
    END IF;
END
\$\$;
SQL

sudo -u postgres psql -v ON_ERROR_STOP=1 -tc "SELECT 1 FROM pg_database WHERE datname = 'mail_db'" | grep -q 1 \
    || sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE mail_db OWNER mail_app;"

sudo -u postgres psql -v ON_ERROR_STOP=1 -d mail_db -f "$REPO_ROOT/sql/vm2/001_schema.sql"
sudo -u postgres psql -v ON_ERROR_STOP=1 -d mail_db -v app_role=mail_app -f "$REPO_ROOT/sql/vm2/002_grants.sql"

systemctl reload "postgresql-${PG_VER}"

pkg_install_idempotent python3-dnf-plugin-versionlock
dnf versionlock add "postgresql${PG_VER}-server" "postgresql${PG_VER}" "postgresql${PG_VER}-contrib" 2>/dev/null || true

log_info "PostgreSQL ${PG_VER} + mail_db gotowe."
mark_step_done "$STEP_NAME"
