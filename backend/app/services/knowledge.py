"""Upsert, linking, and compatibility helpers for professional knowledge."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import (
    CareerDocument,
    CareerEvidence,
    Experience,
    KnowledgeContext,
    ProfessionalKnowledge,
    User,
)
from ..models.career import KNOWLEDGE_ACQUISITION_MODES, KNOWLEDGE_DEPTHS, KNOWLEDGE_KINDS
from ..retrieval.pipeline import index_entity

KIND_ALIASES = {
    "industry": "industry",
    "sector": "industry",
    "domain": "domain",
    "business_function": "business_function",
    "function": "business_function",
    "functional": "business_function",
    "process": "process",
    "workflow": "process",
    "methodology": "methodology",
    "methodologies": "methodology",
    "regulation": "regulation",
    "regulatory": "regulation",
    "compliance": "regulation",
    "product_service": "product_service",
    "product": "product_service",
    "service": "product_service",
    "customer_stakeholder": "customer_stakeholder",
    "stakeholder": "customer_stakeholder",
    "customer": "customer_stakeholder",
    "terminology": "terminology",
    "glossary": "terminology",
}

DEPTH_ALIASES = {
    "awareness": "awareness",
    "exposed": "awareness",
    "exposure": "awareness",
    "familiar": "awareness",
    "applied": "applied",
    "used": "applied",
    "practiced": "practiced",
    "regular": "practiced",
    "expert": "expert",
    "expertise": "expert",
}

MODE_ALIASES = {
    "acquired_through_role": "acquired_through_role",
    "role": "acquired_through_role",
    "applied": "applied",
    "adjacent_exposure": "adjacent_exposure",
    "adjacent": "adjacent_exposure",
    "exposure": "adjacent_exposure",
    "training": "training",
}


def normalize_kind(value: str | None) -> str:
    raw = (value or "domain").strip().lower().replace(" ", "_").replace("-", "_")
    return KIND_ALIASES.get(raw, raw if raw in KNOWLEDGE_KINDS else "domain")


def normalize_depth(value: str | None) -> str:
    raw = (value or "applied").strip().lower().replace(" ", "_").replace("-", "_")
    return DEPTH_ALIASES.get(raw, raw if raw in KNOWLEDGE_DEPTHS else "applied")


def normalize_mode(value: str | None) -> str:
    raw = (value or "acquired_through_role").strip().lower().replace(" ", "_").replace("-", "_")
    return MODE_ALIASES.get(raw, raw if raw in KNOWLEDGE_ACQUISITION_MODES else "acquired_through_role")


def canonical_key(name: str) -> str:
    return " ".join((name or "").strip().split()).lower()


def _record_provenance(
    db: Session,
    user_id: str,
    entity_type: str,
    entity_id: str,
    claim: str,
    document: CareerDocument | None = None,
    section: str = "Knowledge",
    confidence: float = 0.6,
) -> None:
    db.add(
        CareerEvidence(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            claim=claim,
            source_document_id=document.id if document else None,
            source_section=section,
            original_text=claim,
            verification_status="needs_review",
            confidence=confidence,
        )
    )
    db.flush()


def find_knowledge(db: Session, user_id: str, name: str) -> ProfessionalKnowledge | None:
    key = canonical_key(name)
    if not key:
        return None
    rows = (
        db.query(ProfessionalKnowledge)
        .filter(ProfessionalKnowledge.user_id == user_id, ProfessionalKnowledge.is_deleted == False)  # noqa: E712
        .all()
    )
    for row in rows:
        aliases = {canonical_key(row.name), canonical_key(row.canonical_name)}
        aliases.update(canonical_key(alias) for alias in (row.synonyms or []) if alias)
        if key in aliases:
            return row
    return None


def upsert_knowledge(
    db: Session,
    user: User,
    payload: dict,
    *,
    document: CareerDocument | None = None,
    index: bool = True,
) -> ProfessionalKnowledge:
    name = (payload.get("name") or payload.get("canonical_name") or "").strip()
    if not name:
        raise ValueError("Knowledge name is required")
    canonical = (payload.get("canonical_name") or name).strip()
    kind = normalize_kind(payload.get("kind"))
    depth = normalize_depth(payload.get("depth"))
    summary = (payload.get("summary") or "").strip()
    synonyms = [str(item).strip() for item in (payload.get("synonyms") or []) if str(item).strip()]
    confidence = float(payload.get("confidence") or 0.6)
    years = payload.get("years_experience")
    row = find_knowledge(db, user.id, canonical) or find_knowledge(db, user.id, name)
    if row:
        row.synonyms = sorted(set(row.synonyms or []) | {name} | set(synonyms) - {row.canonical_name})
        row.evidence_count = (row.evidence_count or 0) + 1
        if summary and not (row.summary or "").strip():
            row.summary = summary
        if payload.get("kind") and row.kind == "domain":
            row.kind = kind
        depth_rank = {name: i for i, name in enumerate(KNOWLEDGE_DEPTHS)}
        if depth_rank.get(depth, 0) > depth_rank.get(row.depth, 0):
            row.depth = depth
        if years and (row.years_experience is None or float(years) > float(row.years_experience)):
            row.years_experience = float(years)
        row.verification_status = "needs_review"
        row.confidence = max(float(row.confidence or 0), confidence)
    else:
        row = ProfessionalKnowledge(
            user_id=user.id,
            name=name,
            canonical_name=canonical,
            kind=kind,
            summary=summary,
            depth=depth,
            years_experience=float(years) if years not in (None, "") else None,
            synonyms=synonyms,
            evidence_count=1,
            verification_status=payload.get("verification_status") or "needs_review",
            confidence=confidence,
        )
        db.add(row)
        db.flush()
    _record_provenance(db, user.id, "professional_knowledge", row.id, name, document, confidence=confidence)
    if index:
        index_entity(db, "professional_knowledge", row.id)
    return row


def attach_context(
    db: Session,
    user: User,
    knowledge: ProfessionalKnowledge,
    payload: dict,
    *,
    document: CareerDocument | None = None,
) -> KnowledgeContext:
    experience_id = payload.get("experience_id") or None
    project_id = payload.get("project_id") or None
    achievement_id = payload.get("achievement_id") or None
    education_id = payload.get("education_id") or None
    existing = (
        db.query(KnowledgeContext)
        .filter(
            KnowledgeContext.user_id == user.id,
            KnowledgeContext.knowledge_id == knowledge.id,
            KnowledgeContext.experience_id == experience_id,
            KnowledgeContext.project_id == project_id,
            KnowledgeContext.achievement_id == achievement_id,
            KnowledgeContext.education_id == education_id,
            KnowledgeContext.is_deleted == False,  # noqa: E712
        )
        .first()
    )
    how_acquired = (payload.get("how_acquired") or "").strip()
    how_applied = (payload.get("how_applied") or "").strip()
    mode = normalize_mode(payload.get("acquisition_mode"))
    confidence = float(payload.get("confidence") or knowledge.confidence or 0.6)
    if existing:
        if how_acquired and how_acquired not in (existing.how_acquired or ""):
            existing.how_acquired = f"{existing.how_acquired}\n{how_acquired}".strip()
        if how_applied and how_applied not in (existing.how_applied or ""):
            existing.how_applied = f"{existing.how_applied}\n{how_applied}".strip()
        existing.acquisition_mode = mode or existing.acquisition_mode
        existing.verification_status = "needs_review"
        db.flush()
        return existing
    context = KnowledgeContext(
        user_id=user.id,
        knowledge_id=knowledge.id,
        experience_id=experience_id,
        project_id=project_id,
        achievement_id=achievement_id,
        education_id=education_id,
        acquisition_mode=mode,
        how_acquired=how_acquired,
        how_applied=how_applied,
        source_document_id=document.id if document else payload.get("source_document_id"),
        verification_status=payload.get("verification_status") or "needs_review",
        confidence=confidence,
    )
    db.add(context)
    db.flush()
    _record_provenance(
        db,
        user.id,
        "knowledge_context",
        context.id,
        how_applied or how_acquired or knowledge.canonical_name,
        document,
        section="Knowledge context",
        confidence=confidence,
    )
    return context


def sync_experience_domains(db: Session, experience: Experience) -> None:
    """Keep Experience.domains populated for older clients."""
    rows = (
        db.query(ProfessionalKnowledge)
        .join(KnowledgeContext, KnowledgeContext.knowledge_id == ProfessionalKnowledge.id)
        .filter(
            KnowledgeContext.experience_id == experience.id,
            KnowledgeContext.is_deleted == False,  # noqa: E712
            ProfessionalKnowledge.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    names = []
    seen = set()
    for row in rows:
        key = canonical_key(row.canonical_name)
        if key in seen:
            continue
        seen.add(key)
        names.append(row.canonical_name)
    if names:
        experience.domains = names
        db.flush()
        index_entity(db, "experience", experience.id)


def knowledge_payload(db: Session, row: ProfessionalKnowledge) -> dict:
    contexts = (
        db.query(KnowledgeContext)
        .filter(
            KnowledgeContext.knowledge_id == row.id,
            KnowledgeContext.is_deleted == False,  # noqa: E712
        )
        .order_by(KnowledgeContext.created_at.desc())
        .all()
    )
    return {
        "id": row.id,
        "user_id": row.user_id,
        "name": row.name,
        "canonical_name": row.canonical_name,
        "kind": row.kind,
        "summary": row.summary,
        "depth": row.depth,
        "years_experience": row.years_experience,
        "synonyms": row.synonyms or [],
        "evidence_count": row.evidence_count,
        "verification_status": row.verification_status,
        "confidence": row.confidence,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "contexts": [
            {
                "id": ctx.id,
                "knowledge_id": ctx.knowledge_id,
                "experience_id": ctx.experience_id,
                "project_id": ctx.project_id,
                "achievement_id": ctx.achievement_id,
                "education_id": ctx.education_id,
                "acquisition_mode": ctx.acquisition_mode,
                "how_acquired": ctx.how_acquired,
                "how_applied": ctx.how_applied,
                "source_document_id": ctx.source_document_id,
                "verification_status": ctx.verification_status,
                "confidence": ctx.confidence,
            }
            for ctx in contexts
        ],
    }


def knowledge_items_from_extraction(result) -> list[dict]:
    items: list[dict] = []
    for raw in getattr(result, "professional_knowledge", None) or []:
        payload = raw.model_dump() if hasattr(raw, "model_dump") else dict(raw)
        items.append(payload)
    for exp in getattr(result, "experiences", None) or []:
        payload = exp.model_dump() if hasattr(exp, "model_dump") else dict(exp)
        org = payload.get("organization") or ""
        title = payload.get("job_title") or ""
        nested = payload.get("professional_knowledge") or []
        for item in nested:
            data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            data.setdefault("organization_hint", org)
            data.setdefault("job_title_hint", title)
            items.append(data)
        for domain in payload.get("domains") or []:
            name = str(domain).strip()
            if not name:
                continue
            items.append(
                {
                    "name": name,
                    "kind": "domain",
                    "depth": "applied",
                    "organization_hint": org,
                    "job_title_hint": title,
                    "how_acquired": f"Listed as a domain of {title} at {org}".strip(),
                    "confidence": payload.get("confidence") or 0.6,
                }
            )
    return items
