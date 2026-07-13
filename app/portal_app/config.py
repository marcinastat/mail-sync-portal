import os
from functools import lru_cache
from pathlib import Path


def _read_credential(name: str) -> bytes:
    """Czyta sekret dostarczony przez systemd LoadCredentialEncrypted= (patrz
    templates/systemd/portal-*.service.tmpl). $CREDENTIALS_DIRECTORY istnieje
    tylko w trakcie działania usługi, w pamięci prywatnej danego unitu."""
    creds_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not creds_dir:
        raise RuntimeError(
            f"Brak CREDENTIALS_DIRECTORY — proces musi być uruchomiony przez systemd "
            f"z LoadCredentialEncrypted={name}:... (patrz docs/technical/architecture.md)."
        )
    return (Path(creds_dir) / name).read_bytes()


@lru_cache
def get_db_dsn() -> str:
    db_pass = Path("/etc/portal/secrets/vm1-portal-db.pass").read_text().strip()
    return f"postgresql+psycopg://portal_app:{db_pass}@127.0.0.1/portal_db"


@lru_cache
def get_secret_key() -> str:
    return _read_credential("portal-secret-key").decode("utf-8").strip()


@lru_cache
def get_credential_encryption_key() -> bytes:
    return _read_credential("portal-credential-key").strip()


VM2_CLIENT_CERT = Path("/etc/portal/vm1-client/client.crt")
VM2_CLIENT_KEY = Path("/etc/portal/vm1-client/client.key")
VM2_CA_CERT = Path("/etc/portal/vm1-client/ca.crt")
IMPORT_TMP_DIR = Path("/run/portal-import")
IMAPSYNC_LOG_DIR = Path("/var/log/portal/imapsync")


class Settings:
    """Kompatybilność z resztą kodu, który woli jeden obiekt settings — pola
    wymagające sekretów są leniwe (property), więc konstrukcja obiektu nie
    wymaga jeszcze $CREDENTIALS_DIRECTORY (potrzebne np. dla Alembica, który
    używa tylko db_dsn)."""

    db_dsn = property(lambda self: get_db_dsn())
    secret_key = property(lambda self: get_secret_key())
    credential_encryption_key = property(lambda self: get_credential_encryption_key())
    vm2_client_cert = VM2_CLIENT_CERT
    vm2_client_key = VM2_CLIENT_KEY
    vm2_ca_cert = VM2_CA_CERT
    import_tmp_dir = IMPORT_TMP_DIR
    imapsync_log_dir = IMAPSYNC_LOG_DIR


@lru_cache
def get_settings() -> Settings:
    return Settings()
