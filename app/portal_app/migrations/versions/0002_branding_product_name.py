"""Dodaje branding_config.product_name (edytowalny podpis "Portal Poczty").

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "branding_config",
        sa.Column("product_name", sa.String(length=120), nullable=False, server_default="Portal Poczty"),
    )


def downgrade() -> None:
    op.drop_column("branding_config", "product_name")
