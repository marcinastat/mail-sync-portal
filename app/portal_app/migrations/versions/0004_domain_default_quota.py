"""Dodaje domains.default_quota_mb (domyślna quota per domena).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "domains",
        sa.Column("default_quota_mb", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("domains", "default_quota_mb")
