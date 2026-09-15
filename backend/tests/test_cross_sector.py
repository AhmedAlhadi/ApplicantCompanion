"""Cross-sector generalization: non-tech profiles, uncategorized defaults, aliases."""
from __future__ import annotations

from app.llm import mock_logic
from app.scoring.engine import DEFAULT_WEIGHTS, normalize_weights


NURSE_CV = """
PROFESSIONAL EXPERIENCE
Registered Nurse at City General Hospital
January 2018 - December 2023
- Provided patient care and medication administration on the medical-surgical ward
- Documented vital signs in the EHR and practiced infection control
- Precepted new nurses during triage on night shift

SKILLS
Patient care, IV therapy, charting, infection control
"""

TEACHER_CV = """
PROFESSIONAL EXPERIENCE
Classroom Teacher at Riverside Primary
September 2016 - June 2024
- Designed lesson planning and differentiated instruction for mixed-ability classes
- Led classroom management and parent communication
- Maintained safeguarding records and formative assessment

SKILLS
Lesson planning, classroom management, pedagogy
"""

ELECTRICIAN_CV = """
PROFESSIONAL EXPERIENCE
Electrician at Metro Electrical
March 2015 - Present
- Installed conduit and panel work to NEC code
- Performed lockout/tagout and voltage troubleshooting
- Mentored apprentices on grounding and schematics

SKILLS
Wiring, lockout, troubleshooting, apprenticeship
"""

SALES_CV = """
PROFESSIONAL EXPERIENCE
Account Manager at Northwind Wholesale
June 2017 - Present
- Owned a regional pipeline and quota in CRM
- Coordinated order management and inventory with operations
- Improved customer onboarding and forecasting accuracy

SKILLS
Account management, forecasting, CRM, pipeline
"""

NURSE_JD = """
Registered Nurse — Medical Surgical Unit
City General Hospital
Requirements:
- Current RN license
- 2 years acute-care patient care experience
- Infection control and EHR charting
Responsibilities:
- Administer medications and document vital signs
"""


def _confirm_pending(client, headers, pending_id):
    if not pending_id:
        return
    pending = client.get(f"/api/career/pending-ingestions/{pending_id}", headers=headers).json()
    client.post(
        f"/api/career/pending-ingestions/{pending_id}/confirm",
        headers=headers,
        json={
            "decisions": [
                {
                    "proposal_id": p["proposal_id"],
                    "action": p.get("action") or "create",
                    "target_id": p.get("target_id"),
                }
                for p in pending.get("proposals", [])
            ]
        },
    )


def test_skill_category_does_not_default_to_technical():
    assert mock_logic._skill_category("Patient care") == "clinical"
    assert mock_logic._skill_category("lesson planning") == "functional"
    assert mock_logic._skill_category("lockout") == "tools"
    assert mock_logic._skill_category("Python") == "technical"
    assert mock_logic._skill_category("obscure-local-process") == "uncategorized"


def test_normalize_weights_aliases_skills_and_tools():
    out = normalize_weights({"skills_and_tools": 0.15, **{k: v for k, v in DEFAULT_WEIGHTS.items() if k != "technical_skills"}})
    assert out["technical_skills"] == 0.15
    assert "skills_and_tools" not in out


def test_nurse_extraction_is_clinical_not_tech():
    result = mock_logic.mock_career_extraction(f"<document>{NURSE_CV}</document>")
    cats = {s["name"].lower(): s["category"] for s in result["skills"]}
    assert cats.get("patient care") == "clinical"
    assert "technical" not in cats.values()
    blob = " ".join(result["experiences"][0].get("domains") or []).lower()
    assert any(term in blob for term in ("health", "clinical", "nursing", "patient care"))


def test_teacher_electrician_sales_extraction(client, auth_headers):
    for cv, expected in (
        (TEACHER_CV, ("curriculum", "classroom", "pedagogy", "education", "safeguarding")),
        (ELECTRICIAN_CV, ("electrical", "apprenticeship")),
        (SALES_CV, ("sales", "operations", "inventory")),
    ):
        resp = client.post("/api/career/ingest-text", headers=auth_headers, json={"text": cv, "doc_type": "cv"})
        assert resp.status_code == 200, resp.text
        _confirm_pending(client, auth_headers, resp.json().get("pending_ingestion_id"))

    skills = client.get("/api/career/skills", headers=auth_headers).json()
    by_name = {s["name"].lower(): s["category"] for s in skills}
    assert by_name.get("lesson planning") != "technical"
    assert by_name.get("wiring") != "technical"
    knowledge = " ".join(
        (row.get("canonical_name") or "") + " " + (row.get("summary") or "")
        for row in client.get("/api/career/knowledge", headers=auth_headers).json()
    ).lower()
    assert any(term in knowledge for term in ("curriculum", "classroom", "pedagogy", "education"))
    assert any(term in knowledge for term in ("electrical", "apprenticeship"))


def test_nurse_ingestion_and_search(client, auth_headers):
    resp = client.post("/api/career/ingest-text", headers=auth_headers, json={"text": NURSE_CV, "doc_type": "cv"})
    assert resp.status_code == 200, resp.text
    _confirm_pending(client, auth_headers, resp.json().get("pending_ingestion_id"))
    skills = client.get("/api/career/skills", headers=auth_headers).json()
    nurse_names = ("patient care", "iv therapy", "charting", "infection control")
    nurse_skills = [s for s in skills if s["name"].lower() in nurse_names]
    assert nurse_skills
    assert all(s["category"] != "technical" for s in nurse_skills)
    search = client.get("/api/career/search?q=patient care infection control", headers=auth_headers)
    assert search.status_code == 200
    assert search.json()


def test_nurse_jd_not_forced_technical():
    result = mock_logic.mock_jd_analysis(f"<job_description>{NURSE_JD}</job_description>")
    classifications = {k["classification"] for k in result["keywords"]}
    assert "technical" not in classifications or any(
        k["classification"] != "technical" for k in result["keywords"]
    )
    categories = {r["category"] for r in result["requirements"]}
    assert "education" in categories or "certification" in categories or "experience" in categories


def test_profile_profession_and_ats_setting(client, auth_headers):
    saved = client.put(
        "/api/career/profile",
        headers=auth_headers,
        json={
            "full_name": "Sam Nurse",
            "primary_profession": "registered nurse",
            "target_sectors": ["healthcare", "acute care"],
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["primary_profession"] == "registered nurse"
    assert "healthcare" in body["target_sectors"]

    settings = client.put(
        "/api/settings",
        headers=auth_headers,
        json={"ats_relevance": "low", "scoring_weights": {**DEFAULT_WEIGHTS, "skills_and_tools": DEFAULT_WEIGHTS["technical_skills"]}},
    )
    assert settings.status_code == 200, settings.text
    data = settings.json()
    assert data["ats_relevance"] == "low"
    assert "technical_skills" in data["scoring_weights"]
    assert abs(sum(data["scoring_weights"].values()) - 1.0) < 0.02
