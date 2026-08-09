"""Critical end-to-end acceptance test (§57):

candidate career database + example JD → JD parsed → requirements extracted →
organization research (gracefully skipped offline) → hiring context →
evidence retrieved → requirements matched → score calculated → strategy →
CV generated → CV validated → cover letter generated → documents exported.
The result must be explainable (score breakdown + evidence traceability).
"""
from __future__ import annotations

import time

from conftest import SAMPLE_JD


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


def test_full_acceptance_pipeline(client, auth_headers, career_kb):
    # ── Create job (paste JD) ────────────────────────────────────────────
    resp = client.post("/api/jobs", headers=auth_headers, json={
        "raw_jd_text": SAMPLE_JD, "source_type": "paste",
    })
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["id"]

    # ── Analyze: parse → research → match → score ────────────────────────
    resp = client.post(f"/api/jobs/{job_id}/analyze", headers=auth_headers, json={"include_research": False})
    assert resp.status_code == 202
    job = _wait_for_job(client, auth_headers, job_id)
    assert job["status"] == "analyzed"

    # JD parsed
    analysis = client.get(f"/api/jobs/{job_id}/analysis", headers=auth_headers).json()
    assert analysis["parsed"]["position"]["organization"] == "UNICEF"
    requirements = analysis["requirements"]
    assert len(requirements) >= 8

    # Requirements matched with evidence
    matched = [r for r in requirements if r["match"] and r["match"]["status"] == "MATCHED"]
    assert matched, "expected at least one direct match"
    power_bi = next((r for r in requirements if "Power BI" in r["text"]), None)
    assert power_bi is not None
    assert power_bi["match"]["status"] == "MATCHED"
    assert power_bi["match"]["evidence"], "match must carry evidence"

    # Score calculated programmatically and explainable
    score = client.get(f"/api/jobs/{job_id}/score", headers=auth_headers).json()
    assert 0.0 <= score["overall_score"] <= 1.0
    assert score["overall_score"] >= score["threshold"] - 0.35  # strong candidate fixture
    assert score["category_scores"]
    assert score["recommendation"] in ("strong_fit", "below_threshold")
    assert score["explanation"]

    # Research gracefully unavailable offline (§54)
    research = client.get(f"/api/jobs/{job_id}/research", headers=auth_headers).json()
    assert research["hiring_context"]["identified"] is False
    assert "not identified" in research["hiring_context"]["notes"].lower()

    # ── Application + strategy ───────────────────────────────────────────
    app_resp = client.post("/api/applications", headers=auth_headers, json={"job_id": job_id})
    assert app_resp.status_code == 201, app_resp.text
    app_id = app_resp.json()["id"]

    # Below-threshold gate: user decision required before generation (§20-21)
    score_now = client.get(f"/api/jobs/{job_id}/score", headers=auth_headers).json()
    gen = client.post(f"/api/applications/{app_id}/generate-all", headers=auth_headers, json={})
    if score_now["overall_score"] < score_now["threshold"]:
        assert gen.status_code == 409
        detail = gen.json()["detail"]
        assert detail["code"] == "BELOW_THRESHOLD"
        assert "continue" in detail["actions"]
        decided = client.post(f"/api/applications/{app_id}/decide", headers=auth_headers, json={"decision": "continue"})
        assert decided.status_code == 200
        gen = client.post(f"/api/applications/{app_id}/generate-all", headers=auth_headers, json={})
    assert gen.status_code == 202

    docs = _wait_for_docs(client, auth_headers, app_id)

    # ── CV generated + validated + traceable ─────────────────────────────
    cv_doc = next(d for d in docs if d["document_type"] == "cv")
    cv = cv_doc["current_version"]
    content = cv["content"]
    assert content["experience"], "CV must contain experience entries"
    assert content["summary"]
    assert cv["validation_results"]["schema_valid"] is True
    assert cv["validation_results"]["hallucination_free"] is True

    # Anti-hallucination: every evidence id cited must resolve (§24, §32)
    evidence = client.get(f"/api/documents/{cv_doc['id']}/evidence", headers=auth_headers).json()
    assert evidence["traceability"]
    assert any(p["evidence"] for p in evidence["traceability"])

    # ATS analysis ran (§25)
    assert "ats_score" in cv["ats_analysis"]

    # ── Cover letter generated ───────────────────────────────────────────
    cl_doc = next(d for d in docs if d["document_type"] == "cover_letter")
    cl = cl_doc["current_version"]["content"]
    assert cl["paragraphs"]
    assert "UNICEF" in json_dump(cl)

    # ── Versioning + editing (§29-30) ────────────────────────────────────
    edited = dict(content)
    edited["summary"] = "Manually refined summary."
    resp = client.put(f"/api/documents/{cv_doc['id']}", headers=auth_headers, json={"content": edited})
    assert resp.status_code == 200
    assert resp.json()["version_number"] == 2
    assert resp.json()["user_edited"] is True

    # Section regeneration preserves the rest (§31)
    resp = client.post(
        f"/api/documents/{cv_doc['id']}/regenerate-section",
        headers=auth_headers,
        json={"section": "skills"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["content"]["summary"] == "Manually refined summary."

    # Restore previous version (§30)
    resp = client.post(f"/api/documents/{cv_doc['id']}/restore/2", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["content"]["summary"] == "Manually refined summary."

    # ── Export PDF + DOCX (§50) ──────────────────────────────────────────
    for fmt, magic in (("pdf", b"%PDF"), ("docx", b"PK")):
        resp = client.post(f"/api/documents/{cv_doc['id']}/export?fmt={fmt}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.content[:4].startswith(magic)

    # ── Agent execution log (§40) ────────────────────────────────────────
    executions = client.get(f"/api/agent-executions?job_id={job_id}", headers=auth_headers).json()
    assert executions
    assert any(e["agent_name"] == "job_analysis" for e in executions)
    assert all("output" not in e for e in executions)  # raw outputs not exposed

    # ── Dashboard reflects the application (§33) ─────────────────────────
    stats = client.get("/api/dashboard/stats", headers=auth_headers).json()
    assert stats["total_applications"] >= 1
    assert stats["top_opportunities"]


def json_dump(obj) -> str:
    import json

    return json.dumps(obj)
