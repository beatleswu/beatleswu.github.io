"""B020 PostgreSQL acceptance using the known-good container-network path."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, timedelta
import os
from urllib.parse import urlsplit

import pytest

import app as app_module
from daily_challenge_authority import issue_daily_attempt
from db import PostgresConnectionWrapper
from migrations.review_log_submission_idempotency_v1 import upgrade as upgrade_review_schema


_REAL_CHECK_AND_AWARD_DAILY = app_module.check_and_award_daily
_REAL_GET_DAILY_SUBMIT_STREAK = app_module.get_daily_submit_streak
_REAL_GIVE_DAILY_APPEARANCE = app_module.give_daily_appearance


def _pg_url():
    url = os.environ.get("B020_DAILY_POSTGRES_URL") or os.environ.get("D5B_OUTBOX_POSTGRES_URL")
    if not url or os.environ.get("B020_DAILY_POSTGRES_DISPOSABLE") != "1":
        pytest.skip("requires explicitly marked disposable B020 PostgreSQL")
    database = (urlsplit(url).path or "").lstrip("/").lower()
    if "test" not in database and "b020" not in database:
        pytest.skip("refusing PostgreSQL URL without a test/b020 database")
    return url


def _connect(url=None):
    import psycopg2
    from psycopg2.extras import DictCursor

    raw = psycopg2.connect(url or _pg_url())
    raw.cursor_factory = DictCursor
    return PostgresConnectionWrapper(raw)


def _reset_schema(conn):
    conn.execute("DROP TABLE IF EXISTS daily_challenge_log CASCADE")
    conn.execute("DROP TABLE IF EXISTS user_stats CASCADE")
    conn.execute("DROP TABLE IF EXISTS badges_earned CASCADE")
    conn.execute("DROP TABLE IF EXISTS player_wardrobe CASCADE")
    conn.execute("DROP TABLE IF EXISTS review_log CASCADE")
    conn.execute(
        """CREATE TABLE review_log(
               id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
               question_id INTEGER NOT NULL, grade INTEGER NOT NULL,
               topic TEXT, level TEXT, difficulty TEXT,
               reviewed_at TEXT NOT NULL, response_ms INTEGER,
               discipline TEXT, player_rating_snapshot REAL,
               question_rating_snapshot REAL, item_rating_version TEXT,
               question_version TEXT, source_context TEXT,
               is_scaffolding INTEGER NOT NULL DEFAULT 0,
               training_set_id INTEGER)"""
    )
    conn.execute(
        """CREATE TABLE daily_challenge_log(
               id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
               challenge_date TEXT NOT NULL, question_id INTEGER NOT NULL,
               correct INTEGER NOT NULL DEFAULT 0, submitted_at TEXT NOT NULL,
               UNIQUE(user_id, challenge_date))"""
    )
    conn.execute(
        """CREATE TABLE user_stats(
               user_id INTEGER PRIMARY KEY, xp INTEGER NOT NULL DEFAULT 0,
               rank_xp INTEGER NOT NULL DEFAULT 0,
               rank_level TEXT NOT NULL DEFAULT 'LV1', updated_at TEXT)"""
    )
    conn.execute(
        """CREATE TABLE badges_earned(
               user_id INTEGER NOT NULL, badge_id TEXT NOT NULL,
               earned_at TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0,
               UNIQUE(user_id, badge_id))"""
    )
    conn.execute(
        """CREATE TABLE player_wardrobe(
               id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
               item_id TEXT NOT NULL, obtained_at TEXT NOT NULL,
               source TEXT NOT NULL, UNIQUE(user_id, item_id))"""
    )
    upgrade_review_schema(conn)
    conn.commit()


def _question():
    return {
        "id": 301,
        "content": "(;GM[1]FF[4]SZ[19]PL[B](;B[dd]))",
        "accepted_moves": [],
    }


@pytest.fixture(scope="module")
def pg_database():
    url = _pg_url()
    conn = _connect(url)
    try:
        _reset_schema(conn)
        yield url
    finally:
        conn.rollback()
        for table in ("daily_challenge_log", "user_stats", "badges_earned", "player_wardrobe", "review_log"):
            conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        conn.commit()
        conn.close()


@pytest.fixture()
def daily_pg(monkeypatch, pg_database):
    question = _question()
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _connect(pg_database),
    )
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
    conn = _connect(pg_database)
    conn.execute("TRUNCATE review_log, daily_challenge_log, user_stats, badges_earned, player_wardrobe")
    conn.commit()
    conn.close()
    today = date.today().isoformat()
    token = issue_daily_attempt(
        app_module.app.secret_key,
        user_id=7,
        challenge_date=today,
        question=question,
        question_context=app_module._map_battle_question_context(question),
    )
    return pg_database, token, question


def _client(payload):
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 7
    return client.post("/api/daily-challenge/submit", json=payload)


def _payload(token, submission_id="pg-daily-1", *, move=(3, 3), correct=True):
    return {
        "submission_id": submission_id,
        "attempt_token": token,
        "moves": [{"x": move[0], "y": move[1]}],
        "correct": correct,
    }


def _count(url, sql, params=()):
    conn = _connect(url)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def test_postgres_server_authority_and_exact_replay(daily_pg):
    url, token, _question_value = daily_pg
    first = _client(_payload(token, correct=False))
    retry = _client(_payload(token, correct=True))
    assert first.status_code == 200, first.get_json()
    assert retry.status_code == 200, retry.get_json()
    assert retry.get_json() == first.get_json()
    assert retry.data == first.data
    assert first.get_json()["server_correct"] is True
    assert _count(url, "SELECT COUNT(*) FROM daily_challenge_log") == 1
    assert _count(url, "SELECT xp FROM user_stats WHERE user_id=7") == 50
    assert _count(url, "SELECT COUNT(*) FROM review_log WHERE user_id=7 AND submission_id='pg-daily-1'") == 1


def test_postgres_client_correct_cannot_authorize_wrong_move(daily_pg):
    url, token, _question_value = daily_pg
    response = _client(_payload(token, submission_id="pg-forged-correct", move=(4, 4), correct=True))
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["server_correct"] is False
    assert body["xp_awarded"] == 0
    assert _count(
        url,
        "SELECT correct FROM daily_challenge_log WHERE user_id=7",
    ) == 0
    assert _count(url, "SELECT COUNT(*) FROM user_stats WHERE user_id=7") == 0


def test_postgres_changed_payload_conflict_and_no_extra_side_effect(daily_pg):
    url, token, _question_value = daily_pg
    first = _client(_payload(token, submission_id="pg-conflict"))
    changed = _client(_payload(token, submission_id="pg-conflict", move=(4, 4)))
    assert first.status_code == 200
    assert changed.status_code == 409
    assert changed.get_json()["code"] == "idempotency_conflict"
    assert _count(url, "SELECT COUNT(*) FROM daily_challenge_log") == 1
    assert _count(url, "SELECT xp FROM user_stats WHERE user_id=7") == 50


def test_postgres_concurrent_same_submission_has_one_execution_and_replays(daily_pg, monkeypatch):
    url, token, _question_value = daily_pg
    monkeypatch.setattr(app_module, "check_and_award_daily", _REAL_CHECK_AND_AWARD_DAILY)
    monkeypatch.setattr(app_module, "get_daily_submit_streak", _REAL_GET_DAILY_SUBMIT_STREAK)
    monkeypatch.setattr(app_module, "give_daily_appearance", _REAL_GIVE_DAILY_APPEARANCE)
    payload = _payload(token, submission_id="pg-concurrent", correct=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(_client, (payload, payload)))
    assert sorted(response.status_code for response in responses) == [200, 200]
    assert responses[0].get_json() == responses[1].get_json()
    assert responses[0].data == responses[1].data
    assert _count(url, "SELECT COUNT(*) FROM daily_challenge_log") == 1
    assert _count(url, "SELECT xp FROM user_stats WHERE user_id=7") == 50
    assert _count(url, "SELECT COUNT(*) FROM review_log WHERE user_id=7 AND submission_id='pg-concurrent'") == 1
    assert _count(url, "SELECT COUNT(*) FROM badges_earned WHERE user_id=7") == 2
    assert _count(url, "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=7") == 0


def test_postgres_current_submission_is_visible_to_streak_threshold(daily_pg, monkeypatch):
    url, token, _question_value = daily_pg
    monkeypatch.setattr(app_module, "check_and_award_daily", _REAL_CHECK_AND_AWARD_DAILY)
    monkeypatch.setattr(app_module, "get_daily_submit_streak", _REAL_GET_DAILY_SUBMIT_STREAK)
    monkeypatch.setattr(app_module, "give_daily_appearance", _REAL_GIVE_DAILY_APPEARANCE)
    conn = _connect(url)
    try:
        for offset in range(1, 7):
            challenge_date = (date.today() - timedelta(days=offset)).isoformat()
            conn.execute(
                """INSERT INTO daily_challenge_log
                   (user_id, challenge_date, question_id, correct, submitted_at)
                   VALUES(?,?,?,?,?)""",
                (7, challenge_date, 301, 1, f"{challenge_date}T00:00:00"),
            )
        conn.commit()
    finally:
        conn.close()

    response = _client(_payload(token, submission_id="pg-threshold"))
    assert response.status_code == 200, response.get_json()
    assert _count(
        url,
        "SELECT COUNT(*) FROM badges_earned WHERE user_id=7 AND badge_id='daily_7'",
    ) == 1
    assert _count(
        url,
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=7 AND item_id='title_wanderer'",
    ) == 1


def test_postgres_rollback_removes_identity_and_all_daily_side_effects(daily_pg, monkeypatch):
    url, token, _question_value = daily_pg
    monkeypatch.setattr(app_module, "check_and_award_daily", _REAL_CHECK_AND_AWARD_DAILY)
    monkeypatch.setattr(app_module, "get_daily_submit_streak", _REAL_GET_DAILY_SUBMIT_STREAK)

    def fail_reward(*args, **kwargs):
        raise RuntimeError("forced B020 rollback")

    monkeypatch.setattr(app_module, "give_daily_appearance", fail_reward)
    with pytest.raises(RuntimeError, match="forced B020 rollback"):
        _client(_payload(token, submission_id="pg-rollback"))

    assert _count(url, "SELECT COUNT(*) FROM daily_challenge_log") == 0
    assert _count(url, "SELECT COUNT(*) FROM review_log") == 0
    assert _count(url, "SELECT COUNT(*) FROM user_stats") == 0
    assert _count(url, "SELECT COUNT(*) FROM badges_earned") == 0
    assert _count(url, "SELECT COUNT(*) FROM player_wardrobe") == 0


def test_postgres_invalid_attempt_fails_closed_without_reward(daily_pg):
    url, token, _question_value = daily_pg
    response = _client(_payload(token + "tampered", submission_id="pg-invalid"))
    assert response.status_code == 409
    assert _count(url, "SELECT COUNT(*) FROM daily_challenge_log") == 0
    assert _count(url, "SELECT COUNT(*) FROM review_log") == 0
