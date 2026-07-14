"""Przebiegi aktualizacji systemu (system_update_runs) — aktualizacje w tle.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_update_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host", sa.String(length=8), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("phase", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output", sa.Text(), nullable=False, server_default=""),
        sa.Column("reboot_needed", sa.Boolean(), nullable=True),
        sa.Column("healthy", sa.Boolean(), nullable=True),
        sa.Column("backup_path", sa.String(length=500), nullable=True),
        sa.Column("reboot_token", sa.String(length=128), nullable=True),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("actor_admin_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("system_update_runs")
