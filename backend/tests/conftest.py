"""Test fixtures. Environment is configured BEFORE app imports so every test
runs against an isolated SQLite file with the deterministic mock LLM and
research disabled (§56: deterministic fixtures)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

_TMP = Path(tempfile.mkdtemp(prefix="ac-test-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "SECRET_KEY": "test-secret-key",
        "VECTOR_STORE": "memory",
        "OBJECT_STORE": "local",
        "LOCAL_STORAGE_PATH": str(_TMP / "storage"),
        "RESEARCH_ENABLED": "false",
        "RATE_LIMIT_PER_MINUTE": "0",
        "SEED_DEMO_DATA": "false",
        "GOOGLE_CLIENT_ID": "test-google-client-id.apps.googleusercontent.com",
        "LLM_MODEL_EXTRACTION": "mock:deterministic",
        "LLM_MODEL_CLASSIFICATION": "mock:deterministic",
        "LLM_MODEL_RESEARCH": "mock:deterministic",
        "LLM_MODEL_SCORING": "mock:deterministic",
        "LLM_MODEL_MATCHING": "mock:deterministic",
        "LLM_MODEL_STRATEGY": "mock:deterministic",
        "LLM_MODEL_CV_GENERATION": "mock:deterministic",
        "LLM_MODEL_COVER_LETTER": "mock:deterministic",
        "LLM_MODEL_ATS": "mock:deterministic",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402

TEST_EMAIL = "tester@example.com"
TEST_PASSWORD = "test-password-123"

Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _seed():
    os.environ["SEED_USER_EMAIL"] = TEST_EMAIL
    os.environ["SEED_USER_PASSWORD"] = TEST_PASSWORD
    seed_if_empty()
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client) -> dict:
    resp = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── deterministic career fixtures (§56) ──────────────────────────────────────

SAMPLE_JD = """Digital Transformation Specialist
Organization: UNICEF
Location: Amman, Jordan
Contract Type: Fixed Term
Deadline: 2026-09-01

Responsibilities:
- Lead the design and implementation of digital transformation initiatives
- Develop data platforms and Power BI dashboards for programme monitoring
- Advise management on AI adoption and data governance
- Manage a small team of analysts and engineers

Requirements:
- Master's degree in Information Systems, Computer Science or related field
- Minimum 5 years of experience in digital transformation or data platforms
- Proven experience with Power BI and data visualization
- Experience with Python and SQL for data analysis
- Experience managing technical teams
- Fluency in English is required
- Knowledge of Azure cloud platforms

Preferred:
- PRINCE2 or PMP certification
- Experience in the humanitarian sector
- Knowledge of French is an asset
"""


@pytest.fixture()
def career_kb(client, auth_headers):
    """A candidate who clearly qualifies for SAMPLE_JD."""
    exp = client.post("/api/career/experiences", headers=auth_headers, json={
        "organization": "UNDP",
        "job_title": "Digital Transformation Specialist",
        "start_date": "2020-01",
        "end_date": None,
        "location": "Amman",
        "responsibilities": [
            "Lead digital transformation initiatives and data platform delivery",
            "Develop Power BI dashboards for programme monitoring",
            "Advise management on AI adoption and data governance",
            "Manage a team of 6 engineers and analysts",
        ],
        "technologies": ["Power BI", "Python", "SQL", "Azure"],
        "domains": ["digital transformation", "humanitarian"],
        "leadership": ["Managed a team of 6 engineers and analysts"],
        "verification_status": "verified",
        "confidence": 0.95,
    })
    assert exp.status_code == 201, exp.text
    exp_id = exp.json()["id"]

    ach = client.post("/api/career/achievements", headers=auth_headers, json={
        "experience_id": exp_id,
        "description": "Led implementation of an AI-enabled MIS platform adopted by 12 country offices, cutting reporting time by 40%",
        "quantified_result": "12 offices, 40% faster reporting",
        "verification_status": "verified",
    })
    assert ach.status_code == 201, ach.text

    for name in ["Python", "SQL", "Power BI", "Azure", "Data platform", "Digital transformation"]:
        resp = client.post("/api/career/skills", headers=auth_headers, json={"name": name, "verification_status": "verified"})
        assert resp.status_code == 201, resp.text

    edu = client.post("/api/career/education", headers=auth_headers, json={
        "institution": "University of Manchester",
        "degree": "Master's degree",
        "field_of_study": "Information Systems",
        "verification_status": "verified",
    })
    assert edu.status_code == 201, edu.text

    cert = client.post("/api/career/certifications", headers=auth_headers, json={
        "name": "PRINCE2 Practitioner", "issuer": "AXELOS", "verification_status": "verified",
    })
    assert cert.status_code == 201, cert.text

    lang = client.post("/api/career/languages", headers=auth_headers, json={
        "language": "English", "proficiency": "Fluent",
    })
    assert lang.status_code == 201, lang.text

    return {"experience_id": exp_id}
