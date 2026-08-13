"""Structured output schemas for AI agents (§38).

Every agent returns JSON validated against one of these Pydantic models —
critical application logic never depends on free-form LLM text.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ── Career knowledge extraction (§6) ─────────────────────────────────────────


def _coerce_str_list(value: Any) -> list[str]:
    """Accept plain strings or dicts like {description, quantified_result}."""
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
            continue
        if isinstance(item, dict):
            text = (
                item.get("description")
                or item.get("text")
                or item.get("achievement")
                or item.get("name")
                or ""
            )
            if not isinstance(text, str):
                text = str(text) if text is not None else ""
            text = text.strip()
            metric = item.get("quantified_result") or item.get("metric") or item.get("result")
            if isinstance(metric, str) and metric.strip() and metric.strip() not in text:
                text = f"{text} ({metric.strip()})" if text else metric.strip()
            if text:
                out.append(text)
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _coerce_skill_list(value: Any) -> list[dict[str, str]]:
    """Accept skill name strings or {name, category} objects."""
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    out: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append({"name": name, "category": "technical"})
            continue
        if isinstance(item, BaseModel):
            dumped = item.model_dump()
            name = str(dumped.get("name") or "").strip()
            if name:
                out.append(
                    {
                        "name": name,
                        "category": str(dumped.get("category") or "technical").strip() or "technical",
                    }
                )
            continue
        if isinstance(item, dict):
            name = item.get("name") or item.get("skill") or item.get("canonical_name") or ""
            if not isinstance(name, str):
                name = str(name) if name is not None else ""
            name = name.strip()
            if not name:
                continue
            category = item.get("category") or "technical"
            if not isinstance(category, str) or not category.strip():
                category = "technical"
            out.append({"name": name, "category": category.strip()})
    return out


class ExtractedExperience(BaseModel):
    organization: str = ""
    job_title: str = ""
    start_date: str = ""
    end_date: str = ""
    employment_type: str = ""
    location: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    leadership: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    quantified_results: list[str] = Field(default_factory=list)
    confidence: float = 0.5

    @field_validator(
        "responsibilities",
        "achievements",
        "projects",
        "technologies",
        "skills",
        "domains",
        "leadership",
        "stakeholders",
        "quantified_results",
        mode="before",
    )
    @classmethod
    def _normalize_str_lists(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)


class ExtractedEducation(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""


class ExtractedCertification(BaseModel):
    name: str = ""
    issuer: str = ""
    issue_date: str = ""


class ExtractedSkill(BaseModel):
    name: str = ""
    category: str = "technical"


class ExtractedLanguage(BaseModel):
    language: str = ""
    proficiency: str = ""


class ExtractedPublication(BaseModel):
    title: str = ""
    venue: str = ""
    year: str = ""


class CareerExtractionResult(BaseModel):
    experiences: list[ExtractedExperience] = Field(default_factory=list)
    skills: list[ExtractedSkill] = Field(default_factory=list)
    education: list[ExtractedEducation] = Field(default_factory=list)
    certifications: list[ExtractedCertification] = Field(default_factory=list)
    languages: list[ExtractedLanguage] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    publications: list[ExtractedPublication] = Field(default_factory=list)
    summary: str = ""
    notes: list[str] = Field(default_factory=list)

    @field_validator("skills", mode="before")
    @classmethod
    def _normalize_skills(cls, value: Any) -> list[dict[str, str]]:
        return _coerce_skill_list(value)

    @field_validator("achievements", "notes", mode="before")
    @classmethod
    def _normalize_str_lists(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)


# ── Career reconciliation (merge vs create) ──────────────────────────────────


class ReconciliationProposal(BaseModel):
    """One suggested action for an extracted career entity vs existing KB."""

    proposal_id: str = ""
    entity_type: Literal["experience", "project", "achievement"] = "experience"
    action: Literal["create", "merge"] = "create"
    target_id: str | None = None
    target_label: str = ""
    confidence: float = 0.5
    reasoning: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class CareerReconciliationResult(BaseModel):
    proposals: list[ReconciliationProposal] = Field(default_factory=list)


# ── JD analysis (§10-11) ─────────────────────────────────────────────────────


class JDPositionInfo(BaseModel):
    organization: str = ""
    department: str = ""
    team: str = ""
    job_title: str = ""
    grade_level: str = ""
    location: str = ""
    contract_type: str = ""
    duration: str = ""
    deadline: str = ""
    remote_policy: str = ""
    reporting_line: str = ""


class JDRequirement(BaseModel):
    text: str
    category: Literal[
        "education", "experience", "technical_skill", "functional", "domain",
        "language", "certification", "management", "responsibility",
        "competency", "other",
    ] = "functional"
    requirement_type: Literal["mandatory", "preferred", "responsibility", "competency"] = "mandatory"
    importance: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    keywords: list[str] = Field(default_factory=list)


class JDKeyword(BaseModel):
    term: str
    classification: Literal[
        "technical", "functional", "domain", "organizational",
        "behavioral", "tools", "methodologies", "certifications",
    ] = "technical"


class JDAnalysisResult(BaseModel):
    position: JDPositionInfo = Field(default_factory=JDPositionInfo)
    requirements: list[JDRequirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)
    keywords: list[JDKeyword] = Field(default_factory=list)
    summary: str = ""


# ── Research (§12-14) ────────────────────────────────────────────────────────


class ResearchClaim(BaseModel):
    claim: str
    category: str = "general"
    source_url: str = ""
    source_type: str = "other"
    publication_date: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    relevance_to_job: str = ""


class OrganizationResearchResult(BaseModel):
    organization: str = ""
    website: str = ""
    claims: list[ResearchClaim] = Field(default_factory=list)
    unavailable: bool = False
    note: str = ""


class IdentifiedPerson(BaseModel):
    name: str
    role: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    evidence: list[str] = Field(default_factory=list)
    profile_url: str = ""


class HiringContextResult(BaseModel):
    hiring_manager: IdentifiedPerson | None = None
    recruiter: IdentifiedPerson | None = None
    other_people: list[IdentifiedPerson] = Field(default_factory=list)
    team_insights: list[str] = Field(default_factory=list)
    identified: bool = False
    note: str = ""


# ── Matching (§15-17) ────────────────────────────────────────────────────────

MatchStatus = Literal["MATCHED", "PARTIALLY_MATCHED", "TRANSFERABLE", "NOT_MATCHED", "UNKNOWN"]


class MatchEvidence(BaseModel):
    entity_type: str
    entity_id: str
    evidence: str
    source: str = ""


class RequirementMatchResult(BaseModel):
    requirement_id: str
    status: MatchStatus = "UNKNOWN"
    evidence: list[MatchEvidence] = Field(default_factory=list)
    explanation: str = ""
    confidence: float = 0.0
    match_kind: Literal["direct", "transferable"] = "direct"


class MatchingResult(BaseModel):
    matches: list[RequirementMatchResult] = Field(default_factory=list)


# ── Scoring (§18-19) — qualitative overlay only; numbers are computed ────────


class ScoreNarrative(BaseModel):
    strong_matches: list[str] = Field(default_factory=list)
    partial_matches: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    transferable: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    explanation: str = ""


# ── Application strategy (§22) ───────────────────────────────────────────────


class ApplicationStrategyResult(BaseModel):
    positioning: str = ""
    priority_experience: list[str] = Field(default_factory=list)  # experience ids
    priority_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    evidence_plan: list[dict] = Field(default_factory=list)
    de_emphasis: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    messaging_strategy: str = ""


# ── Documents (§23-27) ───────────────────────────────────────────────────────


class CVBullet(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class CVExperienceEntry(BaseModel):
    organization: str
    job_title: str
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    bullets: list[CVBullet] = Field(default_factory=list)


class CVSection(BaseModel):
    name: str
    entries: list[dict] = Field(default_factory=list)


class GeneratedCV(BaseModel):
    headline: str = ""
    summary: str = ""
    summary_evidence_ids: list[str] = Field(default_factory=list)
    experience: list[CVExperienceEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[dict] = Field(default_factory=list)
    additional_sections: list[CVSection] = Field(default_factory=list)


class GeneratedCoverLetter(BaseModel):
    subject: str = ""
    salutation: str = "Dear Hiring Manager,"
    paragraphs: list[dict] = Field(default_factory=list)  # {text, evidence_ids}
    closing: str = "Sincerely,"


# ── ATS analysis (§25) ───────────────────────────────────────────────────────


class ATSAnalysis(BaseModel):
    ats_score: float = 0.0  # 0..1
    keyword_coverage: float = 0.0
    covered_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    keyword_overuse_warnings: list[str] = Field(default_factory=list)
    formatting_risks: list[str] = Field(default_factory=list)
    requirement_coverage: float = 0.0
    notes: list[str] = Field(default_factory=list)


# ── Validation (§41) ─────────────────────────────────────────────────────────


class ValidationReport(BaseModel):
    schema_valid: bool = True
    evidence_valid: bool = True
    requirement_coverage_ok: bool = True
    ats_ok: bool = True
    hallucination_free: bool = True
    quality_ok: bool = True
    unsupported_claims: list[str] = Field(default_factory=list)
    uncovered_requirements: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            [
                self.schema_valid,
                self.evidence_valid,
                self.requirement_coverage_ok,
                self.ats_ok,
                self.hallucination_free,
                self.quality_ok,
            ]
        )
