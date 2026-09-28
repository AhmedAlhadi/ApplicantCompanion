"""Background document ingest status.

Revision ID: 0010_document_ingest_status
Revises: 0009_career_coach
Create Date: 2026-09-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_document_ingest_status"
down_revision: Union[str, None] = "0009_career_coach"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_default(value: str) -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text(f"'{value}'::json")
    return sa.text(f"'{value}'")


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if table not in tables:
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    cols = _columns("career_documents")
    if "ingest_status" not in cols:
        op.add_column(
            "career_documents",
            sa.Column("ingest_status", sa.String(length=32), nullable=False, server_default="idle"),
        )
    if "ingest_error" not in cols:
        op.add_column(
            "career_documents",
            sa.Column("ingest_error", sa.Text(), nullable=False, server_default=""),
        )
    if "ingest_result" not in cols:
        op.add_column(
            "career_documents",
            sa.Column("ingest_result", sa.JSON(), nullable=False, server_default=_json_default("{}")),
        )


def downgrade() -> None:
    cols = _columns("career_documents")
    if "ingest_result" in cols:
        op.drop_column("career_documents", "ingest_result")
    if "ingest_error" in cols:
        op.drop_column("career_documents", "ingest_error")
    if "ingest_status" in cols:
        op.drop_column("career_documents", "ingest_status")
