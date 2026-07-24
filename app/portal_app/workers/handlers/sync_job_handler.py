from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from ...db import session_scope
from ...models import Credential, Domain, ImapsyncConfig, JobRun, Mailbox, SyncJob, Vm2Connection
from ...services import imapsync_flags, imapsync_runner, vm2_client
from ...services.alert_service import dispatch as dispatch_alert
from ...services.audit_service import record
from ...services.credential_crypto import decrypt_password

DEST_IMAP_PORT = 993


def handle(payload: dict) -> None:
    mailbox_id = payload["mailbox_id"]
    # Skąd przyszła ta synchronizacja: "manual" (przycisk w panelu),
    # "scheduled" (scheduler) lub "assess" (inwentaryzacja po dodaniu skrzynki).
    trigger = payload.get("trigger", "scheduled")
    # Tryb inwentaryzacji: imapsync --dry (NIC nie przenosi), tylko zbiera ile
    # jest do zebrania (liczby/rozmiar źródła) i uzupełnia bazę. Realny transfer
    # robi dopiero kolejny (normalny) przebieg.
    assess = payload.get("mode") == "assess"

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

        # Flagi imapsync: globalne (ImapsyncConfig) + per-skrzynka (sync_job.custom_flags).
        # Odczytujemy wartości TERAZ (sesja otwarta) do prostego obiektu, żeby
        # zbudować argv poza transakcją. Brak konfiguracji = bezpieczny domyślny
        # (weryfikacja SSL włączona).
        _cfg = db.query(ImapsyncConfig).first()
        imap_cfg = SimpleNamespace(
            verify_source_ssl=_cfg.verify_source_ssl if _cfg else True,
            add_missing_headers=_cfg.add_missing_headers if _cfg else False,
            max_size_mb=_cfg.max_size_mb if _cfg else 0,
            timeout_seconds=_cfg.timeout_seconds if _cfg else 0,
            allow_size_mismatch=_cfg.allow_size_mismatch if _cfg else False,
            custom_flags=_cfg.custom_flags if _cfg else "",
        )
        mailbox_custom_flags = sync_job.custom_flags or ""

        job_run = JobRun(sync_job_id=sync_job.id, mailbox_id=mailbox.id, status="running", started_at=datetime.now(timezone.utc))
        db.add(job_run)
        db.flush()
        job_run_id = job_run.id
        # Ścieżkę logu wyliczamy i ZAPISUJEMY już na rekordzie „running", żeby
        # panel mógł podglądać przebieg na żywo (imapsync pisze do tego pliku w
        # trakcie). Ten sam plik trafi do wyniku poniżej.
        live_log_path = imapsync_runner.new_log_path(mailbox.id)
        job_run.imapsync_log_path = str(live_log_path)
        db.add(job_run)
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
        # Złożenie flag: globalne + per-skrzynka. Walidacja allowlistą jest tu
        # ponawiana (obrona w głąb — router waliduje przy zapisie); błąd = sync
        # kończy się jako failed z czytelnym komunikatem, źródło i tak nietknięte.
        extra_flags = imapsync_flags.build_global_flags(imap_cfg)
        extra_flags += imapsync_flags.validate_custom_flags(mailbox_custom_flags)
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
            extra_flags=extra_flags,
            log_path=Path(live_log_path),
            dry_run=assess,  # inwentaryzacja = --dry (nic nie przenosi)
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

        # Audyt KAŻDEJ synchronizacji (nie tylko nieudanej) — żeby w logu audytu
        # było widać: kiedy, skąd (ręcznie/harmonogram), ile trwała i z jakim
        # wynikiem. Czas trwania z started_at/finished_at przebiegu.
        duration_seconds = None
        if job_run.started_at and job_run.finished_at:
            duration_seconds = round((job_run.finished_at - job_run.started_at).total_seconds())
        record(
            db,
            actor_admin_user_id=None,
            action="sync.completed",
            target_type="mailbox",
            target_id=str(mailbox_id),
            details={
                "trigger": trigger,                       # manual | scheduled
                "source": "worker",
                "status": status,                         # success | failed
                "duration_seconds": duration_seconds,
                "messages_transferred": stats.get("messages_transferred", 0),
                "job_run_id": job_run_id,
                "error": error_summary,
            },
            source_ip=None,
        )
        if status == "failed":
            dispatch_alert(
                db,
                event="sync_failed",
                subject=f"Synchronizacja skrzynki #{mailbox_id} nie powiodła się",
                details={"mailbox_id": mailbox_id, "error": error_summary, "job_run_id": job_run_id},
            )
