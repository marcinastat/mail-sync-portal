from cryptography.fernet import Fernet

from ..config import get_settings


def _fernet() -> Fernet:
    return Fernet(get_settings().credential_encryption_key)


def encrypt_password(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_password(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
