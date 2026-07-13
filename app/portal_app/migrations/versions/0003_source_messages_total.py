"""Dodaje job_runs.source_messages_total (liczba wiadomości na źródle).

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_runs",
        sa.Column("source_messages_total", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("job_runs", "source_messages_total")
