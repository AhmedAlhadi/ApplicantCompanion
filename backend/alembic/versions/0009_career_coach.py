"""Career Coach persistence.

Revision ID: 0009_career_coach
Revises: 0008_cross_sector_profile
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_career_coach"
down_revision: Union[str, None] = "0008_cross_sector_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_default(value: str) -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text(f"'{value}'::json")
    return sa.text(f"'{value}'")


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "coach_conversations" not in tables:
        op.create_table(
            "coach_conversations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id"), nullable=True),
            sa.Column("application_id", sa.String(length=36), sa.ForeignKey("applications.id"), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "coach_messages" not in tables:
        op.create_table(
            "coach_messages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("conversation_id", sa.String(length=36), sa.ForeignKey("coach_conversations.id"), nullable=False, index=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
            sa.Column("content", sa.Text(), nullable=False, server_default=""),
            sa.Column("citations", sa.JSON(), nullable=False, server_default=_json_default("[]")),
            sa.Column("token_usage", sa.JSON(), nullable=False, server_default=_json_default("{}")),
            sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "coach_messages" in tables:
        op.drop_table("coach_messages")
    if "coach_conversations" in tables:
        op.drop_table("coach_conversations")
