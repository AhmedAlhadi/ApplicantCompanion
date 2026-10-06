"""Resolve the plan a user can actually use, including overrides."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..entitlements.constants import (
    ALL_FEATURES,
    ALL_METERS,
    DEFAULT_PLAN_CODE,
    SEEDED_PLANS,
    USABLE_STATUSES,
)
from ..models.entitlements import CreditGrant, EntitlementOverride, Plan, PlanVersion, Subscription
from ..models.user import User
from .usage_errors import EntitlementError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def next_month(start: datetime) -> datetime:
    month = start.month + 1
    year = start.year + (1 if month == 13 else 0)
    month = 1 if month == 13 else month
    return start.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def period_bounds(moment: datetime | None = None) -> tuple[str, datetime, datetime]:
    moment = aware(moment) or utcnow()
    start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m"), start, next_month(start)


@dataclass
class EffectiveEntitlement:
    user_id: str
    subscription: Subscription | None
    plan: Plan | None
    version: PlanVersion | None
    usable: bool
    features: dict[str, bool] = field(default_factory=dict)
    limits: dict[str, int | None] = field(default_factory=dict)
    template_keys: list[str] = field(default_factory=list)
    priority: int = 0
    period_key: str = ""
    period_start: datetime | None = None
    period_end: datetime | None = None
    rollover_caps: dict[str, int] = field(default_factory=dict)

    @property
    def plan_code(self) -> str:
        return self.plan.code if self.plan else ""

    @property
    def plan_name(self) -> str:
        return self.plan.display_name if self.plan else ""


class EntitlementsService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_catalog(self) -> None:
        for spec in SEEDED_PLANS:
            plan = self.db.query(Plan).filter(Plan.code == spec["code"]).one_or_none()
            if plan is None:
                plan = Plan(code=spec["code"], display_name=spec["display_name"], status="published")
                self.db.add(plan)
                self.db.flush()
            version = (
                self.db.query(PlanVersion)
                .filter(PlanVersion.plan_id == plan.id, PlanVersion.version_number == 1)
                .one_or_none()
            )
            if version is None:
                version = PlanVersion(
                    plan_id=plan.id,
                    version_number=1,
                    limits=dict(spec["limits"]),
                    rollover_caps=dict(spec["rollover_caps"]),
                    features=dict(spec["features"]),
                    template_keys=list(spec["template_keys"]),
                    priority=spec["priority"],
                    published_at=utcnow(),
                    notes="Seeded catalog",
                )
                self.db.add(version)
                self.db.flush()
            if not plan.current_version_id:
                plan.current_version_id = version.id
                plan.status = "published"
        self.db.flush()

    def backfill_subscriptions(self, plan_code: str = DEFAULT_PLAN_CODE) -> int:
        self.ensure_catalog()
        assigned = 0
        users = self.db.query(User).filter(User.is_deleted == False).all()  # noqa: E712
        for user in users:
            existing = (
                self.db.query(Subscription)
                .filter(
                    Subscription.user_id == user.id,
                    Subscription.status.in_(("trialing", "active", "past_due", "cancelled")),
                )
                .first()
            )
            if existing:
                continue
            self.assign(user.id, plan_code=plan_code, notes="Default plan")
            assigned += 1
        return assigned

    def assign(
        self,
        user_id: str,
        *,
        plan_code: str | None = None,
        plan_version_id: str | None = None,
        status: str = "active",
        period_end: datetime | None = None,
        grace_until: datetime | None = None,
        notes: str = "",
        assigned_by: str | None = None,
    ) -> Subscription:
        self.ensure_catalog()
        version = self._resolve_version(plan_code, plan_version_id)
        _, period_start, default_end = period_bounds()
        for current in (
            self.db.query(Subscription)
            .filter(Subscription.user_id == user_id, Subscription.status.in_(("trialing", "active", "past_due")))
            .all()
        ):
            current.status = "expired"
        sub = Subscription(
            user_id=user_id,
            plan_id=version.plan_id,
            plan_version_id=version.id,
            status=status,
            current_period_start=period_start,
            current_period_end=aware(period_end) or default_end,
            grace_until=aware(grace_until),
            notes=notes,
            assigned_by=assigned_by,
        )
        self.db.add(sub)
        self.db.flush()
        return sub

    def resolve(self, user_id: str) -> EffectiveEntitlement:
        self.ensure_catalog()
        now = utcnow()
        period_key, period_start, period_end = period_bounds(now)
        sub = (
            self.db.query(Subscription)
            .filter(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .first()
        )
        if sub is None:
            return EffectiveEntitlement(
                user_id=user_id,
                subscription=None,
                plan=None,
                version=None,
                usable=False,
                period_key=period_key,
                period_start=period_start,
                period_end=period_end,
            )
        plan = self.db.get(Plan, sub.plan_id)
        version = self.db.get(PlanVersion, sub.plan_version_id)
        features = {key: bool((version.features or {}).get(key)) for key in ALL_FEATURES} if version else {}
        limits: dict[str, int | None] = {}
        if version:
            for meter in ALL_METERS:
                raw = (version.limits or {}).get(meter)
                limits[meter] = None if raw is None else int(raw)
        for override in self._active_overrides(user_id, now):
            if override.feature_key and override.enabled is not None:
                features[override.feature_key] = bool(override.enabled)
            if override.meter and override.limit_value is not None:
                limits[override.meter] = int(override.limit_value)
        return EffectiveEntitlement(
            user_id=user_id,
            subscription=sub,
            plan=plan,
            version=version,
            usable=self.subscription_usable(sub, now),
            features=features,
            limits=limits,
            template_keys=list(version.template_keys or []) if version else [],
            priority=int(version.priority or 0) if version else 0,
            period_key=period_key,
            period_start=period_start,
            period_end=period_end,
            rollover_caps={k: int(v) for k, v in (version.rollover_caps or {}).items()} if version else {},
        )

    def require_usable(self, user_id: str) -> EffectiveEntitlement:
        effective = self.resolve(user_id)
        if not effective.usable:
            raise EntitlementError(
                "SUBSCRIPTION_INACTIVE",
                message="This account does not have an active plan.",
                plan=effective.plan_code,
                status=effective.subscription.status if effective.subscription else None,
            )
        return effective

    def require_feature(self, user_id: str, feature: str) -> EffectiveEntitlement:
        effective = self.require_usable(user_id)
        if not effective.features.get(feature):
            raise EntitlementError(
                "FEATURE_NOT_AVAILABLE",
                status_code=403,
                message="This feature is not included in the current plan.",
                feature=feature,
                plan=effective.plan_code,
            )
        return effective

    def require_template(self, user_id: str, template_key: str | None) -> EffectiveEntitlement:
        effective = self.require_usable(user_id)
        if template_key and template_key not in set(effective.template_keys):
            raise EntitlementError(
                "FEATURE_NOT_AVAILABLE",
                status_code=403,
                message="This template is not included in the current plan.",
                feature=f"template:{template_key}",
                plan=effective.plan_code,
            )
        return effective

    @staticmethod
    def subscription_usable(sub: Subscription, now: datetime | None = None) -> bool:
        now = aware(now) or utcnow()
        period_end = aware(sub.current_period_end)
        grace = aware(sub.grace_until)
        if sub.status in USABLE_STATUSES:
            return period_end is None or now < period_end
        if sub.status == "past_due":
            return grace is not None and now < grace
        if sub.status == "cancelled":
            return period_end is not None and now < period_end
        return False

    def active_credits(self, user_id: str, meter: str, now: datetime | None = None) -> list[CreditGrant]:
        now = aware(now) or utcnow()
        rows = (
            self.db.query(CreditGrant)
            .filter(
                CreditGrant.user_id == user_id,
                CreditGrant.meter == meter,
                CreditGrant.revoked == False,  # noqa: E712
                CreditGrant.remaining > 0,
            )
            .all()
        )
        usable = []
        for row in rows:
            expires = aware(row.expires_at)
            if expires is not None and expires <= now:
                continue
            usable.append(row)
        usable.sort(key=lambda row: aware(row.expires_at) or datetime.max.replace(tzinfo=timezone.utc))
        return usable

    def _active_overrides(self, user_id: str, now: datetime) -> list[EntitlementOverride]:
        rows = (
            self.db.query(EntitlementOverride)
            .filter(EntitlementOverride.user_id == user_id, EntitlementOverride.revoked == False)  # noqa: E712
            .all()
        )
        active = []
        for row in rows:
            expires = aware(row.expires_at)
            if expires is not None and expires <= now:
                continue
            active.append(row)
        return active

    def _resolve_version(self, plan_code: str | None, plan_version_id: str | None) -> PlanVersion:
        if plan_version_id:
            version = self.db.get(PlanVersion, plan_version_id)
            if version is None or version.published_at is None:
                raise EntitlementError(
                    "PLAN_VERSION_NOT_FOUND",
                    status_code=404,
                    message="Published plan version not found.",
                )
            return version
        plan = self.db.query(Plan).filter(Plan.code == (plan_code or DEFAULT_PLAN_CODE)).one_or_none()
        if plan is None or plan.status == "archived" or not plan.current_version_id:
            raise EntitlementError("PLAN_NOT_FOUND", status_code=404, message="Plan not found.")
        version = self.db.get(PlanVersion, plan.current_version_id)
        if version is None:
            raise EntitlementError("PLAN_VERSION_NOT_FOUND", status_code=404, message="Plan version not found.")
        return version
