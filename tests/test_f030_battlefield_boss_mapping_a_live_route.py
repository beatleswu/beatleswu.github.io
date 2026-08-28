"""F030 live-route closure tests for the F028 Mapping A reward service.

These tests call the real Flask ``/api/adventure/boss/finish`` route with a
disposable SQLite backing store.  The score still comes from the route's
server-authoritative ``review_log`` evidence; the request body is only used
to prove that forged score and reward-id fields cannot select a reward.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
import sys
import types
from pathlib import Path

import pytest

from lord_trial_answer_service import encode_lord_trial_verdict


CONTRACT_VERSION = "F028_BATTLEFIELD_BOSS_MAPPING_A_FIRST_CLEAR_V1"
REPO_ROOT = Path(__file__).resolve().parents[1]
ZONE_TO_ITEM = {
    "k26_30": "back_pack",
    "k21_25": "hat_cloth",
    "k16_20": "hat_bamboo",
    "k11_15": "robe_crane",
    "k6_10": "hat_onihorns",
    "k1_5": "robe_dragon",
    "d1_2": "acc_dragon_pendant",
    "d3_4": "back_cloak",
    "d5_6": "hat_dragon_horn",
    "d7_plus": "hat_celestial_crown",
}
TEST_ATTEMPT_ID = "unit-attempt"
_STARTED_AT_DT = _dt.datetime.now() - _dt.timedelta(minutes=5)
_STARTED_AT = _STARTED_AT_DT.isoformat()


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
        module.grimoire_bp = Blueprint("grimoire_stub_f030", __name__)
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

    return app_module


@pytest.fixture()
def client(app_module):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source_context TEXT NOT NULL DEFAULT 'practice'
        );
        CREATE TABLE adventure_boss_progress (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0,
            stars INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            best_score INTEGER NOT NULL DEFAULT 0,
            cooldown_until_seen INTEGER NOT NULL DEFAULT 0,
            last_attempt_at TEXT,
            cleared_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_id, zone_key)
        );
        CREATE TABLE player_wardrobe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop',
            UNIQUE(user_id, item_id)
        );
        CREATE TABLE player_appearance (
            user_id INTEGER PRIMARY KEY,
            outfit_id TEXT,
            hat_id TEXT,
            back_id TEXT,
            title_id TEXT,
            accessory_id TEXT,
            pet_id TEXT,
            aura_id TEXT,
            updated_at TEXT
        );
        """
    )
    connection.create_function("GREATEST", 2, max)
    connection.commit()


@pytest.fixture()
def route_db(tmp_path):
    path = tmp_path / "f030-route.sqlite"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    _create_schema(connection)
    try:
        yield connection, path
    finally:
        if connection:
            connection.close()


class _FakeDbConnectionContext:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def execute(self, statement, parameters=None):
        return self.connection.execute(statement, parameters or ())

    def rollback(self):
        self.connection.rollback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        return False


class _FailingWardrobeDbConnectionContext(_FakeDbConnectionContext):
    def execute(self, statement, parameters=None):
        if statement.startswith("INSERT OR IGNORE INTO player_wardrobe"):
            raise sqlite3.OperationalError("ownership write failure")
        return super().execute(statement, parameters)


@pytest.fixture()
def patched_route(app_module, route_db, monkeypatch):
    connection, _ = route_db
    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _FakeDbConnectionContext(connection),
    )
    state = {"zone_key": "k1_5"}
    monkeypatch.setattr(
        app_module,
        "_adventure_state",
        lambda _uid: [{
            "key": state["zone_key"],
            "seen": 50,
            "unlocked": True,
            "cleared": False,
        }],
    )
    spirit_results = [{"source": "D035_D036_ACCEPTED_FIXTURE"}]
    monkeypatch.setattr(
        app_module,
        "_adventure_map_state",
        lambda _uid, selected_stage_key=None, use_cache=False: {
            "adventure_spirit_unlock_results": spirit_results,
        },
    )
    return connection, state, spirit_results


def _login(client, uid=1):
    with client.session_transaction() as session:
        session["user_id"] = uid


def _set_exam(client, *, zone_key, question_ids, attempt_mode=None):
    exam = {
        "zone_key": zone_key,
        "question_ids": question_ids,
        "started_at": _STARTED_AT,
        "attempt_id": TEST_ATTEMPT_ID,
    }
    if attempt_mode is not None:
        exam["attempt_mode"] = attempt_mode
    with client.session_transaction() as session:
        session["adventure_boss_exam"] = exam


def _seed_reviews(connection, app_module, uid, question_ids, *, grade=5):
    reviewed_at = (_STARTED_AT_DT + _dt.timedelta(seconds=60)).isoformat()
    verdict = "AUTHORITATIVE_PASS" if grade >= 3 else "AUTHORITATIVE_FAIL"
    authoritative_grade = 5 if verdict == "AUTHORITATIVE_PASS" else 0
    connection.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES (?,?,?,?,?)",
        [
            (
                uid,
                question_id,
                grade,
                reviewed_at,
                encode_lord_trial_verdict({
                    "schema": "lord_trial_verdict_v1",
                    "attempt_id": TEST_ATTEMPT_ID,
                    "question_id": int(question_id),
                    "verdict": verdict,
                    "authoritative_grade": authoritative_grade,
                    "judge_version": "lord-trial-map-battle-judge-v1",
                    "reason_code": "f030_route_fixture",
                }),
            )
            for question_id in question_ids
        ],
    )
    connection.commit()


def _finish_one(client, app_module, connection, state, *, zone_key, uid=1, passed=True):
    state["zone_key"] = zone_key
    question_ids = list(range(100000 + uid * 100, 100000 + uid * 100 + 20))
    _seed_reviews(connection, app_module, uid, question_ids, grade=5 if passed else 0)
    _login(client, uid)
    _set_exam(client, zone_key=zone_key, question_ids=question_ids)
    return client.post(
        "/api/adventure/boss/finish",
        json={"correct": 999, "total": 999, "reward_id": "forged-unrelated-id"},
    )


def _assert_common_reward(body, expected_status, expected_item):
    reward = body["reward"]
    assert body["ok"] is True
    assert reward["contract_version"] == CONTRACT_VERSION
    assert reward["status"] == expected_status
    assert reward["coins"] == 0
    assert reward["compensation"] is False
    assert reward["replacement_reward"] is False
    assert reward["auto_equip"] is False
    assert reward["auto_equipped"] is False
    assert reward["combat_power"] == 0
    if expected_item is None:
        assert reward["item_id"] is None
        assert reward["reward_item"] is None
        assert body["reward_item"] is None
    else:
        assert reward["item_id"] == expected_item
        assert reward["reward_item"]["item_id"] == expected_item
        assert reward["reward_item"]["equipped"] is False
        assert reward["reward_item"]["auto_equipped"] is False
        assert reward["reward_item"]["presentation_only"] is True
        assert reward["reward_item"]["combat_power"] == 0
        assert body["reward_item"] == reward["reward_item"]


@pytest.mark.parametrize("zone_key,expected_item", tuple(ZONE_TO_ITEM.items()))
def test_all_ten_route_level_mapping_a_persists_and_reloads(
    client, app_module, route_db, patched_route, zone_key, expected_item
):
    connection, state, spirit_results = patched_route
    response = _finish_one(
        client,
        app_module,
        connection,
        state,
        zone_key=zone_key,
        uid=10 + list(ZONE_TO_ITEM).index(zone_key),
    )
    assert response.status_code == 200
    body = response.get_json()
    _assert_common_reward(body, "GRANTED", expected_item)
    reward = body["reward"]
    assert body["passed"] is True
    assert body["replay"] is False
    assert reward["passed"] is True
    assert reward["first_clear"] is True
    assert reward["entitlement_consumed"] is True
    assert reward["ownership_authority"] == "player_wardrobe"
    assert reward["ownership_persisted"] is True
    assert body["adventure_spirit_unlock_results"] == spirit_results
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=? AND item_id=?",
        (10 + list(ZONE_TO_ITEM).index(zone_key), expected_item),
    ).fetchone()[0] == 1
    appearance = connection.execute(
        "SELECT outfit_id,hat_id,back_id,accessory_id FROM player_appearance WHERE user_id=?",
        (10 + list(ZONE_TO_ITEM).index(zone_key),),
    ).fetchone()
    assert appearance is None

    connection.commit()
    connection.close()
    reloaded = sqlite3.connect(route_db[1])
    reloaded.row_factory = sqlite3.Row
    try:
        row = reloaded.execute(
            "SELECT item_id FROM player_wardrobe WHERE user_id=?",
            (10 + list(ZONE_TO_ITEM).index(zone_key),),
        ).fetchone()
        assert row["item_id"] == expected_item
    finally:
        reloaded.close()


def test_already_owned_is_noop_without_compensation_or_replacement(
    client, app_module, route_db, patched_route
):
    connection, state, _ = patched_route
    uid = 71
    expected_item = ZONE_TO_ITEM["k1_5"]
    connection.execute(
        "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)",
        (uid, expected_item, "before-first-clear", "existing_authoritative_ownership"),
    )
    connection.commit()
    response = _finish_one(client, app_module, connection, state, zone_key="k1_5", uid=uid)
    assert response.status_code == 200
    body = response.get_json()
    _assert_common_reward(body, "ALREADY_OWNED", expected_item)
    reward = body["reward"]
    assert reward["first_clear"] is True
    assert reward["entitlement_consumed"] is True
    assert reward["reward_item"]["new"] is False
    assert reward["reward_item"]["already_owned"] is True
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=? AND item_id=?",
        (uid, expected_item),
    ).fetchone()[0] == 1


def test_replay_has_no_reward_and_no_duplicate_ownership(
    client, app_module, route_db, patched_route
):
    connection, state, _ = patched_route
    uid = 72
    zone_key = "k1_5"
    expected_item = ZONE_TO_ITEM[zone_key]
    connection.execute(
        "INSERT INTO adventure_boss_progress "
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        "last_attempt_at,cleared_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (uid, zone_key, 1, 1, 1, 20, 0, "before", "before", "before"),
    )
    connection.execute(
        "INSERT INTO player_wardrobe(user_id,item_id,obtained_at,source) VALUES(?,?,?,?)",
        (uid, expected_item, "before", "battlefield_boss_first_clear:k1_5"),
    )
    connection.commit()
    state["zone_key"] = zone_key
    question_ids = list(range(120000, 120020))
    _seed_reviews(connection, app_module, uid, question_ids)
    _login(client, uid)
    _set_exam(client, zone_key=zone_key, question_ids=question_ids, attempt_mode="replay")
    response = client.post("/api/adventure/boss/finish", json={})
    assert response.status_code == 200
    body = response.get_json()
    _assert_common_reward(body, "NO_REWARD", None)
    assert body["replay"] is True
    assert body["reward"]["replay"] is True
    assert body["reward"]["first_clear"] is False
    assert body["reward"]["entitlement_consumed"] is False
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=? AND item_id=?",
        (uid, expected_item),
    ).fetchone()[0] == 1


def test_failed_boss_has_no_reward_or_ownership(client, app_module, route_db, patched_route):
    connection, state, _ = patched_route
    response = _finish_one(client, app_module, connection, state, zone_key="k21_25", uid=73, passed=False)
    assert response.status_code == 200
    body = response.get_json()
    assert body["passed"] is False
    _assert_common_reward(body, "NO_REWARD", None)
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=?", (73,)
    ).fetchone()[0] == 0


def test_unknown_zone_fails_closed_and_rolls_back_progress(client, app_module, route_db, patched_route):
    connection, state, _ = patched_route
    zone_key = "unknown-zone"
    state["zone_key"] = zone_key
    question_ids = list(range(130000, 130020))
    _seed_reviews(connection, app_module, 74, question_ids)
    _login(client, 74)
    _set_exam(client, zone_key=zone_key, question_ids=question_ids)
    response = client.post("/api/adventure/boss/finish", json={})
    assert response.status_code == 400
    assert response.get_json() == {"error": "UNKNOWN_ZONE", "ok": False}
    assert connection.execute(
        "SELECT COUNT(*) FROM adventure_boss_progress WHERE user_id=?", (74,)
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=?", (74,)
    ).fetchone()[0] == 0


def test_service_validation_failure_rolls_back_progress_and_keeps_exam(
    client, app_module, route_db, patched_route, monkeypatch
):
    connection, state, _ = patched_route
    question_ids = list(range(140000, 140020))
    _seed_reviews(connection, app_module, 75, question_ids)
    _login(client, 75)
    _set_exam(client, zone_key="k1_5", question_ids=question_ids)

    monkeypatch.setattr(
        app_module,
        "APPEARANCE_DEFS",
        [item for item in app_module.APPEARANCE_DEFS if item["id"] != "robe_dragon"],
    )
    response = client.post("/api/adventure/boss/finish", json={})
    assert response.status_code == 400
    assert response.get_json() == {"error": "MAPPING_A_CATALOG_MISSING", "ok": False}
    assert connection.execute(
        "SELECT COUNT(*) FROM adventure_boss_progress WHERE user_id=?", (75,)
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=?", (75,)
    ).fetchone()[0] == 0
    with client.session_transaction() as session:
        assert session["adventure_boss_exam"]["zone_key"] == "k1_5"


def test_ownership_db_failure_rolls_back_progress_and_has_no_fake_success(
    client, app_module, route_db, patched_route, monkeypatch
):
    connection, state, _ = patched_route
    question_ids = list(range(150000, 150020))
    _seed_reviews(connection, app_module, 76, question_ids)
    _login(client, 76)
    _set_exam(client, zone_key="d7_plus", question_ids=question_ids)

    monkeypatch.setattr(
        app_module,
        "get_db",
        lambda: _FailingWardrobeDbConnectionContext(connection),
    )
    with pytest.raises(sqlite3.OperationalError, match="ownership write failure"):
        client.post("/api/adventure/boss/finish", json={})
    assert connection.execute(
        "SELECT COUNT(*) FROM adventure_boss_progress WHERE user_id=?", (76,)
    ).fetchone()[0] == 0
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=?", (76,)
    ).fetchone()[0] == 0


def test_retry_after_lost_response_converges_to_replay_without_duplicate_reward(
    client, app_module, route_db, patched_route
):
    connection, state, _ = patched_route
    uid = 77
    zone_key = "k6_10"
    expected_item = ZONE_TO_ITEM[zone_key]
    first = _finish_one(client, app_module, connection, state, zone_key=zone_key, uid=uid)
    assert first.status_code == 200
    assert first.get_json()["reward"]["status"] == "GRANTED"
    _set_exam(
        client,
        zone_key=zone_key,
        question_ids=list(range(100000 + uid * 100, 100000 + uid * 100 + 20)),
    )
    second = client.post("/api/adventure/boss/finish", json={})
    assert second.status_code == 200
    body = second.get_json()
    _assert_common_reward(body, "NO_REWARD", None)
    assert body["replay"] is True
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=? AND item_id=?",
        (uid, expected_item),
    ).fetchone()[0] == 1


def test_unauthenticated_finish_cannot_mutate_reward_state(
    client, route_db, patched_route
):
    connection, _, _ = patched_route
    response = client.post("/api/adventure/boss/finish", json={})
    assert response.status_code in (302, 401, 403)
    assert connection.execute("SELECT COUNT(*) FROM player_wardrobe").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM adventure_boss_progress").fetchone()[0] == 0


def test_app_wiring_is_thin_and_reuses_existing_authorities(app_module):
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    route_start = source.index("def adventure_boss_finish()")
    route_end = source.index("\n@app.route(", route_start + 1)
    route = source[route_start:route_end]
    assert "_adventure_boss_record_attempt(" in route
    assert "BattlefieldBossFirstClearSettlement.from_authoritative_attempt" in route
    assert "grant_battlefield_boss_first_clear_reward(" in route
    assert "APPEARANCE_DEFS" in route
    assert "PURE_COSMETIC_PRESENTATION_REGISTRY" in route
    assert "APPEARANCE_EFFECTS" in route
    assert "BATTLEFIELD_BOSS_MAPPING_A_ITEM_BY_ZONE" not in route
    assert "player_appearance" not in route
    assert "_grant_coins(" not in route
    assert "ADVENTURE_FIRST_CLEAR_REWARD_COINS" not in source


def test_route_response_keeps_f028_projection_and_d035_d036_spirit_data(app_module):
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    route_start = source.index("def adventure_boss_finish()")
    route_end = source.index("\n@app.route(", route_start + 1)
    route = source[route_start:route_end]
    assert "reward_result.as_response()" in route
    assert "'reward_item': reward_payload['reward_item']" in route
    assert "**map_state" in route


def test_same_reconciled_source_keeps_b051_verdict_authority_and_f030_reward(
    client, app_module, route_db, patched_route
):
    """The final app.py must preserve B051 judging while settling F030 rewards."""
    connection, state, _ = patched_route
    uid = 81
    zone_key = "k26_30"
    question = {
        "id": 170001,
        "content": "(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]C[answer]))",
        "accepted_moves": [{"x": 3, "y": 3}],
    }
    exam = {"attempt_id": TEST_ATTEMPT_ID, "zone_key": zone_key}
    _canonical, judged = app_module.judge_lord_trial_answer(
        {"moves": [{"x": 3, "y": 3}]}, question=question, exam=exam
    )
    assert judged.result == "CORRECT"
    assert judged.authoritative_grade == 5

    question_ids = list(range(170001, 170021))
    reviewed_at = (_STARTED_AT_DT + _dt.timedelta(seconds=60)).isoformat()
    rows = []
    for question_id in question_ids:
        verdict = app_module.build_lord_trial_verdict(
            attempt_id=TEST_ATTEMPT_ID,
            question_id=question_id,
            judge=judged,
        )
        rows.append(
            (
                uid,
                question_id,
                0,  # forged/low client scheduling grade; verdict remains server-owned
                reviewed_at,
                encode_lord_trial_verdict(verdict),
            )
        )
    connection.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES (?,?,?,?,?)",
        rows,
    )
    connection.commit()

    state["zone_key"] = zone_key
    _login(client, uid)
    _set_exam(client, zone_key=zone_key, question_ids=question_ids)
    response = client.post(
        "/api/adventure/boss/finish",
        json={"correct": 0, "total": 20, "grade": 0},
    )

    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["passed"] is True
    assert body["correct"] == 20
    assert body["reward"]["item_id"] == "back_pack"
    assert connection.execute(
        "SELECT COUNT(*) FROM player_wardrobe WHERE user_id=? AND item_id=?",
        (uid, "back_pack"),
    ).fetchone()[0] == 1
