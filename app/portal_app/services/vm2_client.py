import ssl

import httpx

from ..models import Vm2Connection


class Vm2ApiError(RuntimeError):
    pass


def _client(conn: Vm2Connection, timeout: float = 15.0) -> httpx.Client:
    base_url = f"https://{conn.vm2_host}:{conn.vm2_api_port}"
    return httpx.Client(
        base_url=base_url,
        cert=(conn.client_cert_path, conn.client_key_path),
        verify=conn.ca_cert_path,
        timeout=timeout,
    )


def _request(conn: Vm2Connection, method: str, path: str, *, timeout: float = 15.0, **kwargs) -> dict:
    """Jedno miejsce, które KAŻDY błąd transportu/HTTP (VM2 wyłączona,
    connection refused, timeout, 5xx) zamienia na Vm2ApiError. Bez tego surowe
    httpx.ConnectError wyciekało z disk_usage()/av_status() i wywalało dashboard
    na 500, gdy VM2 była zgaszona (wołający łapał tylko Vm2ApiError)."""
    try:
        with _client(conn, timeout=timeout) as client:
            resp = client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise Vm2ApiError(str(exc)) from exc
    except (OSError, ssl.SSLError) as exc:
        # Budowa klienta mTLS (httpx.Client w _client) pada JESZCZE PRZED
        # wysłaniem żądania, gdy pliki cert/klucz/CA nie istnieją lub są
        # nieczytelne — httpx rzuca wtedy OSError/SSLError, NIE httpx.HTTPError,
        # więc bez tego wyciekało jako surowe 500 (np. w kreatorze first-run,
        # gdy nie pobrano jeszcze certów skryptem fetch-vm2-client-cert.sh).
        raise Vm2ApiError(
            f"Błąd certyfikatów mTLS do VM2 ({exc}). Upewnij się, że na VM1 "
            "pobrano certyfikat kliencki i CA: scripts/vm1/fetch-vm2-client-cert.sh."
        ) from exc


def check_health(conn: Vm2Connection) -> dict:
    return _request(conn, "GET", "/health")


def dashboard_snapshot(conn: Vm2Connection, timeout: float = 15.0) -> dict:
    """Trzy odczyty dashboardu (dysk + AV + wykrycia) na JEDNYM połączeniu mTLS.
    Osobne wywołania (_request) otwierały 3 klienty = 3 handshake'i TLS, co przy
    renderze synchronicznym dawało kilka sekund. Tu keep-alive jednego klienta
    zdejmuje handshake z 2. i 3. żądania. Każdy odczyt jest niezależnie
    best-effort (None przy błędzie) — dashboard i tak pokazuje resztę."""
    out: dict = {"disk_usage": None, "av": None, "findings": None}
    calls = [
        ("disk_usage", "/system/disk-usage", None),
        ("av", "/av/status", None),
        ("findings", "/av/findings", {"since_id": 0, "limit": 8}),
    ]
    try:
        with _client(conn, timeout=timeout) as client:
            for key, path, params in calls:
                try:
                    resp = client.request("GET", path, params=params)
                    resp.raise_for_status()
                    out[key] = resp.json()
                except httpx.HTTPError:
                    out[key] = None  # ten jeden odczyt się nie udał — reszta leci dalej
    except (httpx.HTTPError, OSError, ssl.SSLError):
        pass  # VM2 niedostępna / brak certów mTLS — cała trójka None
    return out


def create_domain(conn: Vm2Connection, name: str) -> dict:
    return _request(conn, "POST", "/domains", json={"name": name})


def add_domain_alias(conn: Vm2Connection, *, domain: str, alias: str) -> dict:
    """Dopnij domenę logowania (alias) do domeny kanonicznej na VM2 — po tym
    login user@alias trafia do skrzynki user@domain (Dovecot)."""
    return _request(conn, "POST", f"/domains/{domain}/aliases", json={"alias": alias})


def delete_domain_alias(conn: Vm2Connection, *, domain: str, alias: str) -> dict:
    return _request(conn, "DELETE", f"/domains/{domain}/aliases/{alias}")


def create_mailbox(conn: Vm2Connection, *, domain: str, local_part: str, password: str, quota_mb: int = 0) -> dict:
    return _request(
        conn, "POST", "/mailboxes",
        json={"domain": domain, "local_part": local_part, "password": password, "quota_mb": quota_mb},
    )


def reset_mailbox_password(conn: Vm2Connection, mailbox_id: str, new_password: str) -> dict:
    return _request(conn, "POST", f"/mailboxes/{mailbox_id}/reset-password", json={"new_password": new_password})


def delete_mailbox(conn: Vm2Connection, mailbox_id: str) -> dict:
    """Trwałe usunięcie skrzynki docelowej na VM2 (rekord + maildir). Źródła
    nie dotyka. Wołane po potwierdzeniu w panelu (routers/mailboxes.py)."""
    return _request(conn, "DELETE", f"/mailboxes/{mailbox_id}")


def get_mailbox_status(conn: Vm2Connection, mailbox_id: str) -> dict:
    return _request(conn, "GET", f"/mailboxes/{mailbox_id}/status")


def get_mailbox_quota(conn: Vm2Connection, mailbox_id: str) -> dict:
    return _request(conn, "GET", f"/mailboxes/{mailbox_id}/quota")


def update_mailbox_quota(conn: Vm2Connection, mailbox_id: str, quota_mb: int) -> dict:
    return _request(conn, "PATCH", f"/mailboxes/{mailbox_id}", json={"quota_mb": quota_mb})


def av_scan(conn: Vm2Connection, *, domain: str, local_part: str) -> dict:
    return _request(conn, "POST", "/av/scan", json={"domain": domain, "local_part": local_part})


def av_status(conn: Vm2Connection) -> dict:
    return _request(conn, "GET", "/av/status")


def av_findings(conn: Vm2Connection, since_id: int = 0, limit: int = 100) -> dict:
    return _request(conn, "GET", "/av/findings", params={"since_id": since_id, "limit": limit})


def get_system_updates(conn: Vm2Connection) -> dict:
    # check-update może pobierać metadane — dłuższy timeout niż domyślny.
    return _request(conn, "GET", "/system/updates", timeout=180.0)


def system_update(conn: Vm2Connection, security_only: bool = True) -> dict:
    # Wołane z workera (nie z żądania web) — dnf update potrafi trwać, stąd
    # długi timeout. Worker nie ma limitu gunicorna, więc może czekać.
    return _request(conn, "POST", "/system/update", json={"security_only": security_only}, timeout=1800.0)


def disk_usage(conn: Vm2Connection) -> dict:
    return _request(conn, "GET", "/system/disk-usage")


def set_scan_schedule(conn: Vm2Connection, payload: dict) -> dict:
    return _request(conn, "POST", "/system/scan-schedule", json=payload, timeout=40.0)


def system_reboot(conn: Vm2Connection, confirm_token: str | None = None) -> dict:
    body = {"confirm_token": confirm_token} if confirm_token else {}
    return _request(conn, "POST", "/system/reboot", json=body)
