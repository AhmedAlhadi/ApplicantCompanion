"""Persist structured alternative qualification paths and evaluations.

Revision ID: 0004_qualification_paths
Revises: 0003_achievement_parent_links
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_qualification_paths"
down_revision: Union[str, None] = "0003_achievement_parent_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_default(value: str) -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text(f"'{value}'::json")
    return sa.text(f"'{value}'")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    requirement_cols = (
        {c["name"] for c in insp.get_columns("job_requirements")}
        if "job_requirements" in insp.get_table_names()
        else set()
    )
    match_cols = (
        {c["name"] for c in insp.get_columns("requirement_matches")}
        if "requirement_matches" in insp.get_table_names()
        else set()
    )
    if "qualification_paths" not in requirement_cols:
        op.add_column(
            "job_requirements",
            sa.Column(
                "qualification_paths",
                sa.JSON(),
                nullable=False,
                server_default=_json_default("[]"),
            ),
        )
    if "qualification_evaluation" not in match_cols:
        op.add_column(
            "requirement_matches",
            sa.Column(
                "qualification_evaluation",
                sa.JSON(),
                nullable=False,
                server_default=_json_default("{}"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    match_cols = (
        {c["name"] for c in insp.get_columns("requirement_matches")}
        if "requirement_matches" in insp.get_table_names()
        else set()
    )
    requirement_cols = (
        {c["name"] for c in insp.get_columns("job_requirements")}
        if "job_requirements" in insp.get_table_names()
        else set()
    )
    if "qualification_evaluation" in match_cols:
        op.drop_column("requirement_matches", "qualification_evaluation")
    if "qualification_paths" in requirement_cols:
        op.drop_column("job_requirements", "qualification_paths")
