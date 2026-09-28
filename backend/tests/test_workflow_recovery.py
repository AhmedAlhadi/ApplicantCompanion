"""Failure-injection tests for analysis workflow termination and recovery."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Job, WorkflowRun


def _create_job(client, auth_headers, title: str) -> str:
    response = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={
            "source_type": "paste",
            "position_title": title,
            "raw_jd_text": "Requirements:\n- Python experience",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_unexpected_background_failure_is_terminal(
    client,
    auth_headers,
    db,
    monkeypatch,
):
    job_id = _create_job(client, auth_headers, "Failure Harness")
    monkeypatch.setattr(
        "app.api.jobs.Orchestrator.run_job_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("retrieval exploded")),
    )
    monkeypatch.setattr(
        "app.api.jobs.submit",
        lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    response = client.post(
        f"/api/jobs/{job_id}/analyze",
        headers=auth_headers,
        json={"include_research": False},
    )

    assert response.status_code == 202
    db.expire_all()
    run = db.get(WorkflowRun, response.json()["workflow_run_id"])
    job = db.get(Job, job_id)
    assert run.status == "FAILED"
    assert "Something went wrong" in run.error
    assert job.status == "failed"


def test_stale_run_is_superseded(
    client,
    auth_headers,
    db,
    monkeypatch,
):
    job_id = _create_job(client, auth_headers, "Stale Harness")
    job = db.get(Job, job_id)
    run = WorkflowRun(
        user_id=job.user_id,
        job_id=job.id,
        workflow_type="job_analysis",
        status="RUNNING",
        stages=[{"name": "ParseJD", "status": "RUNNING"}],
        updated_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    job.status = "analyzing"
    db.add(run)
    db.commit()
    old_id = run.id
    monkeypatch.setattr("app.api.jobs.submit", lambda *args, **kwargs: None)

    response = client.post(
        f"/api/jobs/{job_id}/analyze",
        headers=auth_headers,
        json={"include_research": False},
    )

    assert response.status_code == 202
    assert response.json()["workflow_run_id"] != old_id
    db.expire_all()
    assert db.get(WorkflowRun, old_id).status == "FAILED"
    assert db.get(WorkflowRun, response.json()["workflow_run_id"]).status == "RUNNING"


def test_reanalysis_replaces_requirements_without_fk_violation(
    client,
    auth_headers,
    db,
    monkeypatch,
):
    job_id = _create_job(client, auth_headers, "Reanalysis Harness")
    monkeypatch.setattr(
        "app.api.jobs.submit",
        lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    first = client.post(
        f"/api/jobs/{job_id}/analyze",
        headers=auth_headers,
        json={"include_research": False},
    )
    assert first.status_code == 202, first.text
    db.expire_all()
    assert db.get(WorkflowRun, first.json()["workflow_run_id"]).status == "COMPLETED"

    second = client.post(
        f"/api/jobs/{job_id}/analyze",
        headers=auth_headers,
        json={"include_research": False},
    )
    assert second.status_code == 202, second.text
    db.expire_all()
    run = db.get(WorkflowRun, second.json()["workflow_run_id"])
    job = db.get(Job, job_id)
    assert run.status == "COMPLETED", run.error
    assert job.status == "analyzed"
