import psycopg
from fastapi import APIRouter, Depends, Request, status

from ..audit import insert_audit_log
from ..auth.ip_allowlist import require_vm1_ip
from ..db import get_conn
from ..schemas import MailboxCreate, MailboxOut, MailboxResetPassword, MailboxUpdate
from ..services import postfix_dovecot_admin as pda

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])


def _to_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "domain": row["domain_name"] if "domain_name" in row else row.get("domain"),
        "local_part": row["local_part"],
        "quota_bytes": row["quota_bytes"],
        "is_active": row["is_active"],
        "password_overridden": row["password_overridden"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@router.post("", response_model=MailboxOut, status_code=status.HTTP_201_CREATED)
def create_mailbox(
    body: MailboxCreate,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    row, created = pda.create_mailbox(
        conn,
        domain_name=body.domain,
        local_part=body.local_part,
        password_plain=body.password,
        quota_bytes=body.quota_mb * 1024 * 1024,
    )
    if created:
        insert_audit_log(
            conn,
            actor=actor,
            action="mailbox.create",
            target_type="mailbox",
            target_id=str(row["id"]),
            details={"domain": body.domain, "local_part": body.local_part},
            source_ip=request.client.host if request.client else None,
        )
    full = pda.get_mailbox(conn, row["id"])
    return _to_out(full)


@router.patch("/{mailbox_id}", response_model=MailboxOut)
def patch_mailbox(
    mailbox_id: int,
    body: MailboxUpdate,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    quota_bytes = body.quota_mb * 1024 * 1024 if body.quota_mb is not None else None
    row = pda.update_mailbox(conn, mailbox_id, quota_bytes=quota_bytes, is_active=body.is_active)
    insert_audit_log(
        conn,
        actor=actor,
        action="mailbox.update",
        target_type="mailbox",
        target_id=str(mailbox_id),
        details=body.model_dump(exclude_none=True),
        source_ip=request.client.host if request.client else None,
    )
    return _to_out(row)


@router.post("/{mailbox_id}/reset-password", response_model=MailboxOut)
def reset_password(
    mailbox_id: int,
    body: MailboxResetPassword,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    row = pda.reset_password(conn, mailbox_id, body.new_password)
    insert_audit_log(
        conn,
        actor=actor,
        action="mailbox.reset_password",
        target_type="mailbox",
        target_id=str(mailbox_id),
        details={},  # hasło nigdy nie trafia do audit logu
        source_ip=request.client.host if request.client else None,
    )
    return _to_out(row)


@router.get("/{mailbox_id}/status", response_model=MailboxOut)
def get_mailbox_status(
    mailbox_id: int,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    row = pda.get_mailbox(conn, mailbox_id)
    return _to_out(row)


@router.get("/{mailbox_id}/quota")
def get_mailbox_quota(
    mailbox_id: int,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    row = pda.get_mailbox(conn, mailbox_id)
    email = f"{row['local_part']}@{row['domain_name']}"
    quota = pda.get_used_quota(email)
    quota["quota_bytes_limit_db"] = row["quota_bytes"]
    return quota
