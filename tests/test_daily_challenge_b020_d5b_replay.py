"""B020 Daily Challenge exact-result replay tests."""

from __future__ import annotations

import sqlite3

import pytest

import app as app_module
from daily_challenge_authority import DailyAttemptError, issue_daily_attempt
from migrations.review_log_submission_idempotency_v1 import upgrade as upgrade_review_schema


class _SqliteContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        return False


def _question():
    return {
        "id": 301,
        "content": "(;GM[1]FF[4]SZ[19]PL[B](;B[dd]))",
        "accepted_moves": [],
    }


def _daily_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            topic TEXT,
            level TEXT,
            difficulty TEXT,
            reviewed_at TEXT NOT NULL,
            response_ms INTEGER,
            discipline TEXT,
            player_rating_snapshot REAL,
            question_rating_snapshot REAL,
            item_rating_version TEXT,
            question_version TEXT,
            source_context TEXT,
            is_scaffolding INTEGER NOT NULL DEFAULT 0,
            training_set_id INTEGER
        );
        CREATE TABLE daily_challenge_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            challenge_date TEXT NOT NULL,
            question_id INTEGER NOT NULL,
            correct INTEGER NOT NULL DEFAULT 0,
            submitted_at TEXT NOT NULL,
            UNIQUE(user_id, challenge_date)
        );
        CREATE TABLE user_stats (
            user_id INTEGER PRIMARY KEY,
            xp INTEGER NOT NULL DEFAULT 0,
            rank_xp INTEGER NOT NULL DEFAULT 0,
            rank_level TEXT NOT NULL DEFAULT 'LV1',
            updated_at TEXT
        );
        CREATE TABLE badges_earned (
            user_id INTEGER NOT NULL,
            badge_id TEXT NOT NULL,
            earned_at TEXT NOT NULL,
            seen INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, badge_id)
        );
        CREATE TABLE player_wardrobe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL,
            UNIQUE(user_id, item_id)
        );
        """
    )
    upgrade_review_schema(conn)
    conn.commit()
    return conn


@pytest.fixture()
def daily_route(monkeypatch):
    conn = _daily_db()
    question = _question()
    monkeypatch.setenv("SECRET_KEY", "b020-test-secret")
    monkeypatch.setattr(app_module, "get_db", lambda: _SqliteContext(conn))
    monkeypatch.setattr(
        app_module,
        "get_or_create_daily_challenge",
        lambda today: {"question_id": question["id"], "challenge_date": today},
    )
    monkeypatch.setattr(app_module, "_load_questions", lambda: [question])
    monkeypatch.setattr(app_module, "_observe_xp_shadow", lambda **kwargs: None)
    monkeypatch.setattr(app_module, "check_and_award_daily", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "get_daily_submit_streak", lambda *args, **kwargs: 0)
    monkeypatch.setattr(app_module, "give_daily_appearance", lambda *args, **kwargs: [])
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 7
        today = __import__("datetime").date.today().isoformat()
        token = issue_daily_attempt(
            app_module.app.secret_key,
            user_id=7,
            challenge_date=today,
            question=question,
            question_context=app_module._map_battle_question_context(question),
        )
        yield client, conn, token
    conn.close()


def _correct_payload(token, submission_id="daily-replay-1", client_correct=True):
    return {
        "submission_id": submission_id,
        "attempt_token": token,
        "moves": [{"x": 3, "y": 3}],
        "correct": client_correct,
    }


def test_daily_today_issues_a_server_bound_attempt(daily_route):
    client, _conn, _token = daily_route
    response = client.get("/api/daily-challenge/today")
    assert response.status_code == 200
    body = response.get_json()
    assert body["attempt_token"]
    assert body["question_id"] == 301


def test_same_d5b_submission_replays_exact_original_result(daily_route):
    client, conn, token = daily_route
    first = client.post(
        "/api/daily-challenge/submit",
        json=_correct_payload(token, client_correct=True),
    )
    retry = client.post(
        "/api/daily-challenge/submit",
        json=_correct_payload(token, client_correct=False),
    )

    assert first.status_code == 200, first.get_json()
    assert retry.status_code == 200, retry.get_json()
    assert retry.get_json() == first.get_json()
    assert retry.data == first.data
    assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log").fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM review_log WHERE user_id=? AND submission_id=?",
        (7, "daily-replay-1"),
    ).fetchone()[0] == 1
    assert conn.execute("SELECT xp FROM user_stats WHERE user_id=7").fetchone()[0] == 50


def test_response_loss_retry_replays_without_rejudging_or_second_side_effect(
    daily_route, monkeypatch
):
    client, conn, token = daily_route
    first = client.post(
        "/api/daily-challenge/submit",
        json=_correct_payload(token, submission_id="daily-response-loss"),
    )
    assert first.status_code == 200

    def verifier_unavailable(*args, **kwargs):
        raise DailyAttemptError("daily_attempt_expired")

    monkeypatch.setattr(app_module, "verify_daily_attempt", verifier_unavailable)
    retry = client.post(
        "/api/daily-challenge/submit",
        json=_correct_payload(token, submission_id="daily-response-loss"),
    )

    assert retry.status_code == 200
    assert retry.get_json() == first.get_json()
    assert retry.data == first.data
    assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log").fetchone()[0] == 1
    assert conn.execute("SELECT xp FROM user_stats WHERE user_id=7").fetchone()[0] == 50


def test_same_d5b_submission_changed_payload_is_conflict(daily_route):
    client, conn, token = daily_route
    first = client.post(
        "/api/daily-challenge/submit",
        json=_correct_payload(token, submission_id="daily-conflict"),
    )
    changed = client.post(
        "/api/daily-challenge/submit",
        json={
            **_correct_payload(token, submission_id="daily-conflict"),
            "moves": [{"x": 4, "y": 4}],
        },
    )

    assert first.status_code == 200
    assert changed.status_code == 409
    assert changed.get_json()["code"] == "idempotency_conflict"
    assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log").fetchone()[0] == 1
    assert conn.execute("SELECT xp FROM user_stats WHERE user_id=7").fetchone()[0] == 50


def test_client_correct_boolean_never_authorizes_reward(daily_route):
    client, conn, token = daily_route
    response = client.post(
        "/api/daily-challenge/submit",
        json={
            "submission_id": "daily-wrong",
            "attempt_token": token,
            "moves": [{"x": 4, "y": 4}],
            "correct": True,
        },
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["server_correct"] is False
    assert body["xp_awarded"] == 0
    assert conn.execute("SELECT correct FROM daily_challenge_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM user_stats").fetchone()[0] == 0


def test_d5b_identity_is_not_accepted_without_server_attempt(daily_route):
    client, conn, _token = daily_route
    response = client.post(
        "/api/daily-challenge/submit",
        json={"submission_id": "daily-no-attempt", "correct": True},
    )

    assert response.status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM daily_challenge_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 0
