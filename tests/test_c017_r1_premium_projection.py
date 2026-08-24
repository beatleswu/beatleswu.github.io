"""C017-R1 coverage for live Premium projections across read surfaces."""

import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest


TEST_SECRET = "test-only-c017-r1-premium-projection-secret"


def _app_module():
    os.environ.setdefault("SECRET_KEY", TEST_SECRET)
    sys.modules.pop("app", None)
    return importlib.import_module("app")


class _DbContext:
    def __init__(self, path):
        self.path = path
        self.conn = None

    def __enter__(self):
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        self.conn.close()


@pytest.fixture()
def projection_app(tmp_path, monkeypatch):
    path = tmp_path / "c017-r1-projection.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                nickname TEXT,
                email TEXT,
                email_verified INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                plan TEXT,
                premium_until TEXT,
                created_at TEXT,
                last_login TEXT,
                admin_note TEXT,
                elo_rating INTEGER,
                elo_provisional INTEGER DEFAULT 0,
                onboarding_path TEXT,
                onboarding_required INTEGER DEFAULT 0,
                password_hash TEXT
            );
            CREATE TABLE user_stats (
                user_id INTEGER PRIMARY KEY,
                go_rank TEXT,
                tour_done INTEGER DEFAULT 0,
                total_correct INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0
            );
            CREATE TABLE newbie_quest_state (user_id INTEGER PRIMARY KEY, graduated INTEGER DEFAULT 0);
            CREATE TABLE badges_earned (user_id INTEGER, badge_id INTEGER);
            CREATE TABLE subscriptions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                mer_order_no TEXT,
                plan_key TEXT,
                amount INTEGER,
                status TEXT,
                charged_times INTEGER,
                total_times INTEGER,
                created_at TEXT,
                cancelled_at TEXT
            );
            """
        )
    app = _app_module()
    monkeypatch.setattr(app, "get_db", lambda: _DbContext(path))
    app.app.config.update(TESTING=True)
    return app, path


def _insert_user(path, *, user_id=1, plan="premium", premium_until="2000-01-01T00:00:00", is_admin=0):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO users(
                id, username, nickname, email, email_verified, is_admin, plan,
                premium_until, created_at, last_login, admin_note, elo_rating,
                elo_provisional, onboarding_path, onboarding_required
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                f"user-{user_id}",
                "",
                f"user-{user_id}@example.invalid",
                1,
                is_admin,
                plan,
                premium_until,
                "2026-01-01T00:00:00",
                None,
                "",
                1200,
                0,
                None,
                0,
            ),
        )
        conn.execute("INSERT INTO user_stats(user_id, go_rank, tour_done) VALUES(?,?,?)", (user_id, "30k", 0))


def _set_session(client, **values):
    with client.session_transaction() as session:
        session.update(values)


@pytest.mark.parametrize(
    "db_plan,premium_until,expected",
    [
        ("premium", "2000-01-01T00:00:00", False),
        ("premium", "2099-01-01T00:00:00", True),
        ("free", "2099-01-01T00:00:00", False),
        ("premium", "not-a-date", False),
        ("premium", None, True),
    ],
)
def test_auth_me_uses_live_entitlement_and_preserves_raw_plan(
    projection_app, db_plan, premium_until, expected
):
    app, path = projection_app
    _insert_user(path, plan=db_plan, premium_until=premium_until)
    client = app.app.test_client()
    _set_session(client, user_id=1, username="user-1", nickname="", plan="premium", is_admin=False)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    body = response.get_json()
    assert body["is_premium"] is expected
    assert body["is_premium_live"] is expected
    assert body["plan"] == ("premium" if expected else "free")
    with sqlite3.connect(path) as conn:
        stored = conn.execute("SELECT plan, premium_until FROM users WHERE id=1").fetchone()
    assert tuple(stored) == (db_plan, premium_until)


def test_auth_me_preserves_session_admin_override(projection_app):
    app, path = projection_app
    _insert_user(path, plan="free", premium_until=None, is_admin=0)
    client = app.app.test_client()
    _set_session(client, user_id=1, username="user-1", nickname="", plan="free", is_admin=True)

    body = client.get("/api/auth/me").get_json()

    assert body["is_premium"] is True
    assert body["plan"] == "premium"


def test_admin_list_exposes_live_state_without_erasing_raw_expired_plan(projection_app):
    app, path = projection_app
    _insert_user(path, plan="premium", premium_until="2000-01-01T00:00:00")
    _insert_user(path, user_id=2, plan="premium", premium_until="2099-01-01T00:00:00")
    client = app.app.test_client()
    _set_session(client, user_id=99, username="admin", plan="free", is_admin=True)

    response = client.get("/api/admin/users")

    assert response.status_code == 200
    rows = {row["id"]: row for row in response.get_json()}
    assert rows[1]["plan"] == "premium"
    assert rows[1]["is_premium_live"] is False
    assert rows[2]["is_premium_live"] is True
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT plan FROM users WHERE id=1").fetchone()[0] == "premium"


def test_payment_subscription_projection_is_live_and_keeps_raw_plan(projection_app):
    app, path = projection_app
    _insert_user(path, plan="premium", premium_until="2000-01-01T00:00:00")
    client = app.app.test_client()
    _set_session(client, user_id=1, username="user-1", plan="premium", is_admin=False)

    response = client.get("/api/pay/subscription")

    assert response.status_code == 200
    body = response.get_json()
    assert body["plan"] == "free"
    assert body["is_premium"] is False
    assert body["is_premium_live"] is False
    assert body["stored_plan"] == "premium"
    assert body["premium_until"] == "2000-01-01T00:00:00"


def test_admin_html_consumes_live_projection_field():
    html = Path("admin.html").read_text(encoding="utf-8")
    assert "is_premium_live" in html
    assert "Premium（已到期）" in html
    assert "日期格式錯誤" in html
