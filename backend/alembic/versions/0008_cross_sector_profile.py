"""Profession context, credential types, and uncategorized skill default.

Revision ID: 0008_cross_sector_profile
Revises: 0007_professional_knowledge
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008_cross_sector_profile"
down_revision: Union[str, None] = "0007_professional_knowledge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_default(value: str) -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text(f"'{value}'::json")
    return sa.text(f"'{value}'")


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    profile_cols = _columns("career_profiles")
    if "primary_profession" not in profile_cols:
        op.add_column(
            "career_profiles",
            sa.Column("primary_profession", sa.String(length=255), nullable=False, server_default=""),
        )
    if "target_sectors" not in profile_cols:
        op.add_column(
            "career_profiles",
            sa.Column("target_sectors", sa.JSON(), nullable=False, server_default=_json_default("[]")),
        )

    cert_cols = _columns("certifications")
    if "credential_type" not in cert_cols:
        op.add_column(
            "certifications",
            sa.Column("credential_type", sa.String(length=64), nullable=False, server_default=""),
        )

    bind = op.get_bind()
    if "skills" in sa.inspect(bind).get_table_names():
        bind.execute(
            sa.text("UPDATE skills SET category = 'uncategorized' WHERE category IS NULL OR TRIM(category) = ''")
        )


def downgrade() -> None:
    cert_cols = _columns("certifications")
    if "credential_type" in cert_cols:
        op.drop_column("certifications", "credential_type")
    profile_cols = _columns("career_profiles")
    if "target_sectors" in profile_cols:
        op.drop_column("career_profiles", "target_sectors")
    if "primary_profession" in profile_cols:
        op.drop_column("career_profiles", "primary_profession")
