from __future__ import annotations

import pytest
from werkzeug.security import check_password_hash

pytestmark = pytest.mark.backend


def test_login_accepts_valid_credentials_and_sets_session(client, seeded_user):
    response = client.post(
        "/api/auth/login",
        json={
            "username": seeded_user["username"],
            "password": seeded_user["password"],
        },
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    with client.session_transaction() as flask_session:
        assert flask_session["user_id"] == seeded_user["id"]
        assert flask_session["username"] == seeded_user["username"]


def test_login_rejects_wrong_password(client, seeded_user):
    response = client.post(
        "/api/auth/login",
        json={"username": seeded_user["username"], "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "error" in response.get_json()


def test_login_rejects_missing_fields(client):
    response = client.post("/api/auth/login", json={"username": "alice"})

    assert response.status_code == 400


def test_logout_clears_authenticated_session(client, seeded_user):
    login = client.post(
        "/api/auth/login",
        json={
            "username": seeded_user["username"],
            "password": seeded_user["password"],
        },
    )
    assert login.status_code == 200

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    with client.session_transaction() as flask_session:
        assert "user_id" not in flask_session


def test_registration_creates_hashed_user_and_authenticates(client, isolated_db):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "new_player",
            "nickname": "New Player",
            "email": "new-player@example.test",
            "password": "safe-password-123",
            "confirm": "safe-password-123",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    row = isolated_db.execute(
        "SELECT * FROM users WHERE username = ?", ("new_player",)
    ).fetchone()
    assert row is not None
    assert row["password_hash"] != "safe-password-123"
    assert check_password_hash(row["password_hash"], "safe-password-123")
    with client.session_transaction() as flask_session:
        assert flask_session["user_id"] == row["id"]


def test_registration_rejects_duplicate_username(client, seeded_user):
    response = client.post(
        "/api/auth/register",
        json={
            "username": seeded_user["username"].upper(),
            "email": "different@example.test",
            "password": "safe-password-123",
            "confirm": "safe-password-123",
        },
    )

    assert response.status_code == 409


def test_registration_rejects_invalid_payload_without_insert(client, isolated_db):
    before = isolated_db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    response = client.post(
        "/api/auth/register",
        json={
            "username": "x",
            "email": "not-an-email",
            "password": "short",
            "confirm": "different",
        },
    )

    assert response.status_code == 400
    after = isolated_db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert after == before

