import io
import secrets

import pyotp
import qrcode
from passlib.hash import argon2

from .credential_crypto import decrypt_password, encrypt_password


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_qr_png(secret: str, account_name: str, issuer: str = "Portal Poczty") -> bytes:
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def verify_code(secret_encrypted: str, code: str) -> bool:
    secret = decrypt_password(secret_encrypted)
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def encrypt_secret(secret: str) -> str:
    return encrypt_password(secret)


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [secrets.token_hex(5) for _ in range(count)]


def hash_recovery_codes(codes: list[str]) -> list[str]:
    return [argon2.hash(code) for code in codes]


def verify_recovery_code(hashed_codes: list[str], candidate: str) -> int | None:
    """Zwraca indeks pasującego kodu (do usunięcia po użyciu) albo None."""
    for index, hashed in enumerate(hashed_codes):
        if argon2.verify(candidate, hashed):
            return index
    return None
