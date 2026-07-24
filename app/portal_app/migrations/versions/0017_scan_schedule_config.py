"""scan_schedule_config — harmonogram skanów ClamAV/rspamd (konfigurowalny).

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scan_schedule_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clamav_incremental_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("clamav_full_mode", sa.String(length=8), nullable=False, server_default="daily"),
        sa.Column("clamav_full_dow", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("clamav_full_hour", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("rspamd_incremental_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("rspamd_full_mode", sa.String(length=8), nullable=False, server_default="off"),
        sa.Column("rspamd_full_dow", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("rspamd_full_hour", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scan_schedule_config")
