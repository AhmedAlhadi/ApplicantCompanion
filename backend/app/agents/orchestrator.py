"""Central orchestrator coordinating the specialized agents (§5, §39).

Two workflows:
  job_analysis:        JobCreated → ParseJD → ResearchOrganization →
                       ResearchHiringContext → RetrieveCandidateEvidence →
                       MatchRequirements → CalculateScore
  document_generation: GenerateApplicationStrategy → AwaitUserDecision →
                       GenerateCV → ValidateCV → GenerateCoverLetter →
                       ValidateDocuments → ReadyForReview

Every stage is statused PENDING/RUNNING/COMPLETED/FAILED/SKIPPED and persisted
on a WorkflowRun, and agent failures degrade gracefully (§54).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Application,
    ApplicationStrategy,
    HiringContext,
    Job,
    JobRequirement,
    JobScore,
    Organization,
    OrganizationResearch,
    Person,
    RequirementMatch,
    User,
    WorkflowRun,
)
from ..retrieval.pipeline import retrieve_evidence
from ..schemas.agents import HiringContextResult, OrganizationResearchResult
from ..scoring.engine import compute_score
from ..services.research import extract_urls, gather_snippets
from ..services.serializers import to_dict
from .base import AgentContext, AgentError
from .job_analysis import JobAnalysisAgent
from .matching import (
    ApplicationStrategyAgent,
    CandidateMatchingAgent,
    ScoringNarrativeAgent,
)
from .research import HiringTeamResearchAgent, OrganizationResearchAgent

logger = logging.getLogger(__name__)

ANALYSIS_STAGES = [
    "ParseJD",
    "ResearchOrganization",
    "ResearchHiringContext",
    "RetrieveCandidateEvidence",
    "MatchRequirements",
    "CalculateScore",
]

GENERATION_STAGES = [
    "GenerateApplicationStrategy",
    "AwaitUserDecision",
    "GenerateCV",
    "ValidateCV",
    "GenerateCoverLetter",
    "ValidateDocuments",
    "ReadyForReview",
]


class Orchestrator:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    # ── workflow plumbing ────────────────────────────────────────────────

    def _new_run(self, workflow_type: str, stages: list[str], job_id=None, application_id=None) -> WorkflowRun:
        run = WorkflowRun(
            user_id=self.user.id,
            job_id=job_id,
            application_id=application_id,
            workflow_type=workflow_type,
            status="RUNNING",
            stages=[{"name": s, "status": "PENDING"} for s in stages],
        )
        self.db.add(run)
        self.db.flush()
        return run

    def _stage(self, run: WorkflowRun, name: str, status: str, error: str = "") -> None:
        stages = [dict(s) for s in run.stages]
        for s in stages:
            if s["name"] == name:
                s["status"] = status
                key = {"RUNNING": "started_at", "COMPLETED": "ended_at", "FAILED": "ended_at", "SKIPPED": "ended_at"}.get(status)
                if key:
                    s[key] = datetime.now(timezone.utc).isoformat()
                if error:
                    s["error"] = error[:1000]
        run.stages = stages
        run.current_stage = name
        self.db.flush()
        try:
            from ..workers.runner import publish

            publish("workflow", run.id, {"type": "workflow", "data": {
                "id": run.id, "status": run.status, "current_stage": run.current_stage,
                "stages": run.stages, "workflow_type": run.workflow_type,
            }})
        except Exception:
            pass  # SSE fan-out is best-effort; polling remains as fallback

    def _ctx(self, run: WorkflowRun, job_id=None, application_id=None) -> AgentContext:
        return AgentContext(
            db=self.db,
            user_id=self.user.id,
            job_id=job_id,
            application_id=application_id,
            workflow_run_id=run.id,
        )

    def create_run(self, workflow_type: str, stages: list[str], job_id=None, application_id=None) -> WorkflowRun:
        """Create the run row synchronously so the API can return its id
        before background execution starts."""
        return self._new_run(workflow_type, stages, job_id=job_id, application_id=application_id)

    # ── workflow 1: job analysis (§9) ─────────────────────────────────────

    def run_job_analysis(self, job: Job, *, include_research: bool = True, run: WorkflowRun | None = None) -> WorkflowRun:
        run = run or self._new_run("job_analysis", ANALYSIS_STAGES, job_id=job.id)
        ctx = self._ctx(run, job_id=job.id)
        job.status = "analyzing"
        self.db.flush()

        # 1. Parse JD ──────────────────────────────────────────────────────
        self._stage(run, "ParseJD", "RUNNING")
        try:
            analysis = JobAnalysisAgent().run(ctx, jd_text=job.raw_jd_text)
        except AgentError as exc:
            self._stage(run, "ParseJD", "FAILED", str(exc))
            run.status = "FAILED"
            run.error = f"JD parsing failed: {exc}"
            job.status = "failed"
            self.db.commit()
            return run

        job.parsed = analysis.model_dump()
        pos = analysis.position
        job.organization_name = job.organization_name or pos.organization
        job.position_title = job.position_title or pos.job_title
        job.department = pos.department
        job.team = pos.team
        job.grade_level = pos.grade_level
        job.location = job.location or pos.location
        job.contract_type = pos.contract_type
        job.duration = pos.duration
        job.deadline = job.deadline or (pos.deadline or None)
        job.remote_policy = pos.remote_policy
        job.reporting_line = pos.reporting_line
        job.executive_summary = analysis.summary

        # Persist requirements (replace any previous analysis)
        self.db.query(JobRequirement).filter(JobRequirement.job_id == job.id).delete()
        requirements = []
        for req in analysis.requirements:
            row = JobRequirement(
                job_id=job.id,
                category=req.category,
                requirement_type=req.requirement_type,
                text=req.text,
                importance=req.importance,
                keywords=req.keywords,
            )
            self.db.add(row)
            requirements.append(row)
        self.db.flush()
        self._stage(run, "ParseJD", "COMPLETED")

        # 2. Research organization (§12) — failure must not block (§54) ────
        org: Organization | None = None
        if job.organization_name:
            org = (
                self.db.query(Organization)
                .filter(Organization.user_id == self.user.id, Organization.name == job.organization_name)
                .first()
            )
            if org is None:
                org = Organization(user_id=self.user.id, name=job.organization_name)
                self.db.add(org)
                self.db.flush()
            job.organization_id = org.id

        self._stage(run, "ResearchOrganization", "RUNNING")
        org_result = OrganizationResearchResult(organization=job.organization_name, unavailable=True)
        if include_research and job.organization_name:
            try:
                snippets = gather_snippets(
                    self.db,
                    queries=[
                        f"{job.organization_name} official website mission strategy",
                        f"{job.organization_name} {job.department or job.position_title} initiatives latest news",
                        f"{job.organization_name} {job.department or job.position_title} department culture environment",
                    ],
                    extra_urls=extract_urls(job.raw_jd_text) + ([job.source_url] if job.source_url else []),
                )
                org_result = OrganizationResearchAgent().run(
                    ctx,
                    organization=job.organization_name,
                    job_title=job.position_title,
                    snippets=snippets,
                )
                self.db.query(OrganizationResearch).filter(OrganizationResearch.job_id == job.id).delete()
                for claim in org_result.claims:
                    self.db.add(
                        OrganizationResearch(
                            organization_id=org.id if org else None,
                            job_id=job.id,
                            category=claim.category,
                            claim=claim.claim,
                            source_url=claim.source_url,
                            source_type=claim.source_type,
                            publication_date=claim.publication_date,
                            confidence=claim.confidence,
                            relevance_to_job=claim.relevance_to_job,
                        )
                    )
                if org_result.website and org and not org.website:
                    org.website = org_result.website
                self._stage(run, "ResearchOrganization", "COMPLETED")
            except AgentError as exc:
                self._stage(run, "ResearchOrganization", "FAILED", f"Research unavailable: {exc}")
        else:
            self._stage(run, "ResearchOrganization", "SKIPPED", "Research disabled or no organization")

        # 3. Research hiring context (§13-14) ─────────────────────────────
        self._stage(run, "ResearchHiringContext", "RUNNING")
        hiring_result = HiringContextResult(
            identified=False, note="Hiring manager not identified with sufficient confidence."
        )
        if include_research and job.organization_name:
            try:
                snippets = gather_snippets(
                    self.db,
                    queries=[
                        f"{job.organization_name} {job.department} director head leadership latest news",
                        f"{job.organization_name} {job.position_title} hiring manager team",
                    ],
                )
                hiring_result = HiringTeamResearchAgent().run(
                    ctx,
                    organization=job.organization_name,
                    department=job.department,
                    job_title=job.position_title,
                    snippets=snippets,
                )
                self._stage(run, "ResearchHiringContext", "COMPLETED")
            except AgentError as exc:
                self._stage(run, "ResearchHiringContext", "FAILED", f"Research unavailable: {exc}")
        else:
            self._stage(run, "ResearchHiringContext", "SKIPPED", "Research disabled or no organization")

        self.db.query(HiringContext).filter(HiringContext.job_id == job.id).delete()
        hiring_row = HiringContext(
            job_id=job.id,
            identified=hiring_result.identified,
            notes=hiring_result.note,
            team_insights=hiring_result.team_insights,
        )

        def _persist_person(p) -> str | None:
            if p is None or not p.name:
                return None
            person = Person(
                organization_id=org.id if org else None,
                name=p.name,
                role=p.role,
                confidence=p.confidence,
                evidence=p.evidence,
                profile_url=p.profile_url,
            )
            self.db.add(person)
            self.db.flush()
            return person.id

        hiring_row.hiring_manager_id = _persist_person(hiring_result.hiring_manager)
        hiring_row.recruiter_id = _persist_person(hiring_result.recruiter)
        for other in hiring_result.other_people:
            _persist_person(other)
        self.db.add(hiring_row)
        self.db.flush()

        # 4. Retrieve candidate evidence (§35-36) ─────────────────────────
        self._stage(run, "RetrieveCandidateEvidence", "RUNNING")
        evidence_by_req: dict[str, list[dict]] = {}
        all_evidence: dict[tuple[str, str], dict] = {}
        for req in requirements:
            items = retrieve_evidence(self.db, self.user.id, req.text, limit=6)
            ev_payloads = []
            for item in items:
                payload = {
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "text": item.text[:600],
                    "verification_status": item.verification_status,
                    "retrieval_score": round(item.score, 4),
                }
                ev_payloads.append(payload)
                all_evidence.setdefault((item.entity_type, item.entity_id), payload)
            evidence_by_req[req.id] = ev_payloads
        self._stage(run, "RetrieveCandidateEvidence", "COMPLETED")

        # 5. Match requirements (§15-17) ──────────────────────────────────
        self._stage(run, "MatchRequirements", "RUNNING")
        try:
            req_payloads = [
                {
                    "id": r.id,
                    "text": r.text,
                    "category": r.category,
                    "importance": r.importance,
                    "requirement_type": r.requirement_type,
                    "keywords": r.keywords,
                }
                for r in requirements
            ]
            matching = CandidateMatchingAgent().run(
                ctx,
                requirements=req_payloads,
                evidence=list(all_evidence.values()),
            )
        except AgentError as exc:
            self._stage(run, "MatchRequirements", "FAILED", str(exc))
            run.status = "FAILED"
            run.error = f"Matching failed: {exc}"
            job.status = "failed"
            self.db.commit()
            return run

        self.db.query(RequirementMatch).filter(RequirementMatch.job_id == job.id).delete()
        req_by_id = {r.id: r for r in requirements}
        match_rows: list[RequirementMatch] = []
        for m in matching.matches:
            if m.requirement_id not in req_by_id:
                continue
            row = RequirementMatch(
                job_id=job.id,
                requirement_id=m.requirement_id,
                status=m.status,
                confidence=m.confidence,
                explanation=m.explanation,
                match_kind=m.match_kind,
                evidence=[e.model_dump() for e in m.evidence],
            )
            self.db.add(row)
            match_rows.append(row)
        self.db.flush()
        self._stage(run, "MatchRequirements", "COMPLETED")

        # 6. Calculate score programmatically (§18) ───────────────────────
        self._stage(run, "CalculateScore", "RUNNING")
        weights = self._scoring_weights()
        threshold = self._threshold()
        computed = compute_score(requirements, match_rows, weights=weights, threshold=threshold)

        narrative_payload = [
            {
                "requirement_text": req_by_id[m.requirement_id].text,
                "status": m.status,
                "importance": req_by_id[m.requirement_id].importance,
                "evidence": m.evidence,
                "keywords": req_by_id[m.requirement_id].keywords,
            }
            for m in match_rows
        ]
        try:
            narrative = ScoringNarrativeAgent().run(
                ctx,
                matches=narrative_payload,
                category_scores=computed["category_scores"],
                overall_score=computed["overall_score"],
            )
        except AgentError as exc:
            logger.warning("Scoring narrative failed (non-fatal): %s", exc)
            narrative = None

        self.db.query(JobScore).filter(JobScore.job_id == job.id).delete()
        score_row = JobScore(
            job_id=job.id,
            overall_score=computed["overall_score"],
            category_scores=computed["category_scores"],
            weights=computed["weights"],
            threshold=threshold,
            recommendation=computed["recommendation"],
            unknown_count=computed["unknown_count"],
            strong_matches=narrative.strong_matches if narrative else computed["strong_matches"],
            partial_matches=narrative.partial_matches if narrative else computed["partial_matches"],
            gaps=narrative.gaps if narrative else computed["gaps"],
            transferable=narrative.transferable if narrative else computed["transferable"],
            risks=narrative.risks if narrative else [],
            advantages=narrative.advantages if narrative else [],
            explanation=narrative.explanation if narrative else "",
        )
        self.db.add(score_row)
        job.status = "analyzed"
        self._stage(run, "CalculateScore", "COMPLETED")

        run.status = "COMPLETED"
        self.db.commit()
        return run

    # ── workflow 2: document generation (§22-31) ─────────────────────────

    def run_strategy(self, application: Application) -> WorkflowRun:
        run = self._new_run(
            "document_generation", ["GenerateApplicationStrategy"], job_id=application.job_id, application_id=application.id
        )
        ctx = self._ctx(run, job_id=application.job_id, application_id=application.id)
        self._stage(run, "GenerateApplicationStrategy", "RUNNING")
        strategy = self._generate_strategy(ctx, application)
        run.status = "COMPLETED"
        self._stage(run, "GenerateApplicationStrategy", "COMPLETED")
        self.db.commit()
        return run

    def run_generation(
        self,
        application: Application,
        *,
        generate_cv: bool = True,
        generate_cover_letter: bool = True,
        template_key: str | None = None,
    ) -> WorkflowRun:
        from ..services.documents import DocumentService

        stages = list(GENERATION_STAGES)
        if not generate_cv:
            stages.remove("GenerateCV")
            stages.remove("ValidateCV")
        if not generate_cover_letter:
            stages.remove("GenerateCoverLetter")
        run = self._new_run(
            "document_generation", stages, job_id=application.job_id, application_id=application.id
        )
        ctx = self._ctx(run, job_id=application.job_id, application_id=application.id)
        docs = DocumentService(self.db, self.user)

        self._stage(run, "GenerateApplicationStrategy", "RUNNING")
        strategy = self._generate_strategy(ctx, application)
        self._stage(run, "GenerateApplicationStrategy", "COMPLETED")

        # Human-in-the-loop checkpoint (§6, §20-21): reaching generation means
        # the user explicitly requested it, so the decision stage is satisfied.
        self._stage(run, "AwaitUserDecision", "COMPLETED", "User confirmed generation")

        if generate_cv:
            self._stage(run, "GenerateCV", "RUNNING")
            try:
                docs.generate_cv(application, strategy, template_key=template_key, ctx=ctx)
                self._stage(run, "GenerateCV", "COMPLETED")
                self._stage(run, "ValidateCV", "COMPLETED")
            except AgentError as exc:
                self._stage(run, "GenerateCV", "FAILED", str(exc))
                self._stage(run, "ValidateCV", "SKIPPED")

        if generate_cover_letter:
            self._stage(run, "GenerateCoverLetter", "RUNNING")
            try:
                docs.generate_cover_letter(application, strategy, template_key=template_key, ctx=ctx)
                self._stage(run, "GenerateCoverLetter", "COMPLETED")
            except AgentError as exc:
                self._stage(run, "GenerateCoverLetter", "FAILED", str(exc))

        if any(s["name"] == "ValidateDocuments" for s in run.stages):
            self._stage(run, "ValidateDocuments", "COMPLETED")
        self._stage(run, "ReadyForReview", "COMPLETED")
        application.status = "ready"
        run.status = "COMPLETED"
        self.db.commit()
        return run

    # ── shared ────────────────────────────────────────────────────────────

    def _generate_strategy(self, ctx: AgentContext, application: Application) -> ApplicationStrategy:
        job = self.db.get(Job, application.job_id)
        matches = (
            self.db.query(RequirementMatch).filter(RequirementMatch.job_id == job.id).all()
        )
        requirements = (
            self.db.query(JobRequirement).filter(JobRequirement.job_id == job.id).all()
        )
        req_by_id = {r.id: r for r in requirements}
        score = self.db.query(JobScore).filter(JobScore.job_id == job.id).order_by(JobScore.created_at.desc()).first()
        research = (
            self.db.query(OrganizationResearch).filter(OrganizationResearch.job_id == job.id).all()
        )
        from ..models import CareerProfile

        profile = (
            self.db.query(CareerProfile).filter(CareerProfile.user_id == self.user.id).first()
        )
        result = ApplicationStrategyAgent().run(
            ctx,
            job_analysis=job.parsed or {},
            matches=[
                {
                    "requirement_text": req_by_id[m.requirement_id].text if m.requirement_id in req_by_id else "",
                    "status": m.status,
                    "importance": req_by_id[m.requirement_id].importance if m.requirement_id in req_by_id else "MEDIUM",
                    "evidence": m.evidence,
                    "keywords": req_by_id[m.requirement_id].keywords if m.requirement_id in req_by_id else [],
                }
                for m in matches
            ],
            score=to_dict(score) if score else {},
            research=[to_dict(r) for r in research],
            profile_summary=profile.summary if profile else "",
        )

        existing = (
            self.db.query(ApplicationStrategy)
            .filter(ApplicationStrategy.application_id == application.id)
            .first()
        )
        if existing:
            self.db.delete(existing)
            self.db.flush()
        strategy = ApplicationStrategy(
            application_id=application.id,
            positioning=result.positioning,
            priority_experience=result.priority_experience,
            priority_skills=result.priority_skills,
            keywords=result.keywords,
            evidence_plan=result.evidence_plan,
            de_emphasis=result.de_emphasis,
            concerns=result.concerns,
            messaging_strategy=result.messaging_strategy,
        )
        self.db.add(strategy)
        if score:
            application.fit_score_snapshot = score.overall_score
        self.db.flush()
        return strategy

    def _threshold(self) -> float:
        from ..services.settings import get_user_setting

        return float(get_user_setting(self.db, self.user.id, "score_threshold", get_settings().score_threshold))

    def _scoring_weights(self) -> dict:
        from ..scoring.engine import DEFAULT_WEIGHTS
        from ..services.settings import get_user_setting

        return get_user_setting(self.db, self.user.id, "scoring_weights", DEFAULT_WEIGHTS)
