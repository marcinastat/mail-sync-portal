"""Globalny harmonogram synchronizacji (sync_schedule_config.interval_minutes).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_schedule_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sync_schedule_config")
