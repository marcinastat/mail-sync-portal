from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SystemUpdateRun(Base, TimestampMixin):
    """Jeden przebieg aktualizacji systemu (VM1 lub VM2), wykonywany przez
    portal-worker w tle. Web tylko zakłada rekord + kolejkuje joba i odpytuje
    ten wiersz (modal z postępem). Dzięki temu długi `dnf` nie blokuje żądania
    HTTP (gunicorn i tak zabiłby workera po --timeout)."""

    __tablename__ = "system_update_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(8))  # vm1 | vm2
    mode: Mapped[str] = mapped_column(String(16))  # security | all
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | success | failed
    # Faza pokazywana w modalu; klucz maszynowy (etykietę PL dokłada front).
    phase: Mapped[str] = mapped_column(String(32), default="queued")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Narastający ogon wyjścia (backup + dnf + health) — do podglądu w modalu.
    output: Mapped[str] = mapped_column(Text, default="")
    reboot_needed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    healthy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    backup_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Ścieżka pliku logu na maszynie, która wykonała aktualizację (VM1: /var/log/
    # portal/system-updates, VM2: /var/log/vm2-api/system-updates) — pełne wyjście
    # zachowane trwale, niezależnie od okna w panelu.
    log_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Token potwierdzający reboot zwrócony przez API VM2 (VM1 rebootuje sudo).
    reboot_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    actor_admin_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
