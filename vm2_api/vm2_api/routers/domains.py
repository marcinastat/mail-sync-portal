import re

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..audit import insert_audit_log
from ..auth.ip_allowlist import require_vm1_ip
from ..db import get_conn
from ..schemas import DomainAliasCreate, DomainAliasOut, DomainCreate, DomainOut
from ..services import postfix_dovecot_admin as pda

# Poprawna nazwa domeny (etykiety alnum/‑, TLD ≥2 liter) — walidacja aliasu.
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")

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


@router.get("/{name}/aliases", response_model=list[DomainAliasOut])
def list_aliases(
    name: str,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    return pda.list_domain_aliases(conn, name)


@router.post("/{name}/aliases", response_model=DomainAliasOut, status_code=status.HTTP_201_CREATED)
def add_alias(
    name: str,
    body: DomainAliasCreate,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    alias = body.alias.strip().lower().rstrip(".")
    if not _DOMAIN_RE.match(alias):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alias musi być poprawną nazwą domeny (np. example.net).")
    if alias == name.lower():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alias nie może być równy domenie kanonicznej.")
    try:
        row = pda.add_domain_alias(conn, name, alias)
    except pda.DomainNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Domena nie istnieje na VM2.")
    except pda.AliasConflict:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ten alias jest już przypisany do innej domeny.")
    insert_audit_log(
        conn, actor=actor, action="domain.alias.add", target_type="domain", target_id=name,
        details={"alias": alias}, source_ip=request.client.host if request.client else None,
    )
    return row


@router.delete("/{name}/aliases/{alias}")
def delete_alias(
    name: str,
    alias: str,
    request: Request,
    actor: str = Depends(require_vm1_ip),
    conn: psycopg.Connection = Depends(get_conn),
):
    removed = pda.remove_domain_alias(conn, name, alias.strip().lower())
    insert_audit_log(
        conn, actor=actor, action="domain.alias.remove", target_type="domain", target_id=name,
        details={"alias": alias, "removed": removed}, source_ip=request.client.host if request.client else None,
    )
    return {"removed": removed}
