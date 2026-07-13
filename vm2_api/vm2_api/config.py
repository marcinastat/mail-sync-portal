import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    allowed_client_ip: str
    db_dsn: str
    listen_port: int = 8443
    tls_cert: Path = Path("/etc/portal/vm2-api/server.crt")
    tls_key: Path = Path("/etc/portal/vm2-api/server.key")
    tls_ca: Path = Path("/etc/portal/vm2-api/ca.crt")
    system_update_confirm_ttl_seconds: int = 600
    maildir_base: Path = Path("/var/mail/vhosts")
    clamd_socket: Path = Path("/run/clamd.scan/clamd.sock")


@lru_cache
def get_settings() -> Settings:
    db_pass_file = Path("/etc/portal/secrets/vm2-mail-db.pass")
    db_pass = db_pass_file.read_text().strip()
    return Settings(
        allowed_client_ip=os.environ["VM2_API_ALLOWED_CLIENT_IP"],
        db_dsn=f"host=127.0.0.1 dbname=mail_db user=mail_app password={db_pass}",
        listen_port=int(os.environ.get("VM2_API_PORT", "8443")),
    )
