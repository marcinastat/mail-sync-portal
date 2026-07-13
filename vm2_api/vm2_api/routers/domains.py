import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..audit import insert_audit_log
from ..auth.ip_allowlist import require_vm1_ip
from ..db import get_conn
from ..schemas import DomainCreate, DomainOut
from ..services import postfix_dovecot_admin as pda

router = APIRouter(prefix="/domains", tags=["domains"])


@router.post("", response_model=DomainOut, status_code=status.HTTP_201_CREATED)
def create_domain(
    body: DomainCreate,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    domain = pda.ensure_domain(conn, body.name)
    insert_audit_log(
        conn,
        actor=actor,
        action="domain.create",
        target_type="domain",
        target_id=str(domain["id"]),
        details={"name": body.name},
        source_ip=request.client.host if request.client else None,
    )
    return domain


@router.get("/{name}", response_model=DomainOut)
def get_domain(
    name: str,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    domain = pda.get_domain(conn, name)
    if not domain:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Domena nie istnieje.")
    return domain
