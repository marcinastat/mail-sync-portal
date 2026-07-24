import logging
import os
import socket
import time
from datetime import datetime, timedelta, timezone

from ..db import session_scope
from ..models import JobQueue, JobRun
from ..services import throttle_service
from .handlers import provision_handler, sync_job_handler, system_update_handler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("portal.worker")

POLL_INTERVAL_SECONDS = 5
WORKER_ID = f"{socket.gethostname()}-{os.getpid()}"

HANDLERS = {
    "provision": provision_handler.handle,
    "sync": sync_job_handler.handle,
    "system_update": system_update_handler.handle,
}


def _claim_next_job(db) -> JobQueue | None:
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(JobQueue)
        .filter(JobQueue.status == "queued", JobQueue.run_after <= now)
        .order_by(JobQueue.priority, JobQueue.id)
        .with_for_update(skip_locked=True)
        .limit(5)
        .all()
    )
    for job in candidates:
        if job.job_type == "sync":
            policy = throttle_service.get_global_policy(db)
            allowed, reason = throttle_service.can_start_sync_now(db, policy)
            if not allowed:
                job.run_after = now + timedelta(seconds=30)
                db.add(job)
                continue
        job.status = "running"
        job.locked_by = WORKER_ID
        job.locked_at = now
        job.attempts += 1
        db.add(job)
        return job
    return None


def _finish_job(job_id: int, *, success: bool, error: str | None = None, max_attempts_from: int | None = None) -> None:
    with session_scope() as db:
        job = db.get(JobQueue, job_id)
        if job is None:
            return
        if success:
            job.status = "done"
        elif job.attempts >= job.max_attempts:
            job.status = "failed"
        else:
            job.status = "retrying"
            job.run_after = datetime.now(timezone.utc) + timedelta(seconds=min(60 * 2 ** job.attempts, 3600))
        db.add(job)
        if error:
            logger.warning("Job %s (%s) failed: %s", job_id, job.job_type, error)


def _reap_orphans() -> None:
    """Sprzątanie osieroconych wpisów przy starcie. Jest tylko JEDNA instancja
    portal-worker, więc po restarcie każdy wpis 'running' jest osierocony (worker
    padł/zrestartowany w trakcie — np. reboot/zawieszenie VM). Bez tego:
      - osierocony job_run zostawał 'running' NA ZAWSZE (panel: „Synchronizacja
        w toku…", skrzynka blokowana),
      - osierocony job_queue 'running' wpadał w `already_pending` schedulera →
        skrzynka NIGDY nie była ponownie kolejkowana (realny objaw: skrzynka
        `scan` utknęła 9 dni po zawieszeniu VM w trakcie synchronizacji)."""
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        stuck_runs = db.query(JobRun).filter(JobRun.status == "running").all()
        for r in stuck_runs:
            r.status = "failed"
            r.finished_at = now
            r.error_summary = "Przerwane — worker zrestartowany (np. reboot VM)."
            db.add(r)
        stuck_jobs = db.query(JobQueue).filter(JobQueue.status == "running").all()
        for j in stuck_jobs:
            if j.job_type == "system_update":
                j.status = "failed"  # aktualizacji systemu NIE wznawiamy automatycznie
            else:
                j.status = "queued"  # sync/provision — bezpiecznie wznowić (idempotentne)
                j.locked_by = None
                j.locked_at = None
                j.run_after = now
            db.add(j)
        if stuck_runs or stuck_jobs:
            logger.warning(
                "Reaper: %d osieroconych job_runs -> failed, %d wpisów kolejki wznowiono/zamknięto.",
                len(stuck_runs), len(stuck_jobs),
            )


def run_forever() -> None:
    logger.info("portal-worker startuje (worker_id=%s)", WORKER_ID)
    _reap_orphans()
    while True:
        job_id = None
        job_type = None
        payload = None
        with session_scope() as db:
            job = _claim_next_job(db)
            if job is not None:
                job_id, job_type, payload = job.id, job.job_type, dict(job.payload)

        if job_id is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        handler = HANDLERS.get(job_type)
        if handler is None:
            _finish_job(job_id, success=False, error=f"Nieznany job_type: {job_type}")
            continue

        try:
            handler(payload)
            _finish_job(job_id, success=True)
        except Exception as exc:
            logger.exception("Błąd przetwarzania joba %s (%s)", job_id, job_type)
            _finish_job(job_id, success=False, error=str(exc))


if __name__ == "__main__":
    run_forever()
