"""Document generation, validation (§41), versioning (§29-31) and ATS (§25)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..agents.base import AgentContext, AgentError
from ..agents.matching import ATSAnalysisAgent, CoverLetterAgent, CVAgent
from ..models import (
    Application,
    ApplicationStrategy,
    CareerProfile,
    CoverLetter,
    CV,
    DocumentVersion,
    HiringContext,
    Job,
    JobRequirement,
    OrganizationResearch,
    Person,
    RequirementMatch,
    User,
)
from ..schemas.agents import GeneratedCoverLetter, GeneratedCV, ValidationReport
from ..templates.renderer import render_text
from .document_postprocess import ensure_all_experiences, sanitize_cover_letter_content, sanitize_cv_content
from .serializers import full_knowledge_base, to_dict

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    # ── generation ───────────────────────────────────────────────────────

    def _profile(self) -> CareerProfile | None:
        return (
            self.db.query(CareerProfile)
            .filter(CareerProfile.user_id == self.user.id)
            .first()
        )

    def _base_payload(self, application: Application, strategy: ApplicationStrategy) -> dict:
        job = self.db.get(Job, application.job_id)
        kb = full_knowledge_base(self.db, self.user.id)
        profile = self._profile()
        matches = self.db.query(RequirementMatch).filter(RequirementMatch.job_id == job.id).all()
        req_by_id = {r.id: r for r in self.db.query(JobRequirement).filter(JobRequirement.job_id == job.id)}
        return {
            "job": {
                "position_title": job.position_title,
                "organization_name": job.organization_name,
                "location": job.location,
                "parsed": job.parsed,
            },
            "profile": to_dict(profile) if profile else {},
            "experiences": kb["experiences"],
            "skills": kb["skills"],
            "education": kb["education"],
            "certifications": kb["certifications"],
            "languages": kb["languages"],
            "strategy": to_dict(strategy),
            "matches": [
                {
                    "requirement_text": req_by_id[m.requirement_id].text if m.requirement_id in req_by_id else "",
                    "status": m.status,
                    "importance": req_by_id[m.requirement_id].importance if m.requirement_id in req_by_id else "MEDIUM",
                    "evidence": m.evidence,
                }
                for m in matches
            ],
        }

    def _new_version(
        self,
        document_type: str,
        document_id: str,
        content: dict,
        *,
        template_key: str,
        model: str,
        prompt_version: str,
        input_refs: dict,
        validation: dict,
        ats: dict,
        user_edited: bool = False,
    ) -> DocumentVersion:
        latest = (
            self.db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_type == document_type,
                DocumentVersion.document_id == document_id,
            )
            .order_by(DocumentVersion.version_number.desc())
            .first()
        )
        if latest:
            latest.is_current = False
        profile = self._profile()
        version = DocumentVersion(
            document_type=document_type,
            document_id=document_id,
            version_number=(latest.version_number + 1) if latest else 1,
            content=content,
            rendered_text=render_text(document_type, content, to_dict(profile) if profile else {}),
            template_key=template_key,
            model=model,
            prompt_version=prompt_version,
            input_refs=input_refs,
            validation_results=validation,
            ats_analysis=ats,
            user_edited=user_edited,
            is_current=True,
            knowledge_base_snapshot=self._kb_snapshot(),
        )
        self.db.add(version)
        self.db.flush()
        return version

    def _kb_snapshot(self) -> dict:
        kb = full_knowledge_base(self.db, self.user.id)
        return {
            "experiences": len(kb["experiences"]),
            "skills": len(kb["skills"]),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

    def generate_cv(
        self,
        application: Application,
        strategy: ApplicationStrategy,
        *,
        template_key: str | None = None,
        ctx: AgentContext | None = None,
    ) -> DocumentVersion:
        ctx = ctx or AgentContext(db=self.db, user_id=self.user.id, job_id=application.job_id, application_id=application.id)
        payload = self._base_payload(application, strategy)
        agent = CVAgent()
        result: GeneratedCV = agent.run(ctx, **payload)

        cv = self.db.query(CV).filter(CV.application_id == application.id).first()
        if cv is None:
            cv = CV(application_id=application.id, template_key=template_key or "minimal-ats",
                    title=f"CV — {self.db.get(Job, application.job_id).position_title or 'Application'}")
            self.db.add(cv)
            self.db.flush()
        elif template_key:
            cv.template_key = template_key

        content = sanitize_cv_content(result.model_dump())
        content = ensure_all_experiences(
            content,
            payload.get("experiences") or [],
            strategy=payload.get("strategy") or {},
            job=payload.get("job") or {},
            matches=payload.get("matches") or [],
        )
        validation = self.validate_document("cv", content, application)
        ats = self._run_ats(ctx, "cv", content, application)
        version = self._new_version(
            "cv",
            cv.id,
            content,
            template_key=cv.template_key,
            model="",
            prompt_version=agent.prompt.version,
            input_refs={"application_id": application.id, "job_id": application.job_id},
            validation=validation.model_dump(),
            ats=ats,
        )
        version.model = self._last_model(ctx)
        if ats.get("ats_score") is not None:
            application.ats_score_snapshot = ats["ats_score"]
        self.db.flush()
        return version

    def generate_cover_letter(
        self,
        application: Application,
        strategy: ApplicationStrategy,
        *,
        template_key: str | None = None,
        ctx: AgentContext | None = None,
    ) -> DocumentVersion:
        ctx = ctx or AgentContext(db=self.db, user_id=self.user.id, job_id=application.job_id, application_id=application.id)
        payload = self._base_payload(application, strategy)
        job = self.db.get(Job, application.job_id)
        payload["research"] = [
            to_dict(r)
            for r in self.db.query(OrganizationResearch).filter(OrganizationResearch.job_id == job.id)
        ]
        hiring = self.db.query(HiringContext).filter(HiringContext.job_id == job.id).first()
        hiring_payload: dict = {"identified": False}
        if hiring:
            hiring_payload = to_dict(hiring)
            if hiring.hiring_manager_id:
                hm = self.db.get(Person, hiring.hiring_manager_id)
                if hm:
                    hiring_payload["hiring_manager"] = to_dict(hm)
        payload["hiring_context"] = hiring_payload

        agent = CoverLetterAgent()
        result: GeneratedCoverLetter = agent.run(ctx, **payload)

        letter = (
            self.db.query(CoverLetter).filter(CoverLetter.application_id == application.id).first()
        )
        if letter is None:
            letter = CoverLetter(
                application_id=application.id,
                template_key=template_key or "minimal-ats",
                title=f"Cover Letter — {job.position_title or 'Application'}",
            )
            self.db.add(letter)
            self.db.flush()
        elif template_key:
            letter.template_key = template_key

        content = sanitize_cover_letter_content(result.model_dump())
        validation = self.validate_document("cover_letter", content, application)
        version = self._new_version(
            "cover_letter",
            letter.id,
            content,
            template_key=letter.template_key,
            model="",
            prompt_version=agent.prompt.version,
            input_refs={"application_id": application.id, "job_id": application.job_id},
            validation=validation.model_dump(),
            ats={},
        )
        version.model = self._last_model(ctx)
        self.db.flush()
        return version

    def _last_model(self, ctx: AgentContext) -> str:
        from ..models import AgentExecution

        row = (
            self.db.query(AgentExecution)
            .filter(AgentExecution.workflow_run_id == ctx.workflow_run_id)
            .order_by(AgentExecution.created_at.desc())
            .first()
        )
        return row.model if row else ""

    # ── validation pipeline (§41) ────────────────────────────────────────

    def validate_document(self, document_type: str, content: dict, application: Application) -> ValidationReport:
        report = ValidationReport()
        job = self.db.get(Job, application.job_id)
        kb = full_knowledge_base(self.db, self.user.id)

        # 1 — schema: Pydantic already validated; re-check round trip
        try:
            if document_type == "cv":
                GeneratedCV.model_validate(content)
            else:
                GeneratedCoverLetter.model_validate(content)
        except Exception as exc:
            report.schema_valid = False
            report.issues.append(f"Schema validation failed: {exc}")

        # 2 + 5 — evidence & hallucination: every evidence_id must exist in the KB
        known_ids = {
            item["id"]
            for key in ("experiences", "achievements", "projects", "skills", "education", "certifications")
            for item in kb[key]
            if item.get("id")
        }
        cited: set[str] = set()
        if document_type == "cv":
            for entry in content.get("experience", []):
                for bullet in entry.get("bullets", []):
                    cited.update(bullet.get("evidence_ids", []))
            cited.update(content.get("summary_evidence_ids", []))
        else:
            for para in content.get("paragraphs", []):
                cited.update(para.get("evidence_ids", []))
        unsupported = sorted(eid for eid in cited if eid and eid not in known_ids)
        if unsupported:
            report.evidence_valid = False
            report.hallucination_free = False
            report.unsupported_claims = unsupported
            report.issues.append(f"Unsupported evidence references: {unsupported}")

        # 3 — requirement coverage: CRITICAL/HIGH requirements should be addressed
        matches = self.db.query(RequirementMatch).filter(RequirementMatch.job_id == job.id).all()
        req_by_id = {r.id: r for r in self.db.query(JobRequirement).filter(JobRequirement.job_id == job.id)}
        uncovered = []
        doc_text = render_text(document_type, content, to_dict(self._profile()) if self._profile() else {}).lower()
        for m in matches:
            req = req_by_id.get(m.requirement_id)
            if not req or req.importance not in ("CRITICAL", "HIGH"):
                continue
            if m.status in ("MATCHED", "PARTIALLY_MATCHED", "TRANSFERABLE"):
                keywords = [k.lower() for k in (req.keywords or [])]
                if keywords and not any(k in doc_text for k in keywords):
                    uncovered.append(req.text[:120])
        if uncovered:
            report.requirement_coverage_ok = len(uncovered) <= 2
            report.uncovered_requirements = uncovered
            if not report.requirement_coverage_ok:
                report.issues.append(f"Important requirements not addressed: {uncovered}")

        # 4 — ATS handled by _run_ats; mark ok if no formatting risks there
        # 6 — quality: basic language checks
        if document_type == "cover_letter" and len(content.get("paragraphs", [])) > 7:
            report.quality_ok = False
            report.issues.append("Cover letter exceeds one page (too many paragraphs)")
        return report

    def _run_ats(self, ctx: AgentContext, document_type: str, content: dict, application: Application) -> dict:
        job = self.db.get(Job, application.job_id)
        keywords = (job.parsed or {}).get("keywords", [])
        requirements = [
            {"text": r.text}
            for r in self.db.query(JobRequirement).filter(JobRequirement.job_id == job.id)
            if r.importance in ("CRITICAL", "HIGH")
        ]
        profile = self._profile()
        doc_text = render_text(document_type, content, to_dict(profile) if profile else {})
        try:
            result = ATSAnalysisAgent().run(
                ctx, document_text=doc_text, keywords=keywords, requirements=requirements
            )
            return result.model_dump()
        except AgentError as exc:
            logger.warning("ATS analysis failed (non-fatal): %s", exc)
            return {"error": str(exc)}

    # ── editing / versioning (§29-31) ────────────────────────────────────

    def get_document(self, document_type: str, document_id: str) -> tuple[CV | CoverLetter, DocumentVersion | None]:
        model = CV if document_type == "cv" else CoverLetter
        doc = self.db.get(model, document_id)
        if doc is None:
            return None, None
        app = self.db.get(Application, doc.application_id)
        if app.user_id != self.user.id:
            return None, None
        current = (
            self.db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_type == document_type,
                DocumentVersion.document_id == document_id,
                DocumentVersion.is_current == True,  # noqa: E712
            )
            .first()
        )
        return doc, current

    def save_user_edit(self, document_type: str, document_id: str, content: dict, template_key: str | None) -> DocumentVersion:
        doc, current = self.get_document(document_type, document_id)
        if doc is None:
            raise AgentError("Document not found")
        if template_key:
            doc.template_key = template_key
        return self._new_version(
            document_type,
            document_id,
            content,
            template_key=doc.template_key,
            model=current.model if current else "",
            prompt_version=current.prompt_version if current else "",
            input_refs={"edited_from_version": current.version_number if current else 0},
            validation=current.validation_results if current else {},
            ats=current.ats_analysis if current else {},
            user_edited=True,
        )

    def restore_version(self, document_type: str, document_id: str, version_number: int) -> DocumentVersion:
        doc, _ = self.get_document(document_type, document_id)
        if doc is None:
            raise AgentError("Document not found")
        target = (
            self.db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_type == document_type,
                DocumentVersion.document_id == document_id,
                DocumentVersion.version_number == version_number,
            )
            .first()
        )
        if target is None:
            raise AgentError(f"Version {version_number} not found")
        return self._new_version(
            document_type,
            document_id,
            target.content,
            template_key=target.template_key,
            model=target.model,
            prompt_version=target.prompt_version,
            input_refs={"restored_from_version": version_number},
            validation=target.validation_results,
            ats=target.ats_analysis,
        )

    def regenerate_section(self, document_type: str, document_id: str, section: str, application: Application, ctx: AgentContext) -> DocumentVersion:
        """Regenerate one section while preserving the rest of the document (§31)."""
        doc, current = self.get_document(document_type, document_id)
        if doc is None or current is None:
            raise AgentError("Document not found")
        strategy = (
            self.db.query(ApplicationStrategy)
            .filter(ApplicationStrategy.application_id == application.id)
            .first()
        )
        payload = self._base_payload(application, strategy) if strategy else self._base_payload_min(application)
        if document_type == "cv":
            result: GeneratedCV = CVAgent().run(ctx, **payload)
            fresh = sanitize_cv_content(result.model_dump())
            if section == "experience":
                fresh = ensure_all_experiences(
                    fresh,
                    payload.get("experiences") or [],
                    strategy=payload.get("strategy") or {},
                    job=payload.get("job") or {},
                    matches=payload.get("matches") or [],
                )
        else:
            result: GeneratedCoverLetter = CoverLetterAgent().run(ctx, **payload)
            fresh = sanitize_cover_letter_content(result.model_dump())

        content = dict(current.content)
        if section in fresh:
            content[section] = fresh[section]  # replace only the requested section
        else:
            raise AgentError(f"Unknown section: {section}")
        validation = self.validate_document(document_type, content, application)
        return self._new_version(
            document_type,
            document_id,
            content,
            template_key=doc.template_key,
            model="",
            prompt_version=current.prompt_version,
            input_refs={"regenerated_section": section},
            validation=validation.model_dump(),
            ats=current.ats_analysis,
        )

    def _base_payload_min(self, application: Application) -> dict:
        job = self.db.get(Job, application.job_id)
        kb = full_knowledge_base(self.db, self.user.id)
        profile = self._profile()
        return {
            "job": {"position_title": job.position_title, "organization_name": job.organization_name},
            "profile": to_dict(profile) if profile else {},
            **{k: kb[k] for k in ("experiences", "skills", "education", "certifications", "languages")},
            "strategy": {},
            "matches": [],
        }

    def list_versions(self, document_type: str, document_id: str) -> list[DocumentVersion]:
        return (
            self.db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_type == document_type,
                DocumentVersion.document_id == document_id,
            )
            .order_by(DocumentVersion.version_number.desc())
            .all()
        )
