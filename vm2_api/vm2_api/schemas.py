from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class DomainCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DomainOut(BaseModel):
    id: int
    name: str
    is_active: bool
    created_at: datetime


class MailboxCreate(BaseModel):
    domain: str
    local_part: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, description="Hasło w postaci jawnej — lustrzana kopia hasła źródłowego z XLS; nigdy nie jest logowane.")
    quota_mb: int = Field(default=0, ge=0)


class MailboxUpdate(BaseModel):
    quota_mb: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class MailboxResetPassword(BaseModel):
    new_password: str = Field(min_length=1)


class MailboxOut(BaseModel):
    id: int
    domain: str
    local_part: str
    quota_bytes: int
    is_active: bool
    password_overridden: bool
    created_at: datetime
    updated_at: datetime


class AvScanRequest(BaseModel):
    domain: str
    local_part: str


class SystemUpdateRequest(BaseModel):
    # Domyślnie tylko łatki bezpieczeństwa — pełny update wymaga jawnego false.
    security_only: bool = True


class SystemUpdateResult(BaseModel):
    dnf_output_tail: str
    health_check: dict
    reboot_needed: bool
    reboot_confirm_token: str | None
    security_only: bool = True
    backup_path: str | None = None


class SystemRebootRequest(BaseModel):
    confirm_token: str
