"""Career Knowledge Base CRUD + ingestion + search (§47, §52).

Every mutation updates the vector index so semantic retrieval stays fresh.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Achievement,
    CareerDocument,
    CareerNarrative,
    CareerProfile,
    Certification,
    Education,
    Experience,
    Language,
    Project,
    Publication,
    Skill,
    User,
)
from ..models import CareerEvidence
from ..retrieval.pipeline import index_entity, retrieve_evidence
from ..schemas.api import (
    AchievementIn,
    CertificationIn,
    EducationIn,
    ExperienceIn,
    IngestTextRequest,
    LanguageIn,
    NarrativeIn,
    ProfileIn,
    ProjectIn,
    PublicationIn,
    SkillIn,
)
from ..security.auth import audit, get_current_user
from ..security.uploads import validate_upload
from ..services.ingestion import IngestionService
from ..services.serializers import evidence_for_entity, to_dict

router = APIRouter(prefix="/api/career", tags=["career"])

# entity registry: path -> (model, input schema, vector entity type)
ENTITIES = {
    "experiences": (Experience, ExperienceIn, "experience"),
    "achievements": (Achievement, AchievementIn, "achievement"),
    "projects": (Project, ProjectIn, "project"),
    "skills": (Skill, SkillIn, "skill"),
    "education": (Education, EducationIn, None),
    "certifications": (Certification, CertificationIn, None),
    "languages": (Language, LanguageIn, None),
    "publications": (Publication, PublicationIn, None),
    "narratives": (CareerNarrative, NarrativeIn, "narrative"),
}


def _get_owned(db: Session, model, entity_id: str, user: User):
    obj = db.get(model, entity_id)
    if obj is None or obj.user_id != user.id or getattr(obj, "is_deleted", False):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return obj


def _claim_for(model, data: dict) -> str:
    if model is Experience:
        return f"{data.get('job_title', '')} at {data.get('organization', '')}".strip(" at")
    for field in ("description", "name", "title", "canonical_name", "institution", "language", "content"):
        if data.get(field):
            return str(data[field])[:500]
    return model.__tablename__


def _record_provenance(db: Session, user: User, model, entity_type: str, entity_id: str, data: dict) -> None:
    """Every fact carries provenance (§6) — manual entries cite the user."""
    db.add(
        CareerEvidence(
            user_id=user.id,
            entity_type=entity_type or model.__tablename__,
            entity_id=entity_id,
            claim=_claim_for(model, data),
            source_document_id=None,
            source_section="manual entry",
            original_text=_claim_for(model, data),
            verification_status=data.get("verification_status", "unverified"),
            confidence=data.get("confidence", 0.5) or 0.5,
        )
    )
    db.flush()


# ── profile ──────────────────────────────────────────────────────────────────


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user.id).first()
    return to_dict(profile) if profile else None


@router.put("/profile")
def put_profile(payload: ProfileIn, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user.id).first()
    if profile is None:
        profile = CareerProfile(user_id=user.id)
        db.add(profile)
    for field, value in payload.model_dump().items():
        setattr(profile, field, value)
    audit(db, user, "career.profile.update", "career_profile", profile.id, request=request)
    db.commit()
    return to_dict(profile)


# ── generic CRUD factory ─────────────────────────────────────────────────────


def _register_entity_routes():
    for path, (model, schema, vector_type) in ENTITIES.items():

        def list_items(path=path, model=model, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
            rows = (
                db.query(model)
                .filter(model.user_id == user.id, model.is_deleted == False)  # noqa: E712
                .order_by(model.created_at.desc())
                .all()
            )
            return [to_dict(r) for r in rows]

        def create_item(payload: schema, request: Request, path=path, model=model, vector_type=vector_type, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
            data = payload.model_dump()
            if model is Skill:
                data.setdefault("canonical_name", data.get("name", ""))
            obj = model(user_id=user.id, **data)
            db.add(obj)
            db.flush()
            _record_provenance(db, user, model, vector_type, obj.id, data)
            if vector_type:
                index_entity(db, vector_type, obj.id)
            audit(db, user, f"career.{path}.create", model.__tablename__, obj.id, request=request)
            db.commit()
            return to_dict(obj)

        def update_item(entity_id: str, payload: schema, request: Request, path=path, model=model, vector_type=vector_type, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
            obj = _get_owned(db, model, entity_id, user)
            for field, value in payload.model_dump().items():
                setattr(obj, field, value)
            if model is Skill and not obj.canonical_name:
                obj.canonical_name = obj.name
            if vector_type:
                index_entity(db, vector_type, obj.id)
            audit(db, user, f"career.{path}.update", model.__tablename__, obj.id, request=request)
            db.commit()
            return to_dict(obj)

        def delete_item(entity_id: str, request: Request, path=path, model=model, vector_type=vector_type, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
            obj = _get_owned(db, model, entity_id, user)
            obj.is_deleted = True  # soft delete (§51)
            if vector_type:
                index_entity(db, vector_type, obj.id)  # removes from index
            audit(db, user, f"career.{path}.delete", model.__tablename__, obj.id, request=request)
            db.commit()
            return {"deleted": entity_id}

        list_items.__name__ = f"list_{path}"
        create_item.__name__ = f"create_{path}"
        update_item.__name__ = f"update_{path}"
        delete_item.__name__ = f"delete_{path}"
        # Resolve the payload schema for FastAPI: closure variables are not
        # visible to get_type_hints, so bind the class directly.
        create_item.__annotations__["payload"] = schema
        update_item.__annotations__["payload"] = schema

        router.get(f"/{path}")(list_items)
        router.post(f"/{path}", status_code=201)(create_item)
        router.put(f"/{path}/{{entity_id}}")(update_item)
        router.delete(f"/{path}/{{entity_id}}")(delete_item)


_register_entity_routes()


# Verification status transitions (§47: verified / unverified / needs_review)


@router.post("/{path}/{entity_id}/verify")
def verify_entity(path: str, entity_id: str, status_value: str = "verified", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if path not in ENTITIES:
        raise HTTPException(404, "Unknown entity")
    if status_value not in ("verified", "unverified", "needs_review"):
        raise HTTPException(422, "Invalid verification status")
    model = ENTITIES[path][0]
    obj = _get_owned(db, model, entity_id, user)
    if not hasattr(obj, "verification_status"):
        raise HTTPException(422, "Entity does not support verification")
    obj.verification_status = status_value
    db.commit()
    return to_dict(obj)


# ── documents & ingestion (§6) ───────────────────────────────────────────────


@router.get("/documents")
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(CareerDocument)
        .filter(CareerDocument.user_id == user.id, CareerDocument.is_deleted == False)  # noqa: E712
        .order_by(CareerDocument.created_at.desc())
        .all()
    )
    return [to_dict(r, exclude={"extracted_text"}) for r in rows]


@router.post("/documents", status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await validate_upload(file)
    service = IngestionService(db, user)
    doc = service.store_document(file.filename or "upload", data, file.content_type or "", doc_type)
    audit(db, user, "career.documents.upload", "career_document", doc.id, {"filename": doc.filename}, request)
    db.commit()
    return to_dict(doc, exclude={"extracted_text"})


@router.post("/documents/{document_id}/ingest")
def ingest_document(document_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    document = _get_owned(db, CareerDocument, document_id, user)
    service = IngestionService(db, user)
    result = service.ingest_document(document)
    audit(db, user, "career.documents.ingest", "career_document", document.id, result, request)
    return result


@router.post("/ingest-text")
def ingest_text(payload: IngestTextRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Paste free-form career text; it is stored then structured by the agent."""
    service = IngestionService(db, user)
    doc = service.store_document(payload.filename, payload.text.encode("utf-8"), "text/plain", payload.doc_type)
    result = service.ingest_document(doc)
    audit(db, user, "career.ingest_text", "career_document", doc.id, result, request)
    return {"document_id": doc.id, "created": result}


# ── evidence / traceability (§32) ────────────────────────────────────────────


@router.get("/evidence/{entity_type}/{entity_id}")
def get_evidence(entity_type: str, entity_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return evidence_for_entity(db, user.id, entity_type, entity_id)


# ── semantic search (§35) ────────────────────────────────────────────────────


@router.get("/search")
def search_knowledge(q: str, limit: int = 10, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = retrieve_evidence(db, user.id, q, limit=min(limit, 50))
    return [
        {
            "entity_type": i.entity_type,
            "entity_id": i.entity_id,
            "text": i.text,
            "score": round(i.score, 4),
            "verification_status": i.verification_status,
        }
        for i in items
    ]
