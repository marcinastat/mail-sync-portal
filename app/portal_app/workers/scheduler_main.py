import logging
from datetime import datetime, timedelta, timezone

from ..db import session_scope
from ..models import JobQueue, SyncScheduleConfig, SyncJob

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("portal.scheduler")

DEFAULT_INTERVAL_MINUTES = 60


def _interval(db) -> timedelta:
    cfg = db.query(SyncScheduleConfig).first()
    minutes = cfg.interval_minutes if cfg and cfg.interval_minutes and cfg.interval_minutes > 0 else DEFAULT_INTERVAL_MINUTES
    return timedelta(minutes=minutes)


def run_once() -> int:
    """Globalny interwał: kolejkuje synchronizację skrzynki, gdy od ostatniego
    zakolejkowania minął ustawiony czas (Ustawienia → Harmonogram synchronizacji)."""
    enqueued = 0
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        interval = _interval(db)
        sync_jobs = db.query(SyncJob).filter(SyncJob.is_enabled.is_(True)).all()
        for sync_job in sync_jobs:
            if sync_job.last_enqueued_at is not None and (now - sync_job.last_enqueued_at) < interval:
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
            db.add(JobQueue(
                job_type="sync",
                payload={"mailbox_id": sync_job.mailbox_id, "trigger": "scheduled"},
                run_after=now,
            ))
            sync_job.last_enqueued_at = now
            db.add(sync_job)
            enqueued += 1
    if enqueued:
        logger.info("Zakolejkowano %d zadań synchronizacji.", enqueued)
    return enqueued


if __name__ == "__main__":
    run_once()
