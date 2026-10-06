"""Idempotent database initialization + seed entrypoint.

Used by docker-compose at container start and by developers:
    python -m app.db_init
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from .database import Base, engine
from . import models  # noqa: F401  (register tables)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_additive_columns()
    logger.info("Database schema ensured.")


def _json_default(value: str) -> str:
    """Return a dialect-safe JSON literal for ALTER TABLE defaults."""
    literal = f"'{value}'"
    if engine.dialect.name == "postgresql":
        return f"{literal}::json"
    return literal


def _table_columns(insp, table: str) -> set[str]:
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _ensure_additive_columns() -> None:
    """create_all does not ALTER existing tables — patch additive columns."""
    insp = inspect(engine)
    statements: list[str] = []

    achievement_cols = _table_columns(insp, "achievements")
    if achievement_cols:
        if "project_id" not in achievement_cols:
            statements.append("ALTER TABLE achievements ADD COLUMN project_id VARCHAR(36)")
        if "education_id" not in achievement_cols:
            statements.append("ALTER TABLE achievements ADD COLUMN education_id VARCHAR(36)")

    requirement_cols = _table_columns(insp, "job_requirements")
    if requirement_cols and "qualification_paths" not in requirement_cols:
        statements.append(
            "ALTER TABLE job_requirements ADD COLUMN qualification_paths "
            f"JSON NOT NULL DEFAULT {_json_default('[]')}"
        )

    match_cols = _table_columns(insp, "requirement_matches")
    if match_cols and "qualification_evaluation" not in match_cols:
        statements.append(
            "ALTER TABLE requirement_matches ADD COLUMN qualification_evaluation "
            f"JSON NOT NULL DEFAULT {_json_default('{}')}"
        )

    score_cols = _table_columns(insp, "job_scores")
    if score_cols:
        if "overall_score_low" not in score_cols:
            statements.append("ALTER TABLE job_scores ADD COLUMN overall_score_low FLOAT")
        if "overall_score_high" not in score_cols:
            statements.append("ALTER TABLE job_scores ADD COLUMN overall_score_high FLOAT")
        if "coverage" not in score_cols:
            statements.append("ALTER TABLE job_scores ADD COLUMN coverage FLOAT NOT NULL DEFAULT 1.0")

    profile_cols = _table_columns(insp, "career_profiles")
    if profile_cols:
        if "primary_profession" not in profile_cols:
            statements.append(
                "ALTER TABLE career_profiles ADD COLUMN primary_profession VARCHAR(255) NOT NULL DEFAULT ''"
            )
        if "target_sectors" not in profile_cols:
            statements.append(
                "ALTER TABLE career_profiles ADD COLUMN target_sectors "
                f"JSON NOT NULL DEFAULT {_json_default('[]')}"
            )

    cert_cols = _table_columns(insp, "certifications")
    if cert_cols and "credential_type" not in cert_cols:
        statements.append(
            "ALTER TABLE certifications ADD COLUMN credential_type VARCHAR(64) NOT NULL DEFAULT ''"
        )

    document_cols = _table_columns(insp, "career_documents")
    if document_cols:
        if "ingest_status" not in document_cols:
            statements.append(
                "ALTER TABLE career_documents ADD COLUMN ingest_status VARCHAR(32) NOT NULL DEFAULT 'idle'"
            )
        if "ingest_error" not in document_cols:
            statements.append(
                "ALTER TABLE career_documents ADD COLUMN ingest_error TEXT NOT NULL DEFAULT ''"
            )
        if "ingest_result" not in document_cols:
            statements.append(
                "ALTER TABLE career_documents ADD COLUMN ingest_result "
                f"JSON NOT NULL DEFAULT {_json_default('{}')}"
            )

    execution_cols = _table_columns(insp, "agent_executions")
    if execution_cols:
        if "user_id" not in execution_cols:
            statements.append("ALTER TABLE agent_executions ADD COLUMN user_id VARCHAR(36)")
        if "usage_reservation_id" not in execution_cols:
            statements.append("ALTER TABLE agent_executions ADD COLUMN usage_reservation_id VARCHAR(36)")

    workflow_cols = _table_columns(insp, "workflow_runs")
    if workflow_cols and "usage_reservation_id" not in workflow_cols:
        statements.append("ALTER TABLE workflow_runs ADD COLUMN usage_reservation_id VARCHAR(36)")

    user_cols = _table_columns(insp, "users")
    if user_cols:
        if "google_sub" not in user_cols:
            statements.append("ALTER TABLE users ADD COLUMN google_sub VARCHAR(255)")
        if "avatar_url" not in user_cols:
            statements.append("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(1000)")
        if engine.dialect.name == "postgresql":
            statements.append("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")

    if statements:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
                logger.info("Applied schema patch: %s", stmt)

    if user_cols:
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users (google_sub)"))


def main() -> None:
    create_schema()
    from .database import SessionLocal
    from .seed import seed_if_empty
    from .services.entitlements import EntitlementsService

    seed_if_empty()
    db = SessionLocal()
    try:
        EntitlementsService(db).backfill_subscriptions()
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
