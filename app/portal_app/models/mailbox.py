from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Credential(Base, TimestampMixin):
    __tablename__ = "credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id", ondelete="RESTRICT"))
    auth_type: Mapped[str] = mapped_column(String(16), default="password")  # fundament pod przyszły OAuth2
    source_username: Mapped[str] = mapped_column(String(255))
    source_password_encrypted: Mapped[str] = mapped_column(String(1024))
    destination_username: Mapped[str] = mapped_column(String(255))
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_provision")


class Mailbox(Base, TimestampMixin):
    __tablename__ = "mailboxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id", ondelete="RESTRICT"))
    credential_id: Mapped[int] = mapped_column(ForeignKey("credentials.id", ondelete="RESTRICT"), unique=True)
    source_address: Mapped[str] = mapped_column(String(255))
    destination_address: Mapped[str] = mapped_column(String(255))
    vm2_mailbox_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provisioning_status: Mapped[str] = mapped_column(String(32), default="pending")
    quota_mb: Mapped[int] = mapped_column(Integer, default=0)
    # True po ręcznym resecie hasła na VM2 — blokuje nadpisanie lustrzaną
    # kopią hasła źródłowego przy kolejnym imporcie/re-provisioningu.
    password_override: Mapped[bool] = mapped_column(Boolean, default=False)
