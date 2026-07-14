"""Globalne opcje imapsync (imapsync_config) + per-skrzynka sync_jobs.custom_flags.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imapsync_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("verify_source_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("add_missing_headers", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_size_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allow_size_mismatch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("custom_flags", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("sync_jobs", sa.Column("custom_flags", sa.String(length=1000), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("sync_jobs", "custom_flags")
    op.drop_table("imapsync_config")
