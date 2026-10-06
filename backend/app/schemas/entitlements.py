"""Request and response contracts for plans, subscriptions, and usage."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)


class PlanUpdate(BaseModel):
    display_name: str | None = None
    status: str | None = None


class PlanVersionDraft(BaseModel):
    limits: dict[str, int] = Field(default_factory=dict)
    rollover_caps: dict[str, int] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)
    template_keys: list[str] = Field(default_factory=list)
    priority: int = 0
    notes: str = ""


class SubscriptionAssign(BaseModel):
    plan_code: str | None = None
    plan_version_id: str | None = None
    status: str = "active"
    period_end: datetime | None = None
    grace_until: datetime | None = None
    notes: str = ""


class CreditGrantCreate(BaseModel):
    meter: str
    quantity: int = Field(gt=0)
    source: str = "admin_adjustment"
    note: str = ""
    expires_at: datetime | None = None


class OverrideCreate(BaseModel):
    feature_key: str | None = None
    meter: str | None = None
    enabled: bool | None = None
    limit_value: int | None = None
    expires_at: datetime | None = None
    reason: str = ""
