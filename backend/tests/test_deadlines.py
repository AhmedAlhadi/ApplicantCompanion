"""Application-deadline extraction and normalization."""
from __future__ import annotations

from app.llm.mock_logic import mock_jd_analysis
from app.schemas.agents import JDAnalysisResult
from app.services.deadlines import extract_application_deadline, normalize_application_deadline


def test_normalize_iso_and_prose_dates():
    assert normalize_application_deadline("2026-09-01") == "2026-09-01"
    assert normalize_application_deadline("15 September 2026") == "2026-09-15"
    assert normalize_application_deadline("September 15, 2026") == "2026-09-15"
    assert normalize_application_deadline("15-Sep-26") == "2026-09-15"
    assert normalize_application_deadline("11:59 p.m. (New York time) on 15 September 2026") == "2026-09-15"
    assert normalize_application_deadline("rolling") == "rolling"
    assert normalize_application_deadline("") == ""


def test_extract_from_common_jd_phrasings():
    assert extract_application_deadline("Deadline: 2026-09-01\n") == "2026-09-01"
    assert extract_application_deadline("Closing Date: 15 September 2026") == "2026-09-15"
    assert extract_application_deadline("Application deadline: Sep 15, 2026") == "2026-09-15"
    assert extract_application_deadline("Apply by 11:59 p.m. (New York time) on 15 September 2026.") == "2026-09-15"
    assert extract_application_deadline("Applications close on September 15, 2026") == "2026-09-15"
    assert extract_application_deadline("Open & closing dates\n08/15/2026 to 09/15/2026") == "2026-09-15"
    assert extract_application_deadline("Deadline for applications: 15-Sep-26") == "2026-09-15"
    assert extract_application_deadline("آخر موعد للتقديم: 15 سبتمبر 2026") == "2026-09-15"


def test_does_not_invent_or_confuse_posted_dates():
    assert extract_application_deadline("A deadline-driven environment with Python experience.") == ""
    assert extract_application_deadline("Posted: 1 August 2026\nLocation: Amman") == ""
    jd = "Posted: 1 August 2026\nDeadline: 15 September 2026"
    assert extract_application_deadline(jd) == "2026-09-15"


def test_schema_normalizes_deadline_aliases():
    result = JDAnalysisResult.model_validate({
        "position": {"closing_date": "15 September 2026", "job_title": "Data Lead"},
    })
    assert result.position.deadline == "2026-09-15"


def test_create_job_persists_deadline_from_jd(client, auth_headers):
    resp = client.post("/api/jobs", headers=auth_headers, json={
        "raw_jd_text": "Information Officer\nClosing date: 6 September 2026\nRequirements:\n- Python",
        "source_type": "paste",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["deadline"] == "2026-09-06"


def test_update_job_details(client, auth_headers):
    created = client.post("/api/jobs", headers=auth_headers, json={
        "raw_jd_text": "Analyst\nDeadline: 2026-09-01\nRequirements:\n- SQL",
        "source_type": "paste",
    }).json()
    resp = client.put(f"/api/jobs/{created['id']}", headers=auth_headers, json={
        "department": "Data",
        "contract_type": "Fixed Term",
        "deadline": "15 September 2026",
        "notes": "Follow up Friday",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["department"] == "Data"
    assert body["contract_type"] == "Fixed Term"
    assert body["deadline"] == "2026-09-15"
    assert body["notes"] == "Follow up Friday"


def test_mock_jd_analysis_stores_deadline_from_prose():
    jd = """Information Management Officer
Organization: OCHA
Closing date for applications: Sunday, 6 September 2026 (midnight New York time)

Requirements:
- Master's degree in information management
"""
    result = mock_jd_analysis(f"<job_description>{jd}</job_description>")
    assert result["position"]["deadline"] == "2026-09-06"

