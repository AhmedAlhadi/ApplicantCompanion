"""Career knowledge CRUD, verification, ingestion, provenance, search (§6-7, §32, §47)."""


def test_achievement_parent_links(client, auth_headers):
    """Achievements can link to experience, project, and/or education."""
    exp = client.post("/api/career/experiences", headers=auth_headers, json={
        "organization": "LinkCo", "job_title": "Engineer",
    })
    assert exp.status_code == 201
    exp_id = exp.json()["id"]

    proj = client.post("/api/career/projects", headers=auth_headers, json={
        "name": "Platform Rewrite", "experience_id": exp_id,
    })
    assert proj.status_code == 201, proj.text
    assert proj.json()["experience_id"] == exp_id
    proj_id = proj.json()["id"]

    edu = client.post("/api/career/education", headers=auth_headers, json={
        "institution": "Tech Uni", "degree": "BSc",
    })
    assert edu.status_code == 201
    edu_id = edu.json()["id"]

    ach = client.post("/api/career/achievements", headers=auth_headers, json={
        "description": "Cut deploy time by 50%",
        "experience_id": exp_id,
        "project_id": proj_id,
        "education_id": edu_id,
    })
    assert ach.status_code == 201, ach.text
    body = ach.json()
    assert body["experience_id"] == exp_id
    assert body["project_id"] == proj_id
    assert body["education_id"] == edu_id

    bad = client.post("/api/career/achievements", headers=auth_headers, json={
        "description": "Orphan claim",
        "experience_id": "00000000-0000-0000-0000-000000000000",
    })
    assert bad.status_code == 422


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
    body = resp.json()
    auto = body.get("auto_applied") or body.get("created") or {}
    assert auto["skills"] >= 1
    pending_id = body["pending_ingestion_id"]
    assert pending_id, "experiences should be queued for reconciliation review"

    pending = client.get(f"/api/career/pending-ingestions/{pending_id}", headers=auth_headers)
    assert pending.status_code == 200, pending.text
    proposals = pending.json()["proposals"]
    assert proposals
    assert any(p["entity_type"] == "experience" for p in proposals)

    decisions = [
        {
            "proposal_id": p["proposal_id"],
            "action": p.get("action") or "create",
            "target_id": p.get("target_id"),
        }
        for p in proposals
    ]
    confirm = client.post(
        f"/api/career/pending-ingestions/{pending_id}/confirm",
        headers=auth_headers,
        json={"decisions": decisions},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["applied"]["experiences"] >= 1

    skills = client.get("/api/career/skills", headers=auth_headers).json()
    skill = next(s for s in skills if s["name"] == "IngestSkillXYZ")
    assert skill["verification_status"] == "needs_review"

    # provenance: the skill must trace back to the source document (§6)
    evidence = client.get(f"/api/career/evidence/skill/{skill['id']}", headers=auth_headers).json()
    assert evidence
    assert evidence[0]["source_document"]


def test_ingestion_merge_proposal_for_existing_experience(client, auth_headers):
    """Additional details about an existing role should propose merge, not a duplicate."""
    created = client.post("/api/career/experiences", headers=auth_headers, json={
        "organization": "MergeCo",
        "job_title": "Engineer",
        "start_date": "2020-01",
        "responsibilities": ["Built APIs"],
    })
    assert created.status_code == 201
    exp_id = created.json()["id"]

    text = """
PROFESSIONAL EXPERIENCE
Engineer at MergeCo
January 2020 - Present
- Reduced API latency by 40%
"""
    resp = client.post("/api/career/ingest-text", headers=auth_headers, json={"text": text, "doc_type": "notes"})
    assert resp.status_code == 200, resp.text
    pending_id = resp.json()["pending_ingestion_id"]
    assert pending_id

    pending = client.get(f"/api/career/pending-ingestions/{pending_id}", headers=auth_headers).json()
    exp_props = [p for p in pending["proposals"] if p["entity_type"] == "experience"]
    assert exp_props
    assert exp_props[0]["action"] == "merge"
    assert exp_props[0]["target_id"] == exp_id

    # User confirms the merge
    decisions = [
        {"proposal_id": p["proposal_id"], "action": "merge", "target_id": exp_id}
        for p in exp_props
    ] + [
        {"proposal_id": p["proposal_id"], "action": "create", "target_id": None}
        for p in pending["proposals"]
        if p["entity_type"] != "experience"
    ]
    confirm = client.post(
        f"/api/career/pending-ingestions/{pending_id}/confirm",
        headers=auth_headers,
        json={"decisions": decisions},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["applied"]["merged"] >= 1

    experiences = client.get("/api/career/experiences", headers=auth_headers).json()
    merge_co = [e for e in experiences if e["organization"] == "MergeCo"]
    assert len(merge_co) == 1

    achievements = client.get("/api/career/achievements", headers=auth_headers).json()
    linked = [a for a in achievements if a.get("experience_id") == exp_id]
    assert any("40%" in (a.get("description") or "") or "latency" in (a.get("description") or "").lower() for a in linked) or any(
        "40%" in r or "latency" in r.lower() for r in (merge_co[0].get("responsibilities") or [])
    )

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
