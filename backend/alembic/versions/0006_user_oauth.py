"""Nullable password_hash plus Google identity columns on users.

Revision ID: 0006_user_oauth
Revises: 0005_score_range
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_user_oauth"
down_revision: Union[str, None] = "0005_score_range"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if "google_sub" not in cols:
        op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
        op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)
    if "avatar_url" not in cols:
        op.add_column("users", sa.Column("avatar_url", sa.String(length=1000), nullable=True))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(length=255), nullable=False)
    if "avatar_url" in cols:
        op.drop_column("users", "avatar_url")
    if "google_sub" in cols:
        op.drop_index("ix_users_google_sub", table_name="users")
        op.drop_column("users", "google_sub")
