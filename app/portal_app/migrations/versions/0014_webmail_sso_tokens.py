"""webmail_sso_tokens — jednorazowe tokeny „Otwórz w Roundcube".

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webmail_sso_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("mailbox_id", sa.Integer(), nullable=False),
        sa.Column("mailbox_address", sa.String(length=255), nullable=False),
        sa.Column("actor_admin_user_id", sa.Integer(), nullable=True),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_webmail_sso_tokens_token_hash", "webmail_sso_tokens", ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_webmail_sso_tokens_token_hash", table_name="webmail_sso_tokens")
    op.drop_table("webmail_sso_tokens")
