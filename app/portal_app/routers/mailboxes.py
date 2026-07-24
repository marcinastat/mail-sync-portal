from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from ..templating import templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import client_ip, get_db, require_login, require_setup_complete
from ..models import AdminUser, Credential, Domain, JobQueue, JobRun, Mailbox, SyncJob, Vm2Connection
from ..services import imapsync_flags, import_service, vm2_client
from ..services.audit_service import record
from ..services.credential_crypto import encrypt_password

router = APIRouter(prefix="/admin/mailboxes", tags=["mailboxes"], dependencies=[Depends(require_setup_complete)])

CONFIRM_PHRASE = "POTWIERDZAM"


@router.get("")
def list_mailboxes(request: Request, current_user: AdminUser = Depends(require_login), db: Session = Depends(get_db)):
    mailboxes = (
        db.query(Mailbox)
        .join(Domain)
        .order_by(Mailbox.destination_address)
        .all()
    )
    sync_jobs = {sj.mailbox_id: sj for sj in db.query(SyncJob).all()}
    # Ostatni udany przebieg per skrzynka — do pokazania postępu (zsynchronizowane / na źródle).
    subq = (
        db.query(JobRun.mailbox_id, func.max(JobRun.id).label("max_id"))
        .filter(JobRun.status == "success")
        .group_by(JobRun.mailbox_id)
        .subquery()
    )
    last_runs = {r.mailbox_id: r for r in db.query(JobRun).join(subq, JobRun.id == subq.c.max_id).all()}
    return templates.TemplateResponse(
        request,
        "mailboxes/list.html",
        {"active": "mailboxes", "current_user": current_user, "mailboxes": mailboxes,
         "sync_jobs": sync_jobs, "last_runs": last_runs},
    )


@router.get("/new")
def new_mailbox_form(request: Request, current_user: AdminUser = Depends(require_login)):
    # Musi być zarejestrowane PRZED /{mailbox_id}, inaczej FastAPI próbowałoby
    # dopasować "new" jako mailbox_id:int i zwrócić 422 zamiast tego formularza.
    return templates.TemplateResponse(request, "mailboxes/new.html", {"active": "mailboxes", "current_user": current_user})


@router.post("/new")
def create_mailbox_manual(
    request: Request,
    source_domain: str = Form(...),
    source_imap_host: str = Form(""),
    source_imap_port: int = Form(993),
    source_username: str = Form(...),
    source_password: str = Form(...),
    destination_username: str = Form(""),
    quota_mb: int = Form(0),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    mailbox, created = import_service.upsert_mailbox(
        db,
        source_domain=source_domain,
        source_username=source_username,
        source_password=source_password,
        destination_username=destination_username or None,
        source_imap_host=source_imap_host or None,
        source_imap_port=source_imap_port,
        quota_mb=quota_mb,
    )
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="mailbox.create_manual",
        target_type="mailbox",
        target_id=str(mailbox.id),
        details={"source_domain": source_domain, "source_username": source_username, "created": created},
        source_ip=client_ip(request),
    )
    return RedirectResponse(f"/admin/mailboxes/{mailbox.id}", status_code=303)


@router.get("/{mailbox_id}")
def mailbox_detail(
    mailbox_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    mailbox = db.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    sync_job = db.query(SyncJob).filter(SyncJob.mailbox_id == mailbox_id).first()
    # Domyślnie tylko 10 ostatnich (resztę pokazuje modal „cała historia").
    runs = db.query(JobRun).filter(JobRun.mailbox_id == mailbox_id).order_by(JobRun.id.desc()).limit(10).all()
    total_runs = db.query(func.count(JobRun.id)).filter(JobRun.mailbox_id == mailbox_id).scalar() or 0
    running_run = next((r for r in runs if r.status == "running"), None)
    running_now = running_run is not None
    last_success = next((r for r in runs if r.status == "success"), None)

    quota = None
    if mailbox.vm2_mailbox_id:
        conn = db.query(Vm2Connection).first()
        if conn is not None:
            try:
                quota = vm2_client.get_mailbox_quota(conn, mailbox.vm2_mailbox_id)
            except Exception:
                quota = None

    return templates.TemplateResponse(
        request,
        "mailboxes/detail.html",
        {
            "active": "mailboxes",
            "current_user": current_user,
            "mailbox": mailbox,
            "sync_job": sync_job,
            "runs": runs,
            "total_runs": total_runs,
            "running_now": running_now,
            "running_run_id": running_run.id if running_run else None,
            "last_success": last_success,
            "quota": quota,
        },
    )


def _run_row(r: JobRun) -> dict:
    return {
        "id": r.id,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "status": r.status,
        "folders_synced": r.folders_synced,
        "folders_total": r.folders_total,
        "messages_transferred": r.messages_transferred,
        "messages_total": r.messages_total,
        "source_messages_total": r.source_messages_total,
        "drift": r.messages_missing_from_source_retained,
        "has_log": bool(r.imapsync_log_path),
    }


@router.get("/{mailbox_id}/runs.json")
def runs_json(
    mailbox_id: int,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Pełna historia przebiegów (do modala „cała historia")."""
    if db.get(Mailbox, mailbox_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    runs = db.query(JobRun).filter(JobRun.mailbox_id == mailbox_id).order_by(JobRun.id.desc()).all()
    return {"runs": [_run_row(r) for r in runs]}


@router.get("/{mailbox_id}/runs/{run_id}/live")
def run_live(
    mailbox_id: int,
    run_id: int,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Podgląd NA ŻYWO trwającego (lub właśnie zakończonego) przebiegu: status +
    bieżąca zawartość pliku logu, do której imapsync dopisuje w trakcie."""
    run = db.get(JobRun, run_id)
    if run is None or run.mailbox_id != mailbox_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    log = ""
    if run.imapsync_log_path:
        p = Path(run.imapsync_log_path)
        if p.exists():
            log = p.read_text(encoding="utf-8", errors="replace")
    return {
        "id": run.id,
        "status": run.status,
        "log": log,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error_summary": run.error_summary,
    }


@router.post("/{mailbox_id}/quota")
def update_quota(
    mailbox_id: int,
    request: Request,
    quota_mb: int = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    mailbox = db.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if not mailbox.vm2_mailbox_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Skrzynka nie jest jeszcze zaprowizonowana na VM2.")
    conn = db.query(Vm2Connection).first()
    if conn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Brak konfiguracji połączenia z VM2.")
    vm2_client.update_mailbox_quota(conn, mailbox.vm2_mailbox_id, quota_mb)
    mailbox.quota_mb = quota_mb
    db.add(mailbox)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="mailbox.quota_update",
        target_type="mailbox",
        target_id=str(mailbox.id),
        details={"quota_mb": quota_mb},
        source_ip=client_ip(request),
    )
    return RedirectResponse(f"/admin/mailboxes/{mailbox_id}", status_code=303)


@router.post("/{mailbox_id}/sync-now")
def sync_now(
    mailbox_id: int,
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    mailbox = db.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    existing = (
        db.query(JobQueue)
        .filter(
            JobQueue.job_type == "sync",
            JobQueue.status.in_(["queued", "running", "retrying"]),
            JobQueue.payload["mailbox_id"].astext == str(mailbox_id),
        )
        .first()
    )
    if existing is None:
        db.add(JobQueue(job_type="sync", payload={"mailbox_id": mailbox_id, "trigger": "manual"}, run_after=datetime.now(timezone.utc)))
        record(
            db,
            actor_admin_user_id=current_user.id,
            action="sync.triggered_manually",
            target_type="mailbox",
            target_id=str(mailbox_id),
            source_ip=client_ip(request),
        )
    return RedirectResponse(f"/admin/mailboxes/{mailbox_id}", status_code=303)


@router.get("/{mailbox_id}/runs/{run_id}/log", response_class=PlainTextResponse)
def view_run_log(
    mailbox_id: int,
    run_id: int,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    run = db.get(JobRun, run_id)
    if run is None or run.mailbox_id != mailbox_id or not run.imapsync_log_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    path = Path(run.imapsync_log_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plik logu nie istnieje (mógł zostać zrotowany).")
    return path.read_text(encoding="utf-8", errors="replace")


@router.post("/sync-config")
async def bulk_sync_config(
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    form = await request.form()
    mailbox_ids = {int(v) for k, v in form.multi_items() if k == "mailbox_ids"}
    days_back = int(form.get("days_back", 365))
    preserve_folder_structure = form.get("preserve_folder_structure") == "on"
    delete_on_dest = form.get("delete_on_dest_when_missing_from_source") == "on"
    is_enabled = form.get("is_enabled") == "on"
    confirm_text = form.get("confirm_text", "")

    if delete_on_dest and confirm_text != CONFIRM_PHRASE:
        mailboxes = db.query(Mailbox).join(Domain).order_by(Mailbox.destination_address).all()
        sync_jobs = {sj.mailbox_id: sj for sj in db.query(SyncJob).all()}
        return templates.TemplateResponse(
            request,
            "mailboxes/list.html",
            {
                "active": "mailboxes",
                "current_user": current_user,
                "mailboxes": mailboxes,
                "sync_jobs": sync_jobs,
                "error": f"Włączenie kasowania na docelowym wymaga wpisania '{CONFIRM_PHRASE}' w polu potwierdzenia.",
            },
            status_code=400,
        )

    if not mailbox_ids:
        return RedirectResponse("/admin/mailboxes", status_code=303)

    sync_jobs = db.query(SyncJob).filter(SyncJob.mailbox_id.in_(mailbox_ids)).all()
    for sj in sync_jobs:
        sj.days_back = days_back
        sj.preserve_folder_structure = preserve_folder_structure
        sj.delete_on_dest_when_missing_from_source = delete_on_dest
        sj.is_enabled = is_enabled
        db.add(sj)

    record(
        db,
        actor_admin_user_id=current_user.id,
        action="sync_job.bulk_update",
        target_type="mailbox",
        details={
            "mailbox_ids": sorted(mailbox_ids),
            "days_back": days_back,
            "preserve_folder_structure": preserve_folder_structure,
            "delete_on_dest_when_missing_from_source": delete_on_dest,
            "is_enabled": is_enabled,
        },
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/mailboxes", status_code=303)


@router.post("/{mailbox_id}/source-password")
def update_source_password(
    mailbox_id: int,
    request: Request,
    new_source_password: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    # Aktualizuje hasło używane do logowania na serwer ŹRÓDŁOWY (imapsync host1).
    # Do użycia, gdy hasło zmieniło się po stronie źródła — inaczej kolejne
    # synchronizacje padają na autoryzacji host1. NIE dotyka hasła docelowego
    # na VM2 (to osobna operacja "reset hasła"). Hasło nigdy nie trafia do audytu.
    mailbox = db.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    credential = db.get(Credential, mailbox.credential_id)
    if credential is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brak poświadczeń dla skrzynki.")
    credential.source_password_encrypted = encrypt_password(new_source_password)
    db.add(credential)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="mailbox.source_password_update",
        target_type="mailbox",
        target_id=str(mailbox.id),
        details={},  # hasło nigdy nie trafia do audit logu
        source_ip=client_ip(request),
    )
    return RedirectResponse(f"/admin/mailboxes/{mailbox_id}", status_code=303)


@router.post("/{mailbox_id}/reset-password")
def reset_password(
    mailbox_id: int,
    request: Request,
    new_password: str = Form(...),
    confirm_text: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    mailbox = db.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if confirm_text != CONFIRM_PHRASE:
        sync_job = db.query(SyncJob).filter(SyncJob.mailbox_id == mailbox_id).first()
        return templates.TemplateResponse(
            request,
            "mailboxes/detail.html",
            {
                "active": "mailboxes",
                "current_user": current_user,
                "mailbox": mailbox,
                "sync_job": sync_job,
                "error": f"Reset hasła wymaga wpisania '{CONFIRM_PHRASE}' w polu potwierdzenia.",
            },
            status_code=400,
        )
    if not mailbox.vm2_mailbox_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Skrzynka nie jest jeszcze zaprowizonowana na VM2.")

    conn = db.query(Vm2Connection).first()
    if conn is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Brak konfiguracji połączenia z VM2.")

    vm2_client.reset_mailbox_password(conn, mailbox.vm2_mailbox_id, new_password)
    mailbox.password_override = True
    mailbox.destination_password_encrypted = encrypt_password(new_password)
    db.add(mailbox)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="mailbox.reset_password",
        target_type="mailbox",
        target_id=str(mailbox.id),
        details={},  # hasło nigdy nie trafia do audit logu
        source_ip=client_ip(request),
    )
    return RedirectResponse(f"/admin/mailboxes/{mailbox_id}", status_code=303)


@router.post("/{mailbox_id}/custom-flags")
def update_custom_flags(
    mailbox_id: int,
    request: Request,
    custom_flags: str = Form(""),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Zapisuje dodatkowe flagi imapsync SPECYFICZNE dla tej skrzynki (np.
    --exclude jakiegoś folderu). Walidowane allowlistą — flagi mutujące źródło
    lub uruchamiające kod są odrzucane. Dokładają się do flag globalnych."""
    mailbox = db.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    sync_job = db.query(SyncJob).filter(SyncJob.mailbox_id == mailbox_id).first()

    try:
        imapsync_flags.validate_custom_flags(custom_flags)
    except imapsync_flags.ImapsyncFlagError as exc:
        return templates.TemplateResponse(
            request,
            "mailboxes/detail.html",
            {"active": "mailboxes", "current_user": current_user, "mailbox": mailbox,
             "sync_job": sync_job, "error": str(exc)},
            status_code=400,
        )

    if sync_job is None:
        sync_job = SyncJob(mailbox_id=mailbox_id)
        db.add(sync_job)
    sync_job.custom_flags = custom_flags.strip()
    db.add(sync_job)
    record(
        db,
        actor_admin_user_id=current_user.id,
        action="mailbox.custom_flags",
        target_type="mailbox",
        target_id=str(mailbox_id),
        details={"custom_flags": sync_job.custom_flags},
        source_ip=client_ip(request),
    )
    return RedirectResponse(f"/admin/mailboxes/{mailbox_id}", status_code=303)


@router.post("/{mailbox_id}/delete")
def delete_mailbox(
    mailbox_id: int,
    request: Request,
    confirm_text: str = Form(...),
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    """Trwałe, potwierdzone usunięcie skrzynki DOCELOWEJ. Wymaga wpisania
    dokładnego adresu skrzynki (silniejsze niż 'POTWIERDZAM' — chroni przed
    pomyłką co do której skrzynki kasujemy). Kasuje na VM2 (rekord + maildir),
    a lokalnie: przebiegi, kolejkę, konfigurację sync i sam rekord. Serwera
    ŹRÓDŁOWEGO nie dotyka — imapsync jest jednokierunkowy."""
    mailbox = db.get(Mailbox, mailbox_id)
    if mailbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    if confirm_text.strip() != mailbox.destination_address:
        sync_job = db.query(SyncJob).filter(SyncJob.mailbox_id == mailbox_id).first()
        return templates.TemplateResponse(
            request,
            "mailboxes/detail.html",
            {
                "active": "mailboxes",
                "current_user": current_user,
                "mailbox": mailbox,
                "sync_job": sync_job,
                "error": f"Usunięcie wymaga wpisania dokładnego adresu skrzynki: {mailbox.destination_address}",
            },
            status_code=400,
        )

    # Najpierw VM2 (rekord + maildir). Gdyby padło — przerywamy i NIE kasujemy
    # lokalnie, żeby stan po obu stronach się nie rozjechał (skrzynka nadal
    # widoczna w panelu, można ponowić).
    if mailbox.vm2_mailbox_id:
        conn = db.query(Vm2Connection).first()
        if conn is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Brak konfiguracji połączenia z VM2.")
        vm2_client.delete_mailbox(conn, mailbox.vm2_mailbox_id)

    deleted_address = mailbox.destination_address
    credential_id = mailbox.credential_id

    # Lokalne sprzątanie. JobRun/SyncJob mają ondelete=CASCADE (FK do mailboxes),
    # ale JobQueue trzyma mailbox_id tylko w payload (JSONB, bez FK) — czyścimy
    # ręcznie ewentualne niezakończone zadania tej skrzynki.
    db.query(JobQueue).filter(
        JobQueue.job_type == "sync",
        JobQueue.payload["mailbox_id"].astext == str(mailbox_id),
    ).delete(synchronize_session=False)
    db.delete(mailbox)
    db.flush()

    # Credential usuwamy tylko, jeśli nie współdzieli go inna skrzynka.
    if credential_id is not None:
        still_used = db.query(Mailbox).filter(Mailbox.credential_id == credential_id).count()
        if still_used == 0:
            cred = db.get(Credential, credential_id)
            if cred is not None:
                db.delete(cred)

    record(
        db,
        actor_admin_user_id=current_user.id,
        action="mailbox.delete",
        target_type="mailbox",
        target_id=str(mailbox_id),
        details={"destination_address": deleted_address},
        source_ip=client_ip(request),
    )
    return RedirectResponse("/admin/mailboxes", status_code=303)
