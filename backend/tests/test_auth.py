"""Auth + access-control tests (§42, §56 security)."""


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
    assert resp.json()["email"]
