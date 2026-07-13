"""Dodaje domains.total_quota_mb — WSPÓLNA PULA quoty na całą domenę
(0 = bez limitu). Zużycie liczone aplikacyjnie z SUM(mailboxes.dest_bytes).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domains", sa.Column("total_quota_mb", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("domains", "total_quota_mb")
