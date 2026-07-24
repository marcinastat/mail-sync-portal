from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class WebmailSsoToken(Base, TimestampMixin):
    """Jednorazowy token „Otwórz w Roundcube" — handoff panel -> Roundcube.
    Panel zapisuje HASH tokenu (nie surowy) + docelową skrzynkę i admina; wtyczka
    Roundcube waliduje go (hash, TTL, jednorazowość) i loguje jako master user.
    Krótki TTL, `used_at` = jednorazowość (atomowe UPDATE ... WHERE used_at IS NULL)."""

    __tablename__ = "webmail_sso_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # sha256 hex
    mailbox_id: Mapped[int] = mapped_column(Integer)
    mailbox_address: Mapped[str] = mapped_column(String(255))
    actor_admin_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
