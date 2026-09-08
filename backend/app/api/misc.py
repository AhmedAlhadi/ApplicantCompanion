"""Templates, dashboard stats, settings, AI model config, agent observability,
and SSE progress streaming (§33, §40, §45-46, §52-53)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..llm.router import provider_status, routing_table
from ..models import (
    AgentExecution,
    Application,
    Job,
    JobScore,
    Template,
    User,
    WorkflowRun,
)
from ..prompts.registry import list_prompts
from ..schemas.api import ModelTestRequest, SettingsUpdate
from ..security.auth import get_current_user
from ..services.serializers import to_dict
from ..services.settings import all_user_settings, set_user_setting
from ..workers.runner import subscribe, unsubscribe

router = APIRouter(prefix="/api", tags=["misc"])


def _normalize_unit_interval(value: float) -> float:
    """Guard against legacy/LLM values stored on a 0-100 scale: scores are
    contractually 0..1, so anything above 1 is treated as a percentage."""
    if value > 1.0:
        value = value / 100.0
    return min(max(value, 0.0), 1.0)


# ── templates (§28) ──────────────────────────────────────────────────────────


@router.get("/templates")
def list_templates(document_type: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Template)
    if document_type:
        query = query.filter(Template.document_type == document_type)
    return [to_dict(t) for t in query.order_by(Template.key).all()]


# ── dashboard (§33) ──────────────────────────────────────────────────────────


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    apps = db.query(Application).filter(Application.user_id == user.id, Application.is_deleted == False).all()  # noqa: E712
    by_status: dict[str, int] = {}
    for app in apps:
        by_status[app.status] = by_status.get(app.status, 0) + 1

    scores = (
        db.query(JobScore)
        .join(Job, Job.id == JobScore.job_id)
        .filter(Job.user_id == user.id, Job.is_deleted == False)  # noqa: E712
        .all()
    )
    latest_by_job: dict[str, JobScore] = {}
    for s in sorted(scores, key=lambda x: x.created_at):
        latest_by_job[s.job_id] = s
    latest = list(latest_by_job.values())

    avg_fit = sum(s.overall_score for s in latest) / len(latest) if latest else 0.0
    ats_values = [
        _normalize_unit_interval(a.ats_score_snapshot)
        for a in apps
        if a.ats_score_snapshot is not None
    ]
    avg_ats = sum(ats_values) / len(ats_values) if ats_values else 0.0

    now = datetime.now(timezone.utc)
    this_month = sum(
        1 for a in apps if a.created_at and a.created_at.year == now.year and a.created_at.month == now.month
    )

    top = sorted(latest, key=lambda s: s.overall_score, reverse=True)[:5]
    top_opportunities = []
    for s in top:
        job = db.get(Job, s.job_id)
        if job:
            top_opportunities.append({
                "job_id": job.id,
                "organization_name": job.organization_name,
                "position_title": job.position_title,
                "overall_score": s.overall_score,
            })

    return {
        "total_applications": len(apps),
        "by_status": by_status,
        "average_fit": round(min(max(avg_fit, 0.0), 1.0), 4),
        "average_ats": round(min(max(avg_ats, 0.0), 1.0), 4),
        "applications_this_month": this_month,
        "top_opportunities": top_opportunities,
    }


# ── settings (§20: configurable threshold/weights) ───────────────────────────


@router.get("/settings")
def get_settings_endpoint(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..config import get_settings
    from ..scoring.engine import DEFAULT_WEIGHTS

    from ..prompts.language import DEFAULT_LANGUAGE, normalize_language

    stored = all_user_settings(db, user.id)
    return {
        "score_threshold": stored.get("score_threshold", get_settings().score_threshold),
        "scoring_weights": stored.get("scoring_weights", DEFAULT_WEIGHTS),
        "model_routing": stored.get("model_routing", routing_table()),
        "ui_language": normalize_language(stored.get("ui_language"), DEFAULT_LANGUAGE),
        "content_language": normalize_language(stored.get("content_language"), DEFAULT_LANGUAGE),
    }


@router.put("/settings")
def update_settings(payload: SettingsUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if payload.score_threshold is not None:
        set_user_setting(db, user.id, "score_threshold", payload.score_threshold)
    if payload.scoring_weights is not None:
        total = sum(payload.scoring_weights.values())
        if abs(total - 1.0) > 0.01:
            raise HTTPException(422, f"Scoring weights must sum to 1.0 (got {total:.3f})")
        if any(v < 0 for v in payload.scoring_weights.values()):
            raise HTTPException(422, "Scoring weights must be non-negative")
        set_user_setting(db, user.id, "scoring_weights", payload.scoring_weights)
    if payload.model_routing is not None:
        set_user_setting(db, user.id, "model_routing", payload.model_routing)
    if payload.ui_language is not None:
        set_user_setting(db, user.id, "ui_language", payload.ui_language)
    if payload.content_language is not None:
        set_user_setting(db, user.id, "content_language", payload.content_language)
    from ..security.auth import audit

    audit(db, user, "settings.update", "user_setting", user.id, payload.model_dump(exclude_none=True), request)
    db.commit()
    return get_settings_endpoint(db=db, user=user)


# ── AI / model configuration (§45-46) ────────────────────────────────────────


@router.get("/models")
def models_config(user: User = Depends(get_current_user)):
    return {"providers": provider_status(), "routing": routing_table()}


_DEFAULT_TEST_MODELS = {
    "openrouter": "openai/gpt-4o-mini",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.2",
    "mock": "deterministic",
}


@router.post("/models/test")
def test_model(payload: ModelTestRequest, user: User = Depends(get_current_user)):
    from ..llm.base import LLMRequest
    from ..llm.router import get_provider

    provider = get_provider(payload.provider)
    if not provider.is_available():
        return {"ok": False, "detail": f"Provider '{payload.provider}' is not available (missing key or unreachable)"}
    model = payload.model or _DEFAULT_TEST_MODELS.get(payload.provider, "deterministic")
    try:
        response = provider.generate(
            model,
            LLMRequest(
                prompt_name="connectivity_test",
                prompt_version="v1",
                system="Reply with the JSON object {\"ok\": true}.",
                user="Return only JSON.",
            ),
        )
        return {"ok": True, "provider": provider.name, "model": response.model, "sample": response.text[:200]}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:500]}


# ── prompts registry (§37) ───────────────────────────────────────────────────


@router.get("/prompts")
def prompts(user: User = Depends(get_current_user)):
    return list_prompts()


# ── agent execution log (§40) ────────────────────────────────────────────────


@router.get("/agent-executions")
def agent_executions(
    job_id: str | None = None,
    application_id: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        db.query(AgentExecution)
        .outerjoin(Job, AgentExecution.job_id == Job.id)
        .outerjoin(Application, AgentExecution.application_id == Application.id)
        .filter((Job.user_id == user.id) | (Application.user_id == user.id))
    )
    if job_id:
        query = query.filter(AgentExecution.job_id == job_id)
    if application_id:
        query = query.filter(AgentExecution.application_id == application_id)
    rows = query.order_by(AgentExecution.created_at.desc()).limit(min(limit, 200)).all()
    # Never expose raw prompts (§40); outputs are truncated summaries.
    return [
        to_dict(r, exclude={"output"})
        for r in rows
    ]


# ── SSE progress (§53) ───────────────────────────────────────────────────────


@router.get("/workflows/{workflow_id}/events")
async def workflow_events(workflow_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    run = db.get(WorkflowRun, workflow_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "Workflow not found")

    async def stream():
        # initial snapshot
        yield f"data: {json.dumps({'type': 'workflow', 'data': to_dict(run)})}\n\n"
        queue = subscribe("workflow", workflow_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    status = event.get("data", {}).get("status")
                    if status in ("COMPLETED", "FAILED"):
                        break
                except asyncio.TimeoutError:
                    db2 = SessionLocal()
                    try:
                        current = db2.get(WorkflowRun, workflow_id)
                        if current is None:
                            break
                        yield f"data: {json.dumps({'type': 'workflow', 'data': to_dict(current)})}\n\n"
                        if current.status in ("COMPLETED", "FAILED"):
                            break
                    finally:
                        db2.close()
        finally:
            unsubscribe("workflow", workflow_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream")
