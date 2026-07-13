"""Dodaje mailboxes.source_bytes / dest_bytes (cache rozmiarów skrzynki).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mailboxes", sa.Column("source_bytes", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("mailboxes", sa.Column("dest_bytes", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("mailboxes", "dest_bytes")
    op.drop_column("mailboxes", "source_bytes")
