"""Career Knowledge Base CRUD + ingestion + search (§47, §52).

Every mutation updates the vector index so semantic retrieval stays fresh.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from ..dates import apply_career_dates
from ..database import get_db
from ..models import (
    Achievement,
    CareerDocument,
    CareerNarrative,
    CareerProfile,
    Certification,
    Education,
    Experience,
    KnowledgeContext,
    Language,
    PendingIngestion,
    ProfessionalKnowledge,
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
    ConfirmPendingIngestionRequest,
    EducationIn,
    ExperienceIn,
    IngestTextRequest,
    KnowledgeContextIn,
    KnowledgeIn,
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
from ..services.knowledge import (
    attach_context,
    knowledge_payload,
    sync_experience_domains,
    upsert_knowledge,
)
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


def _validate_parent_links(db: Session, user: User, data: dict, *, for_achievement: bool = False) -> None:
    """Ensure optional parent FKs point at entities owned by the current user."""
    checks: list[tuple[str, type]] = [("experience_id", Experience)]
    if for_achievement:
        checks.extend([("project_id", Project), ("education_id", Education)])
    for field, model in checks:
        parent_id = data.get(field)
        if not parent_id:
            continue
        parent = db.get(model, parent_id)
        if parent is None or parent.user_id != user.id or getattr(parent, "is_deleted", False):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid {field}")


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
            data = apply_career_dates(payload.model_dump())
            if model is Skill:
                data.setdefault("canonical_name", data.get("name", ""))
            if model is Achievement:
                _validate_parent_links(db, user, data, for_achievement=True)
            elif model is Project:
                _validate_parent_links(db, user, data, for_achievement=False)
            obj = model(user_id=user.id, **data)
            db.add(obj)
            db.flush()
            _record_provenance(db, user, model, vector_type, obj.id, data)
            if vector_type:
                index_entity(db, vector_type, obj.id)
            if model is Experience:
                _sync_experience_knowledge(db, user, obj)
            audit(db, user, f"career.{path}.create", model.__tablename__, obj.id, request=request)
            db.commit()
            return to_dict(obj)

        def update_item(entity_id: str, payload: schema, request: Request, path=path, model=model, vector_type=vector_type, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
            obj = _get_owned(db, model, entity_id, user)
            data = apply_career_dates(payload.model_dump())
            if model is Achievement:
                _validate_parent_links(db, user, data, for_achievement=True)
            elif model is Project:
                _validate_parent_links(db, user, data, for_achievement=False)
            for field, value in data.items():
                setattr(obj, field, value)
            if model is Skill and not obj.canonical_name:
                obj.canonical_name = obj.name
            if vector_type:
                index_entity(db, vector_type, obj.id)
            if model is Experience:
                _sync_experience_knowledge(db, user, obj)
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


def _sync_experience_knowledge(db: Session, user: User, experience: Experience) -> None:
    for domain in experience.domains or []:
        name = str(domain).strip()
        if not name:
            continue
        knowledge = upsert_knowledge(
            db,
            user,
            {
                "name": name,
                "kind": "domain",
                "depth": "applied",
                "how_acquired": f"Used in {experience.job_title} at {experience.organization}",
                "verification_status": experience.verification_status,
                "confidence": experience.confidence,
            },
        )
        attach_context(
            db,
            user,
            knowledge,
            {
                "experience_id": experience.id,
                "acquisition_mode": "acquired_through_role",
                "verification_status": experience.verification_status,
                "confidence": experience.confidence,
            },
        )
    sync_experience_domains(db, experience)


def _validate_knowledge_parents(db: Session, user: User, data: dict) -> None:
    checks = [
        ("experience_id", Experience),
        ("project_id", Project),
        ("achievement_id", Achievement),
        ("education_id", Education),
    ]
    for field, model in checks:
        parent_id = data.get(field)
        if not parent_id:
            continue
        parent = db.get(model, parent_id)
        if parent is None or parent.user_id != user.id or getattr(parent, "is_deleted", False):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Invalid {field}")


# ── professional knowledge ───────────────────────────────────────────────────


@router.get("/knowledge")
def list_knowledge(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(ProfessionalKnowledge)
        .filter(ProfessionalKnowledge.user_id == user.id, ProfessionalKnowledge.is_deleted == False)  # noqa: E712
        .order_by(ProfessionalKnowledge.created_at.desc())
        .all()
    )
    return [knowledge_payload(db, row) for row in rows]


@router.post("/knowledge", status_code=201)
def create_knowledge(
    payload: KnowledgeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    contexts = data.pop("contexts", [])
    row = upsert_knowledge(db, user, data)
    for ctx in contexts:
        _validate_knowledge_parents(db, user, ctx)
        attach_context(db, user, row, ctx)
        if ctx.get("experience_id"):
            experience = db.get(Experience, ctx["experience_id"])
            if experience:
                sync_experience_domains(db, experience)
    index_entity(db, "professional_knowledge", row.id)
    audit(db, user, "career.knowledge.create", "professional_knowledge", row.id, request=request)
    db.commit()
    return knowledge_payload(db, row)


@router.put("/knowledge/{entity_id}")
def update_knowledge(
    entity_id: str,
    payload: KnowledgeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_owned(db, ProfessionalKnowledge, entity_id, user)
    data = payload.model_dump()
    contexts = data.pop("contexts", None)
    for field, value in data.items():
        if field == "canonical_name" and not value:
            continue
        setattr(obj, field, value)
    if not obj.canonical_name:
        obj.canonical_name = obj.name
    if contexts:
        for ctx in contexts:
            _validate_knowledge_parents(db, user, ctx)
            attach_context(db, user, obj, ctx)
            if ctx.get("experience_id"):
                experience = db.get(Experience, ctx["experience_id"])
                if experience:
                    sync_experience_domains(db, experience)
    index_entity(db, "professional_knowledge", obj.id)
    audit(db, user, "career.knowledge.update", "professional_knowledge", obj.id, request=request)
    db.commit()
    return knowledge_payload(db, obj)


@router.delete("/knowledge/{entity_id}")
def delete_knowledge(
    entity_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    obj = _get_owned(db, ProfessionalKnowledge, entity_id, user)
    obj.is_deleted = True
    db.query(KnowledgeContext).filter(
        KnowledgeContext.knowledge_id == obj.id,
        KnowledgeContext.is_deleted == False,  # noqa: E712
    ).update({"is_deleted": True})
    index_entity(db, "professional_knowledge", obj.id)
    audit(db, user, "career.knowledge.delete", "professional_knowledge", obj.id, request=request)
    db.commit()
    return {"deleted": entity_id}


@router.post("/knowledge/{entity_id}/verify")
def verify_knowledge(
    entity_id: str,
    status_value: str = "verified",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if status_value not in ("verified", "unverified", "needs_review"):
        raise HTTPException(422, "Invalid verification status")
    obj = _get_owned(db, ProfessionalKnowledge, entity_id, user)
    obj.verification_status = status_value
    db.commit()
    return knowledge_payload(db, obj)


@router.post("/knowledge/{entity_id}/contexts", status_code=201)
def create_knowledge_context(
    entity_id: str,
    payload: KnowledgeContextIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    knowledge = _get_owned(db, ProfessionalKnowledge, entity_id, user)
    data = payload.model_dump()
    _validate_knowledge_parents(db, user, data)
    ctx = attach_context(db, user, knowledge, data)
    if data.get("experience_id"):
        experience = db.get(Experience, data["experience_id"])
        if experience:
            sync_experience_domains(db, experience)
    index_entity(db, "professional_knowledge", knowledge.id)
    audit(db, user, "career.knowledge_context.create", "knowledge_context", ctx.id, request=request)
    db.commit()
    return knowledge_payload(db, knowledge)


@router.delete("/knowledge-contexts/{entity_id}")
def delete_knowledge_context(
    entity_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ctx = _get_owned(db, KnowledgeContext, entity_id, user)
    ctx.is_deleted = True
    experience_id = ctx.experience_id
    knowledge_id = ctx.knowledge_id
    if experience_id:
        experience = db.get(Experience, experience_id)
        if experience:
            sync_experience_domains(db, experience)
    index_entity(db, "professional_knowledge", knowledge_id)
    audit(db, user, "career.knowledge_context.delete", "knowledge_context", ctx.id, request=request)
    db.commit()
    return {"deleted": entity_id}


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
    return {"document_id": doc.id, **result}


# ── pending ingestion reconciliation (human-in-the-loop) ─────────────────────


def _pending_payload(db: Session, pending: PendingIngestion) -> dict:
    data = to_dict(pending)
    doc = db.get(CareerDocument, pending.document_id) if pending.document_id else None
    data["document"] = (
        {"id": doc.id, "filename": doc.filename, "doc_type": doc.doc_type} if doc else None
    )
    # Enrich proposals with current target snapshots for the review UI
    enriched = []
    for prop in pending.proposals or []:
        item = dict(prop)
        target_id = prop.get("target_id")
        entity_type = prop.get("entity_type")
        if target_id and entity_type:
            model = {"experience": Experience, "project": Project, "achievement": Achievement}.get(entity_type)
            if model:
                target = db.get(model, target_id)
                if target and not getattr(target, "is_deleted", False):
                    if entity_type == "experience":
                        item["target_snapshot"] = {
                            "id": target.id,
                            "label": f"{target.job_title} — {target.organization}",
                            "organization": target.organization,
                            "job_title": target.job_title,
                            "start_date": target.start_date,
                            "end_date": target.end_date,
                            "responsibilities": target.responsibilities or [],
                        }
                    elif entity_type == "project":
                        item["target_snapshot"] = {
                            "id": target.id,
                            "label": target.name,
                            "name": target.name,
                            "description": target.description,
                        }
                    else:
                        item["target_snapshot"] = {
                            "id": target.id,
                            "label": (target.title or target.description or "")[:120],
                            "description": target.description,
                        }
        enriched.append(item)
    data["proposals"] = enriched
    return data


@router.get("/pending-ingestions")
def list_pending_ingestions(
    status_filter: str = "pending",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(PendingIngestion).filter(PendingIngestion.user_id == user.id)
    if status_filter and status_filter != "all":
        q = q.filter(PendingIngestion.status == status_filter)
    rows = q.order_by(PendingIngestion.created_at.desc()).all()
    return [_pending_payload(db, r) for r in rows]


@router.get("/pending-ingestions/{pending_id}")
def get_pending_ingestion(pending_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pending = _get_owned(db, PendingIngestion, pending_id, user)
    return _pending_payload(db, pending)


@router.post("/pending-ingestions/{pending_id}/confirm")
def confirm_pending_ingestion(
    pending_id: str,
    payload: ConfirmPendingIngestionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pending = _get_owned(db, PendingIngestion, pending_id, user)
    if pending.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Pending ingestion is already resolved")
    service = IngestionService(db, user)
    try:
        applied = service.confirm_pending(pending, [d.model_dump() for d in payload.decisions])
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit(db, user, "career.pending_ingestion.confirm", "pending_ingestion", pending.id, applied, request)
    return {"pending_ingestion_id": pending.id, "status": "completed", "applied": applied}


@router.post("/pending-ingestions/{pending_id}/accept-suggested")
def accept_suggested_pending_ingestion(
    pending_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pending = _get_owned(db, PendingIngestion, pending_id, user)
    if pending.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Pending ingestion is already resolved")
    service = IngestionService(db, user)
    try:
        applied = service.accept_suggested(pending)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    audit(db, user, "career.pending_ingestion.accept_suggested", "pending_ingestion", pending.id, applied, request)
    return {"pending_ingestion_id": pending.id, "status": "completed", "applied": applied}


@router.delete("/pending-ingestions/{pending_id}")
def discard_pending_ingestion(
    pending_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pending = _get_owned(db, PendingIngestion, pending_id, user)
    if pending.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Pending ingestion is already resolved")
    service = IngestionService(db, user)
    service.discard_pending(pending)
    audit(db, user, "career.pending_ingestion.discard", "pending_ingestion", pending.id, request=request)
    return {"discarded": pending_id}


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
