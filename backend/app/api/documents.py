"""Document endpoints: view, edit, versions, section regeneration, export (§30-32, §50)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..agents.base import AgentContext
from ..database import get_db
from ..export.exporters import export_document
from ..models import (
    Application,
    CareerProfile,
    CoverLetter,
    CV,
    DocumentVersion,
    Job,
    Template,
    User,
)
from ..schemas.api import DocumentUpdateRequest, RegenerateSectionRequest
from ..security.auth import audit, get_current_user
from ..evidence_citations import cited_ids_from_content
from ..services.documents import DocumentService
from ..services.serializers import evidence_for_entity, to_dict

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _service(db: Session, user: User) -> DocumentService:
    return DocumentService(db, user)


def _resolve(db: Session, user: User, document_id: str):
    """A document id may be a CV or a cover letter."""
    svc = _service(db, user)
    for doc_type in ("cv", "cover_letter"):
        doc, current = svc.get_document(doc_type, document_id)
        if doc is not None:
            return svc, doc_type, doc, current
    raise HTTPException(404, "Document not found")


def _document_payload(db: Session, svc: DocumentService, doc_type: str, doc, current) -> dict:
    data = to_dict(doc)
    data["document_type"] = doc_type
    data["current_version"] = to_dict(current) if current else None
    data["versions"] = [
        {"version_number": v.version_number, "created_at": v.created_at.isoformat(),
         "user_edited": v.user_edited, "is_current": v.is_current, "model": v.model}
        for v in svc.list_versions(doc_type, doc.id)
    ]
    app = db.get(Application, doc.application_id)
    if app:
        job = db.get(Job, app.job_id)
        data["job"] = {"id": job.id, "organization_name": job.organization_name,
                       "position_title": job.position_title} if job else None
        data["application_id"] = app.id
    return data


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc, doc_type, doc, current = _resolve(db, user, document_id)
    return _document_payload(db, svc, doc_type, doc, current)


@router.put("/{document_id}")
def update_document(document_id: str, payload: DocumentUpdateRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc = _service(db, user)
    _, doc_type, doc, _ = _resolve(db, user, document_id)
    version = svc.save_user_edit(doc_type, doc.id, payload.content, payload.template_key)
    audit(db, user, "documents.edit", doc_type, doc.id, {"version": version.version_number}, request)
    db.commit()
    return to_dict(version)


@router.post("/{document_id}/regenerate-section")
def regenerate_section(document_id: str, payload: RegenerateSectionRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc = _service(db, user)
    _, doc_type, doc, _ = _resolve(db, user, document_id)
    ctx = AgentContext(db=db, user_id=user.id, application_id=doc.application_id)
    version = svc.regenerate_section(doc_type, doc.id, payload.section, db.get(Application, doc.application_id), ctx)
    audit(db, user, "documents.regenerate_section", doc_type, doc.id, {"section": payload.section}, request)
    db.commit()
    return to_dict(version)


@router.post("/{document_id}/restore/{version_number}")
def restore_version(document_id: str, version_number: int, request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    svc = _service(db, user)
    _, doc_type, doc, _ = _resolve(db, user, document_id)
    version = svc.restore_version(doc_type, doc.id, version_number)
    audit(db, user, "documents.restore", doc_type, doc.id, {"restored": version_number}, request)
    db.commit()
    return to_dict(version)


@router.get("/{document_id}/evidence")
def document_evidence(document_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Traceability (§32): for each bullet with evidence ids, the provenance panel data."""
    svc = _service(db, user)
    _, doc_type, doc, current = _resolve(db, user, document_id)
    if current is None:
        raise HTTPException(404, "No version generated yet")
    content = current.content
    cited = cited_ids_from_content(content, doc_type)
    entity_type_map = {"cv": "experience", "cover_letter": "experience"}
    panels = []
    seen = set()
    for eid in cited:
        if not eid or eid in seen:
            continue
        seen.add(eid)
        for etype in ("experience", "achievement", "skill", "project", "education", "certification"):
            rows = evidence_for_entity(db, user.id, etype, eid)
            if rows:
                panels.append({"entity_type": etype, "entity_id": eid, "evidence": rows})
                break
        else:
            panels.append({"entity_type": entity_type_map[doc_type], "entity_id": eid, "evidence": []})
    return {"document_id": document_id, "traceability": panels}


@router.post("/{document_id}/export")
def export(
    document_id: str,
    request: Request,
    fmt: str = Query("pdf", pattern="^(pdf|docx)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = _service(db, user)
    _, doc_type, doc, current = _resolve(db, user, document_id)
    if current is None:
        raise HTTPException(404, "No version generated yet")
    profile = db.query(CareerProfile).filter(CareerProfile.user_id == user.id).first()
    template = db.query(Template).filter(
        Template.key == doc.template_key, Template.document_type == doc_type
    ).first()
    from ..prompts.language import content_language_for_user

    config = template.config if template else {}
    data, media_type = export_document(
        fmt,
        doc_type,
        current.content,
        to_dict(profile) if profile else {},
        config,
        content_language=content_language_for_user(db, user.id),
    )
    audit(db, user, "documents.export", doc_type, doc.id, {"format": fmt}, request)
    db.commit()
    import re as _re
    import unicodedata as _ud

    safe_title = _ud.normalize("NFKD", doc.title or doc_type).encode("ascii", "ignore").decode()
    safe_title = _re.sub(r"[^A-Za-z0-9_.-]+", "_", safe_title).strip("_") or doc_type
    filename = f"{safe_title}-v{current.version_number}.{fmt}"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
