import logging
from datetime import datetime, timedelta, timezone

from croniter import croniter

from ..db import session_scope
from ..models import JobQueue, SyncJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("portal.scheduler")


def _is_due(sync_job: SyncJob, now: datetime) -> bool:
    base = sync_job.last_enqueued_at or (now - timedelta(days=1))
    try:
        next_run = croniter(sync_job.schedule_cron, base).get_next(datetime)
    except (ValueError, KeyError):
        logger.warning("Nieprawidłowy schedule_cron dla sync_job %s: %r", sync_job.id, sync_job.schedule_cron)
        return False
    return next_run.replace(tzinfo=timezone.utc) <= now


def run_once() -> int:
    enqueued = 0
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        sync_jobs = db.query(SyncJob).filter(SyncJob.is_enabled.is_(True)).all()
        for sync_job in sync_jobs:
            if not _is_due(sync_job, now):
                continue
            already_pending = (
                db.query(JobQueue)
                .filter(
                    JobQueue.job_type == "sync",
                    JobQueue.status.in_(["queued", "running", "retrying"]),
                    JobQueue.payload["mailbox_id"].astext == str(sync_job.mailbox_id),
                )
                .first()
            )
            if already_pending:
                continue
            db.add(JobQueue(job_type="sync", payload={"mailbox_id": sync_job.mailbox_id}, run_after=now))
            sync_job.last_enqueued_at = now
            db.add(sync_job)
            enqueued += 1
    if enqueued:
        logger.info("Zakolejkowano %d zadań synchronizacji.", enqueued)
    return enqueued


if __name__ == "__main__":
    run_once()
