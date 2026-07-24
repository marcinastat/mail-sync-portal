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


def check_health(conn: Vm2Connection) -> dict:
    return _request(conn, "GET", "/health")


def create_domain(conn: Vm2Connection, name: str) -> dict:
    return _request(conn, "POST", "/domains", json={"name": name})


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


def get_system_updates(conn: Vm2Connection) -> dict:
    # check-update może pobierać metadane — dłuższy timeout niż domyślny.
    return _request(conn, "GET", "/system/updates", timeout=180.0)


def system_update(conn: Vm2Connection, security_only: bool = True) -> dict:
    # Wołane z workera (nie z żądania web) — dnf update potrafi trwać, stąd
    # długi timeout. Worker nie ma limitu gunicorna, więc może czekać.
    return _request(conn, "POST", "/system/update", json={"security_only": security_only}, timeout=1800.0)


def disk_usage(conn: Vm2Connection) -> dict:
    return _request(conn, "GET", "/system/disk-usage")


def system_reboot(conn: Vm2Connection, confirm_token: str | None = None) -> dict:
    body = {"confirm_token": confirm_token} if confirm_token else {}
    return _request(conn, "POST", "/system/reboot", json=body)
