"""system_update_runs.log_path — ścieżka trwałego logu aktualizacji na VMce.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("system_update_runs", sa.Column("log_path", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("system_update_runs", "log_path")
