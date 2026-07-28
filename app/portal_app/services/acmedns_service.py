"""Klient acme-dns: rejestracja konta + generowanie instrukcji DNS.

acme-dns pozwala na DNS-01 nawet gdy serwer jest za firewallem: VM1 aktualizuje
rekord TXT challenge WYŁĄCZNIE w acme-dns (username/password z rejestracji), a w
prawdziwej strefie klienta wpisuje się RAZ, ręcznie, CNAME
`_acme-challenge.<host>` -> fulldomain konta acme-dns. Dzięki temu klucz do
prawdziwego DNS (OVH itd.) nigdy nie trafia na serwer, a challenge działa bez
otwierania czegokolwiek do internetu na VM1.
"""

import httpx
from sqlalchemy.orm import Session

from ..models import AcmeDnsConfig
from . import credential_crypto


class AcmeDnsError(RuntimeError):
    pass


def get_config(db: Session) -> AcmeDnsConfig | None:
    return db.query(AcmeDnsConfig).first()


def register(
    db: Session,
    *,
    server: str,
    hostname: str,
    a_record_ip: str | None = None,
    allowfrom: list[str] | None = None,
) -> AcmeDnsConfig:
    """Rejestruje NOWE konto w acme-dns (POST /register) i zapisuje je (hasło
    szyfrowane Fernet). Nadpisuje ewentualną poprzednią konfigurację — po
    ponownej rejestracji trzeba zaktualizować CNAME w DNS (zmienia się
    fulldomain)."""
    server = (server or "").strip().rstrip("/")
    hostname = (hostname or "").strip().rstrip(".")
    if not server.startswith(("http://", "https://")):
        raise AcmeDnsError("Adres acme-dns musi zaczynać się od http:// lub https://.")
    if not hostname or "." not in hostname:
        raise AcmeDnsError("Podaj pełną nazwę hosta (FQDN), np. poczta.example.com.")

    payload: dict = {}
    if allowfrom:
        # Ograniczenie: tylko te CIDR-y mogą aktualizować TXT (np. egress VM1).
        payload["allowfrom"] = allowfrom

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(f"{server}/register", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise AcmeDnsError(f"Rejestracja w acme-dns ({server}) nie powiodła się: {exc}") from exc

    for field in ("username", "password", "fulldomain", "subdomain"):
        if not data.get(field):
            raise AcmeDnsError(f"Odpowiedź acme-dns nie zawiera pola '{field}'.")

    cfg = get_config(db) or AcmeDnsConfig()
    cfg.acme_dns_server = server
    cfg.hostname = hostname
    cfg.a_record_ip = (a_record_ip or "").strip() or None
    cfg.username = data["username"]
    cfg.password_encrypted = credential_crypto.encrypt_password(data["password"])
    cfg.subdomain = data["subdomain"]
    cfg.fulldomain = data["fulldomain"]
    cfg.allowfrom = ",".join(allowfrom) if allowfrom else None
    from datetime import datetime, timezone
    cfg.registered_at = datetime.now(timezone.utc)
    db.add(cfg)
    db.flush()
    return cfg


def dns_instructions(cfg: AcmeDnsConfig) -> list[dict]:
    """Rekordy do dodania w PRAWDZIWEJ strefie DNS klienta (jednorazowo)."""
    records = [
        {
            "type": "CNAME",
            "name": f"_acme-challenge.{cfg.hostname}",
            "value": f"{cfg.fulldomain}.",
            "note": "Deleguje walidację DNS-01 do acme-dns. Bez tego certyfikat się NIE wystawi.",
        }
    ]
    if cfg.a_record_ip:
        records.append(
            {
                "type": "A",
                "name": cfg.hostname,
                "value": cfg.a_record_ip,
                "note": "Adres, pod którym klienci mają rozwiązywać ten host (może być wewnętrzny/VPN).",
            }
        )
    return records
