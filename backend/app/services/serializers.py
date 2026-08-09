"""Entity -> dict serialization used by API responses and agent payloads."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import (
    Achievement,
    CareerDocument,
    CareerEvidence,
    CareerNarrative,
    Certification,
    Education,
    Experience,
    Language,
    Project,
    Publication,
    Skill,
)


def _dt(v: Any) -> Any:
    return v.isoformat() if isinstance(v, (datetime, date)) else v


def to_dict(obj, exclude: set[str] | None = None) -> dict:
    exclude = exclude or set()
    out = {}
    for col in obj.__table__.columns:
        if col.name in exclude:
            continue
        out[col.name] = _dt(getattr(obj, col.name))
    return out


def experience_payload(db: Session, exp: Experience) -> dict:
    data = to_dict(exp)
    achievements = (
        db.query(Achievement)
        .filter(Achievement.experience_id == exp.id, Achievement.is_deleted == False)  # noqa: E712
        .all()
    )
    data["achievements"] = [
        {"id": a.id, "description": a.description, "quantified_result": a.quantified_result}
        for a in achievements
    ]
    return data


def full_knowledge_base(db: Session, user_id: str) -> dict:
    """The complete structured profile handed to document agents."""
    experiences = (
        db.query(Experience)
        .filter(Experience.user_id == user_id, Experience.is_deleted == False)  # noqa: E712
        .all()
    )
    return {
        "experiences": [experience_payload(db, e) for e in experiences],
        "achievements": [
            to_dict(a)
            for a in db.query(Achievement).filter(
                Achievement.user_id == user_id, Achievement.is_deleted == False  # noqa: E712
            )
        ],
        "projects": [
            to_dict(p)
            for p in db.query(Project).filter(Project.user_id == user_id, Project.is_deleted == False)  # noqa: E712
        ],
        "skills": [
            to_dict(s)
            for s in db.query(Skill).filter(Skill.user_id == user_id, Skill.is_deleted == False)  # noqa: E712
        ],
        "education": [
            to_dict(e)
            for e in db.query(Education).filter(Education.user_id == user_id, Education.is_deleted == False)  # noqa: E712
        ],
        "certifications": [
            to_dict(c)
            for c in db.query(Certification).filter(
                Certification.user_id == user_id, Certification.is_deleted == False  # noqa: E712
            )
        ],
        "languages": [
            to_dict(l)
            for l in db.query(Language).filter(Language.user_id == user_id, Language.is_deleted == False)  # noqa: E712
        ],
        "publications": [
            to_dict(p)
            for p in db.query(Publication).filter(
                Publication.user_id == user_id, Publication.is_deleted == False  # noqa: E712
            )
        ],
        "narratives": [
            to_dict(n)
            for n in db.query(CareerNarrative).filter(
                CareerNarrative.user_id == user_id, CareerNarrative.is_deleted == False  # noqa: E712
            )
        ],
    }


def evidence_lookup(db: Session, user_id: str) -> dict[tuple[str, str], CareerEvidence]:
    rows = db.query(CareerEvidence).filter(CareerEvidence.user_id == user_id).all()
    return {(r.entity_type, r.entity_id): r for r in rows}


def evidence_for_entity(db: Session, user_id: str, entity_type: str, entity_id: str) -> list[dict]:
    rows = (
        db.query(CareerEvidence)
        .filter(
            CareerEvidence.user_id == user_id,
            CareerEvidence.entity_type == entity_type,
            CareerEvidence.entity_id == entity_id,
        )
        .all()
    )
    out = []
    for r in rows:
        doc = db.get(CareerDocument, r.source_document_id) if r.source_document_id else None
        out.append(
            {
                "id": r.id,
                "claim": r.claim,
                "source_document": doc.filename if doc else None,
                "source_page": r.source_page,
                "source_section": r.source_section,
                "original_text": r.original_text,
                "verification_status": r.verification_status,
                "confidence": r.confidence,
            }
        )
    return out
