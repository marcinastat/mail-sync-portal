"""imapsync_config.max_bandwidth_mbit — limit przepustowości (Mbit/s).

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "imapsync_config",
        sa.Column("max_bandwidth_mbit", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("imapsync_config", "max_bandwidth_mbit")
