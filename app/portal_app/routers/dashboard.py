from datetime import datetime, timedelta, timezone
from pathlib import Path

from croniter import croniter
from cryptography import x509
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import get_db, require_login, require_setup_complete
from ..models import AdminUser, AuditLog, JobQueue, JobRun, Mailbox, SyncJob, ThrottlePolicy, Vm2Connection
from ..services import vm2_client
from ..services.throttle_service import get_global_policy
from ..templating import templates

router = APIRouter(prefix="/admin", tags=["dashboard"])

ACTIVE_CERT_PATH = Path("/etc/portal/tls/active/fullchain.pem")


def _cert_days_left() -> int | None:
    if not ACTIVE_CERT_PATH.exists():
        return None
    cert = x509.load_pem_x509_certificate(ACTIVE_CERT_PATH.read_bytes())
    return (cert.not_valid_after_utc - datetime.now(timezone.utc)).days


def _queue_depth(db: Session) -> dict:
    rows = db.query(JobQueue.status, func.count(JobQueue.id)).group_by(JobQueue.status).all()
    return dict(rows)


def _latest_run_subquery(db: Session):
    return (
        db.query(JobRun.mailbox_id, func.max(JobRun.id).label("max_id"))
        .filter(JobRun.status == "success")
        .group_by(JobRun.mailbox_id)
        .subquery()
    )


def _sync_summary(db: Session) -> dict:
    subq = _latest_run_subquery(db)
    latest = db.query(JobRun).join(subq, JobRun.id == subq.c.max_id)
    rows = latest.all()
    synced_mailboxes = len(rows)
    drift_total = sum(r.messages_missing_from_source_retained for r in rows)
    # łączna liczba wiadomości obecnych na docelowym wg ostatnich udanych sync
    messages_on_dest = sum(r.messages_total for r in rows)
    total_transferred = db.query(func.coalesce(func.sum(JobRun.messages_transferred), 0)).scalar() or 0
    last_sync_at = db.query(func.max(JobRun.finished_at)).scalar()
    running = db.query(func.count(JobRun.id)).filter(JobRun.status == "running").scalar() or 0
    failed_recent = (
        db.query(func.count(JobRun.id))
        .filter(JobRun.status == "failed", JobRun.started_at >= datetime.now(timezone.utc) - timedelta(days=1))
        .scalar()
        or 0
    )
    return {
        "synced_mailboxes": synced_mailboxes,
        "messages_on_dest": messages_on_dest,
        "total_transferred": total_transferred,
        "drift_total": drift_total,
        "last_sync_at": last_sync_at,
        "running": running,
        "failed_recent": failed_recent,
    }


def _next_sync(db: Session) -> datetime | None:
    now = datetime.now(timezone.utc)
    soonest = None
    for sj in db.query(SyncJob).filter(SyncJob.is_enabled.is_(True)).all():
        base = sj.last_enqueued_at or (now - timedelta(days=1))
        try:
            nxt = croniter(sj.schedule_cron, base).get_next(datetime)
        except (ValueError, KeyError):
            continue
        nxt = nxt.replace(tzinfo=timezone.utc) if nxt.tzinfo is None else nxt
        if nxt < now:
            nxt = now
        if soonest is None or nxt < soonest:
            soonest = nxt
    return soonest


def _throttle_state(db: Session, policy: ThrottlePolicy) -> dict:
    now = datetime.now(timezone.utc)

    def cnt(since):
        return db.query(func.count(JobRun.id)).filter(JobRun.started_at >= since).scalar() or 0

    running = db.query(func.count(JobRun.id)).filter(JobRun.status == "running").scalar() or 0
    return {
        "minute": {"used": cnt(now - timedelta(minutes=1)), "max": policy.max_connections_per_minute},
        "hour": {"used": cnt(now - timedelta(hours=1)), "max": policy.max_connections_per_hour},
        "day": {"used": cnt(now - timedelta(days=1)), "max": policy.max_connections_per_day},
        "concurrent": {"used": running, "max": policy.concurrent_job_limit},
    }


def _daily_volume(db: Session, days: int = 14) -> list[dict]:
    """Wiadomości przesłane per dzień (do wykresu na dashboardzie)."""
    since = datetime.now(timezone.utc) - timedelta(days=days - 1)
    rows = (
        db.query(
            func.date_trunc("day", JobRun.started_at).label("d"),
            func.coalesce(func.sum(JobRun.messages_transferred), 0).label("n"),
        )
        .filter(JobRun.started_at >= since.replace(hour=0, minute=0, second=0, microsecond=0))
        .group_by("d")
        .all()
    )
    by_day = {r.d.date(): int(r.n) for r in rows}
    out = []
    base = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
    for i in range(days):
        d = base + timedelta(days=i)
        out.append({"day": d.strftime("%m-%d"), "count": by_day.get(d, 0)})
    return out


@router.get("/", dependencies=[Depends(require_setup_complete)])
def dashboard(
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    mailbox_count = db.query(func.count(Mailbox.id)).scalar() or 0
    active_mailbox_count = db.query(func.count(Mailbox.id)).filter(Mailbox.provisioning_status == "active").scalar() or 0
    recent_audit = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()
    policy = get_global_policy(db)

    conn = db.query(Vm2Connection).first()
    vm2_status: dict = {"configured": conn is not None and bool(conn.vm2_host)}
    if vm2_status["configured"]:
        vm2_status["last_health_check_ok"] = conn.last_health_check_ok
        vm2_status["last_health_check_at"] = conn.last_health_check_at
        try:
            vm2_status["disk_usage"] = vm2_client.disk_usage(conn)
        except vm2_client.Vm2ApiError:
            vm2_status["disk_usage"] = None
        try:
            vm2_status["av"] = vm2_client.av_status(conn)
        except vm2_client.Vm2ApiError:
            vm2_status["av"] = None

    volume = _daily_volume(db)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "current_user": current_user,
            "mailbox_count": mailbox_count,
            "active_mailbox_count": active_mailbox_count,
            "queue_depth": _queue_depth(db),
            "cert_days_left": _cert_days_left(),
            "sync": _sync_summary(db),
            "next_sync": _next_sync(db),
            "throttle": _throttle_state(db, policy),
            "volume": volume,
            "volume_max": max((v["count"] for v in volume), default=0),
            "recent_audit": recent_audit,
            "vm2_status": vm2_status,
        },
    )
