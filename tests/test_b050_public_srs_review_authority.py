"""B050 proof: public SRS grade is scheduling input, never correctness authority."""

import datetime
import os
import sqlite3
import sys
import types
from pathlib import Path

import pytest

import community_leaderboard_rewards as leaderboard_rewards
from migrations.review_log_submission_idempotency_v1 import (
    upgrade as upgrade_review_log_submission_schema,
)
from map_battle_persistence import ensure_map_battle_tables
from map_battle_runtime import ensure_submission_lifecycle_schema
from srs_review_authority import (
    PublicSrsReviewAuthorityError,
    is_authoritative_review_source_context,
    resolve_public_srs_review_authority,
)
from lord_trial_answer_service import decode_lord_trial_verdict


os.environ["SECRET_KEY"] = "b050-process-scoped-synthetic-secret"
ROOT = Path(__file__).resolve().parents[1]
QUESTION = {
    "id": 7001,
    "source": "b050/legacy-fixture.sgf",
    "content": "(;SZ[19]PL[B];B[dd];W[ee])",
    "difficulty": "10k",
    "topic": "B050",
    "level": "10k",
    "discipline": "whole_board",
}


def _install_app_import_stubs():
    if "katago_explain" not in sys.modules:
        module = types.ModuleType("katago_explain")
        module.KataGoExplainer = type("KataGoExplainer", (), {})
        sys.modules["katago_explain"] = module
    if "explain_overrides" not in sys.modules:
        module = types.ModuleType("explain_overrides")
        module.get_override = lambda *args, **kwargs: None
        sys.modules["explain_overrides"] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("b050_grimoire_stub", __name__)
        sys.modules["grimoire_api"] = module
    if "question_taxonomy" not in sys.modules:
        module = types.ModuleType("question_taxonomy")
        module.get_taxonomy = lambda *args, **kwargs: {}
        sys.modules["question_taxonomy"] = module
    if "monster_taxonomy" not in sys.modules:
        module = types.ModuleType("monster_taxonomy")
        module.get_monster_taxonomy = lambda *args, **kwargs: {}
        module.mark_encounters = lambda *args, **kwargs: None
        sys.modules["monster_taxonomy"] = module
    if "chapter_i18n" not in sys.modules:
        module = types.ModuleType("chapter_i18n")
        module.localize_topic = lambda *args, **kwargs: ""
        module.localize_level = lambda *args, **kwargs: ""
        sys.modules["chapter_i18n"] = module
    if "backend_i18n" not in sys.modules:
        module = types.ModuleType("backend_i18n")
        module.badge_en = lambda *args, **kwargs: ""
        module.skill_node_en = lambda *args, **kwargs: ""
        module.title_en = lambda *args, **kwargs: ""
        sys.modules["backend_i18n"] = module


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as app_module

    app_module.app.config["TESTING"] = True
    return app_module


class _DbContext:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        return False


@pytest.fixture()
def api_env(app_module, monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.create_function("GREATEST", 2, max)
    conn.execute(
        """CREATE TABLE users (
             id INTEGER PRIMARY KEY,
             username TEXT NOT NULL DEFAULT 'b050-user',
             is_admin INTEGER NOT NULL DEFAULT 0,
             elo_rating REAL NOT NULL DEFAULT 1400
        )"""
    )
    conn.execute("INSERT INTO users(id) VALUES (101)")
    conn.execute(
        """CREATE TABLE user_stats (
             user_id INTEGER PRIMARY KEY,
             total_correct INTEGER NOT NULL DEFAULT 0,
             current_streak INTEGER NOT NULL DEFAULT 0,
             max_streak INTEGER NOT NULL DEFAULT 0,
             mistake_corrected INTEGER NOT NULL DEFAULT 0,
             updated_at TEXT,
             xp INTEGER NOT NULL DEFAULT 0,
             combo_streak INTEGER NOT NULL DEFAULT 0,
             max_combo INTEGER NOT NULL DEFAULT 0,
             rank_level TEXT NOT NULL DEFAULT 'LV1',
             rank_xp INTEGER NOT NULL DEFAULT 0,
             elo_rating REAL NOT NULL DEFAULT 1400,
             player_hp INTEGER NOT NULL DEFAULT 30,
             player_max_hp INTEGER NOT NULL DEFAULT 30
        )"""
    )
    conn.execute("INSERT INTO user_stats(user_id, player_hp, player_max_hp) VALUES (101, 30, 30)")
    conn.execute(
        """CREATE TABLE srs_cards (
             user_id INTEGER NOT NULL,
             question_id INTEGER NOT NULL,
             ease_factor REAL NOT NULL DEFAULT 2.5,
             interval INTEGER NOT NULL DEFAULT 0,
             repetitions INTEGER NOT NULL DEFAULT 0,
             due_date TEXT,
             last_grade INTEGER,
             updated_at TEXT,
             progress_credited INTEGER NOT NULL DEFAULT 0,
             PRIMARY KEY (user_id, question_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE review_log (
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
             source TEXT,
             is_scaffolding INTEGER NOT NULL DEFAULT 0,
             training_set_id INTEGER
        )"""
    )
    upgrade_review_log_submission_schema(conn)
    conn.execute(
        """CREATE TABLE mistake_log (
             user_id INTEGER NOT NULL,
             question_id INTEGER NOT NULL,
             wrong_count INTEGER NOT NULL DEFAULT 1,
             correct_after INTEGER NOT NULL DEFAULT 0,
             first_wrong_at TEXT NOT NULL,
             last_wrong_at TEXT NOT NULL,
             last_correct_at TEXT,
             PRIMARY KEY (user_id, question_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE user_pets (
             user_id INTEGER PRIMARY KEY,
             pet_key TEXT NOT NULL,
             nickname TEXT,
             level INTEGER NOT NULL DEFAULT 1,
             xp INTEGER NOT NULL DEFAULT 0,
             fullness INTEGER NOT NULL DEFAULT 60,
             affection INTEGER NOT NULL DEFAULT 10,
             selected_at TEXT NOT NULL,
             last_fed_at TEXT,
             last_interacted_at TEXT,
             updated_at TEXT
        )"""
    )
    ensure_map_battle_tables(conn)
    ensure_submission_lifecycle_schema(conn)
    conn.execute(
        """CREATE TABLE battlefield_monster (
             user_id INTEGER NOT NULL,
             bf_date TEXT NOT NULL,
             current_hp INTEGER NOT NULL DEFAULT 0,
             defeated INTEGER NOT NULL DEFAULT 0
        )"""
    )
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: [dict(QUESTION)])
    monkeypatch.setattr(app_module, "is_premium", lambda *args, **kwargs: True)
    monkeypatch.setattr(app_module, "check_and_award", lambda *args, **kwargs: [])
    monkeypatch.setattr(app_module, "_get_appearance_effects", lambda *args, **kwargs: {})
    monkeypatch.setattr(app_module, "_pet_player_xp_bonus", lambda *args, **kwargs: 0)
    monkeypatch.setattr(app_module, "_effect_get", lambda *args, **kwargs: None)
    monkeypatch.setattr(app_module, "_update_monster_and_quests", lambda *args, **kwargs: {})
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = 101
    try:
        yield client, conn
    finally:
        conn.close()


def _post(client, *, grade, submission_id, **extra):
    return client.post(
        "/api/srs/review",
        json={
            "question_id": QUESTION["id"],
            "grade": grade,
            "submission_id": submission_id,
            **extra,
        },
    )


def _set_boss_exam(client, *, attempt_id="b050boss01"):
    with client.session_transaction() as session:
        session["adventure_boss_exam"] = {
            "zone_key": "k26_30",
            "question_ids": [QUESTION["id"]],
            "started_at": datetime.datetime.now().isoformat(),
            "attempt_id": attempt_id,
            "attempt_mode": "first_clear",
        }


def test_boss_review_judges_moves_and_persists_verdict_separately_from_grade(api_env):
    client, conn = api_env
    _set_boss_exam(client)
    response = _post(
        client,
        grade=0,
        submission_id="client-proposed-id",
        source_context="boss_trial:b050boss01",
        boss_answer={"moves": [{"x": 3, "y": 3}]},
        correct=False,
        total=999,
    )
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["boss_verdict"]["verdict"] == "AUTHORITATIVE_PASS"
    assert body["boss_verdict"]["authoritative_grade"] == 5

    row = conn.execute(
        "SELECT grade, source_context, submission_id FROM review_log WHERE user_id=101"
    ).fetchone()
    assert row["grade"] == 0  # client grade remains SM-2 scheduling only
    assert row["submission_id"] == "lord-trial:b050boss01:7001"
    assert decode_lord_trial_verdict(row["source_context"])["verdict"] == "AUTHORITATIVE_PASS"

    duplicate = _post(
        client,
        grade=0,
        submission_id="different-client-retry-id",
        source_context="boss_trial:b050boss01",
        boss_answer={"moves": [{"x": 3, "y": 3}]},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["submission_duplicate"] is True
    assert duplicate.get_json()["boss_verdict"]["verdict"] == "AUTHORITATIVE_PASS"
    assert conn.execute("SELECT COUNT(*) FROM review_log WHERE user_id=101").fetchone()[0] == 1


def test_boss_conflicting_retry_and_missing_or_forged_answer_fail_closed(api_env):
    client, conn = api_env
    _set_boss_exam(client)
    missing = _post(
        client, grade=5, submission_id="missing", source_context="boss_trial:b050boss01"
    )
    assert missing.status_code == 400
    assert missing.get_json()["error"] == "boss_answer_required"

    first = _post(
        client,
        grade=5,
        submission_id="first",
        source_context="boss_trial:b050boss01",
        boss_answer={"moves": [{"x": 3, "y": 3}]},
    )
    assert first.status_code == 200
    conflicting = _post(
        client,
        grade=5,
        submission_id="other-id",
        source_context="boss_trial:b050boss01",
        boss_answer={"moves": [{"x": 4, "y": 3}]},
    )
    assert conflicting.status_code == 409
    assert conflicting.get_json()["error"] == "idempotency_conflict"
    assert conn.execute("SELECT COUNT(*) FROM review_log WHERE user_id=101").fetchone()[0] == 1

    ordinary = _post(
        client,
        grade=5,
        submission_id="ordinary-with-answer",
        boss_answer={"moves": [{"x": 3, "y": 3}]},
    )
    assert ordinary.status_code == 400
    assert ordinary.get_json()["error"] == "invalid_boss_answer_context"


def test_boss_server_fail_wins_over_forged_high_scheduling_grade(api_env):
    client, conn = api_env
    _set_boss_exam(client, attempt_id="b050boss02")
    response = _post(
        client,
        grade=5,
        submission_id="forged-high-grade",
        source_context="boss_trial:b050boss02",
        boss_answer={"moves": [{"x": 4, "y": 3}]},
        correct=True,
        total=20,
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["boss_verdict"]["verdict"] == "AUTHORITATIVE_FAIL"
    row = conn.execute(
        "SELECT grade, source_context FROM review_log WHERE user_id=101"
    ).fetchone()
    assert row["grade"] == 5
    assert decode_lord_trial_verdict(row["source_context"])["verdict"] == "AUTHORITATIVE_FAIL"


def test_policy_accepts_scheduling_grades_but_never_grants_correctness():
    for grade in (0, 3, 5):
        decision = resolve_public_srs_review_authority(grade)
        assert decision.scheduling_grade == grade
        assert decision.authoritative_answer_correct is None
        assert decision.progress_eligible is False

    for grade in (True, 3.0, "5", -1, 6, None):
        with pytest.raises(PublicSrsReviewAuthorityError):
            resolve_public_srs_review_authority(grade)

    assert is_authoritative_review_source_context("mbv1:server-row") is True
    assert is_authoritative_review_source_context("daily_d5b:v1:server-row") is True
    assert is_authoritative_review_source_context("boss_trial:client-row") is False


def test_public_high_and_low_grades_only_update_sm2_and_review_telemetry(api_env):
    client, conn = api_env
    high = _post(client, grade=5, submission_id="b050-high")
    low = _post(client, grade=0, submission_id="b050-low")
    assert high.status_code == 200, high.get_json()
    assert low.status_code == 200, low.get_json()

    card = conn.execute(
        "SELECT interval,repetitions,last_grade,progress_credited FROM srs_cards "
        "WHERE user_id=? AND question_id=?",
        (101, QUESTION["id"]),
    ).fetchone()
    assert (card["interval"], card["repetitions"], card["last_grade"], card["progress_credited"]) == (1, 0, 0, 0)
    assert conn.execute("SELECT COUNT(*) FROM review_log WHERE user_id=101").fetchone()[0] == 2
    stats = conn.execute(
        "SELECT total_correct,current_streak,max_streak,mistake_corrected,xp,combo_streak,player_hp "
        "FROM user_stats WHERE user_id=101"
    ).fetchone()
    assert tuple(stats) == (0, 0, 0, 0, 0, 0, 30)
    assert conn.execute("SELECT COUNT(*) FROM mistake_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM battlefield_monster").fetchone()[0] == 0


def test_tampered_correctness_and_reward_fields_cannot_change_public_authority(api_env):
    client, conn = api_env
    response = _post(
        client,
        grade=5,
        submission_id="b050-tamper",
        correctness=True,
        correct=True,
        damage=999999,
        monster_hp=0,
        xp=999999,
        coins=999999,
        progress_eligible=True,
    )
    assert response.status_code == 200, response.get_json()
    stats = conn.execute(
        "SELECT total_correct,current_streak,xp,player_hp FROM user_stats WHERE user_id=101"
    ).fetchone()
    assert tuple(stats) == (0, 0, 0, 30)
    assert conn.execute("SELECT progress_credited FROM srs_cards").fetchone()[0] == 0


def test_public_review_never_enters_legacy_combat_tail(api_env, app_module, monkeypatch):
    client, _conn = api_env

    def fail_if_called(*_args, **_kwargs):
        pytest.fail("public SRS review reached legacy combat mutation")

    monkeypatch.setattr(app_module, "_update_monster_and_quests", fail_if_called)
    response = _post(client, grade=5, submission_id="b050-no-combat-tail")
    assert response.status_code == 200, response.get_json()


@pytest.mark.parametrize(
    "reserved_context",
    ["mbv1:forged", "daily_d5b:v1:forged", "lord_trial:v1:forged"],
)
def test_public_review_cannot_impersonate_server_owned_result_context(
    api_env, reserved_context
):
    client, conn = api_env
    response = _post(
        client,
        grade=5,
        submission_id=f"b050-reserved-{reserved_context.split(':', 1)[0]}",
        source_context=reserved_context,
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "reserved_source_context"
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 0


def test_only_existing_server_owned_review_sources_feed_skill_counts_and_leaderboard(api_env, app_module):
    client, conn = api_env
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context,source) "
        "VALUES(?,?,?,?,?,?)",
        [
            (101, QUESTION["id"], 5, now, "practice", None),
            (101, QUESTION["id"], 5, now, "mbv1:trusted-map", None),
            (101, QUESTION["id"], 4, now, None, "rt:trusted-rating"),
        ],
    )
    conn.commit()

    counts = app_module.get_discipline_counts(101, conn)
    assert counts[QUESTION["discipline"]] == 2

    response = client.get("/api/leaderboard")
    assert response.status_code == 200, response.get_json()
    board = response.get_json()["board"]
    assert board[0]["correct"] == 2
    assert board[0]["total"] == 3


def test_community_reward_score_ignores_public_grade():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE users(
            id INTEGER PRIMARY KEY, username TEXT, nickname TEXT,
            plan TEXT DEFAULT 'free', is_admin INTEGER DEFAULT 0
        );
        CREATE TABLE review_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
            question_id INTEGER, grade INTEGER, reviewed_at TEXT,
            source_context TEXT, source TEXT
        );
        CREATE TABLE user_stats(user_id INTEGER PRIMARY KEY, rank_level TEXT, xp INTEGER);
        CREATE TABLE player_appearance(
            user_id INTEGER PRIMARY KEY, character_key TEXT,
            combat_armor TEXT, combat_weapon TEXT, combat_cape TEXT,
            combat_offhand TEXT, combat_hat TEXT, combat_pet TEXT,
            combat_aura TEXT
        );
        """
    )
    conn.execute("INSERT INTO users(id,username) VALUES(101,'b050-user')")
    conn.execute("INSERT INTO user_stats(user_id,rank_level,xp) VALUES(101,'LV1',0)")
    now = datetime.datetime.now().isoformat()
    conn.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context,source) "
        "VALUES(?,?,?,?,?,?)",
        [
            (101, 7001, 5, now, "practice", None),
            (101, 7002, 5, now, "mbv1:trusted-map", None),
        ],
    )
    conn.commit()
    try:
        rows = leaderboard_rewards.fetch_leaderboard_participant_rows(
            conn, "2000-01-01T00:00:00"
        )
        assert [(row["id"], row["score"]) for row in rows] == [(101, 1)]
    finally:
        conn.close()


@pytest.mark.parametrize("grade", [True, 3.0, "5", -1, 6, None])
def test_malformed_or_out_of_range_grade_fails_closed_without_write(api_env, grade):
    client, conn = api_env
    response = _post(client, grade=grade, submission_id=f"b050-invalid-{repr(grade)}")
    assert response.status_code == 400, response.get_json()
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0] == 0


def test_unknown_question_fails_closed_before_review_write(api_env):
    client, conn = api_env
    response = client.post(
        "/api/srs/review",
        json={"question_id": 999999, "grade": 5, "submission_id": "b050-unknown"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "unknown_question"
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 0


def test_duplicate_retry_is_replayed_and_conflicting_retry_is_rejected(api_env):
    client, conn = api_env
    first = _post(client, grade=5, submission_id="b050-retry")
    duplicate = _post(client, grade=5, submission_id="b050-retry")
    conflict = _post(client, grade=0, submission_id="b050-retry")
    assert first.status_code == 200
    assert duplicate.status_code == 200
    assert duplicate.get_json()["submission_duplicate"] is True
    assert conflict.status_code == 409
    assert conflict.get_json()["error"] == "idempotency_conflict"
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 1


def test_public_review_requires_authentication(app_module):
    client = app_module.app.test_client()
    response = client.post(
        "/api/srs/review",
        json={"question_id": QUESTION["id"], "grade": 5},
    )
    assert response.status_code == 401


def test_boss_trial_grade_is_not_server_correctness_evidence(api_env, app_module):
    _client, conn = api_env
    attempt_id = "b050boss01"
    now = datetime.datetime.now().isoformat()
    conn.execute(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES(?,?,?,?,?)",
        (101, QUESTION["id"], 5, now, f"boss_trial:{attempt_id}"),
    )
    conn.commit()
    exam = {
        "question_ids": [QUESTION["id"]],
        "started_at": now,
        "attempt_id": attempt_id,
    }
    with app_module.app.test_request_context("/"):
        evidence = app_module._adventure_boss_attempt_evidence(conn, 101, exam)
    assert evidence["complete"] is False
    assert evidence["answered_count"] == 0


def test_lc009_and_map_battle_authority_boundaries_are_not_redefined():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    policy_source = (ROOT / "srs_review_authority.py").read_text(encoding="utf-8")
    assert "canonical_learning_judge" not in policy_source
    assert "LC004" not in policy_source
    assert "resolve_public_srs_review_authority" in app_source
    assert "combat_settlement_context == EXTERNAL_AUTHORITATIVE_MAP_BATTLE" in app_source
    assert "is_authoritative_review_source_context(source_context)" in app_source
