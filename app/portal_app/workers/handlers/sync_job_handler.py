from datetime import datetime, timezone

from ...db import session_scope
from ...models import Credential, Domain, JobRun, Mailbox, SyncJob, Vm2Connection
from ...services import imapsync_runner, vm2_client
from ...services.alert_service import dispatch as dispatch_alert
from ...services.audit_service import record
from ...services.credential_crypto import decrypt_password

DEST_IMAP_PORT = 993


def handle(payload: dict) -> None:
    mailbox_id = payload["mailbox_id"]

    with session_scope() as db:
        mailbox = db.get(Mailbox, mailbox_id)
        if mailbox is None or mailbox.provisioning_status != "active":
            return
        credential = db.get(Credential, mailbox.credential_id)
        domain = db.get(Domain, mailbox.domain_id)
        sync_job = db.query(SyncJob).filter(SyncJob.mailbox_id == mailbox_id).first()
        conn = db.query(Vm2Connection).first()
        if sync_job is None or not sync_job.is_enabled or conn is None or not conn.vm2_host:
            return

        source_password = decrypt_password(credential.source_password_encrypted)
        dest_password = decrypt_password(mailbox.destination_password_encrypted)
        source_host, source_port = domain.source_imap_host, domain.source_imap_port
        dest_host = conn.vm2_host
        source_username = credential.source_username
        dest_username = f"{credential.destination_username}@{domain.destination_domain}"
        days_back = sync_job.days_back
        preserve = sync_job.preserve_folder_structure
        delete_on_dest = sync_job.delete_on_dest_when_missing_from_source

        job_run = JobRun(sync_job_id=sync_job.id, mailbox_id=mailbox.id, status="running", started_at=datetime.now(timezone.utc))
        db.add(job_run)
        db.flush()
        job_run_id = job_run.id
        previous_run = (
            db.query(JobRun)
            .filter(JobRun.mailbox_id == mailbox.id, JobRun.id != job_run_id, JobRun.status == "success")
            .order_by(JobRun.id.desc())
            .first()
        )
        previous_messages_total = previous_run.messages_total if previous_run else 0

    # imapsync trwa poza otwartą transakcją bazodanową (do godziny) — patrz
    # docs/technical/architecture.md, uzasadnienie w services/imapsync_runner.py.
    try:
        result = imapsync_runner.run_sync(
            mailbox_id=mailbox.id,
            source_host=source_host,
            source_port=source_port,
            source_user=source_username,
            source_password=source_password,
            dest_host=dest_host,
            dest_port=DEST_IMAP_PORT,
            dest_user=dest_username,
            dest_password=dest_password,
            days_back=days_back,
            preserve_folder_structure=preserve,
            delete_on_dest_when_missing_from_source=delete_on_dest,
        )
        error_summary = None if result["returncode"] == 0 else f"imapsync zakończył się kodem {result['returncode']}"
        status = "success" if result["returncode"] == 0 else "failed"
        stats = result["stats"]
        log_path = result["log_path"]
    except Exception as exc:  # timeout, subprocess error itp. — zapisujemy jako failed, nie wywracamy workera
        status = "failed"
        error_summary = str(exc)[:2000]
        stats = {}
        log_path = None

    messages_total = stats.get("messages_total", 0)
    # Heurystyka driftu: spadek messages_total względem ostatniego udanego
    # przebiegu, przy domyślnej polityce "nie kasuj na docelowym" oznacza
    # wiadomości zachowane na VM2 mimo zniknięcia ze źródła. Przybliżenie —
    # dokładna weryfikacja wymagałaby porównania zbiorów UID, poza zakresem v1.
    drift = max(0, previous_messages_total - messages_total) if not delete_on_dest else 0

    with session_scope() as db:
        job_run = db.get(JobRun, job_run_id)
        job_run.status = status
        job_run.finished_at = datetime.now(timezone.utc)
        job_run.messages_transferred = stats.get("messages_transferred", 0)
        job_run.bytes_transferred = stats.get("bytes_transferred", 0)
        job_run.folders_synced = stats.get("folders_synced", 0)
        job_run.folders_total = stats.get("folders_total", 0)
        job_run.messages_total = messages_total
        job_run.source_messages_total = stats.get("source_messages_total", 0)
        job_run.dest_nb_messages = stats.get("dest_nb_messages", 0)
        job_run.source_nb_messages = stats.get("source_nb_messages", 0)
        job_run.source_duplicates = stats.get("source_duplicates", 0)
        job_run.source_missing = stats.get("source_missing", 0)
        job_run.messages_missing_from_source_retained = drift
        job_run.error_summary = error_summary
        job_run.imapsync_log_path = log_path
        db.add(job_run)

        # Cache rozmiarów skrzynki: źródło z imapsync (host1 total size),
        # docelowy z doveadm quota na VM2 — żeby lista/szczegóły pokazywały
        # zajętość bez odpytywania VM2 przy każdym renderze.
        mb = db.get(Mailbox, mailbox_id)
        if mb is not None:
            if stats.get("source_bytes"):
                mb.source_bytes = stats["source_bytes"]
            if mb.vm2_mailbox_id:
                conn2 = db.query(Vm2Connection).first()
                if conn2 is not None:
                    try:
                        q = vm2_client.get_mailbox_quota(conn2, mb.vm2_mailbox_id)
                        mb.dest_bytes = q.get("used_bytes", 0)
                    except Exception:
                        pass
            db.add(mb)

        if status == "failed":
            record(
                db,
                actor_admin_user_id=None,
                action="sync.failed",
                target_type="mailbox",
                target_id=str(mailbox_id),
                details={"error": error_summary, "job_run_id": job_run_id},
                source_ip=None,
            )
            dispatch_alert(
                db,
                event="sync_failed",
                subject=f"Synchronizacja skrzynki #{mailbox_id} nie powiodła się",
                details={"mailbox_id": mailbox_id, "error": error_summary, "job_run_id": job_run_id},
            )
