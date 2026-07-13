from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Domain(Base, TimestampMixin):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_domain: Mapped[str] = mapped_column(String(255), unique=True)
    destination_domain: Mapped[str] = mapped_column(String(255))
    # Hostname/port źródłowego serwera IMAP (może się różnić od samej domeny
    # pocztowej, np. skrzynki @firma.pl obsługiwane przez imap.dostawca.pl).
    source_imap_host: Mapped[str] = mapped_column(String(255))
    source_imap_port: Mapped[int] = mapped_column(default=993)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
