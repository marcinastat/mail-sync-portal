import subprocess
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

STAGE_DIR = Path("/var/lib/portal-app/tls-stage")


class TlsValidationError(RuntimeError):
    pass


def validate_and_stage(cert_pem: str, key_pem: str) -> None:
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    except Exception as exc:
        raise TlsValidationError(f"Nieprawidłowy certyfikat: {exc}") from exc
    try:
        key = serialization.load_pem_private_key(key_pem.encode("utf-8"), password=None)
    except Exception as exc:
        raise TlsValidationError(f"Nieprawidłowy klucz prywatny: {exc}") from exc

    if cert.public_key().public_numbers() != key.public_key().public_numbers():
        raise TlsValidationError("Certyfikat i klucz prywatny nie pasują do siebie.")

    now = datetime.now(timezone.utc)
    if cert.not_valid_after_utc < now:
        raise TlsValidationError(f"Certyfikat już wygasł ({cert.not_valid_after_utc}).")
    if cert.not_valid_before_utc > now:
        raise TlsValidationError(f"Certyfikat jeszcze nie jest ważny (od {cert.not_valid_before_utc}).")

    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    (STAGE_DIR / "fullchain.pem").write_text(cert_pem, encoding="utf-8")
    (STAGE_DIR / "privkey.pem").write_text(key_pem, encoding="utf-8")


def switch_mode(mode: str) -> None:
    result = subprocess.run(
        ["/usr/bin/sudo", "-n", "/opt/portal-app/bin/apply-tls.sh", mode],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise TlsValidationError(f"Przełączenie trybu TLS nie powiodło się: {result.stderr}")
