"""Hybrid retrieval pipeline (§35-36).

Query → normalization → semantic embedding → vector retrieval →
PostgreSQL metadata filtering → keyword re-ranking → deduplication →
top-N evidence handed to the LLM (never the whole database).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import (
    Achievement,
    CareerNarrative,
    Certification,
    Education,
    Experience,
    KnowledgeContext,
    Language,
    ProfessionalKnowledge,
    Project,
    Skill,
)
from .embeddings import get_embedding_provider, tokenize
from .vector_store import VectorRecord, get_vector_store

# Entity types that are indexed for semantic retrieval (§3 vector database)
INDEXED_ENTITY_TYPES = (
    "experience", "achievement", "project", "skill", "education",
    "certification", "language", "narrative", "professional_knowledge",
)


@dataclass
class EvidenceItem:
    entity_type: str
    entity_id: str
    text: str
    score: float = 0.0
    source: str = ""
    verification_status: str = "unverified"
    confidence: float = 0.5
    metadata: dict = field(default_factory=dict)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def _entity_text(entity_type: str, obj) -> str:
    if isinstance(obj, Experience):
        parts = [obj.job_title, obj.organization, obj.description]
        parts += obj.responsibilities or []
        parts += obj.technologies or []
        parts += obj.domains or []
        parts += obj.leadership or []
        return "\n".join(p for p in parts if p)
    if isinstance(obj, Achievement):
        return "\n".join(p for p in [obj.title, obj.description, obj.quantified_result] if p)
    if isinstance(obj, Project):
        parts = [obj.name, obj.role, obj.description]
        parts += obj.technologies or []
        parts += obj.outcomes or []
        return "\n".join(p for p in parts if p)
    if isinstance(obj, Skill):
        return " ".join([obj.canonical_name, obj.category] + (obj.synonyms or []))
    if isinstance(obj, ProfessionalKnowledge):
        parts = [obj.canonical_name, obj.kind, obj.depth, obj.summary]
        parts += obj.synonyms or []
        return "\n".join(p for p in parts if p)
    if isinstance(obj, Education):
        return "\n".join(p for p in [obj.degree, obj.field_of_study, obj.institution, obj.description] if p)
    if isinstance(obj, Certification):
        return "\n".join(p for p in [obj.name, obj.issuer] if p)
    if isinstance(obj, Language):
        return " ".join(p for p in [obj.language, obj.proficiency, "native" if obj.is_native else ""] if p)
    if isinstance(obj, CareerNarrative):
        return f"{obj.title}\n{obj.content}"
    return str(obj)


_MODEL_FOR = {
    "experience": Experience,
    "achievement": Achievement,
    "project": Project,
    "skill": Skill,
    "professional_knowledge": ProfessionalKnowledge,
    "education": Education,
    "certification": Certification,
    "language": Language,
    "narrative": CareerNarrative,
}


def _structured_metadata(entity_type: str, obj) -> dict:
    if entity_type == "experience":
        return {"start_date": obj.start_date, "end_date": obj.end_date}
    if entity_type == "education":
        return {"degree": obj.degree, "field_of_study": obj.field_of_study}
    if entity_type == "certification":
        return {"name": obj.name, "issuer": obj.issuer}
    if entity_type == "language":
        return {"language": obj.language, "proficiency": obj.proficiency, "is_native": obj.is_native}
    if entity_type == "skill":
        return {"name": obj.canonical_name, "years_experience": obj.years_experience}
    if entity_type == "professional_knowledge":
        return {
            "name": obj.canonical_name,
            "kind": obj.kind,
            "depth": obj.depth,
            "years_experience": obj.years_experience,
        }
    return {}


def index_entity(db: Session, entity_type: str, entity_id: str) -> None:
    """(Re)index one career entity into the vector store."""
    model = _MODEL_FOR[entity_type]
    obj = db.get(model, entity_id)
    if obj is None or getattr(obj, "is_deleted", False):
        get_vector_store().delete([f"{entity_type}:{entity_id}"])
        return
    text = _entity_text(entity_type, obj)
    if entity_type == "professional_knowledge":
        extras = (
            db.query(KnowledgeContext)
            .filter(
                KnowledgeContext.knowledge_id == entity_id,
                KnowledgeContext.is_deleted == False,  # noqa: E712
            )
            .all()
        )
        for ctx in extras:
            text = "\n".join(
                part for part in [text, ctx.how_acquired, ctx.how_applied, ctx.acquisition_mode] if part
            )
    vector = get_embedding_provider().embed([text])[0]
    get_vector_store().upsert(
        [
            VectorRecord(
                id=f"{entity_type}:{entity_id}",
                vector=vector,
                payload={
                    "user_id": obj.user_id,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "verification_status": getattr(obj, "verification_status", "unverified"),
                },
            )
        ]
    )


def index_all_for_user(db: Session, user_id: str) -> int:
    count = 0
    for entity_type, model in _MODEL_FOR.items():
        for (entity_id,) in db.query(model.id).filter(model.user_id == user_id):
            index_entity(db, entity_type, entity_id)
            count += 1
    return count


def _keyword_score(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = set(tokenize(text))
    overlap = query_tokens & text_tokens
    return len(overlap) / len(query_tokens)


_indexed_users: set[str] = set()


def _ensure_indexed(db: Session, user_id: str) -> None:
    """Lazy per-user indexing.

    The in-process vector backend does not survive process restarts, and the
    seeder may run in a different process than the API. On first retrieval per
    user per process, (re)index that user's entities — idempotent for Qdrant.
    """
    if user_id in _indexed_users:
        return
    _indexed_users.add(user_id)
    index_all_for_user(db, user_id)


def retrieve_evidence(
    db: Session,
    user_id: str,
    query: str,
    *,
    limit: int = 12,
    entity_types: tuple[str, ...] = INDEXED_ENTITY_TYPES,
    semantic_weight: float = 0.65,
) -> list[EvidenceItem]:
    """Hybrid retrieval: semantic + keyword + metadata filtering (§35)."""
    _ensure_indexed(db, user_id)
    normalized = normalize_query(query)
    query_vec = get_embedding_provider().embed([normalized])[0]
    hits = get_vector_store().search(
        query_vec, limit=limit * 3, where={"user_id": user_id, "entity_type": list(entity_types)}
    )

    query_tokens = set(tokenize(normalized))
    items: list[EvidenceItem] = []
    for hit in hits:
        entity_type = hit.payload["entity_type"]
        entity_id = hit.payload["entity_id"]
        model = _MODEL_FOR[entity_type]
        obj = db.get(model, entity_id)
        if obj is None or getattr(obj, "is_deleted", False):
            continue
        text = _entity_text(entity_type, obj)
        if entity_type == "professional_knowledge":
            extras = (
                db.query(KnowledgeContext)
                .filter(
                    KnowledgeContext.knowledge_id == entity_id,
                    KnowledgeContext.is_deleted == False,  # noqa: E712
                )
                .all()
            )
            for ctx in extras:
                text = "\n".join(
                    part for part in [text, ctx.how_acquired, ctx.how_applied] if part
                )
        kw = _keyword_score(query_tokens, text)
        combined = semantic_weight * hit.score + (1 - semantic_weight) * kw
        items.append(
            EvidenceItem(
                entity_type=entity_type,
                entity_id=entity_id,
                text=text,
                score=combined,
                source=hit.payload.get("verification_status", ""),
                verification_status=getattr(obj, "verification_status", "unverified"),
                confidence=getattr(obj, "confidence", 0.5),
                metadata=_structured_metadata(entity_type, obj),
            )
        )

    # Deduplicate by entity and rank
    seen: set[tuple[str, str]] = set()
    ranked: list[EvidenceItem] = []
    for item in sorted(items, key=lambda i: i.score, reverse=True):
        key = (item.entity_type, item.entity_id)
        if key in seen:
            continue
        seen.add(key)
        ranked.append(item)
        if len(ranked) >= limit:
            break
    return ranked
