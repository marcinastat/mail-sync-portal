from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from ..templating import templates
from sqlalchemy.orm import Session

from ..deps import get_db, require_login, require_setup_complete
from ..models import AdminUser, JobRun, Mailbox, SyncJob, Vm2Connection
from ..services import fail2ban_service, vm2_client
from ..services.report_export import rows_to_csv, rows_to_pdf

router = APIRouter(prefix="/admin/reports", tags=["reports"], dependencies=[Depends(require_setup_complete)])

HEADER = [
    "Skrzynka docelowa", "Domena źródłowa", "Sync", "Dni wstecz",
    "Ostatni przebieg", "Wiadomości (u nas / źródło)", "Brakujące", "Rozmiar (u nas / źródło)", "Drift",
]


def _fmt_size(b: int) -> str:
    b = b or 0
    if b >= 1073741824:
        return f"{b / 1073741824:.2f} GB"
    return f"{b / 1048576:.1f} MB"


def _report_data(db: Session):
    """Wiersze raportu + podsumowanie. Liczniki „u nas/źródło" i kompletność
    (brakujące) z ostatniego UDANEGO przebiegu; status/czas z ostatniego (dowolnego)."""
    mailboxes = db.query(Mailbox).order_by(Mailbox.destination_address).all()
    sync_jobs = {sj.mailbox_id: sj for sj in db.query(SyncJob).all()}
    rows: list[list] = []
    summary = {"count": len(mailboxes), "active": 0, "dest_msgs": 0, "src_msgs": 0,
               "missing": 0, "drift": 0, "errors": 0, "dest_bytes": 0}
    for m in mailboxes:
        sj = sync_jobs.get(m.id)
        last_run = db.query(JobRun).filter(JobRun.mailbox_id == m.id).order_by(JobRun.id.desc()).first()
        last_ok = (
            db.query(JobRun).filter(JobRun.mailbox_id == m.id, JobRun.status == "success")
            .order_by(JobRun.id.desc()).first()
        )
        if m.provisioning_status == "active":
            summary["active"] += 1
        # Ostatni przebieg: status · kiedy · czas trwania (+ ewentualny błąd).
        if last_run:
            dur = ""
            if last_run.started_at and last_run.finished_at:
                dur = f" · {round((last_run.finished_at - last_run.started_at).total_seconds())}s"
            when = last_run.started_at.strftime("%Y-%m-%d %H:%M") if last_run.started_at else "-"
            run_cell = f"{last_run.status} · {when}{dur}"
            if last_run.status == "failed" and last_run.error_summary:
                run_cell += f" · {last_run.error_summary[:60]}"
            if last_run.status == "failed":
                summary["errors"] += 1
        else:
            run_cell = "brak przebiegów"
        dest_n = (last_ok.dest_nb_messages or last_ok.messages_total) if last_ok else 0
        src_n = (last_ok.source_nb_messages or last_ok.source_messages_total) if last_ok else 0
        missing = last_ok.source_missing if last_ok else 0
        drift = last_ok.messages_missing_from_source_retained if last_ok else 0
        summary["dest_msgs"] += dest_n or 0
        summary["src_msgs"] += src_n or 0
        summary["missing"] += missing or 0
        summary["drift"] += drift or 0
        summary["dest_bytes"] += m.dest_bytes or 0
        rows.append([
            m.destination_address,
            m.domain.source_domain if m.domain else "",
            "włączona" if sj and sj.is_enabled else "wyłączona",
            "wszystko" if sj and sj.days_back == 0 else str(sj.days_back if sj else 365),
            run_cell,
            f"{dest_n} / {src_n or '?'}",
            str(missing) if missing else "0",
            f"{_fmt_size(m.dest_bytes)} / {_fmt_size(m.source_bytes)}",
            drift,
        ])
    summary["dest_size"] = _fmt_size(summary["dest_bytes"])
    return rows, summary


def _report_rows(db: Session) -> list[list]:
    return _report_data(db)[0]


def _scan_findings(db: Session) -> dict | None:
    conn = db.query(Vm2Connection).first()
    if conn is None or not conn.vm2_host:
        return None
    try:
        return vm2_client.av_findings(conn, limit=200)
    except vm2_client.Vm2ApiError:
        return None


def _fail2ban(db: Session) -> dict:
    """Status fail2ban obu serwerów: VM1 lokalnie (sudo-helper), VM2 przez vm2-api.
    Read-only — unban/ban robi się z konsoli (docs/technical/runbooks/fail2ban.md)."""
    vm1 = fail2ban_service.local_status()
    vm2 = None
    conn = db.query(Vm2Connection).first()
    if conn is not None and conn.vm2_host:
        try:
            vm2 = vm2_client.fail2ban_status(conn)
        except vm2_client.Vm2ApiError:
            vm2 = None
    return {"vm1": vm1, "vm2": vm2}


@router.get("")
def show(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    rows, summary = _report_data(db)
    return templates.TemplateResponse(
        request, "reports/index.html",
        {"active": "reports", "current_user": current_user, "header": HEADER, "rows": rows,
         "summary": summary, "findings": _scan_findings(db), "fail2ban": _fail2ban(db)},
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
