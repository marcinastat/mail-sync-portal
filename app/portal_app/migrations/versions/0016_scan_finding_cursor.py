"""instance_state.last_scan_finding_id — kursor alertów o wykryciach skanu.

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instance_state",
        sa.Column("last_scan_finding_id", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("instance_state", "last_scan_finding_id")
