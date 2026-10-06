"""Plans, subscriptions, credits, and the usage ledger."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plans"
    __table_args__ = (UniqueConstraint("code", name="uq_plan_code"),)

    code: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(32), default="published", index=True)  # draft|published|archived
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class PlanVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable once published_at is set. New commercial terms require a new row."""

    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("plan_id", "version_number", name="uq_plan_version_number"),)

    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    limits: Mapped[dict] = mapped_column(JSON, default=dict)
    rollover_caps: Mapped[dict] = mapped_column(JSON, default=dict)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    template_keys: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("plans.id"), index=True)
    plan_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("plan_versions.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grace_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    assigned_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)


class CreditGrant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_grants"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    meter: Mapped[str] = mapped_column(String(64), index=True)
    original: Mapped[int] = mapped_column(BigInteger, default=0)
    remaining: Mapped[int] = mapped_column(BigInteger, default=0)
    source: Mapped[str] = mapped_column(String(32), default="admin_adjustment")  # admin_adjustment|promotion|payg
    note: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    granted_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class EntitlementOverride(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entitlement_overrides"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    feature_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    limit_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class UsageBucket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Hot row for one user, meter, and calendar period."""

    __tablename__ = "usage_buckets"
    __table_args__ = (UniqueConstraint("user_id", "meter", "period_key", name="uq_usage_bucket"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    meter: Mapped[str] = mapped_column(String(64), index=True)
    period_key: Mapped[str] = mapped_column(String(7), index=True)  # YYYY-MM
    included: Mapped[int] = mapped_column(BigInteger, default=0)
    rollover: Mapped[int] = mapped_column(BigInteger, default=0)
    consumed: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, default=0)


class UsageReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_usage_reservation_key"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    meter: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(BigInteger, default=1)
    state: Mapped[str] = mapped_column(String(16), default="reserved", index=True)  # reserved|consumed|released
    period_key: Mapped[str] = mapped_column(String(7), default="")
    idempotency_key: Mapped[str] = mapped_column(String(255))
    reference_type: Mapped[str] = mapped_column(String(64), default="")
    reference_id: Mapped[str] = mapped_column(String(36), default="")
    allocations: Mapped[dict] = mapped_column(JSON, default=dict)  # {plan: n, rollover: n, grants: [{id, qty}]}
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")


class UsageEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only ledger. Corrections are new events, not edits."""

    __tablename__ = "usage_events"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    meter: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(BigInteger, default=0)
    state: Mapped[str] = mapped_column(String(16), index=True)  # reserved|consumed|released|grant|adjust
    period_key: Mapped[str] = mapped_column(String(7), default="")
    reservation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("usage_reservations.id"), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), default="")
    reference_type: Mapped[str] = mapped_column(String(64), default="")
    reference_id: Mapped[str] = mapped_column(String(36), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ApplicationPackUnlock(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One researched application pack for a job description revision."""

    __tablename__ = "application_pack_unlocks"
    __table_args__ = (UniqueConstraint("user_id", "job_id", "content_hash", name="uq_pack_unlock"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    reservation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("usage_reservations.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="reserved", index=True)  # reserved|active|released
