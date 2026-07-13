from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from ..templating import templates
from sqlalchemy.orm import Session

from ..deps import get_db, require_login, require_setup_complete
from ..models import AdminUser, JobRun, Mailbox, SyncJob
from ..services.report_export import rows_to_csv, rows_to_pdf

router = APIRouter(prefix="/admin/reports", tags=["reports"], dependencies=[Depends(require_setup_complete)])

HEADER = ["Skrzynka docelowa", "Provisioning", "Sync włączony", "Ostatni status", "Ostatnia sync.", "Wiadomości", "Drift"]


def _report_rows(db: Session) -> list[list]:
    mailboxes = db.query(Mailbox).order_by(Mailbox.destination_address).all()
    sync_jobs = {sj.mailbox_id: sj for sj in db.query(SyncJob).all()}
    rows = []
    for m in mailboxes:
        last_run = db.query(JobRun).filter(JobRun.mailbox_id == m.id).order_by(JobRun.id.desc()).first()
        sj = sync_jobs.get(m.id)
        rows.append(
            [
                m.destination_address,
                m.provisioning_status,
                "tak" if sj and sj.is_enabled else "nie",
                last_run.status if last_run else "-",
                last_run.started_at.strftime("%Y-%m-%d %H:%M") if last_run else "-",
                f"{last_run.messages_transferred}/{last_run.messages_total}" if last_run else "-",
                last_run.messages_missing_from_source_retained if last_run else 0,
            ]
        )
    return rows


@router.get("")
def show(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    rows = _report_rows(db)
    return templates.TemplateResponse(
        request, "reports/index.html", {"active": "reports", "current_user": current_user, "header": HEADER, "rows": rows}
    )


@router.get("/mailboxes.csv")
def export_csv(current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    csv_bytes = rows_to_csv(HEADER, _report_rows(db))
    return Response(
        content=csv_bytes, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sync_status.csv"}
    )


@router.get("/mailboxes.pdf")
def export_pdf(current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    pdf_bytes = rows_to_pdf("Status synchronizacji skrzynek — Portal Poczty", HEADER, _report_rows(db))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sync_status.pdf"},
    )
