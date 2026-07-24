from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from ..templating import templates
from sqlalchemy.orm import Session

from ..deps import get_db, require_login, require_setup_complete
from ..models import AdminUser, AuditLog, Mailbox
from ..services.report_export import rows_to_csv, rows_to_pdf

router = APIRouter(prefix="/admin/audit", tags=["audit"], dependencies=[Depends(require_setup_complete)])

HEADER = ["Kiedy (UTC)", "Użytkownik", "Akcja", "Cel", "IP źródłowe"]


def _resolve_names(db: Session, entries: list[AuditLog]) -> tuple[dict, dict]:
    """Mapy do czytelnego audytu: id admina -> login, id skrzynki -> adres.
    Dzięki temu kolumny „Użytkownik"/„Cel" pokazują nazwy, nie surowe ID."""
    actor_ids = {e.actor_admin_user_id for e in entries if e.actor_admin_user_id}
    actor_names = {}
    if actor_ids:
        for u in db.query(AdminUser).filter(AdminUser.id.in_(actor_ids)).all():
            actor_names[u.id] = u.username
    mb_ids = {
        int(e.target_id)
        for e in entries
        if e.target_type == "mailbox" and e.target_id and str(e.target_id).isdigit()
    }
    mb_names = {}
    if mb_ids:
        for m in db.query(Mailbox).filter(Mailbox.id.in_(mb_ids)).all():
            mb_names[str(m.id)] = m.destination_address  # klucz str — target_id jest tekstem
    return actor_names, mb_names


def _target_label(e: AuditLog, mb_names: dict) -> str:
    if e.target_type == "mailbox" and e.target_id in mb_names:
        return mb_names[e.target_id]
    return f"{e.target_type or ''} {e.target_id or ''}".strip()


def _filtered_query(
    db: Session,
    date_from: str | None,
    date_to: str | None,
    action: str | None,
):
    query = db.query(AuditLog).order_by(AuditLog.id.desc())
    if date_from:
        query = query.filter(AuditLog.occurred_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(AuditLog.occurred_at <= datetime.fromisoformat(date_to))
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    return query


def _rows(entries: list[AuditLog], actor_names: dict, mb_names: dict) -> list[list]:
    return [
        [
            e.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
            actor_names.get(e.actor_admin_user_id, "system") if e.actor_admin_user_id else "system",
            e.action,
            _target_label(e, mb_names),
            e.source_ip or "",
        ]
        for e in entries
    ]


@router.get("")
def list_audit(
    request: Request,
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    action: str | None = Query(None),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    entries = _filtered_query(db, date_from, date_to, action).limit(200).all()
    actor_names, mb_names = _resolve_names(db, entries)
    return templates.TemplateResponse(
        request,
        "audit/list.html",
        {
            "active": "audit",
            "current_user": current_user,
            "entries": entries,
            "actor_names": actor_names,
            "mb_names": mb_names,
            "date_from": date_from or "",
            "date_to": date_to or "",
            "action": action or "",
        },
    )


@router.get("/export.csv")
def export_csv(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    action: str | None = Query(None),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    entries = _filtered_query(db, date_from, date_to, action).limit(10000).all()
    actor_names, mb_names = _resolve_names(db, entries)
    csv_bytes = rows_to_csv(HEADER, _rows(entries, actor_names, mb_names))
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )


@router.get("/export.pdf")
def export_pdf(
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    action: str | None = Query(None),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    entries = _filtered_query(db, date_from, date_to, action).limit(2000).all()
    actor_names, mb_names = _resolve_names(db, entries)
    pdf_bytes = rows_to_pdf("Audit log — Portal Poczty", HEADER, _rows(entries, actor_names, mb_names))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=audit_log.pdf"},
    )
