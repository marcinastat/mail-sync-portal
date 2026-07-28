"""acme_dns_config — konto acme-dns dla DNS-01 za firewallem.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acme_dns_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("acme_dns_server", sa.String(length=255), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("a_record_ip", sa.String(length=64), nullable=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_encrypted", sa.String(length=512), nullable=False),
        sa.Column("subdomain", sa.String(length=128), nullable=False),
        sa.Column("fulldomain", sa.String(length=255), nullable=False),
        sa.Column("allowfrom", sa.String(length=255), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("acme_dns_config")
