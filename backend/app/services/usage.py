"""Atomic usage reservations, current-state limits, and usage summaries."""
from __future__ import annotations

import hashlib
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..entitlements.constants import (
    METER_ACTIVE_APPLICATIONS,
    METER_APPLICATION_PACK,
    METER_CAREER_DOCUMENTS,
    METER_CONCURRENT_WORKFLOWS,
    METER_FIT_CHECK,
    METER_SECTION_REGENERATION,
    METER_STORAGE_BYTES,
    PERIODIC_METERS,
)
from ..models.agent import WorkflowRun
from ..models.application import Application
from ..models.career import CareerDocument
from ..models.entitlements import (
    ApplicationPackUnlock,
    CreditGrant,
    Subscription,
    UsageBucket,
    UsageEvent,
    UsageReservation,
)
from ..models.job import Job
from .entitlements import EffectiveEntitlement, EntitlementsService, aware, period_bounds, utcnow
from .usage_errors import EntitlementError


def content_hash(text: str) -> str:
    normalized = " ".join((text or "").split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def previous_period_key(period_key: str) -> str:
    year, month = (int(part) for part in period_key.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


class UsageService:
    def __init__(self, db: Session):
        self.db = db
        self.entitlements = EntitlementsService(db)

    def summary(self, user_id: str) -> dict:
        effective = self.entitlements.resolve(user_id)
        meters = [self._periodic_summary(effective, meter) for meter in PERIODIC_METERS]
        for meter in (
            METER_CAREER_DOCUMENTS,
            METER_STORAGE_BYTES,
            METER_CONCURRENT_WORKFLOWS,
            METER_ACTIVE_APPLICATIONS,
        ):
            meters.append(self._state_summary(effective, meter))
        credits = []
        now = utcnow()
        grants = (
            self.db.query(CreditGrant)
            .filter(CreditGrant.user_id == user_id, CreditGrant.revoked == False)  # noqa: E712
            .order_by(CreditGrant.created_at.desc())
            .all()
        )
        for grant in grants:
            expires = aware(grant.expires_at)
            if expires is not None and expires <= now:
                continue
            credits.append({
                "id": grant.id,
                "meter": grant.meter,
                "original": int(grant.original),
                "remaining": int(grant.remaining),
                "source": grant.source,
                "note": grant.note,
                "expires_at": expires.isoformat() if expires else None,
                "granted_at": grant.created_at.isoformat() if grant.created_at else None,
            })
        sub = effective.subscription
        return {
            "subscription": None if sub is None else {
                "id": sub.id,
                "status": sub.status,
                "plan_code": effective.plan_code,
                "plan_name": effective.plan_name,
                "plan_version_id": sub.plan_version_id,
                "usable": effective.usable,
                "current_period_start": aware(sub.current_period_start).isoformat() if sub.current_period_start else None,
                "current_period_end": aware(sub.current_period_end).isoformat() if sub.current_period_end else None,
                "grace_until": aware(sub.grace_until).isoformat() if sub.grace_until else None,
            },
            "period_key": effective.period_key,
            "period_start": effective.period_start.isoformat() if effective.period_start else None,
            "period_end": effective.period_end.isoformat() if effective.period_end else None,
            "features": effective.features,
            "template_keys": effective.template_keys,
            "priority": effective.priority,
            "meters": meters,
            "credits": credits,
        }

    def open_fit_check(self, user_id: str, job: Job) -> tuple[UsageReservation, bool]:
        digest = content_hash(job.raw_jd_text)
        return self.open_reservation(
            user_id,
            METER_FIT_CHECK,
            idempotency_key=f"fit:{user_id}:{job.id}:{digest}",
            reference_type="job",
            reference_id=job.id,
        )

    def open_application_pack(self, user_id: str, job: Job) -> tuple[ApplicationPackUnlock, UsageReservation | None, bool]:
        digest = content_hash(job.raw_jd_text)
        unlock = (
            self.db.query(ApplicationPackUnlock)
            .filter(
                ApplicationPackUnlock.user_id == user_id,
                ApplicationPackUnlock.job_id == job.id,
                ApplicationPackUnlock.content_hash == digest,
            )
            .one_or_none()
        )
        if unlock and unlock.state == "active":
            reservation = self.db.get(UsageReservation, unlock.reservation_id) if unlock.reservation_id else None
            return unlock, reservation, False
        reservation, owned = self.open_reservation(
            user_id,
            METER_APPLICATION_PACK,
            idempotency_key=f"pack:{user_id}:{job.id}:{digest}",
            reference_type="job",
            reference_id=job.id,
        )
        if unlock is None:
            unlock = ApplicationPackUnlock(
                user_id=user_id,
                job_id=job.id,
                content_hash=digest,
                reservation_id=reservation.id,
                state="active" if reservation.state == "consumed" else "reserved",
            )
            self.db.add(unlock)
        else:
            unlock.reservation_id = reservation.id
            unlock.state = "active" if reservation.state == "consumed" else "reserved"
        self.db.flush()
        return unlock, reservation, owned and reservation.state == "reserved"

    def open_section_regeneration(
        self, user_id: str, document_id: str, section: str, version_number: int
    ) -> tuple[UsageReservation, bool]:
        return self.open_reservation(
            user_id,
            METER_SECTION_REGENERATION,
            idempotency_key=f"regen:{user_id}:{document_id}:{section}:{version_number}",
            reference_type="document",
            reference_id=document_id,
        )

    def open_reservation(
        self,
        user_id: str,
        meter: str,
        *,
        idempotency_key: str,
        reference_type: str,
        reference_id: str,
        quantity: int = 1,
    ) -> tuple[UsageReservation, bool]:
        existing = (
            self.db.query(UsageReservation)
            .filter(UsageReservation.idempotency_key == idempotency_key)
            .one_or_none()
        )
        if existing and existing.state == "consumed":
            return existing, False
        if existing and existing.state == "reserved":
            return existing, self._reservation_is_orphaned(existing)
        if existing and existing.state == "released":
            self._allocate(existing, user_id, meter, quantity, reference_type, reference_id)
            return existing, True
        reservation = UsageReservation(
            user_id=user_id,
            meter=meter,
            quantity=quantity,
            state="released",
            idempotency_key=idempotency_key,
            reference_type=reference_type,
            reference_id=reference_id,
            allocations={},
        )
        self.db.add(reservation)
        try:
            with self.db.begin_nested():
                self.db.flush()
        except IntegrityError:
            reservation = (
                self.db.query(UsageReservation)
                .filter(UsageReservation.idempotency_key == idempotency_key)
                .one()
            )
            if reservation.state == "consumed":
                return reservation, False
            if reservation.state == "reserved":
                return reservation, self._reservation_is_orphaned(reservation)
        self._allocate(reservation, user_id, meter, quantity, reference_type, reference_id)
        return reservation, True

    def commit(self, reservation_id: str | None) -> None:
        if not reservation_id:
            return
        reservation = self.db.get(UsageReservation, reservation_id)
        if reservation is None or reservation.state != "reserved":
            return
        bucket = self._lock_bucket(reservation.user_id, reservation.meter, reservation.period_key)
        plan_qty = int((reservation.allocations or {}).get("plan") or 0)
        if bucket is not None:
            bucket.reserved = max(0, int(bucket.reserved) - plan_qty)
            bucket.consumed = int(bucket.consumed) + plan_qty
        for item in (reservation.allocations or {}).get("grants") or []:
            grant = self.db.get(CreditGrant, item["id"])
            if grant is not None:
                grant.remaining = max(0, int(grant.remaining) - int(item["qty"]))
        reservation.state = "consumed"
        self._set_unlock_state(reservation.id, "active")
        self._event(reservation, "consumed")
        self.db.flush()

    def release(self, reservation_id: str | None, reason: str = "") -> None:
        if not reservation_id:
            return
        reservation = self.db.get(UsageReservation, reservation_id)
        if reservation is None or reservation.state != "reserved":
            return
        bucket = self._lock_bucket(reservation.user_id, reservation.meter, reservation.period_key)
        plan_qty = int((reservation.allocations or {}).get("plan") or 0)
        if bucket is not None:
            bucket.reserved = max(0, int(bucket.reserved) - plan_qty)
        reservation.state = "released"
        reservation.error = reason[:1000]
        self._set_unlock_state(reservation.id, "released")
        self._event(reservation, "released", {"reason": reason[:500]})
        self.db.flush()

    def release_stale(self) -> int:
        now = utcnow()
        rows = (
            self.db.query(UsageReservation)
            .filter(UsageReservation.state == "reserved", UsageReservation.expires_at.is_not(None))
            .all()
        )
        released = 0
        for row in rows:
            expires = aware(row.expires_at)
            if expires is not None and expires <= now:
                self.release(row.id, "reservation lease expired")
                released += 1
        return released

    def settle(self, run: WorkflowRun | None) -> None:
        if run is None or not run.usage_reservation_id:
            return
        failed_stage = any(
            stage.get("status") == "FAILED"
            and stage.get("name") in {
                "ParseJD",
                "CalculateScore",
                "GenerateApplicationStrategy",
                "GenerateCV",
                "GenerateCoverLetter",
            }
            for stage in (run.stages or [])
        )
        if run.status == "COMPLETED" and not failed_stage:
            self.commit(run.usage_reservation_id)
        else:
            self.release(run.usage_reservation_id, run.error or "workflow did not produce a usable result")

    def assert_storage(self, user_id: str, incoming_bytes: int) -> None:
        self._assert_state(user_id, METER_CAREER_DOCUMENTS, 1)
        self._assert_state(user_id, METER_STORAGE_BYTES, incoming_bytes)

    def assert_active_application(self, user_id: str) -> None:
        self._assert_state(user_id, METER_ACTIVE_APPLICATIONS, 1)

    def assert_concurrency(self, user_id: str) -> None:
        effective = self.entitlements.require_usable(user_id)
        if effective.subscription is not None:
            query = self.db.query(Subscription).filter(Subscription.id == effective.subscription.id)
            bind = self.db.get_bind()
            if bind is not None and bind.dialect.name == "postgresql":
                query = query.with_for_update()
            query.one_or_none()
        self._assert_state(user_id, METER_CONCURRENT_WORKFLOWS, 1, code="CONCURRENT_WORKFLOW_LIMIT")

    def grant_credits(
        self,
        user_id: str,
        meter: str,
        quantity: int,
        *,
        source: str,
        note: str,
        expires_at,
        granted_by: str | None,
    ) -> CreditGrant:
        if meter not in PERIODIC_METERS:
            raise EntitlementError(
                "METER_NOT_CREDITABLE",
                status_code=422,
                message="Credits apply to periodic meters only.",
                meter=meter,
            )
        grant = CreditGrant(
            user_id=user_id,
            meter=meter,
            original=quantity,
            remaining=quantity,
            source=source,
            note=note,
            expires_at=aware(expires_at),
            granted_by=granted_by,
        )
        self.db.add(grant)
        self.db.flush()
        self.db.add(UsageEvent(
            user_id=user_id,
            meter=meter,
            quantity=quantity,
            state="grant",
            period_key=period_bounds()[0],
            detail={"grant_id": grant.id, "source": source, "note": note},
        ))
        self.db.flush()
        return grant

    def _allocate(self, reservation, user_id, meter, quantity, reference_type, reference_id) -> None:
        effective = self.entitlements.require_usable(user_id)
        limit = effective.limits.get(meter)
        bucket = self._ensure_bucket(effective, meter)
        locked = self._lock_bucket(user_id, meter, bucket.period_key)
        if locked is not None:
            bucket = locked
        plan_available = max(0, int(bucket.included) + int(bucket.rollover) - int(bucket.consumed) - int(bucket.reserved))
        if limit is None:
            plan_qty = quantity
            grant_allocs: list[dict] = []
        else:
            plan_qty = min(quantity, plan_available)
            grant_allocs = self._allocate_grants(user_id, meter, quantity - plan_qty)
            covered = plan_qty + sum(int(item["qty"]) for item in grant_allocs)
            if covered < quantity:
                credits = self._credit_remaining(user_id, meter)
                raise EntitlementError(
                    "USAGE_LIMIT_REACHED",
                    message="The allowance for this action is exhausted.",
                    meter=meter,
                    used=int(bucket.consumed),
                    reserved=int(bucket.reserved),
                    limit=int(bucket.included) + int(bucket.rollover) + credits,
                    remaining=plan_available + credits,
                    period_end=effective.period_end.isoformat() if effective.period_end else None,
                    actions=["view_usage", "contact_admin"],
                )
        bucket.reserved = int(bucket.reserved) + plan_qty
        reservation.user_id = user_id
        reservation.meter = meter
        reservation.quantity = quantity
        reservation.state = "reserved"
        reservation.period_key = bucket.period_key
        reservation.reference_type = reference_type
        reservation.reference_id = reference_id
        reservation.allocations = {"plan": plan_qty, "grants": grant_allocs}
        reservation.expires_at = utcnow() + timedelta(seconds=get_settings().workflow_lease_seconds)
        reservation.error = ""
        self._event(reservation, "reserved")
        self.db.flush()

    def _allocate_grants(self, user_id: str, meter: str, quantity: int) -> list[dict]:
        if quantity <= 0:
            return []
        held = self._reserved_grant_quantities(user_id, meter)
        allocs = []
        remaining = quantity
        for grant in self.entitlements.active_credits(user_id, meter):
            available = int(grant.remaining) - held.get(grant.id, 0)
            take = min(remaining, max(0, available))
            if take <= 0:
                continue
            allocs.append({"id": grant.id, "qty": take})
            remaining -= take
            if remaining == 0:
                break
        return allocs

    def _credit_remaining(self, user_id: str, meter: str) -> int:
        held = self._reserved_grant_quantities(user_id, meter)
        total = 0
        for grant in self.entitlements.active_credits(user_id, meter):
            total += max(0, int(grant.remaining) - held.get(grant.id, 0))
        return total

    def _reserved_grant_quantities(self, user_id: str, meter: str) -> dict[str, int]:
        rows = (
            self.db.query(UsageReservation)
            .filter(
                UsageReservation.user_id == user_id,
                UsageReservation.meter == meter,
                UsageReservation.state == "reserved",
            )
            .all()
        )
        totals: dict[str, int] = {}
        for row in rows:
            for item in (row.allocations or {}).get("grants") or []:
                totals[item["id"]] = totals.get(item["id"], 0) + int(item["qty"])
        return totals

    def _ensure_bucket(self, effective: EffectiveEntitlement, meter: str) -> UsageBucket:
        limit = effective.limits.get(meter)
        included = 0 if limit is None else int(limit)
        bucket = (
            self.db.query(UsageBucket)
            .filter(
                UsageBucket.user_id == effective.user_id,
                UsageBucket.meter == meter,
                UsageBucket.period_key == effective.period_key,
            )
            .one_or_none()
        )
        if bucket is not None:
            if int(bucket.included) != included:
                bucket.included = included
            return bucket
        bucket = UsageBucket(
            user_id=effective.user_id,
            meter=meter,
            period_key=effective.period_key,
            included=included,
            rollover=self._rollover_amount(effective, meter),
        )
        try:
            with self.db.begin_nested():
                self.db.add(bucket)
                self.db.flush()
        except IntegrityError:
            bucket = (
                self.db.query(UsageBucket)
                .filter(
                    UsageBucket.user_id == effective.user_id,
                    UsageBucket.meter == meter,
                    UsageBucket.period_key == effective.period_key,
                )
                .one()
            )
        return bucket

    def _rollover_amount(self, effective: EffectiveEntitlement, meter: str) -> int:
        cap = int(effective.rollover_caps.get(meter) or 0)
        if cap <= 0:
            return 0
        previous = (
            self.db.query(UsageBucket)
            .filter(
                UsageBucket.user_id == effective.user_id,
                UsageBucket.meter == meter,
                UsageBucket.period_key == previous_period_key(effective.period_key),
            )
            .one_or_none()
        )
        if previous is None:
            return 0
        unused = max(0, int(previous.included) + int(previous.rollover) - int(previous.consumed))
        return min(unused, cap)

    def _lock_bucket(self, user_id: str, meter: str, period_key: str) -> UsageBucket | None:
        query = self.db.query(UsageBucket).filter(
            UsageBucket.user_id == user_id,
            UsageBucket.meter == meter,
            UsageBucket.period_key == period_key,
        )
        bind = self.db.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            query = query.with_for_update()
        return query.one_or_none()

    def _reservation_is_orphaned(self, reservation: UsageReservation) -> bool:
        if reservation.state != "reserved":
            return False
        run = (
            self.db.query(WorkflowRun)
            .filter(
                WorkflowRun.usage_reservation_id == reservation.id,
                WorkflowRun.status.in_(("PENDING", "RUNNING")),
            )
            .first()
        )
        return run is None

    def _set_unlock_state(self, reservation_id: str, state: str) -> None:
        unlock = (
            self.db.query(ApplicationPackUnlock)
            .filter(ApplicationPackUnlock.reservation_id == reservation_id)
            .one_or_none()
        )
        if unlock is not None:
            unlock.state = state

    def _event(self, reservation: UsageReservation, state: str, detail: dict | None = None) -> None:
        self.db.add(UsageEvent(
            user_id=reservation.user_id,
            meter=reservation.meter,
            quantity=reservation.quantity,
            state=state,
            period_key=reservation.period_key,
            reservation_id=reservation.id,
            idempotency_key=reservation.idempotency_key,
            reference_type=reservation.reference_type,
            reference_id=reservation.reference_id,
            detail=detail or {},
        ))

    def _assert_state(self, user_id: str, meter: str, incoming: int, code: str | None = None) -> None:
        effective = self.entitlements.require_usable(user_id)
        limit = effective.limits.get(meter)
        used = self.state_used(user_id, meter)
        if limit is not None and used + incoming > int(limit):
            error_code = code or ("STORAGE_LIMIT_REACHED" if meter == METER_STORAGE_BYTES else "USAGE_LIMIT_REACHED")
            raise EntitlementError(
                error_code,
                message="This account is at its plan limit.",
                meter=meter,
                used=used,
                reserved=0,
                limit=int(limit),
                remaining=max(0, int(limit) - used),
                period_end=effective.period_end.isoformat() if effective.period_end else None,
                actions=["view_usage", "contact_admin"],
            )

    def state_used(self, user_id: str, meter: str) -> int:
        if meter == METER_CAREER_DOCUMENTS:
            return (
                self.db.query(CareerDocument)
                .filter(CareerDocument.user_id == user_id, CareerDocument.is_deleted == False)  # noqa: E712
                .count()
            )
        if meter == METER_STORAGE_BYTES:
            rows = (
                self.db.query(CareerDocument.size_bytes)
                .filter(CareerDocument.user_id == user_id, CareerDocument.is_deleted == False)  # noqa: E712
                .all()
            )
            return sum(int(row[0] or 0) for row in rows)
        if meter == METER_CONCURRENT_WORKFLOWS:
            return (
                self.db.query(WorkflowRun)
                .filter(WorkflowRun.user_id == user_id, WorkflowRun.status.in_(("PENDING", "RUNNING")))
                .count()
            )
        if meter == METER_ACTIVE_APPLICATIONS:
            return (
                self.db.query(Application)
                .filter(Application.user_id == user_id, Application.is_deleted == False)  # noqa: E712
                .count()
            )
        return 0

    def _periodic_summary(self, effective: EffectiveEntitlement, meter: str) -> dict:
        included = effective.limits.get(meter)
        if not effective.usable:
            return self._meter_payload(meter, included, 0, 0, 0, effective)
        bucket = (
            self.db.query(UsageBucket)
            .filter(
                UsageBucket.user_id == effective.user_id,
                UsageBucket.meter == meter,
                UsageBucket.period_key == effective.period_key,
            )
            .one_or_none()
        )
        rollover = int(bucket.rollover) if bucket else 0
        consumed = int(bucket.consumed) if bucket else 0
        reserved = int(bucket.reserved) if bucket else 0
        credits = self._credit_remaining(effective.user_id, meter)
        return self._meter_payload(meter, included, rollover, consumed, reserved, effective, credits)

    def _state_summary(self, effective: EffectiveEntitlement, meter: str) -> dict:
        included = effective.limits.get(meter)
        used = self.state_used(effective.user_id, meter)
        return self._meter_payload(meter, included, 0, used, 0, effective)

    def _meter_payload(self, meter, included, rollover, consumed, reserved, effective, credits: int = 0) -> dict:
        capacity = None if included is None else int(included) + int(rollover) + int(credits)
        remaining = None if capacity is None else max(0, capacity - consumed - reserved)
        ratio = 0.0 if not capacity else (consumed + reserved) / capacity
        if ratio >= 1:
            warning = "100"
        elif ratio >= 0.9:
            warning = "90"
        elif ratio >= 0.7:
            warning = "70"
        else:
            warning = "none"
        return {
            "meter": meter,
            "included": included,
            "rollover": rollover,
            "credits": credits,
            "used": consumed,
            "reserved": reserved,
            "remaining": remaining,
            "period_start": effective.period_start.isoformat() if effective.period_start else None,
            "period_end": effective.period_end.isoformat() if effective.period_end else None,
            "warning_level": warning,
        }
