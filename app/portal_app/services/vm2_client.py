import httpx

from ..models import Vm2Connection


class Vm2ApiError(RuntimeError):
    pass


def _client(conn: Vm2Connection) -> httpx.Client:
    base_url = f"https://{conn.vm2_host}:{conn.vm2_api_port}"
    return httpx.Client(
        base_url=base_url,
        cert=(conn.client_cert_path, conn.client_key_path),
        verify=conn.ca_cert_path,
        timeout=15.0,
    )


def check_health(conn: Vm2Connection) -> dict:
    try:
        with _client(conn) as client:
            resp = client.get("/health")
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        raise Vm2ApiError(str(exc)) from exc


def create_domain(conn: Vm2Connection, name: str) -> dict:
    with _client(conn) as client:
        resp = client.post("/domains", json={"name": name})
        resp.raise_for_status()
        return resp.json()


def create_mailbox(conn: Vm2Connection, *, domain: str, local_part: str, password: str, quota_mb: int = 0) -> dict:
    with _client(conn) as client:
        resp = client.post(
            "/mailboxes",
            json={"domain": domain, "local_part": local_part, "password": password, "quota_mb": quota_mb},
        )
        resp.raise_for_status()
        return resp.json()


def reset_mailbox_password(conn: Vm2Connection, mailbox_id: str, new_password: str) -> dict:
    with _client(conn) as client:
        resp = client.post(f"/mailboxes/{mailbox_id}/reset-password", json={"new_password": new_password})
        resp.raise_for_status()
        return resp.json()


def get_mailbox_status(conn: Vm2Connection, mailbox_id: str) -> dict:
    with _client(conn) as client:
        resp = client.get(f"/mailboxes/{mailbox_id}/status")
        resp.raise_for_status()
        return resp.json()


def get_mailbox_quota(conn: Vm2Connection, mailbox_id: str) -> dict:
    with _client(conn) as client:
        resp = client.get(f"/mailboxes/{mailbox_id}/quota")
        resp.raise_for_status()
        return resp.json()


def update_mailbox_quota(conn: Vm2Connection, mailbox_id: str, quota_mb: int) -> dict:
    with _client(conn) as client:
        resp = client.patch(f"/mailboxes/{mailbox_id}", json={"quota_mb": quota_mb})
        resp.raise_for_status()
        return resp.json()


def av_scan(conn: Vm2Connection, *, domain: str, local_part: str) -> dict:
    with _client(conn) as client:
        resp = client.post("/av/scan", json={"domain": domain, "local_part": local_part})
        resp.raise_for_status()
        return resp.json()


def av_status(conn: Vm2Connection) -> dict:
    with _client(conn) as client:
        resp = client.get("/av/status")
        resp.raise_for_status()
        return resp.json()


def system_update(conn: Vm2Connection) -> dict:
    with _client(conn) as client:
        resp = client.post("/system/update")
        resp.raise_for_status()
        return resp.json()


def disk_usage(conn: Vm2Connection) -> dict:
    with _client(conn) as client:
        resp = client.get("/system/disk-usage")
        resp.raise_for_status()
        return resp.json()


def system_reboot(conn: Vm2Connection, confirm_token: str) -> dict:
    with _client(conn) as client:
        resp = client.post("/system/reboot", json={"confirm_token": confirm_token})
        resp.raise_for_status()
        return resp.json()
