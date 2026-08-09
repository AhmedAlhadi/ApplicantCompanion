"""Application, generated documents, versioning and templates (§22-31, §51)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin, UUIDPrimaryKeyMixin, SoftDeleteMixin, utcnow

APPLICATION_STATUSES = ("draft", "ready", "submitted", "interview", "rejected", "offer", "withdrawn")


class ApplicationStrategy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "application_strategies"

    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), unique=True, index=True)
    positioning: Mapped[str] = mapped_column(Text, default="")
    priority_experience: Mapped[list] = mapped_column(JSON, default=list)
    priority_skills: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    evidence_plan: Mapped[list] = mapped_column(JSON, default=list)
    de_emphasis: Mapped[list] = mapped_column(JSON, default=list)
    concerns: Mapped[list] = mapped_column(JSON, default=list)
    messaging_strategy: Mapped[str] = mapped_column(Text, default="")


class Application(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "applications"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    fit_score_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    ats_score_snapshot: Mapped[float | None] = mapped_column(Float, nullable=True)
    applied_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str] = mapped_column(String(64), default="")
    interview_status: Mapped[str] = mapped_column(String(64), default="")
    user_notes: Mapped[str] = mapped_column(Text, default="")
    lessons_learned: Mapped[str] = mapped_column(Text, default="")
    skills_emphasized: Mapped[list] = mapped_column(JSON, default=list)
    keywords_used: Mapped[list] = mapped_column(JSON, default=list)
    user_approved: Mapped[bool] = mapped_column(Boolean, default=False)  # human-in-the-loop (§6)


class CV(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cvs"

    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(64), default="minimal-ats")
    title: Mapped[str] = mapped_column(String(500), default="CV")


class CoverLetter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cover_letters"

    application_id: Mapped[str] = mapped_column(String(36), ForeignKey("applications.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(64), default="minimal-ats")
    title: Mapped[str] = mapped_column(String(500), default="Cover Letter")


class DocumentVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable version of a generated document (§29-30)."""

    __tablename__ = "document_versions"

    document_type: Mapped[str] = mapped_column(String(16), index=True)  # cv|cover_letter
    document_id: Mapped[str] = mapped_column(String(36), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # structured document
    rendered_text: Mapped[str] = mapped_column(Text, default="")
    template_key: Mapped[str] = mapped_column(String(64), default="minimal-ats")
    model: Mapped[str] = mapped_column(String(128), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    input_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    knowledge_base_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_results: Mapped[dict] = mapped_column(JSON, default=dict)
    ats_analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Template(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Data-driven document template (§28)."""

    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("key", "document_type", name="uq_template_key_type"),
    )

    key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(16), default="cv")  # cv|cover_letter
    description: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # config: metadata, typography, spacing, sections, colors, layout, rendering rules
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
