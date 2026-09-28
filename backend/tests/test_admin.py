"""Admin user-management API tests."""
from __future__ import annotations

from uuid import uuid4

from app.api.admin import _would_leave_no_active_admin
from app.models import Experience, User
from conftest import TEST_EMAIL


def test_admin_stats_and_list(client, auth_headers):
    stats = client.get("/api/admin/stats", headers=auth_headers)
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["total_users"] >= 1
    assert body["admin_users"] >= 1
    assert body["active_users"] >= 1

    users = client.get("/api/admin/users", headers=auth_headers)
    assert users.status_code == 200
    emails = {u["email"] for u in users.json()}
    assert TEST_EMAIL in emails
    sample = next(u for u in users.json() if u["email"] == TEST_EMAIL)
    assert sample["is_admin"] is True
    assert sample["has_password"] is True
    assert "onboarding_status" in sample
    assert "password_hash" not in sample
    assert "google_sub" not in sample


def test_admin_create_update_delete_user(client, auth_headers):
    email = f"member-{uuid4().hex[:8]}@example.com"
    created = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={"email": email, "password": "password-123", "full_name": "Member", "is_admin": False},
    )
    assert created.status_code == 201, created.text
    user = created.json()
    assert user["email"] == email
    assert user["is_admin"] is False
    assert user["is_active"] is True
    assert user["has_password"] is True

    login = client.post("/api/auth/login", json={"email": email, "password": "password-123"})
    assert login.status_code == 200
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/admin/users", headers=member_headers).status_code == 403

    patched = client.patch(
        f"/api/admin/users/{user['id']}",
        headers=auth_headers,
        json={"full_name": "Member Two", "is_admin": True},
    )
    assert patched.status_code == 200
    assert patched.json()["full_name"] == "Member Two"
    assert patched.json()["is_admin"] is True

    deactivated = client.patch(
        f"/api/admin/users/{user['id']}",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert client.post("/api/auth/login", json={"email": email, "password": "password-123"}).status_code == 401

    deleted = client.delete(f"/api/admin/users/{user['id']}", headers=auth_headers)
    assert deleted.status_code == 200
    remaining = {u["email"] for u in client.get("/api/admin/users", headers=auth_headers).json()}
    assert email not in remaining


def test_admin_cannot_modify_or_delete_self(client, auth_headers, db):
    me = db.query(User).filter(User.email == TEST_EMAIL).one()
    assert client.patch(f"/api/admin/users/{me.id}", headers=auth_headers, json={"is_admin": False}).status_code == 400
    assert client.patch(f"/api/admin/users/{me.id}", headers=auth_headers, json={"is_active": False}).status_code == 400
    assert client.delete(f"/api/admin/users/{me.id}", headers=auth_headers).status_code == 400


def test_duplicate_email_conflict(client, auth_headers):
    resp = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={"email": TEST_EMAIL, "password": "password-123"},
    )
    assert resp.status_code == 409


def test_unauthenticated_admin_routes(client):
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_admin_reset_onboarding_forces_upload_wizard(client, auth_headers, db):
    email = f"reset-onboard-{uuid4().hex[:8]}@example.com"
    created = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={"email": email, "password": "password-123", "full_name": "Reset Me", "is_admin": False},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert created.json()["onboarding_status"] is None

    login = client.post("/api/auth/login", json={"email": email, "password": "password-123"})
    assert login.status_code == 200
    member_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    db.add(
        Experience(
            user_id=user_id,
            organization="SeedCo",
            job_title="Analyst",
            responsibilities=["Did analysis"],
        )
    )
    db.commit()

    auto = client.get("/api/onboarding", headers=member_headers)
    assert auto.status_code == 200, auto.text
    assert auto.json()["status"] == "completed"
    assert auto.json()["experience_count"] >= 1

    listed = client.get("/api/admin/users", headers=auth_headers).json()
    sample = next(u for u in listed if u["id"] == user_id)
    assert sample["onboarding_status"] == "completed"

    assert client.post(f"/api/admin/users/{user_id}/reset-onboarding", headers=member_headers).status_code == 403

    reset = client.post(f"/api/admin/users/{user_id}/reset-onboarding", headers=auth_headers)
    assert reset.status_code == 200, reset.text
    assert reset.json()["onboarding_status"] == "reset"

    after = client.get("/api/onboarding", headers=member_headers)
    assert after.status_code == 200, after.text
    assert after.json()["status"] == "reset"
    assert after.json()["experience_count"] >= 1

    again = client.get("/api/onboarding", headers=member_headers).json()
    assert again["status"] == "reset"

    done = client.post("/api/onboarding/complete", headers=member_headers)
    assert done.status_code == 200
    assert done.json()["status"] == "completed"


def test_admin_can_reset_own_onboarding(client, auth_headers, db):
    me = db.query(User).filter(User.email == TEST_EMAIL).one()
    reset = client.post(f"/api/admin/users/{me.id}/reset-onboarding", headers=auth_headers)
    assert reset.status_code == 200, reset.text
    assert reset.json()["onboarding_status"] == "reset"
    assert client.get("/api/onboarding", headers=auth_headers).json()["status"] == "reset"
    restore = client.post("/api/onboarding/complete", headers=auth_headers)
    assert restore.status_code == 200
    assert restore.json()["status"] == "completed"


def test_reset_onboarding_unknown_user(client, auth_headers):
    assert client.post(f"/api/admin/users/{uuid4()}/reset-onboarding", headers=auth_headers).status_code == 404


def test_last_admin_guard_helper(db):
    extra = User(
        email=f"extra-admin-{uuid4().hex[:8]}@example.com",
        password_hash="x",
        is_admin=True,
        is_active=True,
    )
    db.add(extra)
    db.flush()
    others = (
        db.query(User)
        .filter(User.is_deleted == False, User.is_active == True, User.is_admin == True, User.id != extra.id)  # noqa: E712
        .count()
    )
    if others == 0:
        assert _would_leave_no_active_admin(db, extra, is_admin=False) is True
    else:
        assert _would_leave_no_active_admin(db, extra, is_admin=False) is False
    db.delete(extra)
    db.flush()
