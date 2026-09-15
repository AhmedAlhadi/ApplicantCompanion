"""Auth + access-control tests (§42, §56 security)."""

import pytest


def test_register_closed_after_first_user(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "second@example.com", "password": "password-123", "full_name": "Second"},
    )
    assert resp.status_code == 403


def test_login_success(client):
    from conftest import TEST_EMAIL, TEST_PASSWORD

    resp = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == TEST_EMAIL
    assert "password_hash" not in body["user"]


def test_login_wrong_password(client):
    from conftest import TEST_EMAIL

    resp = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": "wrong-password"})
    assert resp.status_code == 401


def test_unauthorized_access(client):
    assert client.get("/api/career/experiences").status_code == 401
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/dashboard/stats").status_code == 401


def test_me(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"]
    assert "password_hash" not in body
    assert "google_sub" not in body


def test_google_requests_transport_importable():
    pytest.importorskip("google.auth")
    from google.auth.transport import requests as google_requests

    assert google_requests.Request is not None


def test_auth_config(client):
    resp = client.get("/api/auth/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["registration_open"] is False
    assert "google_client_id" in body


def test_google_creates_non_admin_when_users_exist(client, monkeypatch):
    from uuid import uuid4

    email = f"google-{uuid4().hex[:8]}@example.com"

    def fake_verify(_token: str) -> dict:
        return {"sub": f"sub-{email}", "email": email, "email_verified": True, "name": "Google User", "picture": "https://example.com/a.png"}

    monkeypatch.setattr("app.api.auth.verify_google_id_token", fake_verify)
    resp = client.post("/api/auth/google", json={"id_token": "fake-token"})
    assert resp.status_code == 200, resp.text
    user = resp.json()["user"]
    assert user["email"] == email
    assert user["is_admin"] is False
    assert user["full_name"] == "Google User"
    assert user["avatar_url"] == "https://example.com/a.png"
    assert "password_hash" not in user
    assert client.post("/api/auth/login", json={"email": email, "password": "password-123"}).status_code == 401


def test_google_first_user_becomes_admin(client, monkeypatch):
    from uuid import uuid4

    email = f"first-google-{uuid4().hex[:8]}@example.com"

    def fake_verify(_token: str) -> dict:
        return {"sub": f"sub-{email}", "email": email, "email_verified": True, "name": "Owner"}

    monkeypatch.setattr("app.api.auth.verify_google_id_token", fake_verify)
    monkeypatch.setattr("app.api.auth._non_deleted_user_count", lambda _db: 0)
    resp = client.post("/api/auth/google", json={"id_token": "fake-token"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["is_admin"] is True


def test_google_links_existing_password_account(client, auth_headers, monkeypatch):
    from conftest import TEST_EMAIL

    def fake_verify(_token: str) -> dict:
        return {"sub": "linked-sub-1", "email": TEST_EMAIL, "email_verified": True, "name": "Tester", "picture": "https://example.com/t.png"}

    monkeypatch.setattr("app.api.auth.verify_google_id_token", fake_verify)
    resp = client.post("/api/auth/google", json={"id_token": "fake-token"})
    assert resp.status_code == 200, resp.text
    user = resp.json()["user"]
    assert user["email"] == TEST_EMAIL
    assert user["is_admin"] is True
    assert user["avatar_url"] == "https://example.com/t.png"
    me = client.get("/api/auth/me", headers=auth_headers)
    assert me.status_code == 200


def test_google_inactive_user_rejected(client, auth_headers, monkeypatch):
    from uuid import uuid4

    email = f"inactive-g-{uuid4().hex[:8]}@example.com"
    created = client.post(
        "/api/admin/users",
        headers=auth_headers,
        json={"email": email, "password": "password-123", "full_name": "Inactive"},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert client.patch(f"/api/admin/users/{user_id}", headers=auth_headers, json={"is_active": False}).status_code == 200

    def fake_verify(_token: str) -> dict:
        return {"sub": f"sub-{email}", "email": email, "email_verified": True, "name": "Inactive"}

    monkeypatch.setattr("app.api.auth.verify_google_id_token", fake_verify)
    resp = client.post("/api/auth/google", json={"id_token": "fake-token"})
    assert resp.status_code == 401

