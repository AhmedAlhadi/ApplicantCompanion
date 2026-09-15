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
    from .seed import seed_if_empty

    seed_if_empty()


if __name__ == "__main__":
    main()
