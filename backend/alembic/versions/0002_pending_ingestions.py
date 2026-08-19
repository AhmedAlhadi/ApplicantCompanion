"""Add pending_ingestions table for human-in-the-loop reconciliation.

Revision ID: 0002_pending_ingestions
Revises: 0001_initial
Create Date: 2026-08-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_pending_ingestions"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "pending_ingestions" in insp.get_table_names():
        return
    op.create_table(
        "pending_ingestions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("career_documents.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending", index=True),
        sa.Column("proposals", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("auto_applied", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("pending_ingestions")
