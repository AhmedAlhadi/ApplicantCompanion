"""Entitlement resolution, usage reservations, and admin enforcement."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, SessionLocal
from app.entitlements.constants import METER_APPLICATION_PACK, METER_FIT_CHECK
from app.models import Job, PlanVersion, User
from app.services.entitlements import EntitlementsService
from app.services.usage import UsageService
from app.services.usage_errors import EntitlementError


def _user(db, email="quota@example.com") -> User:
    user = User(email=email, full_name="Quota", password_hash="x", is_admin=False)
    db.add(user)
    db.flush()
    EntitlementsService(db).assign(user.id, plan_code="explorer")
    return user


def _job(db, user, text="Role: Analyst\nMust have SQL") -> Job:
    job = Job(user_id=user.id, raw_jd_text=text, organization_name="Example", position_title="Analyst")
    db.add(job)
    db.flush()
    return job


def test_seeded_catalog_and_summary(client, auth_headers):
    usage = client.get("/api/account/usage", headers=auth_headers)
    assert usage.status_code == 200, usage.text
    body = usage.json()
    assert body["subscription"]["plan_code"] == "power"
    assert body["subscription"]["usable"] is True
    meters = {item["meter"]: item for item in body["meters"]}
    assert meters["fit_check"]["included"] == 150
    assert "organization_research" in body["features"]


def test_reserve_commit_release_and_replay():
    db = SessionLocal()
    try:
        user = _user(db)
        job = _job(db, user)
        usage = UsageService(db)
        reservation, owned = usage.open_fit_check(user.id, job)
        assert owned is True
        assert reservation.state == "reserved"
        usage.commit(reservation.id)
        again, owned_again = usage.open_fit_check(user.id, job)
        assert again.id == reservation.id
        assert owned_again is False
        usage.release(reservation.id, "already consumed")
        assert db.get(type(reservation), reservation.id).state == "consumed"
        db.commit()
    finally:
        db.close()


def test_limit_then_credit_then_expiry():
    db = SessionLocal()
    try:
        user = _user(db, "credits@example.com")
        usage = UsageService(db)
        entitlements = EntitlementsService(db)
        for index in range(2):
            job = _job(db, user, f"JD number {index} with enough text")
            reservation, _owned = usage.open_fit_check(user.id, job)
            usage.commit(reservation.id)
        blocked = _job(db, user, "JD number 3 with enough text")
        with pytest.raises(EntitlementError) as raised:
            usage.open_fit_check(user.id, blocked)
        assert raised.value.code == "USAGE_LIMIT_REACHED"
        grant = usage.grant_credits(user.id, METER_FIT_CHECK, 1, source="payg", note="", expires_at=None, granted_by=None)
        reservation, owned = usage.open_fit_check(user.id, blocked)
        assert owned is True
        usage.commit(reservation.id)
        assert db.get(type(grant), grant.id).remaining == 0
        expired = usage.grant_credits(
            user.id,
            METER_FIT_CHECK,
            5,
            source="promotion",
            note="old",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            granted_by=None,
        )
        assert entitlements.active_credits(user.id, METER_FIT_CHECK) == []
        assert expired.remaining == 5
        db.commit()
    finally:
        db.close()


def test_pack_reuse_and_revision_charges_again():
    db = SessionLocal()
    try:
        user = _user(db, "packs@example.com")
        job = _job(db, user)
        usage = UsageService(db)
        _unlock, reservation, owned = usage.open_application_pack(user.id, job)
        assert owned is True
        usage.commit(reservation.id)
        _unlock, _reservation, owned_again = usage.open_application_pack(user.id, job)
        assert owned_again is False
        job.raw_jd_text = "A substantially different job description for a new revision"
        db.flush()
        with pytest.raises(EntitlementError) as raised:
            usage.open_application_pack(user.id, job)
        assert raised.value.code == "USAGE_LIMIT_REACHED"
        assert raised.value.detail["meter"] == METER_APPLICATION_PACK
        db.commit()
    finally:
        db.close()


def test_storage_and_inactive_subscription():
    db = SessionLocal()
    try:
        user = _user(db, "storage@example.com")
        usage = UsageService(db)
        with pytest.raises(EntitlementError) as raised:
            usage.assert_storage(user.id, 60 * 1024 * 1024)
        assert raised.value.code == "STORAGE_LIMIT_REACHED"
        sub = EntitlementsService(db).resolve(user.id).subscription
        sub.status = "expired"
        db.flush()
        with pytest.raises(EntitlementError) as inactive:
            usage.open_fit_check(user.id, _job(db, user, "another description"))
        assert inactive.value.code == "SUBSCRIPTION_INACTIVE"
        db.commit()
    finally:
        db.close()


def test_admin_plan_immutability_and_assignment(client, auth_headers):
    created = client.post("/api/admin/users", headers=auth_headers, json={
        "email": "member-entitlements@example.com",
        "password": "member-password-123",
        "full_name": "Member",
        "is_admin": False,
    })
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert created.json()["plan_code"] == "explorer"
    denied = client.get("/api/admin/plans", headers={"Authorization": "Bearer nope"})
    assert denied.status_code in (401, 403)
    plans = client.get("/api/admin/plans", headers=auth_headers)
    assert plans.status_code == 200
    explorer = next(plan for plan in plans.json() if plan["code"] == "explorer")
    version_id = explorer["current_version_id"]
    immutable = client.patch(
        f"/api/admin/plans/{explorer['id']}/versions/{version_id}",
        headers=auth_headers,
        json={"limits": {"fit_check": 1}, "features": {}, "template_keys": ["minimal-ats"], "priority": 0},
    )
    assert immutable.status_code == 409
    assigned = client.post(
        f"/api/admin/users/{user_id}/subscription",
        headers=auth_headers,
        json={"plan_code": "essential", "status": "active"},
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["subscription"]["plan_code"] == "essential"
    grant = client.post(
        f"/api/admin/users/{user_id}/credits",
        headers=auth_headers,
        json={"meter": "fit_check", "quantity": 3, "source": "promotion"},
    )
    assert grant.status_code == 201, grant.text
    stats = client.get("/api/admin/usage/stats", headers=auth_headers)
    assert stats.status_code == 200
    assert "users_by_plan" in stats.json()


def test_fit_check_blocks_when_allowance_is_zero(client, auth_headers):
    created = client.post("/api/admin/users", headers=auth_headers, json={
        "email": "blocked-fit@example.com",
        "password": "member-password-123",
        "full_name": "Blocked",
        "is_admin": False,
    })
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    override = client.post(
        f"/api/admin/users/{user_id}/overrides",
        headers=auth_headers,
        json={"meter": "fit_check", "limit_value": 0, "reason": "test block"},
    )
    assert override.status_code == 201, override.text
    login = client.post("/api/auth/login", json={"email": "blocked-fit@example.com", "password": "member-password-123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    job = client.post("/api/jobs", headers=headers, json={"raw_jd_text": "Analyst role requiring SQL and communication."})
    assert job.status_code == 201, job.text
    analyzed = client.post(f"/api/jobs/{job.json()['id']}/analyze", headers=headers, json={"include_research": False})
    assert analyzed.status_code == 409, analyzed.text
    assert analyzed.json()["detail"]["code"] == "USAGE_LIMIT_REACHED"
    summary = client.get("/api/account/usage", headers=headers)
    assert summary.status_code == 200
    fit = next(item for item in summary.json()["meters"] if item["meter"] == "fit_check")
    assert fit["included"] == 0


def _postgres_url() -> str | None:
    url = os.environ.get("ENTITLEMENTS_TEST_DATABASE_URL")
    if url:
        return url
    return None


def test_postgres_reservation_cannot_overspend():
    url = _postgres_url()
    if not url:
        pytest.skip("Set ENTITLEMENTS_TEST_DATABASE_URL to run the PostgreSQL race test")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    setup = sessions()
    try:
        EntitlementsService(setup).ensure_catalog()
        user = User(email="race@example.com", full_name="Race", password_hash="x")
        setup.add(user)
        setup.flush()
        EntitlementsService(setup).assign(user.id, plan_code="explorer")
        version = setup.get(PlanVersion, EntitlementsService(setup).resolve(user.id).version.id)
        limits = dict(version.limits)
        limits[METER_FIT_CHECK] = 1
        version.limits = limits
        setup.commit()
        user_id = user.id
    finally:
        setup.close()

    def attempt(index: int) -> str:
        db = sessions()
        try:
            UsageService(db).open_reservation(
                user_id,
                METER_FIT_CHECK,
                idempotency_key=f"race-{index}",
                reference_type="job",
                reference_id=user_id,
            )
            db.commit()
            return "ok"
        except EntitlementError as exc:
            db.rollback()
            return exc.code
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (1, 2)))
    assert sorted(results) == ["USAGE_LIMIT_REACHED", "ok"]
    engine.dispose()
