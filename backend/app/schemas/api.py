"""Request/response schemas for the REST API (§52)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Auth ─────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class GoogleAuthRequest(BaseModel):
    id_token: str


class AuthConfigResponse(BaseModel):
    google_client_id: str
    registration_open: bool


class AdminUserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str = ""
    is_admin: bool = False


class AdminUserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=8)


# ── Career knowledge ─────────────────────────────────────────────────────────


class ProfileIn(BaseModel):
    full_name: str = ""
    headline: str = ""
    summary: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: dict = Field(default_factory=dict)
    preferred_positioning: str = ""
    career_narratives: list[dict] = Field(default_factory=list)


class ExperienceIn(BaseModel):
    organization: str
    job_title: str
    start_date: str | None = None
    end_date: str | None = None
    employment_type: str = ""
    location: str = ""
    description: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    leadership: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    verification_status: str = "unverified"
    confidence: float = 0.5


class AchievementIn(BaseModel):
    experience_id: str | None = None
    project_id: str | None = None
    education_id: str | None = None
    title: str = ""
    description: str
    quantified_result: str = ""
    skills: list[str] = Field(default_factory=list)
    verification_status: str = "unverified"
    confidence: float = 0.5


class ProjectIn(BaseModel):
    experience_id: str | None = None
    name: str
    description: str = ""
    role: str = ""
    technologies: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    verification_status: str = "unverified"


class SkillIn(BaseModel):
    name: str
    category: str = "technical"
    proficiency: str = ""
    years_experience: float | None = None
    verification_status: str = "unverified"


class EducationIn(BaseModel):
    institution: str
    degree: str = ""
    field_of_study: str = ""
    start_date: str | None = None
    end_date: str | None = None
    grade: str = ""
    description: str = ""
    verification_status: str = "unverified"


class CertificationIn(BaseModel):
    name: str
    issuer: str = ""
    issue_date: str | None = None
    expiry_date: str | None = None
    credential_id: str = ""
    url: str = ""
    verification_status: str = "unverified"


class LanguageIn(BaseModel):
    language: str
    proficiency: str = ""
    is_native: bool = False


class PublicationIn(BaseModel):
    title: str
    publisher: str = ""
    publication_date: str | None = None
    url: str = ""
    description: str = ""
    authors: list[str] = Field(default_factory=list)


class NarrativeIn(BaseModel):
    title: str = ""
    content: str


class KnowledgeContextIn(BaseModel):
    experience_id: str | None = None
    project_id: str | None = None
    achievement_id: str | None = None
    education_id: str | None = None
    acquisition_mode: str = "acquired_through_role"
    how_acquired: str = ""
    how_applied: str = ""
    verification_status: str = "unverified"
    confidence: float = 0.5


class KnowledgeIn(BaseModel):
    name: str
    canonical_name: str = ""
    kind: str = "domain"
    summary: str = ""
    depth: str = "applied"
    years_experience: float | None = None
    synonyms: list[str] = Field(default_factory=list)
    verification_status: str = "unverified"
    confidence: float = 0.5
    contexts: list[KnowledgeContextIn] = Field(default_factory=list)


class IngestTextRequest(BaseModel):
    """Free-form text ingestion into the career knowledge base (§6)."""

    text: str
    doc_type: str = "notes"
    filename: str = "pasted-text.txt"


class ReconciliationDecisionIn(BaseModel):
    proposal_id: str
    action: Literal["create", "merge"] = "create"
    target_id: str | None = None


class ConfirmPendingIngestionRequest(BaseModel):
    """User-confirmed merge/create decisions for a pending ingestion review."""

    decisions: list[ReconciliationDecisionIn] = Field(default_factory=list)


# ── Jobs ─────────────────────────────────────────────────────────────────────


class JobCreate(BaseModel):
    raw_jd_text: str = ""
    source_url: str = ""
    source_type: Literal["paste", "upload", "url"] = "paste"
    organization_name: str = ""
    position_title: str = ""
    location: str = ""
    deadline: str | None = None
    notes: str = ""


class JobUpdate(BaseModel):
    organization_name: str | None = None
    position_title: str | None = None
    location: str | None = None
    deadline: str | None = None
    notes: str | None = None
    status: str | None = None
    department: str | None = None
    team: str | None = None
    grade_level: str | None = None
    contract_type: str | None = None
    duration: str | None = None
    remote_policy: str | None = None
    reporting_line: str | None = None
    source_url: str | None = None
    raw_jd_text: str | None = None


class AnalyzeRequest(BaseModel):
    include_research: bool = True


# ── Applications ─────────────────────────────────────────────────────────────


class ApplicationCreate(BaseModel):
    job_id: str


class ApplicationUpdate(BaseModel):
    status: str | None = None
    user_notes: str | None = None
    lessons_learned: str | None = None
    outcome: str | None = None
    interview_status: str | None = None
    applied_at: str | None = None


class GenerateRequest(BaseModel):
    template_key: str | None = None
    model_override: str | None = None  # "provider:model"


class DecideRequest(BaseModel):
    decision: Literal["continue", "cancel", "review_gaps"]


# ── Documents ────────────────────────────────────────────────────────────────


class DocumentUpdateRequest(BaseModel):
    content: dict
    template_key: str | None = None


class RegenerateSectionRequest(BaseModel):
    section: str  # summary | experience | skills | paragraphs | ...
    instruction: str = ""


# ── Settings ─────────────────────────────────────────────────────────────────


class SettingsUpdate(BaseModel):
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    scoring_weights: dict[str, float] | None = None
    model_routing: dict[str, str] | None = None
    ui_language: Literal["ar", "en"] | None = None
    content_language: Literal["ar", "en"] | None = None
    default_cv_template: str | None = None
    default_cover_letter_template: str | None = None


class ModelTestRequest(BaseModel):
    provider: str
    model: str = ""
