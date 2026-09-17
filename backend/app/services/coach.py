"""Retrieval-grounded Career Coach turns. Never dump the full knowledge base."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..agents.base import AgentContext
from ..agents.coach import CareerCoachAgent
from ..models import (
    Achievement,
    Application,
    ApplicationStrategy,
    CareerProfile,
    Certification,
    CoverLetter,
    CV,
    DocumentVersion,
    Education,
    Experience,
    Job,
    JobRequirement,
    JobScore,
    Language,
    ProfessionalKnowledge,
    Project,
    RequirementMatch,
    Skill,
    User,
)
from ..models.coach import CoachConversation, CoachMessage
from ..prompts.language import reply_language_for_question, ui_language_for_user
from ..retrieval.pipeline import retrieve_evidence
from ..security.injection import sanitize_untrusted

REFUSED_FALLBACK = {
    "ar": "لا تتوفر أدلة كافية في قاعدة معرفتك المهنية للإجابة على ذلك.",
    "en": "I do not have enough evidenced information in your career knowledge base to answer that.",
}

HISTORY_LIMIT = 10
HISTORY_MESSAGE_CHARS = 1500
EVIDENCE_LIMIT = 12
PROFILE_LIST_LIMIT = 8
SKILL_LIST_LIMIT = 15
MATCH_REQUIREMENT_LIMIT = 20
DOCUMENT_EXCERPT_CHARS = 1500


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


def _not_deleted(query, model):
    return query.filter(model.is_deleted == False)  # noqa: E712


def compact_profile(db: Session, user_id: str) -> dict:
    """Compact profile PLUS deterministic knowledge-base overview.

    Aggregate questions ("what skills do I have?", "list my certifications")
    cannot be answered by top-k semantic retrieval — the counts and short
    listings below give the coach ground truth without dumping the KB.
    """
    profile = db.query(CareerProfile).filter_by(user_id=user_id).first()
    skills = (
        _not_deleted(db.query(Skill).filter(Skill.user_id == user_id), Skill)
        .order_by(Skill.evidence_count.desc(), Skill.canonical_name.asc())
        .limit(SKILL_LIST_LIMIT)
        .all()
    )
    experiences = (
        _not_deleted(db.query(Experience).filter(Experience.user_id == user_id), Experience)
        .order_by(Experience.start_date.desc())
        .limit(PROFILE_LIST_LIMIT)
        .all()
    )
    education = (
        _not_deleted(db.query(Education).filter(Education.user_id == user_id), Education)
        .limit(PROFILE_LIST_LIMIT)
        .all()
    )
    certifications = (
        _not_deleted(db.query(Certification).filter(Certification.user_id == user_id), Certification)
        .limit(PROFILE_LIST_LIMIT)
        .all()
    )
    languages = (
        _not_deleted(db.query(Language).filter(Language.user_id == user_id), Language)
        .limit(PROFILE_LIST_LIMIT)
        .all()
    )
    counts = {
        "experiences": _not_deleted(db.query(Experience).filter(Experience.user_id == user_id), Experience).count(),
        "achievements": _not_deleted(db.query(Achievement).filter(Achievement.user_id == user_id), Achievement).count(),
        "projects": _not_deleted(db.query(Project).filter(Project.user_id == user_id), Project).count(),
        "skills": _not_deleted(db.query(Skill).filter(Skill.user_id == user_id), Skill).count(),
        "professional_knowledge": _not_deleted(
            db.query(ProfessionalKnowledge).filter(ProfessionalKnowledge.user_id == user_id),
            ProfessionalKnowledge,
        ).count(),
    }
    return {
        "full_name": profile.full_name if profile else "",
        "headline": profile.headline if profile else "",
        "summary": ((profile.summary or "")[:600]) if profile else "",
        "primary_profession": profile.primary_profession if profile else "",
        "target_sectors": (profile.target_sectors or []) if profile else [],
        "preferred_positioning": ((profile.preferred_positioning or "")[:400]) if profile else "",
        "knowledge_base_counts": counts,
        "skills": [
            {
                "name": s.canonical_name,
                "category": s.category,
                "years_experience": s.years_experience,
                "verification_status": s.verification_status,
            }
            for s in skills
        ],
        "experiences": [
            {
                "job_title": e.job_title,
                "organization": e.organization,
                "start_date": e.start_date,
                "end_date": e.end_date,
            }
            for e in experiences
        ],
        "education": [
            {"degree": e.degree, "field_of_study": e.field_of_study, "institution": e.institution}
            for e in education
        ],
        "certifications": [{"name": c.name, "issuer": c.issuer} for c in certifications],
        "languages": [
            {"language": lang.language, "proficiency": lang.proficiency, "is_native": lang.is_native}
            for lang in languages
        ],
    }


def _match_analysis(db: Session, job_id: str) -> dict | None:
    """Deterministic matching/scoring output — the coach must quote this,
    not re-derive fit from raw requirements."""
    score = (
        db.query(JobScore)
        .filter(JobScore.job_id == job_id)
        .order_by(JobScore.created_at.desc())
        .first()
    )
    matches = (
        db.query(RequirementMatch, JobRequirement)
        .join(JobRequirement, JobRequirement.id == RequirementMatch.requirement_id)
        .filter(RequirementMatch.job_id == job_id)
        .limit(MATCH_REQUIREMENT_LIMIT)
        .all()
    )
    if not score and not matches:
        return None
    return {
        "note": "Deterministic output of the matching/scoring engine. Treat as ground truth; never recompute fit yourself.",
        "overall_score": score.overall_score if score else None,
        "overall_score_range": (
            [score.overall_score_low, score.overall_score_high] if score else None
        ),
        "coverage": score.coverage if score else None,
        "recommendation": score.recommendation if score else "",
        "gaps": (score.gaps or [])[:10] if score else [],
        "strong_matches": (score.strong_matches or [])[:10] if score else [],
        "partial_matches": (score.partial_matches or [])[:10] if score else [],
        "transferable": (score.transferable or [])[:10] if score else [],
        "requirements": [
            {
                "text": (req.text or "")[:200],
                "importance": req.importance,
                "requirement_type": req.requirement_type,
                "status": match.status,
                "match_kind": match.match_kind,
                "explanation": (match.explanation or "")[:240],
            }
            for match, req in matches
        ],
    }


def job_context(db: Session, job: Job | None) -> dict | None:
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
        "match_analysis": _match_analysis(db, job.id),
    }


def _application_documents(db: Session, application_id: str) -> list[dict]:
    """Current CV / cover-letter snapshots so the coach can discuss the actual
    documents (excerpt only — editing stays in the Documents screen)."""
    docs: list[dict] = []
    for doc_type, model in (("cv", CV), ("cover_letter", CoverLetter)):
        doc = db.query(model).filter_by(application_id=application_id).first()
        if not doc:
            continue
        version = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_type == doc_type,
                DocumentVersion.document_id == doc.id,
                DocumentVersion.is_current == True,  # noqa: E712
            )
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )
        if not version:
            continue
        ats = version.ats_analysis if isinstance(version.ats_analysis, dict) else {}
        docs.append(
            {
                "document_type": doc_type,
                "title": doc.title,
                "version": version.version_number,
                "is_approved": version.is_approved,
                "user_edited": version.user_edited,
                "ats_score": ats.get("ats_score"),
                "ats_missing_keywords": (ats.get("missing_keywords") or [])[:8],
                "text_excerpt": (version.rendered_text or "")[:DOCUMENT_EXCERPT_CHARS],
                "note": "Excerpt of the current version. The coach may quote and critique it but cannot edit documents.",
            }
        )
    return docs


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
        "ats_score": app.ats_score_snapshot,
        "note": "Application strategy is advice, not additional career evidence.",
        "positioning": (strategy.positioning if strategy else "")[:400],
        "concerns": (strategy.concerns if strategy else [])[:6],
        "keywords": (strategy.keywords if strategy else [])[:20],
        "priority_skills": (strategy.priority_skills if strategy else [])[:10],
        "de_emphasis": (strategy.de_emphasis if strategy else [])[:6],
        "messaging_strategy": (strategy.messaging_strategy if strategy else "")[:600],
        "documents": _application_documents(db, app.id),
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


def _retrieval_query(question: str, history: list[CoachMessage]) -> str:
    """History-aware retrieval query.

    Follow-up questions ("what about the second one?", "and my education?")
    are meaningless as standalone embedding inputs — ground them in the last
    exchange so retrieval stays on-topic.
    """
    if not history:
        return question
    parts = [f"{m.role}: {m.content[:300]}" for m in history[-2:]]
    parts.append(f"user: {question}")
    return "\n".join(parts)


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

    history = (
        db.query(CoachMessage)
        .filter(
            CoachMessage.conversation_id == conv.id,
            CoachMessage.is_deleted == False,  # noqa: E712
        )
        .order_by(CoachMessage.created_at.asc())
        .all()
    )
    history_rows = [m for m in history[-HISTORY_LIMIT:] if m.id != user_msg.id]
    # Bound per-message size so 10 long turns cannot blow the prompt budget.
    history_payload = [
        {"role": m.role, "content": m.content[:HISTORY_MESSAGE_CHARS]}
        for m in history_rows
    ]
    retrieved = retrieve_evidence(
        db, user.id, _retrieval_query(question, history_rows), limit=EVIDENCE_LIMIT
    )
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
        "job_context": job_context(db, job),
        "application_context": application_context(db, app),
    }

    ctx = AgentContext(db=db, user_id=user.id, job_id=conv.job_id, application_id=conv.application_id)
    agent = CareerCoachAgent()
    result = agent.run(ctx, payload=payload)
    citations = resolve_citations(retrieved, list(result.citation_ids or []))
    if result.refused:
        citations = []

    answer = (result.answer or "").strip()
    if result.refused and not answer:
        lang = reply_language_for_question(
            question, history_payload, ui_language_for_user(db, user.id)
        )
        answer = REFUSED_FALLBACK.get(lang, REFUSED_FALLBACK["en"])

    # Per-instance reference — never query "latest execution by agent name":
    # concurrent coach turns (even across users) would attach the wrong usage.
    execution = agent.last_execution
    usage = (execution.token_usage if execution else {}) or {}
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
