"""Structured output schemas for AI agents (§38).

Every agent returns JSON validated against one of these Pydantic models —
critical application logic never depends on free-form LLM text.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..dates import career_date_or_empty
from ..evidence_citations import sanitize_prose_field

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
                out.append({"name": name, "category": "uncategorized"})
            continue
        if isinstance(item, BaseModel):
            dumped = item.model_dump()
            name = str(dumped.get("name") or "").strip()
            if name:
                out.append(
                    {
                        "name": name,
                        "category": str(dumped.get("category") or "uncategorized").strip() or "uncategorized",
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
            category = item.get("category") or "uncategorized"
            if not isinstance(category, str) or not category.strip():
                category = "uncategorized"
            out.append({"name": name, "category": category.strip()})
    return out


class ExtractedKnowledge(BaseModel):
    """Industry, process, or cross-functional knowledge acquired through work."""

    name: str = ""
    kind: str = "domain"
    summary: str = ""
    depth: str = "applied"
    years_experience: float | None = None
    organization_hint: str = ""
    job_title_hint: str = ""
    how_acquired: str = ""
    how_applied: str = ""
    acquisition_mode: str = "acquired_through_role"
    confidence: float = 0.6

    @field_validator("name", "kind", "summary", "depth", "organization_hint", "job_title_hint", "how_acquired", "how_applied", "acquisition_mode", mode="before")
    @classmethod
    def _normalize_strings(cls, value: Any) -> str:
        return "" if value is None else str(value)


def _coerce_knowledge_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append({"name": name, "kind": "domain", "depth": "applied"})
            continue
        if isinstance(item, BaseModel):
            dumped = item.model_dump()
            name = str(dumped.get("name") or "").strip()
            if name:
                out.append(dumped)
            continue
        if isinstance(item, dict):
            name = item.get("name") or item.get("term") or item.get("canonical_name") or ""
            if not isinstance(name, str):
                name = str(name) if name is not None else ""
            name = name.strip()
            if not name:
                continue
            data = dict(item)
            data["name"] = name
            out.append(data)
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
    professional_knowledge: list[ExtractedKnowledge] = Field(default_factory=list)
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

    @field_validator("professional_knowledge", mode="before")
    @classmethod
    def _normalize_knowledge(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_knowledge_list(value)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _normalize_dates(cls, value: Any) -> str:
        return career_date_or_empty(value)


class ExtractedEducation(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _normalize_dates(cls, value: Any) -> str:
        return career_date_or_empty(value)


class ExtractedCertification(BaseModel):
    name: str = ""
    issuer: str = ""
    issue_date: str = ""

    @field_validator("issue_date", mode="before")
    @classmethod
    def _normalize_dates(cls, value: Any) -> str:
        return career_date_or_empty(value)


class ExtractedSkill(BaseModel):
    name: str = ""
    category: str = "uncategorized"


class ExtractedLanguage(BaseModel):
    language: str = ""
    proficiency: str = ""


class ExtractedPublication(BaseModel):
    title: str = ""
    venue: str = ""
    year: str = ""


class ExtractedProfile(BaseModel):
    """Contact and positioning details found in a career document."""

    full_name: str = ""
    headline: str = ""
    summary: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_nullable_strings(cls, value: Any) -> str:
        return "" if value is None else str(value)


class CareerExtractionResult(BaseModel):
    experiences: list[ExtractedExperience] = Field(default_factory=list)
    skills: list[ExtractedSkill] = Field(default_factory=list)
    education: list[ExtractedEducation] = Field(default_factory=list)
    certifications: list[ExtractedCertification] = Field(default_factory=list)
    languages: list[ExtractedLanguage] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    publications: list[ExtractedPublication] = Field(default_factory=list)
    professional_knowledge: list[ExtractedKnowledge] = Field(default_factory=list)
    profile: ExtractedProfile = Field(default_factory=ExtractedProfile)
    summary: str = ""
    notes: list[str] = Field(default_factory=list)

    @field_validator("profile", mode="before")
    @classmethod
    def _coerce_profile(cls, value: Any) -> Any:
        return value or {}

    @field_validator("skills", mode="before")
    @classmethod
    def _normalize_skills(cls, value: Any) -> list[dict[str, str]]:
        return _coerce_skill_list(value)

    @field_validator("professional_knowledge", mode="before")
    @classmethod
    def _normalize_knowledge(cls, value: Any) -> list[dict[str, Any]]:
        return _coerce_knowledge_list(value)

    @field_validator("achievements", "notes", mode="before")
    @classmethod
    def _normalize_str_lists(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)


# ── Career reconciliation (merge vs create) ──────────────────────────────────


class ReconciliationProposal(BaseModel):
    """Merge-or-create decision for one extracted career entity.

    The extracted record itself is not part of this schema. Strict structured
    output cannot carry a free-form object, so ingestion attaches the original
    payload after the model chooses merge vs create.
    """

    proposal_id: str = ""
    entity_type: Literal["experience", "project", "achievement"] = "experience"
    action: Literal["create", "merge"] = "create"
    target_id: str | None = None
    target_label: str = ""
    confidence: float = 0.5
    reasoning: str = ""


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        aliases = {
            "title": "job_title", "position_title": "job_title",
            "company": "organization", "organisation": "organization",
            "grade": "grade_level", "employment_type": "contract_type",
            "closing_date": "deadline", "application_deadline": "deadline",
            "apply_by": "deadline", "closing": "deadline", "due_date": "deadline",
        }
        for source, target in aliases.items():
            if source in data and not data.get(target):
                data[target] = data[source]
        return data

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_nullable_strings(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @field_validator("deadline", mode="after")
    @classmethod
    def _normalize_deadline(cls, value: str) -> str:
        from ..services.deadlines import normalize_application_deadline

        return normalize_application_deadline(value)


class QualificationPredicate(BaseModel):
    """One independently testable qualification fact.

    Paths use ALL predicate semantics; a requirement uses ANY path semantics.
    Unknown predicate kinds are rejected instead of guessed.
    """

    kind: Literal[
        "degree_level", "relevant_experience", "education_field",
        "certification", "language", "skill", "domain_expertise", "other",
    ] = "other"
    value: str = ""
    minimum_level: str = ""
    minimum_years: float | None = None
    terms: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {"kind": "other", "value": str(value)}
        data = dict(value)
        aliases = {
            "type": "kind", "predicate_type": "kind", "degree": "minimum_level",
            "degree_level": "minimum_level", "years": "minimum_years",
            "min_years": "minimum_years", "keywords": "terms",
        }
        for source, target in aliases.items():
            if source in data and target not in data:
                data[target] = data[source]
        kind_aliases = {
            "degree": "degree_level", "education": "degree_level",
            "experience": "relevant_experience", "years_experience": "relevant_experience",
            "field": "education_field",
            "domain": "domain_expertise",
            "domain_knowledge": "domain_expertise",
            "industry": "domain_expertise",
        }
        data["kind"] = kind_aliases.get(str(data.get("kind", "other")).lower(), data.get("kind", "other"))
        return data

    @field_validator("terms", mode="before")
    @classmethod
    def _normalize_terms(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)


class QualificationPath(BaseModel):
    """An alternative route to satisfying a requirement (predicates are ALL)."""

    label: str = ""
    predicates: list[QualificationPredicate] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _normalize_shape(cls, value: Any) -> Any:
        if isinstance(value, list):
            return {"predicates": value}
        if not isinstance(value, dict):
            return {"label": str(value), "predicates": []}
        data = dict(value)
        for alias in ("all", "conditions", "criteria"):
            if alias in data and "predicates" not in data:
                data["predicates"] = data[alias]
        return data


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
    qualification_paths: list[QualificationPath] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_shape(cls, value: Any) -> Any:
        """Conservatively accept common provider schema drift.

        This only renames fields and wraps explicitly supplied alternatives;
        it does not infer qualifications from arbitrary prose.
        """
        if isinstance(value, str):
            return {"text": value}
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for alias in ("description", "requirement", "name"):
            if alias in data and "text" not in data:
                data["text"] = data[alias]
                break
        if "type" in data and "requirement_type" not in data:
            data["requirement_type"] = data["type"]
        if "priority" in data and "importance" not in data:
            data["importance"] = str(data["priority"]).upper()
        if "importance" in data:
            importance = str(data["importance"]).upper()
            data["importance"] = importance or "MEDIUM"
        category_aliases = {
            "skill": "technical_skill", "skills": "technical_skill",
            "technical": "technical_skill", "qualifications": "functional",
            "skill_or_tool": "technical_skill", "tools": "technical_skill",
        }
        raw_category = str(data.get("category", "functional")).lower()
        category = category_aliases.get(raw_category, raw_category)
        data["category"] = category or "functional"
        type_aliases = {"required": "mandatory", "essential": "mandatory", "desirable": "preferred"}
        raw_req_type = str(data.get("requirement_type", "mandatory")).lower()
        req_type = type_aliases.get(raw_req_type, raw_req_type)
        data["requirement_type"] = req_type or "mandatory"
        if "alternative_paths" in data and "qualification_paths" not in data:
            data["qualification_paths"] = data["alternative_paths"]
        if "qualification_paths" not in data:
            alternatives = data.get("any_of") or data.get("alternatives")
            if isinstance(alternatives, list):
                data["qualification_paths"] = [
                    item if isinstance(item, dict) and "predicates" in item else {"predicates": item if isinstance(item, list) else [item]}
                    for item in alternatives
                ]
        return data


class JDKeyword(BaseModel):
    term: str
    classification: Literal[
        "technical", "functional", "clinical", "domain", "organizational",
        "behavioral", "tools", "methodologies", "certifications", "uncategorized",
    ] = "uncategorized"

    @model_validator(mode="before")
    @classmethod
    def _normalize_shape(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"term": value}
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "term" not in data:
            data["term"] = data.get("keyword") or data.get("name") or ""
        classification_aliases = {
            "technical_skill": "technical",
            "skill": "uncategorized",
            "methodology": "methodologies",
            "certification": "certifications",
            "tool": "tools",
        }
        raw_classification = str(data.get("classification") or "").lower()
        if raw_classification:
            data["classification"] = classification_aliases.get(
                raw_classification,
                raw_classification,
            )
        if not data.get("classification"):
            data["classification"] = "uncategorized"
        return data


class JDAnalysisResult(BaseModel):
    position: JDPositionInfo = Field(default_factory=JDPositionInfo)
    requirements: list[JDRequirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    competencies: list[str] = Field(default_factory=list)
    keywords: list[JDKeyword] = Field(default_factory=list)
    summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "position" not in data:
            data["position"] = data.get("position_info") or data.get("job") or {}
        if "requirements" not in data:
            buckets = []
            for key, req_type in (
                ("mandatory_requirements", "mandatory"),
                ("required_qualifications", "mandatory"),
                ("preferred_requirements", "preferred"),
                ("preferred_qualifications", "preferred"),
            ):
                for item in data.get(key, []) or []:
                    normalized = dict(item) if isinstance(item, dict) else {"text": str(item)}
                    normalized.setdefault("requirement_type", req_type)
                    buckets.append(normalized)
            data["requirements"] = buckets
        elif isinstance(data["requirements"], dict):
            flattened = []
            for key, items in data["requirements"].items():
                req_type = "preferred" if "prefer" in key.lower() or "desir" in key.lower() else "mandatory"
                for item in items or []:
                    normalized = dict(item) if isinstance(item, dict) else {"text": str(item)}
                    normalized.setdefault("requirement_type", req_type)
                    flattened.append(normalized)
            data["requirements"] = flattened
        if isinstance(data.get("keywords"), list):
            data["keywords"] = [
                {"term": item} if isinstance(item, str) else item
                for item in data["keywords"]
            ]
        return data

    @field_validator("responsibilities", "competencies", mode="before")
    @classmethod
    def _normalize_str_lists(cls, value: Any) -> list[str]:
        return _coerce_str_list(value)


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
    qualification_evaluation: dict[str, Any] = Field(default_factory=dict)


class MatchingResult(BaseModel):
    matches: list[RequirementMatchResult] = Field(default_factory=list)


# ── Scoring (§18-19) — qualitative overlay only; numbers are computed ────────


class ScoreNarrative(BaseModel):
    """Qualitative overlay ONLY — strong/partial/gap/transferable lists are
    derived deterministically by the scoring engine from the match statuses,
    so the narrative can never contradict the computed numbers."""

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
    text: str = Field(description="Visible bullet prose. Never include UUIDs or 'Evidence:' labels.")
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Knowledge-base entity ids for the View Evidence UI. Not shown in the CV body.",
    )

    @model_validator(mode="after")
    def _strip_inline_evidence(self):
        self.text, self.evidence_ids = sanitize_prose_field(self.text, self.evidence_ids)
        return self


class CVExperienceEntry(BaseModel):
    experience_id: str = Field(default="", description="Id of the source experience in the knowledge base.")
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

    @model_validator(mode="after")
    def _strip_summary_evidence(self):
        self.summary, self.summary_evidence_ids = sanitize_prose_field(
            self.summary, self.summary_evidence_ids
        )
        return self


class CoverLetterParagraph(BaseModel):
    text: str = Field(
        description="Letter prose the employer reads. Never include UUIDs, evidence ids, or 'Evidence:' labels."
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Knowledge-base entity ids supporting claims in this paragraph. Used only by View Evidence.",
    )

    @model_validator(mode="after")
    def _strip_inline_evidence(self):
        self.text, self.evidence_ids = sanitize_prose_field(self.text, self.evidence_ids)
        return self


class GeneratedCoverLetter(BaseModel):
    subject: str = ""
    salutation: str = "Dear Hiring Manager,"
    paragraphs: list[CoverLetterParagraph] = Field(default_factory=list)
    closing: str = "Sincerely,"

    @field_validator("paragraphs", mode="before")
    @classmethod
    def _coerce_paragraphs(cls, value):
        if not isinstance(value, list):
            return value
        coerced = []
        for item in value:
            if isinstance(item, str):
                coerced.append({"text": item, "evidence_ids": []})
            else:
                coerced.append(item)
        return coerced


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

    @field_validator("ats_score", "keyword_coverage", "requirement_coverage", mode="before")
    @classmethod
    def _normalize_unit_interval(cls, value: Any) -> float:
        """LLMs sometimes return 0-100 despite the 0..1 contract — normalize
        and clamp so an out-of-scale value can never reach the dashboard."""
        try:
            f = float(value)
        except (TypeError, ValueError):
            return 0.0
        if f > 1.0:
            f = f / 100.0
        return min(max(f, 0.0), 1.0)


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


class CoachAnswer(BaseModel):
    answer: str = ""
    citation_ids: list[str] = Field(default_factory=list)
    refused: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalize_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "answer" not in data:
            data["answer"] = data.get("text") or data.get("message") or ""
        ids = data.get("citation_ids") or data.get("citations") or data.get("evidence_ids") or []
        if isinstance(ids, str):
            ids = [ids]
        cleaned: list[str] = []
        for item in ids:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
            elif isinstance(item, dict):
                eid = item.get("entity_id") or item.get("id") or ""
                if eid:
                    cleaned.append(str(eid).strip())
        data["citation_ids"] = cleaned
        return data

