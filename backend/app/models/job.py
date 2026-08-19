"""Job intelligence entities (§10-19, §44, §51)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

JOB_STATUSES = ("draft", "analyzing", "analyzed", "failed")
MATCH_STATUSES = ("MATCHED", "PARTIALLY_MATCHED", "TRANSFERABLE", "NOT_MATCHED", "UNKNOWN")
IMPORTANCE_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(500), index=True)
    website: Mapped[str] = mapped_column(String(1000), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str] = mapped_column(String(255), default="")
    headquarters: Mapped[str] = mapped_column(String(255), default="")


class Job(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "jobs"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True)
    organization_name: Mapped[str] = mapped_column(String(500), default="")
    position_title: Mapped[str] = mapped_column(String(500), default="")
    department: Mapped[str] = mapped_column(String(500), default="")
    team: Mapped[str] = mapped_column(String(500), default="")
    grade_level: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(500), default="")
    contract_type: Mapped[str] = mapped_column(String(128), default="")
    duration: Mapped[str] = mapped_column(String(128), default="")
    deadline: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remote_policy: Mapped[str] = mapped_column(String(32), default="")  # remote|hybrid|on-site
    reporting_line: Mapped[str] = mapped_column(String(500), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="paste")  # paste|upload|url
    source_url: Mapped[str] = mapped_column(String(2000), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    raw_jd_text: Mapped[str] = mapped_column(Text, default="")
    jd_document_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("career_documents.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)  # JDAnalysisResult payload
    executive_summary: Mapped[str] = mapped_column(Text, default="")


class JobRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "job_requirements"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), index=True)
    category: Mapped[str] = mapped_column(String(64), default="functional")
    # education|experience|technical_skill|functional|domain|language|certification|
    # management|responsibility|competency|other
    requirement_type: Mapped[str] = mapped_column(String(32), default="mandatory")
    # mandatory|preferred|responsibility|competency
    text: Mapped[str] = mapped_column(Text)
    importance: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    # Alternative qualification routes: ANY path may qualify; every predicate
    # inside a path must qualify. Empty preserves legacy flat requirements.
    qualification_paths: Mapped[list] = mapped_column(JSON, default=list)


class OrganizationResearch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One researched claim about an organization (§12)."""

    __tablename__ = "organization_research"

    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default="general")
    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(2000), default="")
    source_type: Mapped[str] = mapped_column(String(64), default="other")
    publication_date: Mapped[str] = mapped_column(String(32), default="")
    confidence: Mapped[str] = mapped_column(String(16), default="LOW")  # HIGH|MEDIUM|LOW
    relevance_to_job: Mapped[str] = mapped_column(Text, default="")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Person(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A publicly identified professional relevant to a job (§13-14)."""

    __tablename__ = "persons"

    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(500), default="")
    confidence: Mapped[str] = mapped_column(String(16), default="LOW")  # HIGH|MEDIUM|LOW
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    profile_url: Mapped[str] = mapped_column(String(2000), default="")


class HiringContext(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "hiring_contexts"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), unique=True, index=True)
    hiring_manager_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("persons.id"), nullable=True)
    recruiter_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("persons.id"), nullable=True)
    identified: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    team_insights: Mapped[list] = mapped_column(JSON, default=list)


class RequirementMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Evidence-based match of one requirement (§15-17, §38)."""

    __tablename__ = "requirement_matches"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), index=True)
    requirement_id: Mapped[str] = mapped_column(String(36), ForeignKey("job_requirements.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    match_kind: Mapped[str] = mapped_column(String(32), default="direct")  # direct|transferable
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    # [{entity_type, entity_id, evidence, source}]
    qualification_evaluation: Mapped[dict] = mapped_column(JSON, default=dict)
    # Deterministic per-path/per-predicate result retained for auditability.


class JobScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Transparent, programmatically calculated score (§18-21)."""

    __tablename__ = "job_scores"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    category_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    threshold: Mapped[float] = mapped_column(Float, default=0.8)
    recommendation: Mapped[str] = mapped_column(String(32), default="")  # strong_fit|below_threshold
    unknown_count: Mapped[int] = mapped_column(default=0)
    strong_matches: Mapped[list] = mapped_column(JSON, default=list)
    partial_matches: Mapped[list] = mapped_column(JSON, default=list)
    gaps: Mapped[list] = mapped_column(JSON, default=list)
    transferable: Mapped[list] = mapped_column(JSON, default=list)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    advantages: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default="")


class ResearchSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cached research source to avoid redundant fetching (§44)."""

    __tablename__ = "research_sources"

    url: Mapped[str] = mapped_column(String(2000), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    title: Mapped[str] = mapped_column(String(1000), default="")
    domain: Mapped[str] = mapped_column(String(255), default="", index=True)
    source_type: Mapped[str] = mapped_column(String(64), default="other")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[str] = mapped_column(String(32), default="")
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    credibility_score: Mapped[float] = mapped_column(Float, default=0.0)
    content_excerpt: Mapped[str] = mapped_column(Text, default="")
