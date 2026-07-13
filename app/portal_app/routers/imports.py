import csv
import io

import openpyxl
from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, ImportBatch, ImportRow
from ..services import archive_extractor, import_service, xls_parser
from ..services.audit_service import record

router = APIRouter(prefix="/admin/imports", tags=["imports"], dependencies=[Depends(require_setup_complete)])
templates = Jinja2Templates(directory="portal_app/templates")

_TEMPLATE_HEADER = xls_parser.REQUIRED_COLUMNS + xls_parser.OPTIONAL_COLUMNS
_TEMPLATE_EXAMPLE_ROW = [
    "firma.pl",
    "jan.kowalski@firma.pl",
    "TajneHaslo123!",
    "jan.kowalski",
    "Jan Kowalski",
]


@router.get("")
def list_imports(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    batches = db.query(ImportBatch).order_by(ImportBatch.id.desc()).limit(50).all()
    return templates.TemplateResponse(
        request,
        "imports/list.html",
        {
            "active": "imports",
            "current_user": current_user,
            "batches": batches,
            "required_columns": xls_parser.REQUIRED_COLUMNS,
            "optional_columns": xls_parser.OPTIONAL_COLUMNS,
        },
    )


@router.get("/template.csv")
def download_template_csv(current_user: AdminUser = Depends(require_login)):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_TEMPLATE_HEADER)
    writer.writerow(_TEMPLATE_EXAMPLE_ROW)
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=szablon_import.csv"},
    )


@router.get("/template.xlsx")
def download_template_xlsx(current_user: AdminUser = Depends(require_login)):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "import"
    sheet.append(_TEMPLATE_HEADER)
    sheet.append(_TEMPLATE_EXAMPLE_ROW)
    buf = io.BytesIO()
    workbook.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=szablon_import.xlsx"},
    )


@router.post("")
async def upload_import(
    request: Request,
    archive: UploadFile,
    archive_password: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    data = await archive.read()
    try:
        batch = import_service.stage_batch(
            db,
            uploaded_by_id=current_user.id,
            original_filename=archive.filename or "upload",
            archive_bytes=data,
            archive_password=archive_password,
        )
    except (archive_extractor.ArchiveError, xls_parser.XlsParseError) as exc:
        batches = db.query(ImportBatch).order_by(ImportBatch.id.desc()).limit(50).all()
        return templates.TemplateResponse(
            request,
            "imports/list.html",
            {"active": "imports", "current_user": current_user, "batches": batches, "error": str(exc)},
            status_code=400,
        )

    record(
        db,
        actor_admin_user_id=current_user.id,
        action="import.staged",
        target_type="import_batch",
        target_id=str(batch.id),
        details={"filename": batch.original_filename, "row_count": batch.row_count},
        source_ip=client_ip(request),
    )
    return RedirectResponse(f"/admin/imports/{batch.id}/review", status_code=303)


@router.get("/{batch_id}/review")
def review_import(
    batch_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        return RedirectResponse("/admin/imports", status_code=303)
    rows = db.query(ImportRow).filter(ImportRow.import_batch_id == batch_id).order_by(ImportRow.id).all()
    return templates.TemplateResponse(
        request,
        "imports/review.html",
        {"active": "imports", "current_user": current_user, "batch": batch, "rows": rows},
    )


@router.post("/{batch_id}/commit")
async def commit_import(
    batch_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        return RedirectResponse("/admin/imports", status_code=303)

    form = await request.form()
    selected_row_ids = {int(v) for k, v in form.multi_items() if k == "row_ids"}

    result = import_service.commit_batch(
        db, batch=batch, selected_row_ids=selected_row_ids, actor_admin_user_id=current_user.id
    )
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="import.committed",
        target_type="import_batch",
        target_id=str(batch.id),
        details=result,
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/mailboxes", status_code=303)
