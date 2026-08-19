"""Generation endpoints create a pollable workflow run before background work."""
from __future__ import annotations

from app.models import ApplicationStrategy, WorkflowRun


def _create_application(client, auth_headers, title: str) -> str:
    job = client.post(
        "/api/jobs",
        headers=auth_headers,
        json={
            "source_type": "paste",
            "position_title": title,
            "raw_jd_text": "Requirements:\n- Python experience",
        },
    )
    assert job.status_code == 201, job.text
    app = client.post("/api/applications", headers=auth_headers, json={"job_id": job.json()["id"]})
    assert app.status_code == 201, app.text
    return app.json()["id"]


def test_strategy_returns_workflow_run_id_immediately(client, auth_headers, db, monkeypatch):
    app_id = _create_application(client, auth_headers, "Strategy Run")
    monkeypatch.setattr("app.api.applications.submit", lambda *args, **kwargs: None)

    response = client.post(f"/api/applications/{app_id}/strategy", headers=auth_headers)
    assert response.status_code == 202, response.text
    run_id = response.json()["workflow_run_id"]
    assert run_id

    db.expire_all()
    run = db.get(WorkflowRun, run_id)
    assert run is not None
    assert run.application_id == app_id
    assert run.workflow_type == "document_generation"
    assert run.status in ("PENDING", "RUNNING")
    assert any(stage["name"] == "GenerateApplicationStrategy" for stage in run.stages)


def test_generate_cv_returns_workflow_run_id_immediately(client, auth_headers, db, monkeypatch):
    app_id = _create_application(client, auth_headers, "CV Run")
    monkeypatch.setattr("app.api.applications.submit", lambda *args, **kwargs: None)

    response = client.post(
        f"/api/applications/{app_id}/generate-cv",
        headers=auth_headers,
        json={"template_key": "minimal-ats"},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["workflow_run_id"]
    db.expire_all()
    run = db.get(WorkflowRun, run_id)
    assert run is not None
    assert {stage["name"] for stage in run.stages} >= {"GenerateApplicationStrategy", "GenerateCV", "ValidateCV"}
    assert "GenerateCoverLetter" not in {stage["name"] for stage in run.stages}


def test_strategy_background_completion_persists_result(client, auth_headers, db, monkeypatch):
    app_id = _create_application(client, auth_headers, "Strategy Complete")
    monkeypatch.setattr(
        "app.api.applications.submit",
        lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    response = client.post(f"/api/applications/{app_id}/strategy", headers=auth_headers)
    assert response.status_code == 202, response.text
    run_id = response.json()["workflow_run_id"]

    db.expire_all()
    run = db.get(WorkflowRun, run_id)
    assert run.status == "COMPLETED"
    strategy = (
        db.query(ApplicationStrategy)
        .filter(ApplicationStrategy.application_id == app_id)
        .first()
    )
    assert strategy is not None
    fetched = client.get(f"/api/applications/{app_id}/strategy", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text


def test_strategy_background_failure_is_terminal(client, auth_headers, db, monkeypatch):
    app_id = _create_application(client, auth_headers, "Strategy Fail")
    monkeypatch.setattr(
        "app.api.applications.Orchestrator.run_strategy",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("strategy exploded")),
    )
    monkeypatch.setattr(
        "app.api.applications.submit",
        lambda fn, *args, **kwargs: fn(*args, **kwargs),
    )

    response = client.post(f"/api/applications/{app_id}/strategy", headers=auth_headers)
    assert response.status_code == 202, response.text
    db.expire_all()
    run = db.get(WorkflowRun, response.json()["workflow_run_id"])
    assert run.status == "FAILED"
    assert "strategy exploded" in run.error
