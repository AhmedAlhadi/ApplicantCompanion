"""First-run onboarding status, CV profile prefill, and accept-suggested."""
from __future__ import annotations

import time

from app.models import Experience, User
from app.security.auth import create_access_token, hash_password
from conftest import SAMPLE_JD, post_ingest_text


def _headers_for(db, *, email: str, full_name: str = "", with_experience: bool = False) -> dict:
    user = User(
        email=email,
        password_hash=hash_password("onboard-password-123"),
        full_name=full_name,
    )
    db.add(user)
    db.flush()
    if with_experience:
        db.add(
            Experience(
                user_id=user.id,
                organization="SeedCo",
                job_title="Analyst",
                responsibilities=["Did analysis"],
            )
        )
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _wait_for_job(client, headers, job_id: str, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
        if job["status"] in ("analyzed", "failed"):
            return job
        time.sleep(0.2)
    raise TimeoutError("analysis did not complete")


def _wait_for_docs(client, headers, app_id: str, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        docs = client.get(f"/api/applications/{app_id}/documents", headers=headers).json()
        types = {d["document_type"] for d in docs if d.get("current_version")}
        if {"cv", "cover_letter"} <= types:
            return docs
        time.sleep(0.2)
    raise TimeoutError("document generation did not complete")


def test_empty_user_is_in_progress(client, db):
    headers = _headers_for(db, email="onboard-empty@example.com")
    resp = client.get("/api/onboarding", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["experience_count"] == 0
    assert body["has_profile"] is False

    again = client.get("/api/onboarding", headers=headers).json()
    assert again["status"] == "in_progress"


def test_existing_experience_auto_completes(client, db):
    headers = _headers_for(db, email="onboard-legacy@example.com", with_experience=True)
    resp = client.get("/api/onboarding", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"
    assert client.get("/api/onboarding", headers=headers).json()["status"] == "completed"


def test_complete_and_skip_persist(client, db):
    headers = _headers_for(db, email="onboard-skip@example.com")
    assert client.get("/api/onboarding", headers=headers).json()["status"] == "in_progress"

    skipped = client.post("/api/onboarding/skip", headers=headers)
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["status"] == "skipped"
    assert client.get("/api/onboarding", headers=headers).json()["status"] == "skipped"

    headers2 = _headers_for(db, email="onboard-done@example.com")
    completed = client.post("/api/onboarding/complete", headers=headers2)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert client.get("/api/onboarding", headers=headers2).json()["status"] == "completed"


def test_ingest_fills_empty_profile_and_accept_suggested(client, db):
    headers = _headers_for(db, email="onboard-ingest@example.com", full_name="")
    text = """
Jane Onboard
Digital Transformation Specialist
jane.onboard@example.com
+962 79 123 4567
Location: Amman, Jordan
https://www.linkedin.com/in/janeonboard

PROFESSIONAL EXPERIENCE
Data Analyst at IngestOnboard
January 2021 - December 2023
- Built Power BI dashboards for programme monitoring
- Increased reporting efficiency by 35%

SKILLS
Python, OnboardSkillXYZ
"""
    body = post_ingest_text(client, headers, {"text": text, "doc_type": "cv"})
    pending_id = body["pending_ingestion_id"]
    assert pending_id
    profile = body.get("profile") or {}
    assert profile.get("full_name") == "Jane Onboard"
    assert profile.get("email") == "jane.onboard@example.com"

    saved = client.get("/api/career/profile", headers=headers).json()
    assert saved["full_name"] == "Jane Onboard"
    assert saved["email"] == "jane.onboard@example.com"
    assert saved["location"] == "Amman, Jordan"
    assert saved["links"].get("linkedin", "").startswith("https://www.linkedin.com/in/janeonboard")

    accepted = client.post(f"/api/career/pending-ingestions/{pending_id}/accept-suggested", headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["applied"]["experiences"] >= 1

    experiences = client.get("/api/career/experiences", headers=headers).json()
    assert any(e["organization"] == "IngestOnboard" for e in experiences)

    # Existing profile values must not be overwritten on a second ingest
    post_ingest_text(
        client,
        headers,
        {"text": "Other Name\nother@example.com\nLocation: Paris\n", "doc_type": "notes"},
    )
    saved2 = client.get("/api/career/profile", headers=headers).json()
    assert saved2["full_name"] == "Jane Onboard"
    assert saved2["email"] == "jane.onboard@example.com"


def test_onboarding_pipeline_then_complete(client, db):
    headers = _headers_for(db, email="onboard-pipeline@example.com", full_name="Pipeline User")
    client.put(
        "/api/career/profile",
        headers=headers,
        json={"full_name": "Pipeline User", "email": "onboard-pipeline@example.com", "headline": "Data Leader"},
    )
    exp = client.post(
        "/api/career/experiences",
        headers=headers,
        json={
            "organization": "UNDP",
            "job_title": "Digital Transformation Specialist",
            "start_date": "2020-01",
            "responsibilities": [
                "Lead digital transformation initiatives and data platform delivery",
                "Develop Power BI dashboards for programme monitoring",
            ],
            "technologies": ["Power BI", "Python", "SQL", "Azure"],
            "verification_status": "verified",
            "confidence": 0.95,
        },
    )
    assert exp.status_code == 201, exp.text
    client.post("/api/career/skills", headers=headers, json={"name": "Python", "verification_status": "verified"})
    client.post("/api/career/skills", headers=headers, json={"name": "Power BI", "verification_status": "verified"})

    # Status was never fetched, so experiences would auto-complete. Mark in-progress first
    # by skipping that path: user already has experiences so GET would complete.
    # Complete the pipeline independently, then POST /complete.
    job = client.post("/api/jobs", headers=headers, json={"raw_jd_text": SAMPLE_JD, "source_type": "paste"})
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    analyze = client.post(f"/api/jobs/{job_id}/analyze", headers=headers, json={"include_research": False})
    assert analyze.status_code == 202
    analyzed = _wait_for_job(client, headers, job_id)
    assert analyzed["status"] == "analyzed"

    app = client.post("/api/applications", headers=headers, json={"job_id": job_id})
    assert app.status_code == 201, app.text
    app_id = app.json()["id"]
    decide = client.post(f"/api/applications/{app_id}/decide", headers=headers, json={"decision": "continue"})
    assert decide.status_code == 200
    gen = client.post(
        f"/api/applications/{app_id}/generate-all",
        headers=headers,
        json={"template_key": "minimal-ats"},
    )
    assert gen.status_code == 202, gen.text
    docs = _wait_for_docs(client, headers, app_id)
    assert {d["document_type"] for d in docs} >= {"cv", "cover_letter"}

    done = client.post("/api/onboarding/complete", headers=headers)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "completed"
    assert body["job_count"] >= 1
    assert body["latest_application"]["id"] == app_id
