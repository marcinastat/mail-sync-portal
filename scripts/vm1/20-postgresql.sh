#!/usr/bin/env bash
# VM1 — krok 20: PostgreSQL z repo PGDG — jedna instancja, dwie bazy:
# roundcube_db (Roundcube) i portal_db (aplikacja /admin), osobne role.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STEP_NAME="vm1-20-postgresql"
require_root
step_done "$STEP_NAME"
load_install_conf

PG_VER="${PGDG_MAJOR_VERSION:?PGDG_MAJOR_VERSION musi być ustawione}"
PG_BIN_DIR="/usr/pgsql-${PG_VER}/bin"
PG_DATA_DIR="/var/lib/pgsql/${PG_VER}/data"
SECRETS_DIR="/etc/portal/secrets"

if ! rpm -q pgdg-redhat-repo >/dev/null 2>&1; then
    log_info "Dodaję repozytorium PGDG..."
    dnf install -y "https://download.postgresql.org/pub/repos/yum/reporpms/EL-10-x86_64/pgdg-redhat-repo-latest.noarch.rpm"
fi

dnf -qy module disable postgresql 2>/dev/null || true
pkg_install_idempotent "postgresql${PG_VER}-server" "postgresql${PG_VER}-contrib"

if [[ ! -f "$PG_DATA_DIR/PG_VERSION" ]]; then
    log_info "Inicjalizuję klaster PostgreSQL ${PG_VER}..."
    "$PG_BIN_DIR/postgresql-${PG_VER}-setup" initdb
fi

sed -i "s/^#listen_addresses.*/listen_addresses = 'localhost'/" "$PG_DATA_DIR/postgresql.conf"

for role_line in \
    "host    roundcube_db    roundcube_app    127.0.0.1/32    md5" \
    "host    portal_db       portal_app       127.0.0.1/32    md5"
do
    grep -qF "$role_line" "$PG_DATA_DIR/pg_hba.conf" 2>/dev/null || echo "$role_line" >> "$PG_DATA_DIR/pg_hba.conf"
done

systemctl enable --now "postgresql-${PG_VER}"

create_role_and_db() {
    local role="$1" db="$2" pass_file="$3"
    ensure_secret_file "$pass_file" 32
    local pass
    pass="$(cat "$pass_file")"
    sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${role}') THEN
        CREATE ROLE ${role} LOGIN PASSWORD '${pass}';
    ELSE
        ALTER ROLE ${role} WITH PASSWORD '${pass}';
    END IF;
END
\$\$;
SQL
    sudo -u postgres psql -v ON_ERROR_STOP=1 -tc "SELECT 1 FROM pg_database WHERE datname = '${db}'" | grep -q 1 \
        || sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${db} OWNER ${role};"
}

create_role_and_db roundcube_app roundcube_db "$SECRETS_DIR/vm1-roundcube-db.pass"
create_role_and_db portal_app portal_db "$SECRETS_DIR/vm1-portal-db.pass"

systemctl reload "postgresql-${PG_VER}"

log_info "PostgreSQL ${PG_VER} gotowe: roundcube_db + portal_db (osobne role, schematy stosowane w kolejnych fazach)."
mark_step_done "$STEP_NAME"
