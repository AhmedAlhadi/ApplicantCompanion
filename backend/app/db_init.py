"""Idempotent database initialization + seed entrypoint.

Used by docker-compose at container start and by developers:
    python -m app.db_init
"""
from __future__ import annotations

import logging

from .database import Base, engine
from . import models  # noqa: F401  (register tables)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ensured.")


def main() -> None:
    create_schema()
    from .seed import seed_if_empty

    seed_if_empty()


if __name__ == "__main__":
    main()
