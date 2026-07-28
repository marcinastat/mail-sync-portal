"""Klient acme-dns: rejestracja konta + generowanie instrukcji DNS.

acme-dns pozwala na DNS-01 nawet gdy serwer jest za firewallem: VM1 aktualizuje
rekord TXT challenge WYŁĄCZNIE w acme-dns (username/password z rejestracji), a w
prawdziwej strefie klienta wpisuje się RAZ, ręcznie, CNAME
`_acme-challenge.<host>` -> fulldomain konta acme-dns. Dzięki temu klucz do
prawdziwego DNS (OVH itd.) nigdy nie trafia na serwer, a challenge działa bez
otwierania czegokolwiek do internetu na VM1.
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
from cryptography import x509
from sqlalchemy.orm import Session

from ..models import AcmeDnsConfig
from . import credential_crypto

# Odszyfrowane konto acme-dns dla auth-hooka certbota. Musi być w katalogu, do
# którego portal-app może PISAĆ (DAC): /var/lib/portal-app jest jego własnością.
# /etc/portal/secrets jest 0711 root -> portal-app nie utworzyłby tam pliku.
# Root (certbot/auth-hook przez systemd-run) i tak odczyta plik 0600. MUSI być
# zgodne z CREDS w certbot-acmedns.sh i acmedns-auth-hook.sh.
CREDS_FILE = Path("/var/lib/portal-app/acmedns.json")
ACTIVE_CERT = Path("/etc/portal/tls/active/fullchain.pem")
_ISSUE_HELPER = "/usr/local/sbin/certbot-acmedns.sh"


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
    write_creds_file(cfg)  # plik dla auth-hooka certbota (używany przy wystawianiu)
    return cfg


def write_creds_file(cfg: AcmeDnsConfig) -> None:
    """Zapisuje ODSZYFROWANE konto acme-dns do pliku 0600 czytanego przez
    auth-hook certbota (jako root, poza sandboxem). Wołane przy rejestracji i
    tuż przed wystawieniem certu, żeby plik zawsze odpowiadał bazie."""
    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "server": cfg.acme_dns_server,
        "hostname": cfg.hostname,
        "username": cfg.username,
        "password": credential_crypto.decrypt_password(cfg.password_encrypted),
        "subdomain": cfg.subdomain,
        "fulldomain": cfg.fulldomain,
    }
    CREDS_FILE.write_text(json.dumps(data), encoding="utf-8")
    CREDS_FILE.chmod(0o600)


def status(cfg: AcmeDnsConfig) -> dict:
    """Lekki status pod kartę TLS: osiągalność acme-dns, gotowość DNS (CNAME ->
    acme-dns przez dig, jeśli dostępny) oraz aktualny aktywny certyfikat."""
    out: dict = {
        "acme_reachable": None,
        "dns_ready": None,
        "dns_note": "",
        "cert_issuer": None,
        "cert_days_left": None,
        "cert_is_letsencrypt": False,
        "checked_at": datetime.now(timezone.utc),
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            client.get(cfg.acme_dns_server)  # jakakolwiek odpowiedź = osiągalny
        out["acme_reachable"] = True
    except httpx.HTTPError:
        out["acme_reachable"] = False

    dig = shutil.which("dig")
    if not dig:
        out["dns_note"] = "Nie sprawdzono automatycznie (brak narzędzia 'dig' — dnf install bind-utils)."
    else:
        try:
            res = subprocess.run(
                [dig, "+short", "TXT", f"_acme-challenge.{cfg.hostname}"],
                capture_output=True, text=True, timeout=10,
            )
            out["dns_ready"] = bool(res.stdout.strip())
            out["dns_note"] = (
                "CNAME rozwiązuje się do acme-dns (rekord TXT obecny) — można wystawiać certyfikat."
                if out["dns_ready"]
                else "Brak rekordu TXT — dodaj CNAME w DNS i poczekaj na propagację."
            )
        except Exception:
            out["dns_note"] = "Nie udało się sprawdzić DNS (dig)."

    if ACTIVE_CERT.exists():
        try:
            cert = x509.load_pem_x509_certificate(ACTIVE_CERT.read_bytes())
            issuer = cert.issuer.rfc4514_string()
            out["cert_issuer"] = issuer
            out["cert_days_left"] = (cert.not_valid_after_utc - datetime.now(timezone.utc)).days
            out["cert_is_letsencrypt"] = "let's encrypt" in issuer.lower()
        except Exception:
            pass
    return out


def issue_certificate(cfg: AcmeDnsConfig) -> tuple[bool, str]:
    """Wystawia certyfikat Let's Encrypt przez acme-dns i przełącza nginx —
    przez root-helper (systemd-run escape, bo certbot pisze /etc/letsencrypt, a
    usługa działa w sandboxie ProtectSystem=full). Zwraca (ok, komunikat)."""
    try:
        write_creds_file(cfg)  # świeże konto dla auth-hooka
    except OSError as exc:
        return False, f"Nie udało się zapisać konta acme-dns dla certbota: {exc}"
    try:
        res = subprocess.run(
            ["/usr/bin/sudo", "-n", _ISSUE_HELPER],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return False, "Wystawianie certyfikatu przekroczyło limit czasu (180 s)."
    ok = res.returncode == 0
    msg = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
    return ok, msg[-2000:] if msg else ("OK" if ok else "Nieznany błąd certbota.")


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
