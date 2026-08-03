"""Sprint 2B executable Legacy Map Battle bridge and lifecycle coverage."""

import ast
import json
import os
import subprocess
import sqlite3
import sys
import types
from pathlib import Path

import pytest

from map_battle_persistence import ensure_map_battle_tables, hash_submission_nonce
from map_battle_runtime import ensure_submission_lifecycle_schema


# The app import below is deliberately process-scoped to a synthetic key.  It
# must never read the canonical or isolated secret sentinel.
os.environ["SECRET_KEY"] = "e10-sprint2b-process-scoped-synthetic-secret"

ROOT = Path(__file__).resolve().parents[1]
BASE = "0d4a255d20bfa40343a954f422c1f6f839c301e8"
ANSWER_ENDPOINT = "/api/adventure/map-battles/v1/answers"
ATTEMPT_ENDPOINT = "/api/adventure/map-battles/v1/attempts"
PROTOCOL = {"X-Map-Battle-Client-Protocol": "v1"}
QUESTION = {
    "id": 7001,
    "source": "sprint2b/legacy-fixture.sgf",
    "content": "(;SZ[19];B[dd];W[ee])",
    "accepted_moves": [{"x": 3, "y": 3}],
    "monster_hp": 40,
    "monster_atk": 6,
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
        module.grimoire_bp = Blueprint("grimoire_stub_map_battle", __name__)
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
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """CREATE TABLE users (
             id INTEGER PRIMARY KEY,
             is_admin INTEGER NOT NULL DEFAULT 0,
             elo_rating REAL NOT NULL DEFAULT 1400
        )"""
    )
    conn.executemany("INSERT INTO users(id) VALUES (?)", [(101,), (202,)])
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
             source TEXT,
             response_ms INTEGER,
             discipline TEXT,
             player_rating_snapshot REAL,
             question_rating_snapshot REAL,
             item_rating_version TEXT,
             question_version TEXT,
             source_context TEXT,
             is_scaffolding INTEGER NOT NULL DEFAULT 0,
             training_set_id INTEGER
        )"""
    )
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
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: [dict(QUESTION)])
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


def _prepare(client, zone_key):
    response = client.post(
        ATTEMPT_ENDPOINT,
        json={"zone_key": zone_key, "question_id": QUESTION["id"]},
        headers=PROTOCOL,
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _answer_payload(state, moves):
    return {
        "battle_id": state["battle_id"],
        "attempt_id": state["attempt_id"],
        "submission_nonce": state["submission_nonce"],
        "battle_revision": state["battle"]["battle_revision"],
        "question_revision": state["question_revision"],
        "player_color": state["player_color"],
        "transform_id": state["transform_id"],
        "transform_version": state["transform_version"],
        "moves": moves,
    }


def _battle(conn, battle_id):
    return dict(conn.execute("SELECT * FROM map_battles WHERE id=?", (battle_id,)).fetchone())


def _set_authoritative_admin(conn, user_id, enabled):
    conn.execute(
        "UPDATE users SET is_admin=? WHERE id=?",
        (1 if enabled else 0, user_id),
    )
    conn.commit()


def test_pre_fix_legacy_regression_is_reproduced_from_exact_base():
    baseline = subprocess.check_output(
        ["git", "show", f"{BASE}:index.html"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    assert "map_battle_v1_adapter.js" not in baseline
    assert "if (data.monster && !_isAdventureZonePractice())" in baseline
    assert "SRS.review(currentQ.id,grade" in baseline


def test_legacy_bridge_is_wired_without_e10_or_srs_damage_fallback(api_env):
    client, _ = api_env
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    adapter = (ROOT / "js/map_battle_v1_adapter.js").read_text(encoding="utf-8")
    assert "/js/map_battle_v1_adapter.js?v=20260803e10s2b" in html
    served = client.get("/js/map_battle_v1_adapter.js?v=20260803e10s2b")
    assert served.status_code == 200
    assert "MapBattleV1" in served.get_data(as_text=True)
    assert "window.MapBattleV1 && window.MapBattleV1.legacy" in html
    assert "_submitMapBattleV1IfActive(_mapBattleV1Moves)" in html
    assert "response.player_hp_after" in adapter
    assert "response.monster_hp_after" in adapter
    assert "response.battle_revision" in adapter
    assert "window.MapBattleV1.e10" not in adapter
    wrong_flow = html[html.index("function onBoardClick"):html.index("function resetProblem")]
    assert wrong_flow.index("_mapBattleV1IsActive()") < wrong_flow.index("/api/srs/review")
    assert "SRS.review(currentQ.id,grade" in html


def test_legacy_prepare_creates_resumes_battle_and_hashes_nonce(api_env):
    client, conn = api_env
    first = _prepare(client, "legacy::forest")
    second = _prepare(client, "legacy::forest")
    assert first["battle_id"] == second["battle_id"]
    assert first["attempt_id"] != second["attempt_id"]
    assert first["submission_nonce"] != second["submission_nonce"]
    assert first["battle"]["player_hp"] == 30
    assert first["battle"]["monster_hp"] == 40
    assert conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM map_battle_attempts").fetchone()[0] == 2
    stored = conn.execute(
        "SELECT submission_nonce_hash FROM map_battle_attempts WHERE id=?",
        (first["attempt_id"],),
    ).fetchone()[0]
    assert stored == hash_submission_nonce(first["submission_nonce"])
    assert first["submission_nonce"] not in stored


def test_legacy_correct_duplicate_incorrect_and_invalid_are_authoritative(api_env):
    client, conn = api_env

    correct = _prepare(client, "legacy::correct")
    correct_response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(correct, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    )
    assert correct_response.status_code == 200, correct_response.get_json()
    result = correct_response.get_json()
    assert result["result"] == "CORRECT"
    assert result["monster_hp_after"] < result["monster_hp_before"]
    assert result["player_hp_after"] == result["player_hp_before"] == 30
    assert result["battle_revision"] == 1
    assert result["progression"]["status"] == "applied"
    assert conn.execute(
        "SELECT COUNT(*) FROM review_log WHERE user_id=101"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT source_context FROM review_log WHERE user_id=101"
    ).fetchone()[0].startswith("mbv1:")
    card = conn.execute(
        "SELECT progress_credited,last_grade FROM srs_cards WHERE user_id=101 AND question_id=?",
        (QUESTION["id"],),
    ).fetchone()
    assert (card["progress_credited"], card["last_grade"]) == (1, 5)
    stats = conn.execute(
        "SELECT total_correct,current_streak,xp FROM user_stats WHERE user_id=101"
    ).fetchone()
    assert stats["total_correct"] == stats["current_streak"] == 1
    assert stats["xp"] > 0

    duplicate_payload = _answer_payload(correct, [{"x": 3, "y": 3}])
    duplicate_payload["battle_revision"] = 0
    duplicate_response = client.post(
        ANSWER_ENDPOINT,
        json=duplicate_payload,
        headers=PROTOCOL,
    )
    duplicate = duplicate_response.get_json()
    assert duplicate_response.status_code == 200
    assert duplicate["duplicate"] is True
    assert duplicate["monster_hp_after"] == result["monster_hp_after"]
    assert duplicate["battle_revision"] == result["battle_revision"]
    assert duplicate["progression"]["status"] == "duplicate"
    assert conn.execute(
        "SELECT COUNT(*) FROM review_log WHERE user_id=101"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT total_correct,current_streak,xp FROM user_stats WHERE user_id=101"
    ).fetchone() == stats

    incorrect = _prepare(client, "legacy::incorrect")
    incorrect_response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(incorrect, [{"x": 0, "y": 0}]),
        headers=PROTOCOL,
    )
    incorrect_result = incorrect_response.get_json()
    assert incorrect_response.status_code == 200
    assert incorrect_result["result"] == "INCORRECT"
    assert incorrect_result["monster_hp_after"] == incorrect_result["monster_hp_before"] == 40
    assert incorrect_result["player_hp_after"] < incorrect_result["player_hp_before"]
    assert incorrect_result["battle_revision"] == 1

    invalid = _prepare(client, "legacy::invalid")
    invalid_response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(invalid, []),
        headers=PROTOCOL,
    )
    invalid_result = invalid_response.get_json()
    assert invalid_response.status_code == 200
    assert invalid_result["result"] == "INVALID"
    assert invalid_result["damage_to_monster"] == invalid_result["damage_to_player"] == 0
    assert invalid_result["battle_revision"] == 0
    assert invalid_result["progression"]["status"] == "not_applicable"
    invalid_battle = _battle(conn, invalid["battle_id"])
    assert (invalid_battle["monster_hp"], invalid_battle["player_hp"], invalid_battle["battle_revision"]) == (40, 30, 0)
    assert conn.execute(
        "SELECT settlement_state FROM map_battle_submissions WHERE id=?",
        (invalid_result["submission_id"],),
    ).fetchone()[0] == "REJECTED"
    assert conn.execute(
        "SELECT COUNT(*) FROM review_log WHERE user_id=101"
    ).fetchone()[0] == 2


def test_legacy_forged_fields_expiry_and_stale_revision_do_not_mutate(api_env):
    client, conn = api_env

    forged = _prepare(client, "legacy::forged")
    forged_payload = _answer_payload(forged, [{"x": 3, "y": 3}])
    forged_payload.update({"grade": 5, "correctness": True, "damage": 999, "monster_hp": 0, "player_hp": 0})
    forged_response = client.post(ANSWER_ENDPOINT, json=forged_payload, headers=PROTOCOL)
    assert forged_response.status_code == 400
    assert forged_response.get_json()["code"] == "client_authority_field_forbidden"
    unchanged = _battle(conn, forged["battle_id"])
    assert unchanged["monster_hp"] == 40
    assert unchanged["player_hp"] == 30
    assert unchanged["battle_revision"] == 0
    assert conn.execute("SELECT COUNT(*) FROM map_battle_submissions").fetchone()[0] == 0

    expired = _prepare(client, "legacy::expired")
    conn.execute(
        "UPDATE map_battle_attempts SET issued_at=?, expires_at=? WHERE id=?",
        ("2000-01-01T00:00:00+00:00", "2000-01-02T00:00:00+00:00", expired["attempt_id"]),
    )
    conn.commit()
    expired_response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(expired, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    )
    assert expired_response.status_code == 409
    assert expired_response.get_json()["code"] == "map_battle_attempt_expired"
    expired_battle = _battle(conn, expired["battle_id"])
    assert (expired_battle["monster_hp"], expired_battle["player_hp"], expired_battle["battle_revision"]) == (40, 30, 0)

    stale_first = _prepare(client, "legacy::stale")
    stale_second = _prepare(client, "legacy::stale")
    settled = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(stale_first, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    ).get_json()
    assert settled["battle_revision"] == 1
    stale_response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(stale_second, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    )
    assert stale_response.status_code == 409
    assert "stale" in stale_response.get_json()["message"]
    final = _battle(conn, stale_first["battle_id"])
    assert final["battle_revision"] == 1
    assert final["monster_hp"] == settled["monster_hp_after"]
    refreshed = client.get(
        f"/api/adventure/map-battles/v1/battles/{stale_first['battle_id']}",
        headers=PROTOCOL,
    )
    assert refreshed.status_code == 200
    assert refreshed.get_json()["battle"]["battle_revision"] == 1
    assert refreshed.get_json()["battle"]["monster_hp"] == final["monster_hp"]


def test_legacy_feature_off_and_old_client_fail_closed(api_env, monkeypatch):
    client, conn = api_env
    old_client = client.post(
        ATTEMPT_ENDPOINT,
        json={"zone_key": "legacy::old", "question_id": QUESTION["id"]},
    )
    assert old_client.status_code == 426
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "off")
    disabled = client.post(
        ATTEMPT_ENDPOINT,
        json={"zone_key": "legacy::off", "question_id": QUESTION["id"]},
        headers=PROTOCOL,
    )
    assert disabled.status_code == 503
    assert disabled.get_json()["code"] == "map_battle_v1_disabled"
    assert conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0] == 0


def test_admin_mode_uses_authoritative_db_status_for_attempt_and_answer(api_env, monkeypatch):
    client, conn = api_env
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "admin")
    _set_authoritative_admin(conn, 101, True)
    with client.session_transaction() as session:
        session["is_admin"] = False
        session["plan"] = "free"

    state = _prepare(client, "legacy::admin")
    response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(state, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    )

    assert response.status_code == 200, response.get_json()
    result = response.get_json()
    assert result["result"] == "CORRECT"
    assert result["monster_hp_after"] < result["monster_hp_before"]


@pytest.mark.parametrize(
    ("user_id", "db_admin", "session_admin", "plan"),
    [
        (101, False, False, "free"),
        (101, False, True, "free"),
        (101, False, False, "premium"),
        (999, False, True, "premium"),
    ],
    ids=["non-admin", "forged-session-admin", "pro-non-admin", "missing-user"],
)
def test_admin_mode_rejects_non_admin_and_missing_users(
    api_env, monkeypatch, user_id, db_admin, session_admin, plan
):
    client, conn = api_env
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "admin")
    if user_id in (101, 202):
        _set_authoritative_admin(conn, user_id, db_admin)
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["is_admin"] = session_admin
        session["plan"] = plan

    response = client.post(
        ATTEMPT_ENDPOINT,
        json={"zone_key": "legacy::admin-denied", "question_id": QUESTION["id"]},
        headers=PROTOCOL,
    )

    assert response.status_code == 403
    assert response.get_json()["code"] == "map_battle_mode_not_eligible"
    assert conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0] == 0


def test_admin_mode_answers_recheck_server_admin_status(api_env, monkeypatch):
    client, conn = api_env
    state = _prepare(client, "legacy::answer-admin-denied")
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "admin")
    with client.session_transaction() as session:
        session["is_admin"] = True
        session["plan"] = "premium"
    _set_authoritative_admin(conn, 101, False)

    response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(state, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    )

    assert response.status_code == 403
    assert response.get_json()["code"] == "map_battle_mode_not_eligible"
    battle = _battle(conn, state["battle_id"])
    assert (battle["monster_hp"], battle["player_hp"], battle["battle_revision"]) == (40, 30, 0)


@pytest.mark.parametrize("mode", ["off", "invalid"])
def test_admin_wiring_preserves_fail_closed_modes(api_env, monkeypatch, mode):
    client, conn = api_env
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", mode)
    response = client.post(
        ATTEMPT_ENDPOINT,
        json={"zone_key": "legacy::admin-fail-closed", "question_id": QUESTION["id"]},
        headers=PROTOCOL,
    )

    assert response.status_code == 503
    assert response.get_json()["code"] == "map_battle_v1_disabled"
    assert conn.execute("SELECT COUNT(*) FROM map_battles").fetchone()[0] == 0


def test_global_mode_remains_available_without_admin_status(api_env, monkeypatch):
    client, _ = api_env
    monkeypatch.setenv("E10_MAP_BATTLE_V1_MODE", "global")
    state = _prepare(client, "legacy::global-unchanged")
    assert state["battle_id"]
    assert state["attempt_id"]


def test_map_battle_progression_reuses_canonical_antifarming_for_new_attempts(api_env):
    client, conn = api_env

    first = _prepare(client, "legacy::progress-first")
    first_result = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(first, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    ).get_json()
    assert first_result["progression"]["status"] == "applied"

    second = _prepare(client, "legacy::progress-second")
    second_result = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(second, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    ).get_json()
    assert second_result["progression"]["status"] == "applied"

    assert conn.execute(
        "SELECT COUNT(*) FROM review_log WHERE user_id=101"
    ).fetchone()[0] == 2
    stats = conn.execute(
        "SELECT total_correct,current_streak,xp FROM user_stats WHERE user_id=101"
    ).fetchone()
    assert (stats["total_correct"], stats["current_streak"]) == (1, 1)
    assert stats["xp"] > 0
    card = conn.execute(
        "SELECT progress_credited,last_grade FROM srs_cards WHERE user_id=101 AND question_id=?",
        (QUESTION["id"],),
    ).fetchone()
    assert (card["progress_credited"], card["last_grade"]) == (1, 5)


def test_normal_srs_review_stays_on_canonical_route_and_reserved_marker_is_server_only(
    api_env, app_module, monkeypatch
):
    client, conn = api_env
    monkeypatch.setattr(app_module, "is_premium", lambda *args, **kwargs: True)

    normal = client.post(
        "/api/srs/review",
        json={"question_id": QUESTION["id"], "grade": 5},
    )
    assert normal.status_code == 200, normal.get_json()
    assert normal.get_json()["ok"] is True
    assert conn.execute(
        "SELECT source_context FROM review_log WHERE user_id=101"
    ).fetchone()[0] == "practice"

    forged_marker = client.post(
        "/api/srs/review",
        json={
            "question_id": QUESTION["id"],
            "grade": 5,
            "source_context": "mbv1:forged-submission",
        },
    )
    assert forged_marker.status_code == 400
    assert forged_marker.get_json()["error"] == "reserved_source_context"
    assert conn.execute(
        "SELECT COUNT(*) FROM review_log WHERE source_context LIKE 'mbv1:%'"
    ).fetchone()[0] == 0


def test_progression_failure_does_not_rollback_authoritative_battle_settlement(
    api_env, app_module, monkeypatch
):
    client, conn = api_env
    state = _prepare(client, "legacy::progress-failure")
    real_operation = app_module._srs_review_operation

    def fail_progression(*args, **kwargs):
        raise RuntimeError("synthetic_failure")

    monkeypatch.setattr(app_module, "_srs_review_operation", fail_progression)

    response = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(state, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    )
    assert response.status_code == 503
    assert response.get_json()["code"] == "adventure_progression_pending"
    battle = _battle(conn, state["battle_id"])
    assert battle["monster_hp"] < battle["monster_hp_max"]
    assert battle["battle_revision"] == 1
    assert conn.execute(
        "SELECT settlement_state FROM map_battle_submissions"
    ).fetchone()[0] == "SETTLED"
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 0

    monkeypatch.setattr(app_module, "_srs_review_operation", real_operation)
    retry = client.post(
        ANSWER_ENDPOINT,
        json=_answer_payload(state, [{"x": 3, "y": 3}]),
        headers=PROTOCOL,
    )
    assert retry.status_code == 200, retry.get_json()
    assert retry.get_json()["duplicate"] is True
    assert retry.get_json()["progression"]["status"] == "applied"
    assert conn.execute("SELECT COUNT(*) FROM review_log").fetchone()[0] == 1


def test_legacy_cross_account_battle_state_is_not_visible(api_env):
    client, conn = api_env
    state = _prepare(client, "legacy::ownership")
    with client.session_transaction() as session:
        session["user_id"] = 202
    response = client.get(
        f"/api/adventure/map-battles/v1/battles/{state['battle_id']}",
        headers=PROTOCOL,
    )
    assert response.status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM map_battles WHERE user_id=101").fetchone()[0] == 1


def test_legacy_adapter_executes_authoritative_network_contract_without_srs():
    adapter_path = ROOT / "js" / "map_battle_v1_adapter.js"
    node_script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const calls = [];
let answerCount = 0;
const battle = { battle_id: 'battle-js', zone_key: 'legacy::js', state: 'OPEN',
  player_hp: 100, player_hp_max: 100, monster_hp: 50, monster_hp_max: 50,
  battle_revision: 0 };
const attempt = { attempt_id: 'attempt-js', battle_id: 'battle-js', question_id: 7001,
  question_revision: 'revision-js', player_color: 'B', transform_id: 'identity',
  transform_version: 'map-battle-v1', issued_at: 'now', expires_at: 'later' };
function reply(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => data };
}
async function fetchImpl(url, options) {
  calls.push({ url, options });
  if (url.endsWith('/attempts')) {
    return reply({ ok: true, battle, attempt, ...attempt, battle_id: battle.battle_id,
      attempt_id: attempt.attempt_id, submission_nonce: 'nonce-js', runtime_service: 'map-battle-v1-runtime' });
  }
  if (url.includes('/battles/')) {
    return reply({ ok: true, battle: { ...battle, monster_hp: 45, battle_revision: 1 }, runtime_service: 'map-battle-v1-runtime' });
  }
  if (!url.endsWith('/answers')) throw new Error('unexpected URL: ' + url);
  const body = JSON.parse(options.body);
  const keys = Object.keys(body).sort();
  const forbidden = ['grade', 'correctness', 'damage', 'player_hp', 'monster_hp'];
  if (forbidden.some((key) => keys.includes(key))) throw new Error('forbidden request field');
  answerCount += 1;
  if (answerCount === 1) return reply({ accepted: true, duplicate: false, result: 'CORRECT',
    damage_to_monster: 5, damage_to_player: 0, monster_hp_before: 50, monster_hp_after: 45,
    player_hp_before: 100, player_hp_after: 100, battle_revision: 1,
    monster_defeated: false, player_defeated: false, runtime_service: 'map-battle-v1-runtime' });
  if (answerCount === 2) return reply({ accepted: true, duplicate: true, result: 'CORRECT',
    damage_to_monster: 5, damage_to_player: 0, monster_hp_before: 50, monster_hp_after: 45,
    player_hp_before: 100, player_hp_after: 100, battle_revision: 1,
    monster_defeated: false, player_defeated: false, runtime_service: 'map-battle-v1-runtime' });
  if (answerCount === 3) return reply({ accepted: true, duplicate: false, result: 'INCORRECT',
    damage_to_monster: 0, damage_to_player: 8, monster_hp_before: 45, monster_hp_after: 45,
    player_hp_before: 100, player_hp_after: 92, battle_revision: 2,
    monster_defeated: false, player_defeated: false, runtime_service: 'map-battle-v1-runtime' });
  return reply({ accepted: false, duplicate: false, result: 'INVALID',
    damage_to_monster: 0, damage_to_player: 0, monster_hp_before: 45, monster_hp_after: 45,
    player_hp_before: 92, player_hp_after: 92, battle_revision: 2,
    monster_defeated: false, player_defeated: false, runtime_service: 'map-battle-v1-runtime' });
}
const window = {};
vm.createContext({ window, console, Number, String, Array, Error, encodeURIComponent });
vm.runInContext(source, vm.createContext({ window, console, Number, String, Array, Error, encodeURIComponent }));
(async () => {
  const api = window.MapBattleV1.legacy;
  const state = await api.prepare({ zoneKey: 'legacy::js', questionId: 7001 }, fetchImpl);
  await api.submit(state, [{ x: 3, y: 3 }], fetchImpl);
  const firstNonce = JSON.parse(calls[1].options.body).submission_nonce;
  await api.retry(state, [{ x: 3, y: 3 }], fetchImpl);
  const retryNonce = JSON.parse(calls[2].options.body).submission_nonce;
  if (firstNonce !== retryNonce || state.monsterHp !== 45 || state.playerHp !== 100 || state.battleRevision !== 1) process.exit(2);
  await api.refreshBattle(state, fetchImpl);
  if (state.monsterHp !== 45 || state.battleRevision !== 1) process.exit(7);
  await api.submit(state, [{ x: 0, y: 0 }], fetchImpl);
  if (state.monsterHp !== 45 || state.playerHp !== 92 || state.battleRevision !== 2) process.exit(3);
  await api.submit(state, [], fetchImpl);
  if (state.monsterHp !== 45 || state.playerHp !== 92 || state.battleRevision !== 2) process.exit(4);
  if (calls.some((call) => call.url.includes('/api/srs/review'))) process.exit(5);
})().catch((error) => { console.error(error); process.exit(6); });
"""
    result = subprocess.run(
        ["node", "-e", node_script, str(adapter_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_battle_runtime_import_boundary_has_no_progression_dependencies():
    runtime = ast.parse(
        (ROOT / "map_battle_runtime.py").read_text(encoding="utf-8")
    )
    forbidden = {"adventure", "guild", "srs", "frontend", "js"}
    imports = []
    for node in ast.walk(runtime):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
    assert not (set(imports) & forbidden)


def test_normal_srs_route_remains_present_and_service_worker_identity_is_unchanged():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    assert "@app.route('/api/srs/review', methods=['POST'])" in (ROOT / "app.py").read_text(encoding="utf-8")
    assert "SRS.review(currentQ.id,grade" in html
    assert "?v=20260803e10s2b" in html
    assert "const VERSION     = 'v227-e10-canonical-layout-contract-recovery'" in sw
