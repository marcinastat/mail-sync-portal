from sqlalchemy import Boolean, ForeignKey, Integer, String
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
    # Domyślny limit (quota) w MB dziedziczony przez NOWE skrzynki tej domeny
    # (0 = bez limitu). Można też jednorazowo wypchnąć na wszystkie istniejące
    # skrzynki domeny — patrz routers/domains.py.
    default_quota_mb: Mapped[int] = mapped_column(Integer, default=0)
    # WSPÓLNA PULA na całą domenę (MB, 0 = bez limitu). To NIE jest limit per
    # skrzynka — to jeden wspólny limit dzielony przez wszystkie skrzynki domeny.
    # Zużycie liczymy na poziomie aplikacji jako SUM(mailboxes.dest_bytes) (cache
    # z doveadm po synchronizacji) — bez XFS/Dovecot-dict, prosto i czytelnie.
    # Przekroczenie sygnalizuje panel (metr) i alert z workera environment-check.
    total_quota_mb: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DomainLoginAlias(Base, TimestampMixin):
    """Dodatkowa nazwa domeny, pod którą można zalogować się do skrzynek domeny
    kanonicznej (domain_id). Np. skrzynki pod example.com, ale historyczne loginy
    user@example.net — oba mają wskazywać tę samą pocztę. Portal trzyma to jako
    źródło prawdy i wypycha na VM2 (virtual_domain_aliases) przy dodaniu/usunięciu;
    faktyczne dopasowanie loginu robią zapytania Dovecota (patrz templates/dovecot/
    dovecot-sql.conf.ext.tmpl). Alias jest GLOBALNIE unikalny (jedna domena logowania
    nie może wskazywać dwóch skrzynkowych)."""

    __tablename__ = "domain_login_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), index=True)
    alias_name: Mapped[str] = mapped_column(String(255), unique=True)
