"""Document ingestion: text extraction from uploads + career extraction (§6)."""
from __future__ import annotations

import io
import logging
import re
import uuid
import zipfile

from sqlalchemy.orm import Session

from ..agents.base import AgentContext
from ..agents.career_knowledge import (
    CareerKnowledgeAgent,
    CareerNormalizationAgent,
    CareerReconciliationAgent,
)
from ..models import (
    Achievement,
    CareerDocument,
    CareerEvidence,
    CareerProfile,
    Certification,
    Education,
    Experience,
    Language,
    PendingIngestion,
    ProfessionalKnowledge,
    Project,
    Skill,
    User,
)
from ..retrieval.pipeline import index_entity
from .knowledge import (
    attach_context,
    knowledge_items_from_extraction,
    sync_experience_domains,
    upsert_knowledge,
)
from .storage import get_object_store

logger = logging.getLogger(__name__)


def extract_text(filename: str, data: bytes) -> str:
    """Best-effort text extraction. PDFs prefer pypdf for Unicode; DOCX
    reads word/document.xml from the zip container."""
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
    """Extract PDF text with pypdf (Unicode-aware), falling back to streams."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        parts = [(page.extract_text() or "") for page in reader.pages]
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception as exc:
        logger.warning("pypdf text extraction failed: %s", exc)
    return _extract_pdf_text_legacy(data)


def _extract_pdf_text_legacy(data: bytes) -> str:
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


def _uniq_extend(existing: list | None, new_items: list | None) -> list:
    """Append unique string items while preserving order."""
    out = list(existing or [])
    seen = {str(x).strip().lower() for x in out if str(x).strip()}
    for item in new_items or []:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


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
        """Run extraction, auto-apply simple entities, queue reconcilable ones for review."""
        ctx = ctx or AgentContext(db=self.db, user_id=self.user.id)
        if not document.extracted_text:
            document.ingested = True
            self.db.flush()
            return {
                "pending_ingestion_id": None,
                "auto_applied": {"experiences": 0, "skills": 0},
                "proposals_count": 0,
                "note": "No extractable text",
            }

        result = CareerKnowledgeAgent().run(
            ctx, document_text=document.extracted_text, document_name=document.filename
        )
        auto_applied = {
            "experiences": 0,
            "skills": 0,
            "achievements": 0,
            "projects": 0,
            "education": 0,
            "certifications": 0,
            "languages": 0,
            "professional_knowledge": 0,
        }

        # Skills / education / certs / languages are still applied immediately
        # (skills already dedupe via normalization). Experiences, projects and
        # achievements go through human-in-the-loop reconciliation.
        if result.skills:
            skill_items = [s.model_dump() for s in result.skills]
            normalized = CareerNormalizationAgent().run(ctx, items=skill_items)
            by_key = {}
            for entry in normalized.get("canonical", []):
                for alias in [entry["canonical_name"], *entry.get("aliases", [])]:
                    by_key[alias.lower()] = entry
            for raw in result.skills:
                entry = by_key.get(raw.name.lower())
                canonical = entry["canonical_name"] if entry else raw.name
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
                    existing.synonyms = sorted(
                        set(existing.synonyms or []) | {raw.name} | set(aliases) - {canonical}
                    )
                    existing.evidence_count = (existing.evidence_count or 0) + 1
                    skill_row = existing
                else:
                    skill_row = Skill(
                        user_id=self.user.id,
                        name=raw.name,
                        canonical_name=canonical,
                        category=(
                            entry.get("category", raw.category)
                            if entry
                            else raw.category or "technical"
                        ),
                        synonyms=aliases,
                        evidence_count=1,
                        verification_status="needs_review",
                        confidence=0.7,
                    )
                    self.db.add(skill_row)
                    self.db.flush()
                auto_applied["skills"] += 1
                self._provenance(skill_row.id, "skill", raw.name, document, "Skills")
                index_entity(self.db, "skill", skill_row.id)

        knowledge_items = knowledge_items_from_extraction(result)
        pending_knowledge: list[dict] = []
        for item in knowledge_items:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            row = upsert_knowledge(self.db, self.user, item, document=document)
            auto_applied["professional_knowledge"] += 1
            pending_knowledge.append(
                {
                    "knowledge_id": row.id,
                    "organization_hint": item.get("organization_hint") or "",
                    "job_title_hint": item.get("job_title_hint") or "",
                    "acquisition_mode": item.get("acquisition_mode") or "acquired_through_role",
                    "how_acquired": item.get("how_acquired") or "",
                    "how_applied": item.get("how_applied") or "",
                    "confidence": item.get("confidence") or 0.6,
                }
            )

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
            auto_applied["education"] += 1

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
            auto_applied["certifications"] += 1

        for lang in result.languages:
            self.db.add(
                Language(
                    user_id=self.user.id,
                    language=lang.language,
                    proficiency=lang.proficiency,
                )
            )
            auto_applied["languages"] += 1

        profile_applied = self._apply_extracted_profile(result)

        extracted_items = self._build_extracted_items(result)
        proposals: list[dict] = []
        pending_id = None

        if extracted_items:
            existing_items = self._existing_reconcilable_items()
            recon = CareerReconciliationAgent().run(
                ctx, extracted_items=extracted_items, existing_items=existing_items
            )
            by_id = {e["id"]: e for e in existing_items}
            for prop in recon.proposals:
                data = prop.model_dump()
                if not data.get("proposal_id"):
                    data["proposal_id"] = str(uuid.uuid4())
                # Validate merge targets belong to the user KB
                if data.get("action") == "merge" and data.get("target_id"):
                    target = by_id.get(data["target_id"])
                    if not target or target.get("entity_type") != data.get("entity_type"):
                        data["action"] = "create"
                        data["target_id"] = None
                        data["target_label"] = ""
                        data["reasoning"] = (
                            (data.get("reasoning") or "")
                            + " (invalid target discarded; defaulted to create)"
                        ).strip()
                    elif not data.get("target_label"):
                        data["target_label"] = target.get("label", "")
                else:
                    data["action"] = data.get("action") or "create"
                    if data["action"] != "merge":
                        data["target_id"] = None
                # Ensure payload is present
                if not data.get("payload"):
                    data["payload"] = {}
                proposals.append(data)

            pending = PendingIngestion(
                user_id=self.user.id,
                document_id=document.id,
                status="pending",
                proposals=proposals,
                auto_applied={**auto_applied, "knowledge_links": pending_knowledge},
                summary=result.summary or f"Extracted from {document.filename}",
            )
            self.db.add(pending)
            self.db.flush()
            pending_id = pending.id
        else:
            self._link_knowledge_items(pending_knowledge, document)

        document.ingested = True
        self.db.commit()
        return {
            "pending_ingestion_id": pending_id,
            "auto_applied": {k: v for k, v in auto_applied.items() if k != "knowledge_links"},
            "proposals_count": len(proposals),
            "profile": profile_applied,
            # Backward-compatible alias used by older clients/tests
            "created": auto_applied if not pending_id else {
                **{k: v for k, v in auto_applied.items() if k != "knowledge_links"},
                "pending_review": len(proposals),
            },
        }

    def _apply_extracted_profile(self, result) -> dict:
        """Fill empty CareerProfile fields from extraction; never overwrite user values."""
        extracted = getattr(result, "profile", None)
        payload = {
            "full_name": (getattr(extracted, "full_name", None) or "").strip(),
            "headline": (getattr(extracted, "headline", None) or "").strip(),
            "summary": (getattr(extracted, "summary", None) or getattr(result, "summary", "") or "").strip(),
            "email": (getattr(extracted, "email", None) or "").strip(),
            "phone": (getattr(extracted, "phone", None) or "").strip(),
            "location": (getattr(extracted, "location", None) or "").strip(),
            "linkedin": (getattr(extracted, "linkedin", None) or "").strip(),
        }
        if not any(payload.values()):
            return {}

        profile = (
            self.db.query(CareerProfile)
            .filter(CareerProfile.user_id == self.user.id)
            .first()
        )
        if profile is None:
            profile = CareerProfile(user_id=self.user.id)
            self.db.add(profile)
            self.db.flush()

        applied: dict[str, str] = {}
        for field in ("full_name", "headline", "summary", "email", "phone", "location"):
            incoming = payload[field]
            if incoming and not (getattr(profile, field) or "").strip():
                setattr(profile, field, incoming)
                applied[field] = incoming
        if payload["linkedin"]:
            links = dict(profile.links or {})
            if not (links.get("linkedin") or "").strip():
                links["linkedin"] = payload["linkedin"]
                profile.links = links
                applied["linkedin"] = payload["linkedin"]
        return applied

    def accept_suggested(self, pending: PendingIngestion) -> dict:
        """Confirm every proposal using the agent's suggested action."""
        decisions = []
        for prop in pending.proposals or []:
            action = prop.get("action") or "create"
            decisions.append({
                "proposal_id": prop.get("proposal_id"),
                "action": action,
                "target_id": prop.get("target_id") if action == "merge" else None,
            })
        return self.confirm_pending(pending, decisions)

    def confirm_pending(self, pending: PendingIngestion, decisions: list[dict]) -> dict:
        """Apply user-confirmed merge/create decisions and mark pending completed."""
        if pending.status != "pending":
            raise ValueError("Pending ingestion is not awaiting confirmation")

        document = None
        if pending.document_id:
            document = self.db.get(CareerDocument, pending.document_id)

        proposals_by_id = {p["proposal_id"]: p for p in (pending.proposals or []) if p.get("proposal_id")}
        applied = {"experiences": 0, "achievements": 0, "projects": 0, "merged": 0, "created": 0}

        for decision in decisions:
            proposal_id = decision.get("proposal_id")
            proposal = proposals_by_id.get(proposal_id)
            if not proposal:
                continue
            action = decision.get("action") or proposal.get("action") or "create"
            target_id = decision.get("target_id") if action == "merge" else None
            if action == "merge" and not target_id:
                target_id = proposal.get("target_id")
            entity_type = proposal.get("entity_type", "experience")
            payload = proposal.get("payload") or {}

            if entity_type == "experience":
                if action == "merge" and target_id:
                    row = self._get_owned(Experience, target_id)
                    if row is None:
                        action = "create"
                    else:
                        self._merge_experience(row, payload, document)
                        applied["experiences"] += 1
                        applied["merged"] += 1
                        continue
                self._create_experience(payload, document)
                applied["experiences"] += 1
                applied["created"] += 1

            elif entity_type == "project":
                if action == "merge" and target_id:
                    row = self._get_owned(Project, target_id)
                    if row is None:
                        action = "create"
                    else:
                        self._merge_project(row, payload)
                        applied["projects"] += 1
                        applied["merged"] += 1
                        continue
                self._create_project(payload, document)
                applied["projects"] += 1
                applied["created"] += 1

            elif entity_type == "achievement":
                if action == "merge" and target_id:
                    row = self._get_owned(Achievement, target_id)
                    if row is None:
                        action = "create"
                    else:
                        self._merge_achievement(row, payload, document)
                        applied["achievements"] += 1
                        applied["merged"] += 1
                        continue
                self._create_achievement(payload, document)
                applied["achievements"] += 1
                applied["created"] += 1

        self._link_knowledge_items(
            (pending.auto_applied or {}).get("knowledge_links") or [],
            document,
        )
        pending.status = "completed"
        self.db.commit()
        return applied

    def discard_pending(self, pending: PendingIngestion) -> None:
        pending.status = "discarded"
        self.db.commit()

    # ── reconciliation helpers ───────────────────────────────────────────────

    def _build_extracted_items(self, result) -> list[dict]:
        items: list[dict] = []
        for exp in result.experiences:
            payload = exp.model_dump()
            items.append({"entity_type": "experience", "payload": payload})
            # Nested projects as separate reconcilable entities
            for proj_text in exp.projects or []:
                if not str(proj_text).strip():
                    continue
                items.append(
                    {
                        "entity_type": "project",
                        "payload": {
                            "name": str(proj_text).strip()[:500],
                            "description": str(proj_text).strip(),
                            "role": exp.job_title or "",
                            "technologies": list(exp.technologies or []),
                            "outcomes": [],
                            "organization_hint": exp.organization,
                            "job_title_hint": exp.job_title,
                        },
                    }
                )
        for ach in result.achievements or []:
            text = str(ach).strip()
            if not text:
                continue
            items.append(
                {
                    "entity_type": "achievement",
                    "payload": {
                        "description": text,
                        "quantified_result": text if re.search(r"\d", text) else "",
                        "title": "",
                    },
                }
            )
        return items

    def _existing_reconcilable_items(self) -> list[dict]:
        items: list[dict] = []
        for exp in (
            self.db.query(Experience)
            .filter(Experience.user_id == self.user.id, Experience.is_deleted == False)  # noqa: E712
            .all()
        ):
            items.append(
                {
                    "id": exp.id,
                    "entity_type": "experience",
                    "label": f"{exp.job_title} at {exp.organization}".strip(" at"),
                    "organization": exp.organization,
                    "job_title": exp.job_title,
                    "start_date": exp.start_date or "",
                    "end_date": exp.end_date or "",
                }
            )
        for proj in (
            self.db.query(Project)
            .filter(Project.user_id == self.user.id, Project.is_deleted == False)  # noqa: E712
            .all()
        ):
            items.append(
                {
                    "id": proj.id,
                    "entity_type": "project",
                    "label": proj.name,
                    "name": proj.name,
                    "description": (proj.description or "")[:300],
                }
            )
        for ach in (
            self.db.query(Achievement)
            .filter(Achievement.user_id == self.user.id, Achievement.is_deleted == False)  # noqa: E712
            .all()
        ):
            items.append(
                {
                    "id": ach.id,
                    "entity_type": "achievement",
                    "label": (ach.title or ach.description or "")[:120],
                    "description": ach.description or "",
                    "name": ach.title or "",
                }
            )
        return items

    def _get_owned(self, model, entity_id: str):
        obj = self.db.get(model, entity_id)
        if obj is None or obj.user_id != self.user.id or getattr(obj, "is_deleted", False):
            return None
        return obj

    def _create_experience(self, payload: dict, document: CareerDocument | None) -> Experience:
        row = Experience(
            user_id=self.user.id,
            organization=payload.get("organization") or "",
            job_title=payload.get("job_title") or "",
            start_date=payload.get("start_date") or None,
            end_date=payload.get("end_date") or None,
            employment_type=payload.get("employment_type") or "",
            location=payload.get("location") or "",
            description=payload.get("description") or "",
            responsibilities=list(payload.get("responsibilities") or []),
            technologies=list(payload.get("technologies") or []),
            domains=list(payload.get("domains") or []),
            leadership=list(payload.get("leadership") or []),
            stakeholders=list(payload.get("stakeholders") or []),
            source_document_id=document.id if document else None,
            verification_status="needs_review",
            confidence=float(payload.get("confidence") or 0.5),
        )
        self.db.add(row)
        self.db.flush()
        self._provenance(
            row.id,
            "experience",
            f"{row.job_title} at {row.organization}",
            document,
            row.organization or "Experience",
        )
        for achievement_text in payload.get("achievements") or []:
            self._create_achievement(
                {
                    "description": achievement_text,
                    "quantified_result": achievement_text if re.search(r"\d", str(achievement_text)) else "",
                    "experience_id": row.id,
                    "confidence": payload.get("confidence", 0.5),
                },
                document,
            )
        index_entity(self.db, "experience", row.id)
        self._attach_experience_knowledge(row, payload, document)
        return row

    def _merge_experience(self, row: Experience, payload: dict, document: CareerDocument | None) -> None:
        # Fill blank scalar fields; never overwrite user-verified content blindly
        for field in ("employment_type", "location", "description"):
            incoming = (payload.get(field) or "").strip()
            if incoming and not (getattr(row, field) or "").strip():
                setattr(row, field, incoming)
        if not row.start_date and payload.get("start_date"):
            row.start_date = payload.get("start_date") or None
        if not row.end_date and payload.get("end_date"):
            row.end_date = payload.get("end_date") or None

        row.responsibilities = _uniq_extend(row.responsibilities, payload.get("responsibilities"))
        row.technologies = _uniq_extend(row.technologies, payload.get("technologies"))
        row.domains = _uniq_extend(row.domains, payload.get("domains"))
        row.leadership = _uniq_extend(row.leadership, payload.get("leadership"))
        row.stakeholders = _uniq_extend(row.stakeholders, payload.get("stakeholders"))
        row.verification_status = "needs_review"
        if document and not row.source_document_id:
            row.source_document_id = document.id

        existing_ach_texts = {
            (a.description or "").strip().lower()
            for a in self.db.query(Achievement)
            .filter(
                Achievement.experience_id == row.id,
                Achievement.user_id == self.user.id,
                Achievement.is_deleted == False,  # noqa: E712
            )
            .all()
        }
        for achievement_text in payload.get("achievements") or []:
            text = str(achievement_text).strip()
            if not text or text.lower() in existing_ach_texts:
                continue
            self._create_achievement(
                {
                    "description": text,
                    "quantified_result": text if re.search(r"\d", text) else "",
                    "experience_id": row.id,
                    "confidence": payload.get("confidence", 0.5),
                },
                document,
            )
            existing_ach_texts.add(text.lower())

        self._provenance(
            row.id,
            "experience",
            f"Additional details for {row.job_title} at {row.organization}",
            document,
            row.organization or "Experience",
        )
        self.db.flush()
        index_entity(self.db, "experience", row.id)
        self._attach_experience_knowledge(row, payload, document)

    def _attach_experience_knowledge(
        self, experience: Experience, payload: dict, document: CareerDocument | None
    ) -> None:
        items = list(payload.get("professional_knowledge") or [])
        for domain in payload.get("domains") or []:
            name = str(domain).strip()
            if name:
                items.append(
                    {
                        "name": name,
                        "kind": "domain",
                        "depth": "applied",
                        "how_acquired": f"Used in {experience.job_title} at {experience.organization}",
                        "confidence": payload.get("confidence") or 0.6,
                    }
                )
        for item in items:
            data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            name = (data.get("name") or "").strip()
            if not name:
                continue
            knowledge = upsert_knowledge(self.db, self.user, data, document=document)
            attach_context(
                self.db,
                self.user,
                knowledge,
                {
                    "experience_id": experience.id,
                    "acquisition_mode": data.get("acquisition_mode") or "acquired_through_role",
                    "how_acquired": data.get("how_acquired") or "",
                    "how_applied": data.get("how_applied") or "",
                    "confidence": data.get("confidence") or 0.6,
                },
                document=document,
            )
        sync_experience_domains(self.db, experience)

    def _link_knowledge_items(self, links: list[dict], document: CareerDocument | None) -> None:
        for link in links or []:
            knowledge = self.db.get(ProfessionalKnowledge, link.get("knowledge_id"))
            if knowledge is None or knowledge.user_id != self.user.id or knowledge.is_deleted:
                continue
            experience_id = self._resolve_experience_id(link)
            if not experience_id:
                continue
            attach_context(self.db, self.user, knowledge, {**link, "experience_id": experience_id}, document=document)
            experience = self.db.get(Experience, experience_id)
            if experience:
                sync_experience_domains(self.db, experience)

    def _resolve_experience_id(self, payload: dict) -> str | None:
        """Use explicit experience_id, else match organization/job_title hints."""
        explicit = payload.get("experience_id")
        if explicit and self._get_owned(Experience, explicit):
            return explicit
        org = (payload.get("organization_hint") or "").strip().lower()
        title = (payload.get("job_title_hint") or "").strip().lower()
        if not org and not title:
            return None
        for exp in (
            self.db.query(Experience)
            .filter(Experience.user_id == self.user.id, Experience.is_deleted == False)  # noqa: E712
            .all()
        ):
            org_ok = not org or (exp.organization or "").strip().lower() == org
            title_ok = not title or (exp.job_title or "").strip().lower() == title
            if org_ok and title_ok:
                return exp.id
        return None

    def _create_project(self, payload: dict, document: CareerDocument | None) -> Project:
        row = Project(
            user_id=self.user.id,
            experience_id=self._resolve_experience_id(payload),
            name=payload.get("name") or "Untitled project",
            description=payload.get("description") or "",
            role=payload.get("role") or "",
            technologies=list(payload.get("technologies") or []),
            outcomes=list(payload.get("outcomes") or []),
            urls=list(payload.get("urls") or []),
            verification_status="needs_review",
            confidence=float(payload.get("confidence") or 0.5),
        )
        self.db.add(row)
        self.db.flush()
        self._provenance(row.id, "project", row.name, document, "Projects")
        index_entity(self.db, "project", row.id)
        return row

    def _merge_project(self, row: Project, payload: dict) -> None:
        if payload.get("description") and payload["description"] not in (row.description or ""):
            if row.description:
                row.description = f"{row.description.rstrip()}\n\n{payload['description']}".strip()
            else:
                row.description = payload["description"]
        if payload.get("role") and not row.role:
            row.role = payload["role"]
        if not row.experience_id:
            resolved = self._resolve_experience_id(payload)
            if resolved:
                row.experience_id = resolved
        row.technologies = _uniq_extend(row.technologies, payload.get("technologies"))
        row.outcomes = _uniq_extend(row.outcomes, payload.get("outcomes"))
        row.urls = _uniq_extend(row.urls, payload.get("urls"))
        row.verification_status = "needs_review"
        self.db.flush()
        index_entity(self.db, "project", row.id)

    def _create_achievement(self, payload: dict, document: CareerDocument | None) -> Achievement:
        description = payload.get("description") or ""
        experience_id = payload.get("experience_id") or self._resolve_experience_id(payload)
        project_id = payload.get("project_id")
        if project_id and not self._get_owned(Project, project_id):
            project_id = None
        education_id = payload.get("education_id")
        if education_id and not self._get_owned(Education, education_id):
            education_id = None
        ach = Achievement(
            user_id=self.user.id,
            experience_id=experience_id if experience_id and self._get_owned(Experience, experience_id) else None,
            project_id=project_id,
            education_id=education_id,
            title=payload.get("title") or "",
            description=description,
            quantified_result=payload.get("quantified_result")
            or (description if re.search(r"\d", description) else ""),
            skills=list(payload.get("skills") or []),
            source_document_id=document.id if document else None,
            verification_status="needs_review",
            confidence=float(payload.get("confidence") or 0.5),
        )
        self.db.add(ach)
        self.db.flush()
        self._provenance(ach.id, "achievement", description, document, "Achievements")
        index_entity(self.db, "achievement", ach.id)
        return ach

    def _merge_achievement(
        self, row: Achievement, payload: dict, document: CareerDocument | None
    ) -> None:
        incoming = (payload.get("description") or "").strip()
        if incoming and incoming.lower() not in (row.description or "").lower():
            row.description = f"{(row.description or '').rstrip()}\n\n{incoming}".strip()
        qr = (payload.get("quantified_result") or "").strip()
        if qr and not row.quantified_result:
            row.quantified_result = qr
        if not row.experience_id:
            resolved = self._resolve_experience_id(payload)
            if resolved:
                row.experience_id = resolved
        if not row.project_id and payload.get("project_id") and self._get_owned(Project, payload["project_id"]):
            row.project_id = payload["project_id"]
        if not row.education_id and payload.get("education_id") and self._get_owned(Education, payload["education_id"]):
            row.education_id = payload["education_id"]
        row.skills = _uniq_extend(row.skills, payload.get("skills"))
        row.verification_status = "needs_review"
        if document and not row.source_document_id:
            row.source_document_id = document.id
        self._provenance(row.id, "achievement", incoming or row.description, document, "Achievements")
        self.db.flush()
        index_entity(self.db, "achievement", row.id)

    def _provenance(
        self,
        entity_id: str,
        entity_type: str,
        claim: str,
        document: CareerDocument | None,
        section: str,
    ) -> None:
        self.db.add(
            CareerEvidence(
                user_id=self.user.id,
                entity_type=entity_type,
                entity_id=entity_id,
                claim=claim,
                source_document_id=document.id if document else None,
                source_section=section,
                original_text=claim,
                verification_status="needs_review",
                confidence=0.7,
            )
        )
        self.db.flush()
