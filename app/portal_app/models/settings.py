from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ThrottlePolicy(Base, TimestampMixin):
    __tablename__ = "throttle_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), default="global")  # "global" | "domain"
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=True)
    max_connections_per_minute: Mapped[int] = mapped_column(Integer, default=10)
    max_connections_per_hour: Mapped[int] = mapped_column(Integer, default=100)
    max_connections_per_day: Mapped[int] = mapped_column(Integer, default=500)
    max_bandwidth_kbps: Mapped[int] = mapped_column(Integer, default=0)  # 0 = bez limitu
    concurrent_job_limit: Mapped[int] = mapped_column(Integer, default=3)


class BrandingConfig(Base, TimestampMixin):
    __tablename__ = "branding_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_name: Mapped[str] = mapped_column(String(120), default="Portal Poczty")
    primary_color: Mapped[str] = mapped_column(String(7), default="#2563eb")
    secondary_color: Mapped[str] = mapped_column(String(7), default="#1e293b")
    accent_color: Mapped[str] = mapped_column(String(7), default="#f59e0b")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TlsConfig(Base, TimestampMixin):
    __tablename__ = "tls_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), default="selfsigned")  # selfsigned | certbot | manual
    certbot_dns_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certbot_last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manual_cert_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manual_key_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manual_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InstanceState(Base, TimestampMixin):
    __tablename__ = "instance_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_run_required: Mapped[bool] = mapped_column(Boolean, default=True)
    setup_step_completed: Mapped[int] = mapped_column(Integer, default=0)


class Vm2Connection(Base, TimestampMixin):
    __tablename__ = "vm2_connection"

    id: Mapped[int] = mapped_column(primary_key=True)
    vm2_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vm2_api_port: Mapped[int] = mapped_column(Integer, default=8443)
    client_cert_path: Mapped[str] = mapped_column(String(500), default="/etc/portal/vm1-client/client.crt")
    client_key_path: Mapped[str] = mapped_column(String(500), default="/etc/portal/vm1-client/client.key")
    ca_cert_path: Mapped[str] = mapped_column(String(500), default="/etc/portal/vm1-client/ca.crt")
    last_health_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_check_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class NetworkAccessConfig(Base, TimestampMixin):
    """Dozwolone sieci źródłowe (CIDR) osobno dla panelu /admin i dla webmaila
    Roundcube. Egzekwowane na poziomie nginx (allow/deny per location) — nie
    firewalld, bo obie usługi dzielą port 443 i trzeba je rozróżnić po ścieżce.
    Puste pole = brak dodatkowego ograniczenia (obowiązuje tylko firewalld).
    Listy CIDR trzymane jako tekst: jeden wpis na linię lub po przecinku."""

    __tablename__ = "network_access_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_networks: Mapped[str] = mapped_column(String(2000), default="")
    webmail_networks: Mapped[str] = mapped_column(String(2000), default="")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertChannel(Base, TimestampMixin):
    __tablename__ = "alert_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_type: Mapped[str] = mapped_column(String(16))  # email | webhook
    target: Mapped[str] = mapped_column(String(500))
    events: Mapped[str] = mapped_column(String(500), default="sync_failed,av_infected,cert_expiring,update_failed")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
