"""First-class professional knowledge and role-linked contexts.

Revision ID: 0007_professional_knowledge
Revises: 0006_user_oauth
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_professional_knowledge"
down_revision: Union[str, None] = "0006_user_oauth"
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
    tables = set(insp.get_table_names())
    if "professional_knowledge" not in tables:
        op.create_table(
            "professional_knowledge",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("canonical_name", sa.String(length=255), nullable=False, index=True),
            sa.Column("kind", sa.String(length=64), nullable=False, server_default="domain", index=True),
            sa.Column("summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("depth", sa.String(length=32), nullable=False, server_default="applied"),
            sa.Column("years_experience", sa.Float(), nullable=True),
            sa.Column("synonyms", sa.JSON(), nullable=False, server_default=_json_default("[]")),
            sa.Column("evidence_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="unverified"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if "knowledge_contexts" not in tables:
        op.create_table(
            "knowledge_contexts",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column(
                "knowledge_id",
                sa.String(length=36),
                sa.ForeignKey("professional_knowledge.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("experience_id", sa.String(length=36), sa.ForeignKey("experiences.id"), nullable=True, index=True),
            sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id"), nullable=True),
            sa.Column("achievement_id", sa.String(length=36), sa.ForeignKey("achievements.id"), nullable=True),
            sa.Column("education_id", sa.String(length=36), sa.ForeignKey("educations.id"), nullable=True),
            sa.Column("acquisition_mode", sa.String(length=64), nullable=False, server_default="acquired_through_role"),
            sa.Column("how_acquired", sa.Text(), nullable=False, server_default=""),
            sa.Column("how_applied", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_document_id", sa.String(length=36), sa.ForeignKey("career_documents.id"), nullable=True),
            sa.Column("verification_status", sa.String(length=32), nullable=False, server_default="unverified"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0"), index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    if "experiences" not in tables:
        return
    experiences = sa.table(
        "experiences",
        sa.column("id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("domains", sa.JSON),
        sa.column("is_deleted", sa.Boolean),
        sa.column("verification_status", sa.String),
        sa.column("confidence", sa.Float),
    )
    knowledge = sa.table(
        "professional_knowledge",
        sa.column("id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("name", sa.String),
        sa.column("canonical_name", sa.String),
        sa.column("kind", sa.String),
        sa.column("summary", sa.Text),
        sa.column("depth", sa.String),
        sa.column("synonyms", sa.JSON),
        sa.column("evidence_count", sa.Integer),
        sa.column("verification_status", sa.String),
        sa.column("confidence", sa.Float),
        sa.column("is_deleted", sa.Boolean),
    )
    contexts = sa.table(
        "knowledge_contexts",
        sa.column("id", sa.String),
        sa.column("user_id", sa.String),
        sa.column("knowledge_id", sa.String),
        sa.column("experience_id", sa.String),
        sa.column("acquisition_mode", sa.String),
        sa.column("how_acquired", sa.Text),
        sa.column("how_applied", sa.Text),
        sa.column("verification_status", sa.String),
        sa.column("confidence", sa.Float),
        sa.column("is_deleted", sa.Boolean),
    )
    rows = bind.execute(
        sa.select(
            experiences.c.id,
            experiences.c.user_id,
            experiences.c.domains,
            experiences.c.verification_status,
            experiences.c.confidence,
        ).where(experiences.c.is_deleted.is_(False))
    ).fetchall()
    existing = {
        (row.user_id, (row.canonical_name or "").strip().lower()): {"id": row.id, "count": 0}
        for row in bind.execute(
            sa.select(knowledge.c.id, knowledge.c.user_id, knowledge.c.canonical_name).where(
                knowledge.c.is_deleted.is_(False)
            )
        ).fetchall()
    }
    import uuid

    for row in rows:
        for domain in row.domains or []:
            name = str(domain).strip()
            if not name:
                continue
            key = (row.user_id, name.lower())
            found = existing.get(key)
            if found is None:
                knowledge_id = str(uuid.uuid4())
                bind.execute(
                    knowledge.insert().values(
                        id=knowledge_id,
                        user_id=row.user_id,
                        name=name,
                        canonical_name=name,
                        kind="domain",
                        summary="",
                        depth="applied",
                        synonyms=[],
                        evidence_count=1,
                        verification_status=row.verification_status or "unverified",
                        confidence=float(row.confidence or 0.5),
                        is_deleted=False,
                    )
                )
                existing[key] = {"id": knowledge_id, "count": 1}
                knowledge_id = existing[key]["id"]
            else:
                found["count"] += 1
                knowledge_id = found["id"]
                bind.execute(
                    knowledge.update()
                    .where(knowledge.c.id == knowledge_id)
                    .values(evidence_count=found["count"] or 1)
                )
            bind.execute(
                contexts.insert().values(
                    id=str(uuid.uuid4()),
                    user_id=row.user_id,
                    knowledge_id=knowledge_id,
                    experience_id=row.id,
                    acquisition_mode="acquired_through_role",
                    how_acquired="",
                    how_applied="",
                    verification_status=row.verification_status or "unverified",
                    confidence=float(row.confidence or 0.5),
                    is_deleted=False,
                )
            )


def downgrade() -> None:
    op.drop_table("knowledge_contexts")
    op.drop_table("professional_knowledge")
