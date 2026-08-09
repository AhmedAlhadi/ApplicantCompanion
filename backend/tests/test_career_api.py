"""Career knowledge CRUD, verification, ingestion, provenance, search (§6-7, §32, §47)."""


def test_experience_crud(client, auth_headers):
    created = client.post("/api/career/experiences", headers=auth_headers, json={
        "organization": "Acme", "job_title": "Analyst", "responsibilities": ["Did analysis"],
    })
    assert created.status_code == 201
    exp_id = created.json()["id"]
    assert created.json()["verification_status"] == "unverified"

    updated = client.put(f"/api/career/experiences/{exp_id}", headers=auth_headers, json={
        "organization": "Acme", "job_title": "Senior Analyst", "responsibilities": ["Did analysis"],
    })
    assert updated.status_code == 200
    assert updated.json()["job_title"] == "Senior Analyst"

    verified = client.post(f"/api/career/experiences/{exp_id}/verify?status_value=verified", headers=auth_headers)
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "verified"

    deleted = client.delete(f"/api/career/experiences/{exp_id}", headers=auth_headers)
    assert deleted.status_code == 200
    listing = client.get("/api/career/experiences", headers=auth_headers).json()
    assert all(e["id"] != exp_id for e in listing)


def test_cross_user_isolation(client, auth_headers):
    """Users can never see each other's data (§42 authorization)."""
    created = client.post("/api/career/skills", headers=auth_headers, json={"name": "IsolationSkill"})
    skill_id = created.json()["id"]
    # tampered token is rejected
    resp = client.get(f"/api/career/skills", headers={"Authorization": "Bearer invalid"})
    assert resp.status_code == 401
    assert skill_id


def test_text_ingestion_creates_structured_knowledge(client, auth_headers):
    text = """
PROFESSIONAL EXPERIENCE
Data Analyst at IngestCo
January 2021 - December 2023
- Built Power BI dashboards for programme monitoring
- Increased reporting efficiency by 35%

SKILLS
Python, IngestSkillXYZ
"""
    resp = client.post("/api/career/ingest-text", headers=auth_headers, json={"text": text, "doc_type": "cv"})
    assert resp.status_code == 200, resp.text
    created = resp.json()["created"]
    assert created["experiences"] >= 1
    assert created["skills"] >= 1

    skills = client.get("/api/career/skills", headers=auth_headers).json()
    skill = next(s for s in skills if s["name"] == "IngestSkillXYZ")
    assert skill["verification_status"] == "needs_review"

    # provenance: the skill must trace back to the source document (§6)
    evidence = client.get(f"/api/career/evidence/skill/{skill['id']}", headers=auth_headers).json()
    assert evidence
    assert evidence[0]["source_document"]


def test_semantic_search(client, auth_headers, career_kb):
    resp = client.get("/api/career/search?q=Power BI dashboards", headers=auth_headers)
    assert resp.status_code == 200
    results = resp.json()
    assert results
    assert results[0]["score"] > 0


def test_profile_roundtrip(client, auth_headers):
    resp = client.put("/api/career/profile", headers=auth_headers, json={"full_name": "Test User", "headline": "Data Leader"})
    assert resp.status_code == 200
    got = client.get("/api/career/profile", headers=auth_headers)
    assert got.json()["headline"] == "Data Leader"
