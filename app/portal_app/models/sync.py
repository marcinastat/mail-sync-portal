from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SyncJob(Base, TimestampMixin):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox_id: Mapped[int] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"), unique=True)
    schedule_cron: Mapped[str] = mapped_column(String(64), default="0 * * * *")
    days_back: Mapped[int] = mapped_column(Integer, default=365)
    preserve_folder_structure: Mapped[bool] = mapped_column(Boolean, default=True)
    delete_on_dest_when_missing_from_source: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobQueue(Base, TimestampMixin):
    __tablename__ = "job_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32))  # sync | provision | import | av_scan | alert | audit_verify
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed|retrying
    priority: Mapped[int] = mapped_column(Integer, default=100)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)


class JobRun(Base, TimestampMixin):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_job_id: Mapped[int | None] = mapped_column(ForeignKey("sync_jobs.id", ondelete="SET NULL"), nullable=True)
    job_queue_id: Mapped[int | None] = mapped_column(ForeignKey("job_queue.id", ondelete="SET NULL"), nullable=True)
    mailbox_id: Mapped[int] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|partial|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    messages_transferred: Mapped[int] = mapped_column(Integer, default=0)
    bytes_transferred: Mapped[int] = mapped_column(BigInteger, default=0)
    folders_synced: Mapped[int] = mapped_column(Integer, default=0)
    folders_total: Mapped[int] = mapped_column(Integer, default=0)
    messages_total: Mapped[int] = mapped_column(Integer, default=0)
    # Liczba wiadomości na skrzynce ŹRÓDŁOWEJ (suma po folderach host1),
    # niezależna od --maxage — pokazuje ile w ogóle jest do zsynchronizowania.
    source_messages_total: Mapped[int] = mapped_column(Integer, default=0)
    # Wiadomości obecne na VM2, których już nie ma w źródle (zachowane
    # zgodnie z domyślną polityką "nie kasuj na docelowym") — wskaźnik "drift".
    messages_missing_from_source_retained: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    imapsync_log_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
