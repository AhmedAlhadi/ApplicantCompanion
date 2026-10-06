"""Agent execution logging and workflow orchestration state (§39-40)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow

EXECUTION_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED")


class AgentExecution(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_executions"

    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True, index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    workflow_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workflow_runs.id"), nullable=True, index=True)
    usage_reservation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(128), index=True)
    prompt_name: Mapped[str] = mapped_column(String(128), default="")
    prompt_version: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    input_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    output_summary: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks the orchestration pipeline stage-by-stage (§39, §53)."""

    __tablename__ = "workflow_runs"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True, index=True)
    application_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("applications.id"), nullable=True, index=True)
    workflow_type: Mapped[str] = mapped_column(String(64), default="job_analysis")  # job_analysis|document_generation
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    current_stage: Mapped[str] = mapped_column(String(64), default="")
    stages: Mapped[list] = mapped_column(JSON, default=list)
    # [{name, status, started_at, ended_at, error}]
    error: Mapped[str] = mapped_column(Text, default="")
    usage_reservation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
