from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..deps import get_db, require_login, require_setup_complete
from ..models import AdminUser, AuditLog
from ..services.report_export import rows_to_csv, rows_to_pdf

router = APIRouter(prefix="/admin/audit", tags=["audit"], dependencies=[Depends(require_setup_complete)])
templates = Jinja2Templates(directory="portal_app/templates")

HEADER = ["Kiedy (UTC)", "Użytkownik", "Akcja", "Cel", "IP źródłowe"]


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


def _rows(entries: list[AuditLog]) -> list[list]:
    return [
        [
            e.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
            e.actor_admin_user_id or "system",
            e.action,
            f"{e.target_type or ''} {e.target_id or ''}".strip(),
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
    return templates.TemplateResponse(
        request,
        "audit/list.html",
        {
            "active": "audit",
            "current_user": current_user,
            "entries": entries,
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
    csv_bytes = rows_to_csv(HEADER, _rows(entries))
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
    pdf_bytes = rows_to_pdf("Audit log — Portal Poczty", HEADER, _rows(entries))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=audit_log.pdf"},
    )
