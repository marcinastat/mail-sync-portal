"""domain_login_aliases — dodatkowe domeny logowania (alias -> domena kanoniczna).

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domain_login_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain_id", sa.Integer(), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias_name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_domain_login_aliases_domain_id", "domain_login_aliases", ["domain_id"])


def downgrade() -> None:
    op.drop_index("ix_domain_login_aliases_domain_id", table_name="domain_login_aliases")
    op.drop_table("domain_login_aliases")
