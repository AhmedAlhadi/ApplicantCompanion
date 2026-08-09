"""Document ingestion: text extraction from uploads + career extraction (§6)."""
from __future__ import annotations

import io
import logging
import re
import zipfile

from sqlalchemy.orm import Session

from ..agents.base import AgentContext
from ..agents.career_knowledge import CareerKnowledgeAgent, CareerNormalizationAgent
from ..models import (
    Achievement,
    CareerDocument,
    CareerEvidence,
    Certification,
    Education,
    Experience,
    Language,
    Skill,
    User,
)
from ..retrieval.pipeline import index_entity
from .storage import get_object_store

logger = logging.getLogger(__name__)


def extract_text(filename: str, data: bytes) -> str:
    """Best-effort text extraction. PDFs use a minimal built-in extractor;
    DOCX reads word/document.xml from the zip container."""
    lower = filename.lower()
    if lower.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="replace")
    if lower.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            xml = re.sub(r"<[^>]+>", "", xml)
            return re.sub(r"\n{3,}", "\n\n", xml).strip()
        except (zipfile.BadZipFile, KeyError):
            return ""
    if lower.endswith(".pdf"):
        return _extract_pdf_text(data)
    return ""


def _extract_pdf_text(data: bytes) -> str:
    """Minimal PDF text extraction: pull strings from content streams.

    Handles the common single-byte-encoded case well enough for ingestion;
    complex PDFs should be pasted as text instead.
    """
    text_parts: list[str] = []
    try:
        raw = data
        streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL)
        for stream in streams:
            try:
                import zlib

                decoded = zlib.decompress(stream)
            except Exception:
                decoded = stream
            for match in re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj", decoded):
                text_parts.append(_unescape_pdf(match))
            for arr in re.findall(rb"\[((?:[^\[\]\\]|\\.)*)\]\s*TJ", decoded):
                pieces = re.findall(rb"\(((?:[^()\\]|\\.)*)\)", arr)
                text_parts.append("".join(_unescape_pdf(p) for p in pieces))
    except Exception as exc:  # never let a malformed PDF crash ingestion
        logger.warning("PDF text extraction partial failure: %s", exc)
    return "\n".join(t for t in text_parts if t.strip())


def _unescape_pdf(raw: bytes) -> str:
    out = raw.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
    return out.decode("latin-1", errors="replace")


class IngestionService:
    """Turns raw user documents into structured, provenance-tracked knowledge."""

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    def store_document(self, filename: str, data: bytes, content_type: str, doc_type: str) -> CareerDocument:
        store = get_object_store()
        doc = CareerDocument(
            user_id=self.user.id,
            filename=filename,
            content_type=content_type,
            doc_type=doc_type,
            size_bytes=len(data),
        )
        self.db.add(doc)
        self.db.flush()
        object_key = f"{self.user.id}/{doc.id}/{filename}"
        store.put(object_key, data, content_type)
        doc.object_key = object_key
        doc.extracted_text = extract_text(filename, data)
        self.db.flush()
        return doc

    def ingest_document(self, document: CareerDocument, ctx: AgentContext | None = None) -> dict:
        """Run the Career Knowledge Agent over a stored document (§6)."""
        ctx = ctx or AgentContext(db=self.db, user_id=self.user.id)
        if not document.extracted_text:
            document.ingested = True
            self.db.flush()
            return {"experiences": 0, "skills": 0, "note": "No extractable text"}

        result = CareerKnowledgeAgent().run(
            ctx, document_text=document.extracted_text, document_name=document.filename
        )
        created = {"experiences": 0, "skills": 0, "achievements": 0, "education": 0, "certifications": 0, "languages": 0}

        for exp in result.experiences:
            row = Experience(
                user_id=self.user.id,
                organization=exp.organization,
                job_title=exp.job_title,
                start_date=exp.start_date or None,
                end_date=exp.end_date or None,
                employment_type=exp.employment_type,
                location=exp.location,
                responsibilities=exp.responsibilities,
                technologies=exp.technologies,
                domains=exp.domains,
                leadership=exp.leadership,
                stakeholders=exp.stakeholders,
                source_document_id=document.id,
                verification_status="needs_review",
                confidence=exp.confidence,
            )
            self.db.add(row)
            self.db.flush()
            created["experiences"] += 1
            for achievement_text in exp.achievements:
                ach = Achievement(
                    user_id=self.user.id,
                    experience_id=row.id,
                    description=achievement_text,
                    quantified_result=achievement_text if re.search(r"\d", achievement_text) else "",
                    source_document_id=document.id,
                    verification_status="needs_review",
                    confidence=exp.confidence,
                )
                self.db.add(ach)
                self.db.flush()
                created["achievements"] += 1
                self._provenance(ach.id, "achievement", achievement_text, document, exp.organization)
                index_entity(self.db, "achievement", ach.id)
            self._provenance(row.id, "experience", f"{exp.job_title} at {exp.organization}", document, exp.organization)
            index_entity(self.db, "experience", row.id)

        # skills via normalization agent (§7)
        if result.skills:
            normalized = CareerNormalizationAgent().run(ctx, items=result.skills)
            by_key = {}
            for entry in normalized.get("canonical", []):
                for alias in [entry["canonical_name"], *entry.get("aliases", [])]:
                    by_key[alias.lower()] = entry
            for raw in result.skills:
                entry = by_key.get(raw.get("name", "").lower())
                canonical = entry["canonical_name"] if entry else raw.get("name", "")
                aliases = entry.get("aliases", []) if entry else []
                existing = (
                    self.db.query(Skill)
                    .filter(
                        Skill.user_id == self.user.id,
                        Skill.canonical_name == canonical,
                        Skill.is_deleted == False,  # noqa: E712
                    )
                    .first()
                )
                if existing:
                    existing.synonyms = sorted(set(existing.synonyms or []) | {raw.get("name", "")} | set(aliases) - {canonical})
                    existing.evidence_count = (existing.evidence_count or 0) + 1
                    skill_row = existing
                else:
                    skill_row = Skill(
                        user_id=self.user.id,
                        name=raw.get("name", ""),
                        canonical_name=canonical,
                        category=entry.get("category", raw.get("category", "technical")) if entry else raw.get("category", "technical"),
                        synonyms=aliases,
                        evidence_count=1,
                        verification_status="needs_review",
                        confidence=0.7,
                    )
                    self.db.add(skill_row)
                    self.db.flush()
                created["skills"] += 1
                self._provenance(skill_row.id, "skill", raw.get("name", ""), document, "Skills")
                index_entity(self.db, "skill", skill_row.id)

        for edu in result.education:
            self.db.add(
                Education(
                    user_id=self.user.id,
                    institution=edu.institution,
                    degree=edu.degree,
                    field_of_study=edu.field_of_study,
                    start_date=edu.start_date or None,
                    end_date=edu.end_date or None,
                    verification_status="needs_review",
                )
            )
            created["education"] += 1

        for cert in result.certifications:
            self.db.add(
                Certification(
                    user_id=self.user.id,
                    name=cert.name,
                    issuer=cert.issuer,
                    issue_date=cert.issue_date or None,
                    verification_status="needs_review",
                )
            )
            created["certifications"] += 1

        for lang in result.languages:
            self.db.add(
                Language(
                    user_id=self.user.id,
                    language=lang.get("language", ""),
                    proficiency=lang.get("proficiency", ""),
                )
            )
            created["languages"] += 1

        document.ingested = True
        self.db.commit()
        return created

    def _provenance(self, entity_id: str, entity_type: str, claim: str, document: CareerDocument, section: str) -> None:
        self.db.add(
            CareerEvidence(
                user_id=self.user.id,
                entity_type=entity_type,
                entity_id=entity_id,
                claim=claim,
                source_document_id=document.id,
                source_section=section,
                original_text=claim,
                verification_status="needs_review",
                confidence=0.7,
            )
        )
        self.db.flush()
