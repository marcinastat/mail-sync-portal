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


class AcmeDnsConfig(Base, TimestampMixin):
    """Konto w serwerze acme-dns używane do DNS-01 za firewallem. VM1 aktualizuje
    rekord TXT challenge WYŁĄCZNIE w acme-dns (przez username/password), a w
    prawdziwej strefie klienta wpisuje się RAZ CNAME `_acme-challenge.<host>` ->
    fulldomain. Klucz do prawdziwego DNS (np. OVH) nigdy nie trafia na serwer."""

    __tablename__ = "acme_dns_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    acme_dns_server: Mapped[str] = mapped_column(String(255))       # np. https://auth.astat.cloud
    hostname: Mapped[str] = mapped_column(String(255))              # host certyfikatu, np. poczta.example.com
    a_record_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)  # IP do rekordu A (informacyjnie)
    username: Mapped[str] = mapped_column(String(128))             # konto acme-dns
    password_encrypted: Mapped[str] = mapped_column(String(512))   # hasło acme-dns (Fernet)
    subdomain: Mapped[str] = mapped_column(String(128))           # subdomena konta acme-dns
    fulldomain: Mapped[str] = mapped_column(String(255))          # cel CNAME (np. <uuid>.auth.astat.cloud)
    allowfrom: Mapped[str | None] = mapped_column(String(255), nullable=True)  # CIDR-y dozwolone do update (opcjonalnie)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InstanceState(Base, TimestampMixin):
    __tablename__ = "instance_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_run_required: Mapped[bool] = mapped_column(Boolean, default=True)
    setup_step_completed: Mapped[int] = mapped_column(Integer, default=0)
    # Kursor ostatnio zaalarmowanego wykrycia skanu (findings id z VM2) — żeby
    # environment-check nie alarmował w kółko o tym samym.
    last_scan_finding_id: Mapped[int] = mapped_column(Integer, default=0)


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


class SyncScheduleConfig(Base, TimestampMixin):
    """Globalny harmonogram synchronizacji — co ile minut scheduler kolejkuje
    synchronizację KAŻDEJ włączonej skrzynki. Jedna wartość dla całości (prosto
    i czytelnie); ręczny „Synchronizuj teraz" działa niezależnie."""

    __tablename__ = "sync_schedule_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60)  # domyślnie co godzinę


class ImapsyncConfig(Base, TimestampMixin):
    """Globalne, bezpieczne opcje imapsync stosowane do KAŻDEJ synchronizacji
    (skrzynka może dołożyć własne w SyncJob.custom_flags). Pole `custom_flags`
    jest walidowane allowlistą — patrz services/imapsync_flags.py."""

    __tablename__ = "imapsync_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Weryfikacja certyfikatu TLS serwera źródłowego (domyślnie WŁĄCZONA —
    # decyzja: bezpieczniej; można wyłączyć dla źródeł z self-signed).
    verify_source_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    add_missing_headers: Mapped[bool] = mapped_column(Boolean, default=False)   # --addheader
    max_size_mb: Mapped[int] = mapped_column(Integer, default=0)                # --maxsize (0=bez limitu)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=0)            # --timeout (0=domyślny)
    allow_size_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)   # --allowsizemismatch
    # „Kaganiec" na łącze — limit przepustowości w Mbit/s (0 = bez limitu).
    # Przeliczany na bajty/s dla --maxbytespersecond (1 Mbit/s = 125000 B/s).
    max_bandwidth_mbit: Mapped[int] = mapped_column(Integer, default=0)
    custom_flags: Mapped[str] = mapped_column(String(1000), default="")         # walidowane allowlistą


class ScanScheduleConfig(Base, TimestampMixin):
    """Harmonogram skanów antywirusa/antyspamu na VM2. Panel edytuje, a przy
    zapisie wypycha do VM2 (przepisuje systemd timery). Interwał 0 = wyłącz skan
    przyrostowy; full_mode off/daily/weekly (dow 0=pon..6=niedz, godzina)."""

    __tablename__ = "scan_schedule_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    clamav_incremental_minutes: Mapped[int] = mapped_column(Integer, default=60)
    clamav_full_mode: Mapped[str] = mapped_column(String(8), default="daily")     # off|daily|weekly
    clamav_full_dow: Mapped[int] = mapped_column(Integer, default=6)              # 0=pon..6=niedz
    clamav_full_hour: Mapped[int] = mapped_column(Integer, default=3)
    rspamd_incremental_minutes: Mapped[int] = mapped_column(Integer, default=60)
    rspamd_full_mode: Mapped[str] = mapped_column(String(8), default="off")
    rspamd_full_dow: Mapped[int] = mapped_column(Integer, default=6)
    rspamd_full_hour: Mapped[int] = mapped_column(Integer, default=4)


class WebmailSsoConfig(Base, TimestampMixin):
    """Przełącznik funkcji „Otwórz w Roundcube" (SSO admina do skrzynki bez
    hasła). DOMYŚLNIE WYŁĄCZONA — to impersonacja, więc włączenie jest świadomą
    decyzją. Gdy wyłączona: przycisk ukryty i endpoint nie wydaje tokenów, więc
    nie da się otworzyć skrzynki (bez tokenu wtyczka nie ma czego zalogować)."""

    __tablename__ = "webmail_sso_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)


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
