"""Career Knowledge Base entities (§2, §6, §51).

Every extracted fact keeps provenance through CareerEvidence and the
verification_status / confidence fields, so the system can always answer
"where did this claim come from?".
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, utcnow

VERIFICATION_STATUSES = ("verified", "unverified", "needs_review")


class CareerProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "career_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    headline: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    links: Mapped[dict] = mapped_column(JSON, default=dict)  # linkedin, portfolio, ...
    preferred_positioning: Mapped[str] = mapped_column(Text, default="")
    career_narratives: Mapped[list] = mapped_column(JSON, default=list)


class CareerDocument(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An uploaded source document (CV, JD, notes…) stored in object storage."""

    __tablename__ = "career_documents"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    doc_type: Mapped[str] = mapped_column(String(32), default="other")  # cv|cover_letter|jd|notes|other
    object_key: Mapped[str] = mapped_column(String(500), default="")
    size_bytes: Mapped[int] = mapped_column(default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    ingested: Mapped[bool] = mapped_column(default=False)


class Experience(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "experiences"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    organization: Mapped[str] = mapped_column(String(500), index=True)
    job_title: Mapped[str] = mapped_column(String(500))
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # null => current
    employment_type: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    responsibilities: Mapped[list] = mapped_column(JSON, default=list)
    technologies: Mapped[list] = mapped_column(JSON, default=list)
    domains: Mapped[list] = mapped_column(JSON, default=list)
    leadership: Mapped[list] = mapped_column(JSON, default=list)
    stakeholders: Mapped[list] = mapped_column(JSON, default=list)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("career_documents.id"), nullable=True
    )
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class Achievement(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Measurable outcome, typically linked to an experience, project, or education.

    Parent FKs are optional and independent: an achievement may hang off a role,
    a standalone/nested project, an academic context, or (rarely) none yet.
    """

    __tablename__ = "achievements"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    experience_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiences.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True)
    education_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("educations.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text)
    quantified_result: Mapped[str] = mapped_column(String(500), default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("career_documents.id"), nullable=True
    )
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class Project(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    experience_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("experiences.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(255), default="")
    technologies: Mapped[list] = mapped_column(JSON, default=list)
    outcomes: Mapped[list] = mapped_column(JSON, default=list)
    urls: Mapped[list] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class Skill(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Canonical skill with synonym mapping and normalization metadata (§7)."""

    __tablename__ = "skills"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))  # original wording
    canonical_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(64), default="technical")
    proficiency: Mapped[str] = mapped_column(String(64), default="")
    years_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    synonyms: Mapped[list] = mapped_column(JSON, default=list)
    evidence_count: Mapped[int] = mapped_column(default=0)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class Education(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "educations"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    institution: Mapped[str] = mapped_column(String(500))
    degree: Mapped[str] = mapped_column(String(255), default="")
    field_of_study: Mapped[str] = mapped_column(String(255), default="")
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    grade: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")


class Certification(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "certifications"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(500))
    issuer: Mapped[str] = mapped_column(String(500), default="")
    issue_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    expiry_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    credential_id: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")


class Language(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "languages"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    language: Mapped[str] = mapped_column(String(128))
    proficiency: Mapped[str] = mapped_column(String(64), default="")
    is_native: Mapped[bool] = mapped_column(default=False)


class Publication(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "publications"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(1000))
    publisher: Mapped[str] = mapped_column(String(500), default="")
    publication_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    url: Mapped[str] = mapped_column(String(1000), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    authors: Mapped[list] = mapped_column(JSON, default=list)


class CareerEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provenance ledger: links a claim to its source (§6 critical rule)."""

    __tablename__ = "career_evidence"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)  # experience|achievement|...
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    claim: Mapped[str] = mapped_column(Text)
    source_document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("career_documents.id"), nullable=True
    )
    source_page: Mapped[str] = mapped_column(String(32), default="")
    source_section: Mapped[str] = mapped_column(String(255), default="")
    original_text: Mapped[str] = mapped_column(Text, default="")
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)


class CareerNarrative(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Free-form user-provided career narratives (§2)."""

    __tablename__ = "career_narratives"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    content: Mapped[str] = mapped_column(Text)
    indexed: Mapped[bool] = mapped_column(default=False)


class PendingIngestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Human-in-the-loop reconciliation queue for extracted career entities.

    After extraction, experiences / projects / achievements are stored here as
    merge-or-create proposals until the user confirms them.
    """

    __tablename__ = "pending_ingestions"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("career_documents.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    # pending | completed | discarded
    proposals: Mapped[list] = mapped_column(JSON, default=list)
    # Auto-applied entity counts (skills, education, …) written immediately
    auto_applied: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
