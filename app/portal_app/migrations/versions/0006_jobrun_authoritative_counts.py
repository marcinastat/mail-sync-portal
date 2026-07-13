"""Autorytatywne liczniki imapsync na job_runs (realny stan skrzynek + duplikaty
+ faktyczne braki) — do rzetelnego, nie-alarmującego pokazania w panelu.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_runs", sa.Column("dest_nb_messages", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("job_runs", sa.Column("source_nb_messages", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("job_runs", sa.Column("source_duplicates", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("job_runs", sa.Column("source_missing", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("job_runs", "source_missing")
    op.drop_column("job_runs", "source_duplicates")
    op.drop_column("job_runs", "source_nb_messages")
    op.drop_column("job_runs", "dest_nb_messages")
