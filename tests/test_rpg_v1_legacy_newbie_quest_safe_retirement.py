"""Deterministic coverage for the RPG V1 legacy Newbie Quest retirement.

These tests exercise the server-backed retirement contract with a deliberately
small SQLite schema and inspect the current page wiring for the first-run
handoff.  They do not depend on a browser, external identity provider, mail,
or production data.
"""

import importlib
import os
import sqlite3
import sys
from pathlib import Path

import pytest


TEST_SECRET = "test-only-rpg-v1-newbie-quest-retirement-secret"
REPO_ROOT = Path(__file__).resolve().parents[1]


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
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()


@pytest.fixture()
def retirement_app(tmp_path, monkeypatch):
    path = tmp_path / "rpg-v1-newbie-quest-retirement.sqlite"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                nickname TEXT,
                email TEXT,
                email_verified INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                plan TEXT DEFAULT 'free',
                premium_until TEXT,
                created_at TEXT,
                last_login TEXT,
                admin_note TEXT,
                elo_rating REAL,
                elo_provisional INTEGER DEFAULT 0,
                onboarding_path TEXT,
                onboarding_required INTEGER DEFAULT 0,
                password_hash TEXT,
                email_verify_token TEXT,
                email_token_expires TEXT,
                google_sub TEXT
            );
            CREATE TABLE user_stats (
                user_id INTEGER PRIMARY KEY,
                go_rank TEXT DEFAULT '30k',
                tour_done INTEGER DEFAULT 0,
                coins INTEGER DEFAULT 0,
                total_correct INTEGER DEFAULT 0,
                max_streak INTEGER DEFAULT 0
            );
            CREATE TABLE newbie_quest_state (
                user_id INTEGER PRIMARY KEY,
                stage INTEGER DEFAULT 1,
                graduated INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE newbie_quest_tasks (
                user_id INTEGER,
                task_key TEXT,
                source TEXT,
                completed_at TEXT,
                PRIMARY KEY(user_id, task_key)
            );
            CREATE TABLE newbie_quest_events (
                user_id INTEGER,
                event_key TEXT,
                event_name TEXT,
                task_key TEXT,
                payload TEXT,
                occurred_at TEXT,
                PRIMARY KEY(user_id, event_key)
            );
            CREATE TABLE daily_training_queue (
                user_id INTEGER,
                date TEXT,
                question_ids TEXT,
                sources TEXT
            );
            CREATE TABLE review_log (
                user_id INTEGER,
                question_id INTEGER,
                reviewed_at TEXT
            );
            CREATE TABLE badges_earned (
                user_id INTEGER,
                badge_id TEXT,
                earned_at TEXT,
                seen INTEGER DEFAULT 0
            );
            CREATE TABLE shop_inventory (
                user_id INTEGER,
                item_key TEXT,
                qty INTEGER
            );
            CREATE TABLE currency_log (
                user_id INTEGER,
                amount INTEGER,
                reason TEXT
            );
            CREATE TABLE player_wardrobe (
                user_id INTEGER,
                item_id TEXT,
                obtained_at TEXT,
                source TEXT
            );
            """
        )

    app = _app_module()
    monkeypatch.setattr(app, "get_db", lambda: _DbContext(path))
    monkeypatch.setattr(app, "_verify_turnstile", lambda token: True)
    monkeypatch.setattr(app, "_send_email_async", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_notify_admin_new_user", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_throttle_check", lambda *args, **kwargs: False)
    monkeypatch.setattr(app, "_throttle_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_record_login_day_if_enabled", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "_e9_rollout_telemetry", lambda *args, **kwargs: None)
    app.app.config.update(TESTING=True, SECRET_KEY=TEST_SECRET)
    return app, path


def _insert_user(
    path,
    *,
    user_id=1,
    username=None,
    email=None,
    nickname="Player",
    onboarding_path="newbie",
    onboarding_required=0,
    password_hash="not-used",
    google_sub=None,
):
    username = username or f"user-{user_id}"
    email = email or f"user-{user_id}@example.invalid"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO users(
                id, username, nickname, email, email_verified, is_admin, plan,
                created_at, onboarding_path, onboarding_required, password_hash,
                google_sub
            ) VALUES(?,?,?,?,0,0,'free',?,?,?,?,?)
            """,
            (
                user_id,
                username,
                nickname,
                email,
                "2026-01-01T00:00:00",
                onboarding_path,
                onboarding_required,
                password_hash,
                google_sub,
            ),
        )
        conn.execute("INSERT INTO user_stats(user_id) VALUES(?)", (user_id,))


def _insert_legacy_state(path, *, user_id=1, stage=1, graduated=0, updated_at="2026-01-01T00:00:00"):
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO newbie_quest_state(user_id,stage,graduated,created_at,updated_at) VALUES(?,?,?,?,?)",
            (user_id, stage, graduated, "2026-01-01T00:00:00", updated_at),
        )
        conn.execute(
            "INSERT INTO newbie_quest_tasks(user_id,task_key,source,completed_at) VALUES(?,?,?,?)",
            (user_id, f"historical_stage_{stage}", "historical", "2026-01-01T00:01:00"),
        )
        conn.execute(
            "INSERT INTO newbie_quest_events(user_id,event_key,event_name,task_key,payload,occurred_at) VALUES(?,?,?,?,?,?)",
            (user_id, f"historical:{stage}", "historical_task", f"historical_stage_{stage}", "{}", "2026-01-01T00:01:00"),
        )
        conn.execute("UPDATE user_stats SET coins=123,tour_done=1 WHERE user_id=?", (user_id,))
        conn.execute(
            "INSERT INTO shop_inventory(user_id,item_key,qty) VALUES(?,?,?)",
            (user_id, "historical_reward", 2),
        )
        conn.execute(
            "INSERT INTO currency_log(user_id,amount,reason) VALUES(?,?,?)",
            (user_id, 123, "historical_newbie_reward"),
        )
        conn.execute(
            "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)",
            (user_id, "title_historical_newbie", "2026-01-01T00:02:00", "newbie_quest"),
        )


def _set_session(client, **values):
    with client.session_transaction() as session:
        session.update(values)


def _counts(path, user_id=1):
    with sqlite3.connect(path) as conn:
        state = conn.execute(
            "SELECT stage,graduated,updated_at FROM newbie_quest_state WHERE user_id=?",
            (user_id,),
        ).fetchone()
        stats = conn.execute(
            "SELECT coins,tour_done FROM user_stats WHERE user_id=?", (user_id,)
        ).fetchone()
        return {
            "state": tuple(state) if state else None,
            "stats": tuple(stats) if stats else None,
            "tasks": conn.execute(
                "SELECT task_key,source,completed_at FROM newbie_quest_tasks WHERE user_id=? ORDER BY task_key",
                (user_id,),
            ).fetchall(),
            "events": conn.execute(
                "SELECT event_key,event_name,task_key,payload,occurred_at FROM newbie_quest_events WHERE user_id=? ORDER BY event_key",
                (user_id,),
            ).fetchall(),
            "shop": conn.execute(
                "SELECT item_key,qty FROM shop_inventory WHERE user_id=? ORDER BY item_key",
                (user_id,),
            ).fetchall(),
            "currency": conn.execute(
                "SELECT amount,reason FROM currency_log WHERE user_id=? ORDER BY reason",
                (user_id,),
            ).fetchall(),
            "wardrobe": conn.execute(
                "SELECT item_id,source FROM player_wardrobe WHERE user_id=? ORDER BY item_id",
                (user_id,),
            ).fetchall(),
        }


def test_email_new_account_path_choice_skips_legacy_nq_and_survives_relogin(retirement_app):
    app, path = retirement_app
    client = app.app.test_client()

    registered = client.post(
        "/api/auth/register",
        json={
            "username": "newplayer",
            "password": "valid-password",
            "confirm": "valid-password",
            "email": "newplayer@example.invalid",
            "nickname": "New Player",
        },
    )
    assert registered.status_code == 200
    assert client.get("/api/auth/me").get_json()["needs_onboarding_choice"] is True

    chosen = client.post("/api/user/onboarding_choice", json={"path": "newbie"})
    assert chosen.status_code == 200
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT onboarding_path,onboarding_required FROM users WHERE username='newplayer'"
        ).fetchone()
        user_id = conn.execute("SELECT id FROM users WHERE username='newplayer'").fetchone()[0]
        nq_count = conn.execute(
            "SELECT COUNT(*) FROM newbie_quest_state WHERE user_id=?", (user_id,)
        ).fetchone()[0]
    assert tuple(row) == ("newbie", 0)
    assert nq_count == 0

    client.post("/api/auth/logout")
    relogin = client.post(
        "/api/auth/login",
        json={"username": "newplayer", "password": "valid-password"},
    )
    assert relogin.status_code == 200
    me = client.get("/api/auth/me").get_json()
    assert me["needs_onboarding_choice"] is False
    assert me["newbie_quest_eligible"] is False
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM newbie_quest_state WHERE user_id=?", (user_id,)
        ).fetchone()[0] == 0


def test_google_new_account_path_choice_skips_legacy_nq(retirement_app, monkeypatch):
    app, path = retirement_app
    monkeypatch.setattr(
        app,
        "_verify_google_id_token",
        lambda credential: {
            "sub": "google-sub-123456",
            "email": "google-new@example.invalid",
            "email_verified": True,
            "name": "Google New Player",
        },
    )
    client = app.app.test_client()

    logged_in = client.post("/api/auth/google_login", json={"credential": "test-token"})
    assert logged_in.status_code == 200
    chosen = client.post("/api/user/onboarding_choice", json={"path": "newbie"})
    assert chosen.status_code == 200

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT id,onboarding_path,onboarding_required FROM users WHERE google_sub=?",
            ("google-sub-123456",),
        ).fetchone()
        nq_count = conn.execute(
            "SELECT COUNT(*) FROM newbie_quest_state WHERE user_id=?", (row[0],)
        ).fetchone()[0]
    assert tuple(row[1:]) == ("newbie", 0)
    assert nq_count == 0


@pytest.mark.parametrize("stage", [1, 3, 6, 7])
def test_incomplete_historical_stage_is_graduated_without_side_effects(retirement_app, stage):
    app, path = retirement_app
    _insert_user(path)
    _insert_legacy_state(path, stage=stage)
    before = _counts(path)
    client = app.app.test_client()
    _set_session(client, user_id=1, username="user-1", nickname="Player", is_admin=False, plan="free")

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["newbie_quest_eligible"] is False

    snapshot = client.get("/api/auth/newbie_quest")
    assert snapshot.status_code == 200
    assert snapshot.get_json()["eligible"] is False
    checkpoint = client.post(
        "/api/newbie_quest/checkpoint", json={"task_key": "stage7_shop_purchase"}
    )
    assert checkpoint.status_code == 403
    assert checkpoint.get_json()["error"] == "not_eligible"

    after = _counts(path)
    assert after["state"][0] == stage
    assert after["state"][1] == 1
    assert after["stats"] == before["stats"]
    assert after["tasks"] == before["tasks"]
    assert after["events"] == before["events"]
    assert after["shop"] == before["shop"]
    assert after["currency"] == before["currency"]
    assert after["wardrobe"] == before["wardrobe"]


def test_retirement_does_not_sync_tour_or_daily_rewards_for_incomplete_state(retirement_app):
    app, path = retirement_app
    _insert_user(path)
    _insert_legacy_state(path, stage=1)
    client = app.app.test_client()
    _set_session(client, user_id=1, username="user-1", nickname="Player", is_admin=False, plan="free")

    response = client.get("/api/auth/newbie_quest")
    assert response.status_code == 200
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM badges_earned WHERE user_id=1").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM newbie_quest_tasks WHERE user_id=1").fetchone()[0] == 1


def test_completed_historical_state_is_preserved_and_not_replayed(retirement_app):
    app, path = retirement_app
    _insert_user(path)
    _insert_legacy_state(path, stage=7, graduated=1, updated_at="2026-02-01T00:00:00")
    before = _counts(path)
    client = app.app.test_client()
    _set_session(client, user_id=1, username="user-1", nickname="Player", is_admin=False, plan="free")

    assert client.get("/api/auth/me").get_json()["newbie_quest_eligible"] is False
    response = client.post(
        "/api/newbie_quest/checkpoint", json={"task_key": "stage7_shop_purchase"}
    )
    assert response.status_code == 403
    assert _counts(path) == before


def test_current_new_account_handoff_and_manual_driver_tour_contract():
    index = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    shop = (REPO_ROOT / "shop.html").read_text(encoding="utf-8")
    curriculum = (REPO_ROOT / "curriculum.html").read_text(encoding="utf-8")
    hero = (REPO_ROOT / "hero.html").read_text(encoding="utf-8")
    bot = (REPO_ROOT / "bot.html").read_text(encoding="utf-8")

    creator = index[index.index("async function finishCreatorFlow"):index.index("async function maybeAutoTour")]
    assert "/api/user/onboarding_choice" in creator
    assert "/api/user/set_placement_elo" in creator
    assert "window.location.href = '/?after_placement=1';" in creator
    assert "/shop" not in creator

    auto_tour = index[index.index("async function maybeAutoTour"):index.index("function _initTourFlow")]
    assert "showNamingModal" in auto_tour
    assert "launchTour(" not in auto_tour
    tour_flow = index[index.index("function _initTourFlow"):index.index("if (document.readyState === 'loading')")]
    assert "after_placement" in tour_flow
    assert "launchTour(" not in tour_flow

    assert "window.startTour = function ()" in index
    assert 'id="tour-nav-btn"' in index
    assert 'id="guild-tour-btn"' in index
    assert 'id="skill-map"' in index
    assert 'id="newbie-quest-card"' not in index
    assert 'id="nq-spotlight-overlay"' not in index
    assert 'id="nq-spotlight-overlay"' not in shop
    assert 'id="nq-spotlight-overlay"' not in curriculum
    for page in (index, shop, curriculum, hero, bot):
        assert "/api/newbie_quest" not in page
        assert "nq-spotlight" not in page
    assert "_nqCheckShopPurchase();" not in shop


def test_legacy_compatibility_keys_remain_documented_in_source(retirement_app):
    app, _ = retirement_app
    index = (REPO_ROOT / "index.html").read_text(encoding="utf-8")
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    handoff = (REPO_ROOT / "docs/planning/rpg_v1_wave2_onboarding_v2_requirements.md").read_text(encoding="utf-8")

    assert app.LEGACY_NEWBIE_QUEST_RETIRED is True
    assert "cg_newbie_quest_v1" in index
    for key in (
        "nq_spotlight_s1..s7_shown/skipped",
        "nq_map_quiz_done",
        "nq_daily_training_done",
        "adventure_intro_seen_v1",
    ):
        assert key in handoff
    assert "newbie_quest_state" in source
    assert "newbie_quest_tasks" in source
    assert "newbie_quest_events" in source
    assert "UPDATE newbie_quest_state SET graduated=1" in source
