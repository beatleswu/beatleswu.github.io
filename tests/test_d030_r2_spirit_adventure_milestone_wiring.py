"""D030-R2 proof for the Adventure-owned Spirit milestone caller wiring."""

from __future__ import annotations

import datetime as dt
import sqlite3
import sys
import types

import pytest

from lord_trial_answer_service import encode_lord_trial_verdict
from migrations.companion_operations_v1 import upgrade as upgrade_companion_schema
from migrations.domain_event_outbox_v1 import upgrade as upgrade_domain_event_outbox


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
        module.grimoire_bp = Blueprint("grimoire_stub_d030_r2", __name__)
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
    import app as module

    return module


class _DbContext:
    """Caller-owned commit/rollback wrapper around one disposable SQLite DB."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        return self._conn.execute(sql, params or ())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        return False


def _new_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.create_function("GREATEST", 2, max)
    conn.executescript(
        """
        CREATE TABLE review_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source_context TEXT NOT NULL DEFAULT 'practice'
        );
        CREATE TABLE adventure_boss_progress(
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
            PRIMARY KEY(user_id, zone_key)
        );
        CREATE TABLE adventure_zone_unlocks(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'placement',
            PRIMARY KEY(user_id, zone_key)
        );
        CREATE TABLE user_stats(
            user_id INTEGER PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE currency_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE user_pets(
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
        );
        CREATE TABLE pet_inventory(
            user_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, item_key)
        );
        CREATE TABLE player_wardrobe(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'drop',
            UNIQUE(user_id, item_id)
        );
        CREATE TABLE pet_action_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE pet_collection(
            user_id INTEGER NOT NULL,
            pet_key TEXT NOT NULL,
            nickname TEXT,
            level INTEGER NOT NULL DEFAULT 1,
            xp INTEGER NOT NULL DEFAULT 0,
            fullness INTEGER NOT NULL DEFAULT 60,
            affection INTEGER NOT NULL DEFAULT 10,
            selected_at TEXT NOT NULL,
            last_fed_at TEXT,
            last_interacted_at TEXT,
            last_pet_at TEXT,
            last_train_at TEXT,
            daily_key TEXT,
            daily_bond INTEGER NOT NULL DEFAULT 0,
            daily_train_xp INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, pet_key)
        );
        """
    )
    upgrade_companion_schema(conn)
    upgrade_domain_event_outbox(conn)
    conn.commit()
    return conn


@pytest.fixture()
def runtime(app_module, monkeypatch):
    conn = _new_db()
    state = {"zone_key": "k11_15"}

    def fake_get_db():
        return _DbContext(conn)

    def fake_adventure_state(_uid):
        return [{
            "key": state["zone_key"],
            "seen": 50,
            "unlocked": True,
            "cleared": False,
        }]

    monkeypatch.setattr(app_module, "get_db", fake_get_db)
    monkeypatch.setattr(app_module, "_adventure_state", fake_adventure_state)
    monkeypatch.setattr(app_module, "_adventure_map_state", lambda *args, **kwargs: {})
    app_module.app.config["TESTING"] = True
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = True
    try:
        yield conn, state
    finally:
        conn.close()


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id


def _set_exam(client, *, zone_key, attempt_id, question_ids):
    started_at = (dt.datetime.now() - dt.timedelta(minutes=5)).isoformat()
    with client.session_transaction() as session:
        session["adventure_boss_exam"] = {
            "zone_key": zone_key,
            "question_ids": question_ids,
            "started_at": started_at,
            "attempt_id": attempt_id,
        }
    return started_at


def _seed_pass(conn, user_id, attempt_id, question_ids, started_at):
    reviewed_at = (dt.datetime.fromisoformat(started_at) + dt.timedelta(seconds=30)).isoformat()
    conn.executemany(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES(?,?,?,?,?)",
        [
            (
                user_id,
                question_id,
                5,
                reviewed_at,
                encode_lord_trial_verdict({
                    "schema": "lord_trial_verdict_v1",
                    "attempt_id": attempt_id,
                    "question_id": question_id,
                    "verdict": "AUTHORITATIVE_PASS",
                    "authoritative_grade": 5,
                    "judge_version": "lord-trial-map-battle-judge-v1",
                    "reason_code": "d030_r2_fixture",
                }),
            )
            for question_id in question_ids
        ],
    )
    conn.commit()


MILESTONE_CASES = (
    ("k11_15", "starpath_antlerling"),
    ("k1_5", "fatty"),
    ("d3_4", "obsidian_bastion"),
)
MAPPING_A_ITEMS = {
    "k11_15": "robe_crane",
    "k1_5": "robe_dragon",
    "d3_4": "back_cloak",
}


def test_real_adventure_settlement_unlocks_all_three_mapped_spirits(
    app_module, client, runtime
):
    conn, state = runtime
    user_id = 30201
    _login(client, user_id)

    for index, (zone_key, spirit_id) in enumerate(MILESTONE_CASES, start=1):
        state["zone_key"] = zone_key
        attempt_id = f"d030-r2-attempt-{index}"
        question_ids = list(range(index * 1000, index * 1000 + 20))
        started_at = _set_exam(
            client,
            zone_key=zone_key,
            attempt_id=attempt_id,
            question_ids=question_ids,
        )
        _seed_pass(conn, user_id, attempt_id, question_ids, started_at)

        response = client.post("/api/adventure/boss/finish", json={
            "zone_key": "forged-client-zone",
            "cleared": True,
            "spirit_id": "ink_drop_kelpie",
        })
        assert response.status_code == 200
        body = response.get_json()
        assert body["passed"] is True
        assert body["reward"]["first_clear"] is True
        assert body["reward"]["status"] == "GRANTED"
        assert body["reward"]["item_id"] == MAPPING_A_ITEMS[zone_key]
        assert body["reward"]["ownership_authority"] == "player_wardrobe"
        current_unlock = next(
            item for item in body["adventure_spirit_unlock_results"]
            if item["zone_key"] == zone_key
        )
        assert current_unlock["spirit_id"] == spirit_id
        assert conn.execute(
            "SELECT cleared FROM adventure_boss_progress WHERE user_id=? AND zone_key=?",
            (user_id, zone_key),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE user_id=? AND pet_key=?",
            (user_id, spirit_id),
        ).fetchone()[0] == 1

    owned = conn.execute(
        "SELECT pet_key FROM pet_collection WHERE user_id=? ORDER BY pet_key",
        (user_id,),
    ).fetchall()
    assert [row[0] for row in owned] == sorted(spirit_id for _, spirit_id in MILESTONE_CASES)
    assert conn.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=? AND operation_type=?",
        (user_id, "SPIRIT_UNLOCK"),
    ).fetchone()[0] == 3
    assert conn.execute(
        "SELECT qty FROM pet_inventory WHERE user_id=? AND item_key='go_spirit_candy'",
        (user_id,),
    ).fetchone()[0] == 9
    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_zone_unlocks WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM user_pets WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0


def test_non_milestone_first_clear_settles_mapping_a_without_spirit_grant(
    app_module, client, runtime
):
    conn, state = runtime
    user_id = 30206
    zone_key = "k26_30"
    question_ids = list(range(6000, 6020))
    _login(client, user_id)
    state["zone_key"] = zone_key
    started_at = _set_exam(
        client, zone_key=zone_key, attempt_id="d030-r2-non-milestone", question_ids=question_ids
    )
    _seed_pass(conn, user_id, "d030-r2-non-milestone", question_ids, started_at)

    response = client.post("/api/adventure/boss/finish", json={"spirit_id": "fatty"})

    assert response.status_code == 200
    body = response.get_json()
    assert body["passed"] is True
    assert body["reward"]["status"] == "GRANTED"
    assert body["reward"]["item_id"] == "back_pack"
    assert {item["result_state"] for item in body["adventure_spirit_unlock_results"]} == {
        "NOT_ELIGIBLE"
    }
    assert conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0


def test_exact_replay_and_later_recheck_do_not_unlock_again(app_module, client, runtime):
    conn, state = runtime
    user_id = 30202
    _login(client, user_id)
    state["zone_key"] = "k11_15"
    question_ids = list(range(2000, 2020))
    attempt_id = "d030-r2-replay-1"
    started_at = _set_exam(
        client, zone_key="k11_15", attempt_id=attempt_id, question_ids=question_ids
    )
    _seed_pass(conn, user_id, attempt_id, question_ids, started_at)
    assert client.post("/api/adventure/boss/finish", json={}).status_code == 200

    before = {
        "owned": conn.execute(
            "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
        ).fetchone()[0],
        "operations": conn.execute(
            "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (user_id,)
        ).fetchone()[0],
        "lineage": conn.execute(
            "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=?",
            (str(user_id),),
        ).fetchone()[0],
    }

    replay = app_module._apply_adventure_spirit_milestone_catch_up(conn, user_id)
    conn.commit()
    assert [result["status"] for result in replay] == ["REPLAY", "NOT_ELIGIBLE", "NOT_ELIGIBLE"]
    assert sum(result["new_unlock_count"] for result in replay) == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchone()[0] == before["owned"]
    assert conn.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (user_id,)
    ).fetchone()[0] == before["operations"]
    assert conn.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=?", (str(user_id),)
    ).fetchone()[0] == before["lineage"]

    later = app_module._apply_adventure_spirit_milestone_catch_up(conn, user_id)
    conn.commit()
    assert [result["status"] for result in later] == ["REPLAY", "NOT_ELIGIBLE", "NOT_ELIGIBLE"]
    assert sum(result["new_unlock_count"] for result in later) == 0


def test_historical_catchup_uses_only_persisted_clears(app_module, client, runtime):
    conn, state = runtime
    user_id = 30203
    for zone_key, _spirit_id in MILESTONE_CASES:
        conn.execute(
            "INSERT INTO adventure_boss_progress(user_id,zone_key,cleared) VALUES(?,?,1)",
            (user_id, zone_key),
        )
    conn.commit()
    _login(client, user_id)
    state["zone_key"] = "k1_5"
    question_ids = list(range(3000, 3020))
    attempt_id = "d030-r2-historical"
    started_at = _set_exam(
        client, zone_key="k1_5", attempt_id=attempt_id, question_ids=question_ids
    )
    _seed_pass(conn, user_id, attempt_id, question_ids, started_at)

    response = client.post("/api/adventure/boss/finish", json={})
    assert response.status_code == 200
    assert response.get_json()["replay"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 3


def test_caller_rollback_removes_clear_and_spirit_unlock_together(app_module, runtime):
    conn, _state = runtime
    user_id = 30204
    with pytest.raises(RuntimeError, match="forced D030 rollback"):
        with _DbContext(conn) as caller_conn:
            app_module._adventure_boss_record_attempt(
                caller_conn,
                user_id,
                "k11_15",
                True,
                20,
                0,
                "2026-08-27T12:00:00",
            )
            results = app_module._apply_adventure_spirit_milestone_catch_up(
                caller_conn, user_id
            )
            assert results[0]["status"] == "UNLOCKED"
            raise RuntimeError("forced D030 rollback")

    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_boss_progress WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM domain_event_outbox WHERE player_id=?", (str(user_id),)
    ).fetchone()[0] == 0


def test_non_adventure_facts_and_client_payload_do_not_unlock(app_module, runtime):
    conn, _state = runtime
    user_id = 30205
    conn.executescript(
        """
        CREATE TABLE monster_defeats(user_id INTEGER, defeated INTEGER);
        CREATE TABLE battlefield_bosses(user_id INTEGER, defeated INTEGER);
        CREATE TABLE quest_completions(user_id INTEGER, completed INTEGER);
        """
    )
    conn.execute("INSERT INTO monster_defeats VALUES(?,1)", (user_id,))
    conn.execute("INSERT INTO battlefield_bosses VALUES(?,1)", (user_id,))
    conn.execute("INSERT INTO quest_completions VALUES(?,1)", (user_id,))
    conn.commit()

    results = app_module._apply_adventure_spirit_milestone_catch_up(conn, user_id)
    conn.commit()
    assert [result["status"] for result in results] == [
        "NOT_ELIGIBLE", "NOT_ELIGIBLE", "NOT_ELIGIBLE"
    ]
    assert sum(result["new_unlock_count"] for result in results) == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM pet_collection WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM companion_operations WHERE user_id=?", (user_id,)
    ).fetchone()[0] == 0
