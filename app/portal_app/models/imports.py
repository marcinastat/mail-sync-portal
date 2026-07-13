from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"))
    original_filename: Mapped[str] = mapped_column(String(255))
    archive_type: Mapped[str] = mapped_column(String(8))  # zip | 7z | rar
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="parsed")  # parsed | committed | failed


class ImportRow(Base, TimestampMixin):
    __tablename__ = "import_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"))
    raw_row: Mapped[dict] = mapped_column(JSONB)
    # new | duplicate_in_file | existing_unchanged | existing_updated
    match_type: Mapped[str] = mapped_column(String(24), default="new")
    validation_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | valid | invalid
    validation_errors: Mapped[list] = mapped_column(JSONB, default=list)
    resulting_credential_id: Mapped[int | None] = mapped_column(ForeignKey("credentials.id"), nullable=True)
