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
    _ensure_achievement_parent_columns()
    logger.info("Database schema ensured.")


def _ensure_achievement_parent_columns() -> None:
    """create_all does not ALTER existing tables — patch additive columns."""
    insp = inspect(engine)
    if "achievements" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("achievements")}
    statements: list[str] = []
    if "project_id" not in cols:
        statements.append("ALTER TABLE achievements ADD COLUMN project_id VARCHAR(36)")
    if "education_id" not in cols:
        statements.append("ALTER TABLE achievements ADD COLUMN education_id VARCHAR(36)")
    if not statements:
        return
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
            logger.info("Applied schema patch: %s", stmt)


def main() -> None:
    create_schema()
    from .seed import seed_if_empty

    seed_if_empty()


if __name__ == "__main__":
    main()
