"""Retrieval-grounded Career Coach turns. Never dump the full knowledge base."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..agents.base import AgentContext
from ..agents.coach import CareerCoachAgent
from ..models import AgentExecution, Application, ApplicationStrategy, CareerProfile, Job, User
from ..models.coach import CoachConversation, CoachMessage
from ..retrieval.pipeline import retrieve_evidence
from ..security.injection import sanitize_untrusted

HISTORY_LIMIT = 10
EVIDENCE_LIMIT = 12


def _owned_job(db: Session, user_id: str, job_id: str | None) -> Job | None:
    if not job_id:
        return None
    return (
        db.query(Job)
        .filter(Job.id == job_id, Job.user_id == user_id, Job.is_deleted == False)  # noqa: E712
        .first()
    )


def _owned_application(db: Session, user_id: str, application_id: str | None) -> Application | None:
    if not application_id:
        return None
    return (
        db.query(Application)
        .filter(
            Application.id == application_id,
            Application.user_id == user_id,
            Application.is_deleted == False,  # noqa: E712
        )
        .first()
    )


def compact_profile(db: Session, user_id: str) -> dict:
    profile = db.query(CareerProfile).filter_by(user_id=user_id).first()
    if not profile:
        return {}
    return {
        "full_name": profile.full_name,
        "headline": profile.headline,
        "summary": (profile.summary or "")[:600],
        "primary_profession": profile.primary_profession,
        "target_sectors": profile.target_sectors or [],
        "preferred_positioning": (profile.preferred_positioning or "")[:400],
    }


def job_context(job: Job | None) -> dict | None:
    if not job:
        return None
    parsed = job.parsed if isinstance(job.parsed, dict) else {}
    return {
        "job_id": job.id,
        "organization_name": job.organization_name,
        "position_title": job.position_title,
        "summary": (job.executive_summary or "")[:800],
        "note": "This is vacancy context only. It is not evidence of the user's capability.",
        "requirements": [
            {"text": r.get("text"), "category": r.get("category"), "importance": r.get("importance")}
            for r in (parsed.get("requirements") or [])[:12]
            if isinstance(r, dict)
        ],
    }


def application_context(db: Session, app: Application | None) -> dict | None:
    if not app:
        return None
    strategy = (
        db.query(ApplicationStrategy).filter_by(application_id=app.id).first()
    )
    return {
        "application_id": app.id,
        "status": app.status,
        "fit_score": app.fit_score_snapshot,
        "note": "Application strategy is advice, not additional career evidence.",
        "positioning": (strategy.positioning if strategy else "")[:400],
        "concerns": (strategy.concerns if strategy else [])[:6],
    }


def resolve_citations(retrieved: list, citation_ids: list[str]) -> list[dict]:
    by_id = {item.entity_id: item for item in retrieved}
    by_key = {f"{item.entity_type}:{item.entity_id}": item for item in retrieved}
    out: list[dict] = []
    seen: set[str] = set()
    for raw in citation_ids:
        item = by_id.get(raw) or by_key.get(raw)
        if item is None or item.entity_id in seen:
            continue
        seen.add(item.entity_id)
        label = (item.metadata or {}).get("name") or (item.text or "").split("\n")[0][:80]
        out.append(
            {
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "label": label or item.entity_type,
                "verification_status": item.verification_status,
            }
        )
    return out


def conversation_payload(conv: CoachConversation, messages: list[CoachMessage] | None = None) -> dict:
    body = {
        "id": conv.id,
        "title": conv.title,
        "job_id": conv.job_id,
        "application_id": conv.application_id,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
    }
    if messages is not None:
        body["messages"] = [message_payload(m) for m in messages]
    return body


def message_payload(msg: CoachMessage) -> dict:
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "citations": msg.citations or [],
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "token_usage": msg.token_usage or {},
    }


def run_turn(
    db: Session,
    user: User,
    conv: CoachConversation,
    question: str,
    *,
    job_id: str | None = None,
    application_id: str | None = None,
) -> CoachMessage:
    question = sanitize_untrusted((question or "").strip())
    if not question:
        raise ValueError("Question is required")

    job = _owned_job(db, user.id, job_id or conv.job_id)
    app = _owned_application(db, user.id, application_id or conv.application_id)
    if job:
        conv.job_id = job.id
    if app:
        conv.application_id = app.id
        if not conv.job_id:
            conv.job_id = app.job_id

    user_msg = CoachMessage(
        conversation_id=conv.id,
        user_id=user.id,
        role="user",
        content=question,
    )
    db.add(user_msg)
    db.flush()

    retrieved = retrieve_evidence(db, user.id, question, limit=EVIDENCE_LIMIT)
    history = (
        db.query(CoachMessage)
        .filter(
            CoachMessage.conversation_id == conv.id,
            CoachMessage.is_deleted == False,  # noqa: E712
        )
        .order_by(CoachMessage.created_at.asc())
        .all()
    )
    history_payload = [
        {"role": m.role, "content": m.content}
        for m in history[-HISTORY_LIMIT:]
        if m.id != user_msg.id
    ]
    evidence_payload = [
        {
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "text": item.text[:1200],
            "verification_status": item.verification_status,
        }
        for item in retrieved
    ]
    payload = {
        "question": question,
        "profile": compact_profile(db, user.id),
        "evidence": evidence_payload,
        "history": history_payload,
        "job_context": job_context(job),
        "application_context": application_context(db, app),
    }

    ctx = AgentContext(db=db, user_id=user.id, job_id=conv.job_id, application_id=conv.application_id)
    result = CareerCoachAgent().run(ctx, payload=payload)
    citations = resolve_citations(retrieved, list(result.citation_ids or []))
    if result.refused:
        citations = []

    answer = (result.answer or "").strip()
    if result.refused and not answer:
        answer = "I do not have enough evidenced information in your career knowledge base to answer that."

    execution = (
        db.query(AgentExecution)
        .filter(AgentExecution.agent_name == "career_coach")
        .order_by(AgentExecution.created_at.desc())
        .first()
    )
    usage = execution.token_usage if execution else {}
    assistant = CoachMessage(
        conversation_id=conv.id,
        user_id=user.id,
        role="assistant",
        content=answer,
        citations=citations,
        token_usage=usage or {},
        prompt_tokens=int((usage or {}).get("prompt_tokens") or 0),
        completion_tokens=int((usage or {}).get("completion_tokens") or 0),
        latency_ms=float(execution.duration_ms) if execution else 0.0,
    )
    db.add(assistant)
    if not conv.title:
        conv.title = question[:80]
    db.flush()
    return assistant
