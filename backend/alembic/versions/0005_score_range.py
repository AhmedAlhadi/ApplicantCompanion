"""Add score uncertainty range and coverage to job_scores.

Revision ID: 0005_score_range
Revises: 0004_qualification_paths
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_score_range"
down_revision: Union[str, None] = "0004_qualification_paths"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = (
        {c["name"] for c in insp.get_columns("job_scores")}
        if "job_scores" in insp.get_table_names()
        else set()
    )
    if "overall_score_low" not in cols:
        op.add_column("job_scores", sa.Column("overall_score_low", sa.Float(), nullable=True))
    if "overall_score_high" not in cols:
        op.add_column("job_scores", sa.Column("overall_score_high", sa.Float(), nullable=True))
    if "coverage" not in cols:
        op.add_column("job_scores", sa.Column("coverage", sa.Float(), nullable=False, server_default="1.0"))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = (
        {c["name"] for c in insp.get_columns("job_scores")}
        if "job_scores" in insp.get_table_names()
        else set()
    )
    if "coverage" in cols:
        op.drop_column("job_scores", "coverage")
    if "overall_score_high" in cols:
        op.drop_column("job_scores", "overall_score_high")
    if "overall_score_low" in cols:
        op.drop_column("job_scores", "overall_score_low")
