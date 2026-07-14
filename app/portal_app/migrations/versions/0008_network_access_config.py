"""Dodaje network_access_config — dozwolone sieci (CIDR) osobno dla /admin i
dla webmaila Roundcube (egzekwowane w nginx allow/deny per location).

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "network_access_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_networks", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("webmail_networks", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("network_access_config")
