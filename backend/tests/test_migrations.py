"""Alembic upgrade on a clean database and on an existing populated database."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Experience, User
from app.models.coach import CoachConversation

BACKEND = Path(__file__).resolve().parent.parent


def _sqlite_url(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def _alembic(db_url: str, *args: str) -> str:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    assert result.returncode == 0, output
    return output


def test_alembic_upgrade_clean_sqlite(tmp_path):
    url = _sqlite_url(tmp_path / "clean.db")
    _alembic(url, "upgrade", "head")
    heads = _alembic(url, "current")
    assert "0011_entitlements_usage" in heads
    engine = create_engine(url)
    with engine.connect() as conn:
        tables = {row[0] for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"professional_knowledge", "knowledge_contexts", "coach_conversations", "coach_messages", "plans", "usage_reservations"} <= tables


def test_alembic_upgrade_existing_sqlite_backfills_domains(tmp_path):
    db_path = tmp_path / "existing.db"
    url = _sqlite_url(db_path)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="migrate@example.com", password_hash="x", full_name="M")
        session.add(user)
        session.flush()
        session.add(
            Experience(
                user_id=user.id,
                organization="Northwind Logistics",
                job_title="Software Developer",
                domains=["logistics", "freight booking"],
                verification_status="verified",
                confidence=0.95,
            )
        )
        session.commit()

    _alembic(url, "stamp", "0006_user_oauth")
    _alembic(url, "upgrade", "head")

    engine = create_engine(url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        names = [
            row[0].lower()
            for row in conn.execute(text("SELECT canonical_name FROM professional_knowledge WHERE is_deleted = 0"))
        ]
        contexts = conn.execute(text("SELECT COUNT(*) FROM knowledge_contexts WHERE is_deleted = 0")).scalar()
        coach_count = conn.execute(text("SELECT COUNT(*) FROM coach_conversations")).scalar()
    assert version == "0011_entitlements_usage"
    assert "logistics" in names
    assert "freight booking" in names
    assert contexts >= 2
    assert coach_count == 0
    assert CoachConversation.__tablename__ == "coach_conversations"
    with Session(engine) as session:
        assert session.scalar(select(User).where(User.email == "migrate@example.com")) is not None
