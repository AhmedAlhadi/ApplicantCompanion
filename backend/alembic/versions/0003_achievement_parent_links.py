"""Add optional project_id and education_id on achievements.

Revision ID: 0003_achievement_parent_links
Revises: 0002_pending_ingestions
Create Date: 2026-08-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_achievement_parent_links"
down_revision: Union[str, None] = "0002_pending_ingestions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "achievements",
        sa.Column("project_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "achievements",
        sa.Column("education_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_achievements_project_id",
        "achievements",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_achievements_education_id",
        "achievements",
        "educations",
        ["education_id"],
        ["id"],
    )
    op.create_index("ix_achievements_project_id", "achievements", ["project_id"])
    op.create_index("ix_achievements_education_id", "achievements", ["education_id"])


def downgrade() -> None:
    op.drop_index("ix_achievements_education_id", table_name="achievements")
    op.drop_index("ix_achievements_project_id", table_name="achievements")
    op.drop_constraint("fk_achievements_education_id", "achievements", type_="foreignkey")
    op.drop_constraint("fk_achievements_project_id", "achievements", type_="foreignkey")
    op.drop_column("achievements", "education_id")
    op.drop_column("achievements", "project_id")
