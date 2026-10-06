"""Admin plan, subscription, credit, and usage monitoring APIs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..entitlements.constants import ALL_FEATURES, ALL_METERS, ALL_TEMPLATE_KEYS, PERIODIC_METERS
from ..models import (
    AgentExecution,
    CreditGrant,
    EntitlementOverride,
    Plan,
    PlanVersion,
    Subscription,
    UsageBucket,
    UsageEvent,
    UsageReservation,
    User,
)
from ..schemas.entitlements import CreditGrantCreate, OverrideCreate, PlanCreate, PlanUpdate, PlanVersionDraft, SubscriptionAssign
from ..security.auth import audit, require_admin
from ..services.entitlements import EntitlementsService, utcnow
from ..services.serializers import to_dict
from ..services.usage import UsageService
from ..services.usage_errors import EntitlementError

router = APIRouter(prefix="/api/admin", tags=["admin-entitlements"])


def _plan_payload(db: Session, plan: Plan) -> dict:
    versions = (
        db.query(PlanVersion)
        .filter(PlanVersion.plan_id == plan.id)
        .order_by(PlanVersion.version_number.desc())
        .all()
    )
    subscribers = (
        db.query(Subscription)
        .filter(Subscription.plan_id == plan.id, Subscription.status.in_(("trialing", "active", "past_due")))
        .count()
    )
    data = to_dict(plan)
    data["versions"] = [to_dict(version) for version in versions]
    data["subscriber_count"] = subscribers
    return data


def _get_plan(db: Session, plan_id: str) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    return plan


@router.get("/plans")
def list_plans(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    EntitlementsService(db).ensure_catalog()
    db.commit()
    plans = db.query(Plan).order_by(Plan.display_name.asc()).all()
    return [_plan_payload(db, plan) for plan in plans]


@router.post("/plans", status_code=201)
def create_plan(payload: PlanCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    code = payload.code.strip().lower()
    if db.query(Plan).filter(Plan.code == code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Plan code already exists")
    plan = Plan(code=code, display_name=payload.display_name.strip(), status="draft")
    db.add(plan)
    db.flush()
    version = PlanVersion(
        plan_id=plan.id,
        version_number=1,
        limits={meter: 0 for meter in ALL_METERS},
        rollover_caps={meter: 0 for meter in PERIODIC_METERS},
        features={feature: False for feature in ALL_FEATURES},
        template_keys=["minimal-ats"],
        priority=0,
    )
    db.add(version)
    db.flush()
    audit(db, admin, "admin.plan.create", "plan", plan.id, {"code": code}, request)
    db.commit()
    return _plan_payload(db, plan)


@router.get("/plans/{plan_id}")
def get_plan(plan_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    return _plan_payload(db, _get_plan(db, plan_id))


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: str, payload: PlanUpdate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    plan = _get_plan(db, plan_id)
    if payload.display_name is not None:
        plan.display_name = payload.display_name.strip()
    if payload.status is not None:
        if payload.status not in ("draft", "published", "archived"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid plan status")
        plan.status = payload.status
    audit(db, admin, "admin.plan.update", "plan", plan.id, payload.model_dump(exclude_none=True), request)
    db.commit()
    return _plan_payload(db, plan)


@router.post("/plans/{plan_id}/versions", status_code=201)
def create_version(plan_id: str, payload: PlanVersionDraft, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    plan = _get_plan(db, plan_id)
    latest = (
        db.query(PlanVersion)
        .filter(PlanVersion.plan_id == plan.id)
        .order_by(PlanVersion.version_number.desc())
        .first()
    )
    version = PlanVersion(
        plan_id=plan.id,
        version_number=(latest.version_number + 1) if latest else 1,
        limits=payload.limits or (latest.limits if latest else {}),
        rollover_caps=payload.rollover_caps or (latest.rollover_caps if latest else {}),
        features=payload.features or (latest.features if latest else {}),
        template_keys=payload.template_keys or (latest.template_keys if latest else []),
        priority=payload.priority if payload.priority else (latest.priority if latest else 0),
        notes=payload.notes,
    )
    unknown = [key for key in version.template_keys if key not in ALL_TEMPLATE_KEYS]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown templates: {', '.join(unknown)}")
    db.add(version)
    db.flush()
    plan.status = "draft"
    audit(db, admin, "admin.plan.version.create", "plan_version", version.id, {"plan_id": plan.id}, request)
    db.commit()
    return to_dict(version)


@router.patch("/plans/{plan_id}/versions/{version_id}")
def update_version(
    plan_id: str,
    version_id: str,
    payload: PlanVersionDraft,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    version = db.get(PlanVersion, version_id)
    if version is None or version.plan_id != plan_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan version not found")
    if version.published_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Published plan versions are immutable")
    if payload.limits:
        version.limits = payload.limits
    if payload.rollover_caps:
        version.rollover_caps = payload.rollover_caps
    if payload.features:
        version.features = payload.features
    if payload.template_keys:
        version.template_keys = payload.template_keys
    version.priority = payload.priority
    version.notes = payload.notes
    audit(db, admin, "admin.plan.version.update", "plan_version", version.id, request=request)
    db.commit()
    return to_dict(version)


@router.post("/plans/{plan_id}/versions/{version_id}/publish")
def publish_version(plan_id: str, version_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    plan = _get_plan(db, plan_id)
    version = db.get(PlanVersion, version_id)
    if version is None or version.plan_id != plan.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan version not found")
    version.published_at = version.published_at or utcnow()
    plan.current_version_id = version.id
    plan.status = "published"
    audit(db, admin, "admin.plan.publish", "plan_version", version.id, {"plan_id": plan.id}, request)
    db.commit()
    return _plan_payload(db, plan)


@router.post("/plans/{plan_id}/archive")
def archive_plan(plan_id: str, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    plan = _get_plan(db, plan_id)
    plan.status = "archived"
    audit(db, admin, "admin.plan.archive", "plan", plan.id, request=request)
    db.commit()
    return _plan_payload(db, plan)


@router.get("/users/{user_id}/subscription")
def get_subscription(user_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UsageService(db).summary(user_id)


@router.post("/users/{user_id}/subscription")
def assign_subscription(
    user_id: str,
    payload: SubscriptionAssign,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if payload.status not in ("trialing", "active", "past_due", "cancelled", "expired"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid subscription status")
    try:
        sub = EntitlementsService(db).assign(
            user_id,
            plan_code=payload.plan_code,
            plan_version_id=payload.plan_version_id,
            status=payload.status,
            period_end=payload.period_end,
            grace_until=payload.grace_until,
            notes=payload.notes,
            assigned_by=admin.id,
        )
    except EntitlementError as exc:
        raise exc.as_http() from exc
    audit(db, admin, "admin.subscription.assign", "subscription", sub.id, payload.model_dump(mode="json"), request)
    db.commit()
    return UsageService(db).summary(user_id)


@router.post("/users/{user_id}/credits", status_code=201)
def grant_credits(user_id: str, payload: CreditGrantCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if payload.source not in ("admin_adjustment", "promotion", "payg"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid credit source")
    try:
        grant = UsageService(db).grant_credits(
            user_id,
            payload.meter,
            payload.quantity,
            source=payload.source,
            note=payload.note,
            expires_at=payload.expires_at,
            granted_by=admin.id,
        )
    except EntitlementError as exc:
        raise exc.as_http() from exc
    audit(db, admin, "admin.credits.grant", "credit_grant", grant.id, payload.model_dump(mode="json"), request)
    db.commit()
    return to_dict(grant)


@router.get("/users/{user_id}/credits")
def list_credits(user_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    rows = db.query(CreditGrant).filter(CreditGrant.user_id == user_id).order_by(CreditGrant.created_at.desc()).all()
    return [to_dict(row) for row in rows]


@router.post("/users/{user_id}/overrides", status_code=201)
def create_override(user_id: str, payload: OverrideCreate, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if not payload.feature_key and not payload.meter:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Override needs a feature or a meter")
    row = EntitlementOverride(
        user_id=user_id,
        feature_key=payload.feature_key,
        meter=payload.meter,
        enabled=payload.enabled,
        limit_value=payload.limit_value,
        expires_at=payload.expires_at,
        reason=payload.reason,
        created_by=admin.id,
    )
    db.add(row)
    db.flush()
    audit(db, admin, "admin.override.create", "entitlement_override", row.id, payload.model_dump(mode="json"), request)
    db.commit()
    return to_dict(row)


@router.get("/users/{user_id}/usage")
def user_usage(user_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    summary = UsageService(db).summary(user_id)
    summary["overrides"] = [
        to_dict(row)
        for row in db.query(EntitlementOverride)
        .filter(EntitlementOverride.user_id == user_id, EntitlementOverride.revoked == False)  # noqa: E712
        .all()
    ]
    return summary


@router.get("/users/{user_id}/usage/events")
def user_usage_events(user_id: str, limit: int = 100, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == user_id)
        .order_by(UsageEvent.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [to_dict(row) for row in rows]


@router.get("/usage/stats")
def usage_stats(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    del admin
    EntitlementsService(db).ensure_catalog()
    now = datetime.now(timezone.utc)
    period_key = now.strftime("%Y-%m")
    by_plan: dict[str, int] = {}
    subs = (
        db.query(Subscription, Plan)
        .join(Plan, Plan.id == Subscription.plan_id)
        .filter(Subscription.status.in_(("trialing", "active", "past_due")))
        .all()
    )
    for _sub, plan in subs:
        by_plan[plan.code] = by_plan.get(plan.code, 0) + 1
    buckets = db.query(UsageBucket).filter(UsageBucket.period_key == period_key).all()
    by_meter: dict[str, dict] = {}
    near = []
    for bucket in buckets:
        entry = by_meter.setdefault(bucket.meter, {"consumed": 0, "reserved": 0})
        entry["consumed"] += int(bucket.consumed)
        entry["reserved"] += int(bucket.reserved)
        capacity = int(bucket.included) + int(bucket.rollover)
        if capacity and (int(bucket.consumed) + int(bucket.reserved)) / capacity >= 0.7:
            user = db.get(User, bucket.user_id)
            near.append({
                "user_id": bucket.user_id,
                "email": user.email if user else "",
                "meter": bucket.meter,
                "pct": round(100 * (int(bucket.consumed) + int(bucket.reserved)) / capacity),
            })
    stale_cutoff = now - timedelta(minutes=30)
    stale = (
        db.query(UsageReservation)
        .filter(UsageReservation.state == "reserved", UsageReservation.created_at < stale_cutoff)
        .count()
    )
    active_reservations = db.query(UsageReservation).filter(UsageReservation.state == "reserved").count()
    token_rows = db.query(AgentExecution.model, AgentExecution.token_usage).all()
    tokens_by_model: dict[str, int] = {}
    for model, usage in token_rows:
        amount = int((usage or {}).get("prompt_tokens") or 0) + int((usage or {}).get("completion_tokens") or 0)
        if amount:
            tokens_by_model[model or "unknown"] = tokens_by_model.get(model or "unknown", 0) + amount
    top = (
        db.query(UsageBucket.user_id, func.sum(UsageBucket.consumed))
        .filter(UsageBucket.period_key == period_key)
        .group_by(UsageBucket.user_id)
        .order_by(func.sum(UsageBucket.consumed).desc())
        .limit(10)
        .all()
    )
    top_consumers = []
    for user_id, consumed in top:
        user = db.get(User, user_id)
        top_consumers.append({"user_id": user_id, "email": user.email if user else "", "consumed": int(consumed or 0)})
    return {
        "period_key": period_key,
        "users_by_plan": by_plan,
        "usage_by_meter": by_meter,
        "users_near_limit": near,
        "stale_reservations": stale,
        "active_reservations": active_reservations,
        "tokens_by_model": tokens_by_model,
        "top_consumers": top_consumers,
    }


@router.get("/usage/events")
def usage_events(
    meter: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    del admin
    query = db.query(UsageEvent)
    if meter:
        query = query.filter(UsageEvent.meter == meter)
    if user_id:
        query = query.filter(UsageEvent.user_id == user_id)
    rows = query.order_by(UsageEvent.created_at.desc()).limit(min(limit, 200)).all()
    return [to_dict(row) for row in rows]
