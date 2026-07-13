from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import JobRun, ThrottlePolicy


def get_global_policy(db: Session) -> ThrottlePolicy:
    policy = db.query(ThrottlePolicy).filter(ThrottlePolicy.scope == "global").first()
    if policy is None:
        policy = ThrottlePolicy(scope="global")
        db.add(policy)
        db.flush()
    return policy


def _count_runs_since(db: Session, since: datetime) -> int:
    return db.query(func.count(JobRun.id)).filter(JobRun.started_at >= since).scalar() or 0


def can_start_sync_now(db: Session, policy: ThrottlePolicy) -> tuple[bool, str | None]:
    now = datetime.now(timezone.utc)
    running = db.query(func.count(JobRun.id)).filter(JobRun.status == "running").scalar() or 0
    if running >= policy.concurrent_job_limit:
        return False, "concurrent_job_limit"
    if _count_runs_since(db, now - timedelta(minutes=1)) >= policy.max_connections_per_minute:
        return False, "max_connections_per_minute"
    if _count_runs_since(db, now - timedelta(hours=1)) >= policy.max_connections_per_hour:
        return False, "max_connections_per_hour"
    if _count_runs_since(db, now - timedelta(days=1)) >= policy.max_connections_per_day:
        return False, "max_connections_per_day"
    return True, None
