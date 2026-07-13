from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..deps import get_db, require_login, require_setup_complete
from ..models import AdminUser, AuditLog, BrandingConfig, JobQueue, JobRun, Mailbox, Vm2Connection
from ..services import vm2_client

router = APIRouter(prefix="/admin", tags=["dashboard"])
templates = Jinja2Templates(directory="portal_app/templates")

ACTIVE_CERT_PATH = Path("/etc/portal/tls/active/fullchain.pem")


def _cert_days_left() -> int | None:
    if not ACTIVE_CERT_PATH.exists():
        return None
    cert = x509.load_pem_x509_certificate(ACTIVE_CERT_PATH.read_bytes())
    return (cert.not_valid_after_utc - datetime.now(timezone.utc)).days


def _queue_depth(db: Session) -> dict:
    rows = db.query(JobQueue.status, func.count(JobQueue.id)).group_by(JobQueue.status).all()
    return dict(rows)


def _latest_drift_total(db: Session) -> int:
    subq = (
        db.query(JobRun.mailbox_id, func.max(JobRun.id).label("max_id"))
        .filter(JobRun.status == "success")
        .group_by(JobRun.mailbox_id)
        .subquery()
    )
    total = (
        db.query(func.coalesce(func.sum(JobRun.messages_missing_from_source_retained), 0))
        .join(subq, JobRun.id == subq.c.max_id)
        .scalar()
    )
    return total or 0


@router.get("/", dependencies=[Depends(require_setup_complete)])
def dashboard(
    request: Request,
    current_user: AdminUser = Depends(require_login),
    db: Session = Depends(get_db),
):
    branding = db.query(BrandingConfig).first()
    mailbox_count = db.query(func.count(Mailbox.id)).scalar() or 0
    active_mailbox_count = db.query(func.count(Mailbox.id)).filter(Mailbox.provisioning_status == "active").scalar() or 0
    recent_audit = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(10).all()

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

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "current_user": current_user,
            "branding": branding,
            "mailbox_count": mailbox_count,
            "active_mailbox_count": active_mailbox_count,
            "queue_depth": _queue_depth(db),
            "cert_days_left": _cert_days_left(),
            "drift_total": _latest_drift_total(db),
            "recent_audit": recent_audit,
            "vm2_status": vm2_status,
        },
    )
