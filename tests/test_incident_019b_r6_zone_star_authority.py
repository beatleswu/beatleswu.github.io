"""Incident019B R6 Zone-star authority and continuity contracts."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

import pytest

from adventure_zone_star_progression import (
    AUTHORITATIVE_BOSS_CLEAR_SOURCE,
    AUTHORITATIVE_ZONE_STAR_SOURCE,
    award_zone_star_from_boss_clear,
    award_zone_star_from_authoritative_answer,
    load_zone_star_rows,
)
from migrations.adventure_zone_star_progression_v1 import (
    EARNINGS_TABLE_NAME,
    PROGRESS_TABLE_NAME,
    upgrade,
    validate_schema,
)


ROOT = Path(__file__).resolve().parent.parent


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE review_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source_context TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE srs_cards (
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            last_grade INTEGER,
            progress_credited INTEGER,
            updated_at TEXT,
            PRIMARY KEY (user_id, question_id)
        )"""
    )
    conn.execute(
        """CREATE TABLE adventure_boss_progress (
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
        )"""
    )
    conn.execute(
        """CREATE TABLE adventure_zone_unlocks (
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            source TEXT,
            start_zone_key TEXT,
            unlocked_at TEXT,
            PRIMARY KEY (user_id, zone_key)
        )"""
    )
    return conn


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
        module.grimoire_bp = Blueprint("incident019b_r6_grimoire_stub", __name__)
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


@pytest.fixture(scope="module")
def app_module():
    os.environ.setdefault("SECRET_KEY", "incident019b-r6-test-only-secret")
    _install_app_import_stubs()
    import app

    app.app.config["TESTING"] = True
    return app


def test_zone_star_schema_is_explicit_additive_and_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    first = upgrade(conn)
    second = upgrade(conn)
    assert first["valid"] is True
    assert second["valid"] is True
    assert validate_schema(conn)["valid"] is True
    assert PROGRESS_TABLE_NAME in first["created"]
    assert EARNINGS_TABLE_NAME in first["created"]
    conn.close()


def test_one_two_three_stars_are_server_event_reachable_and_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade(conn)

    results = [
        award_zone_star_from_authoritative_answer(
            conn, 17, "k26_30", f"submission-{index}",
            f"2026-09-01T00:00:0{index}",
        )
        for index in range(1, 4)
    ]
    duplicate = award_zone_star_from_authoritative_answer(
        conn, 17, "k26_30", "submission-1", "2026-09-01T00:01:00"
    )
    saturated = award_zone_star_from_authoritative_answer(
        conn, 17, "k26_30", "submission-4", "2026-09-01T00:02:00"
    )

    assert [result["stars"] for result in results] == [1, 2, 3]
    assert all(result["source"] == AUTHORITATIVE_ZONE_STAR_SOURCE for result in results)
    assert duplicate["status"] == "duplicate"
    assert duplicate["awarded"] is False
    assert saturated["status"] == "complete"
    assert conn.execute(
        f"SELECT earned_stars FROM {PROGRESS_TABLE_NAME} "
        "WHERE user_id=17 AND zone_key='k26_30'"
    ).fetchone()[0] == 3
    assert conn.execute(
        f"SELECT COUNT(*) FROM {EARNINGS_TABLE_NAME} "
        "WHERE user_id=17 AND zone_key='k26_30'"
    ).fetchone()[0] == 3
    conn.close()


def test_boss_clear_is_an_explicit_first_zone_star_event():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade(conn)

    result = award_zone_star_from_boss_clear(
        conn, 22, "k26_30", "adventure:first_clear:22:k26_30",
        "2026-09-01T00:00:00",
    )
    duplicate = award_zone_star_from_boss_clear(
        conn, 22, "k26_30", "adventure:first_clear:22:k26_30",
        "2026-09-01T00:00:01",
    )
    assert result["status"] == "awarded"
    assert result["stars"] == 1
    assert result["source"] == AUTHORITATIVE_BOSS_CLEAR_SOURCE
    assert duplicate["status"] == "duplicate"
    assert conn.execute(
        f"SELECT source FROM {EARNINGS_TABLE_NAME} WHERE user_id=22"
    ).fetchone()[0] == AUTHORITATIVE_BOSS_CLEAR_SOURCE
    conn.close()


def test_zone_awards_never_mutate_boss_progress_or_consume_history():
    conn = _connection()
    conn.execute(
        "INSERT INTO adventure_boss_progress "
        "(user_id,zone_key,cleared,stars,attempts,best_score) VALUES (?,?,?,?,?,?)",
        (18, "k26_30", 1, 1, 2, 20),
    )
    upgrade(conn)
    before = tuple(conn.execute(
        "SELECT cleared,stars,attempts,best_score FROM adventure_boss_progress "
        "WHERE user_id=18 AND zone_key='k26_30'"
    ).fetchone())

    # This is the only admissible input: a server-owned settlement identity.
    award_zone_star_from_authoritative_answer(
        conn, 18, "k26_30", "server-settlement-1", "2026-09-01T00:00:00"
    )
    after = tuple(conn.execute(
        "SELECT cleared,stars,attempts,best_score FROM adventure_boss_progress "
        "WHERE user_id=18 AND zone_key='k26_30'"
    ).fetchone())
    assert after == before

    # Historical question evidence alone has no Zone-star row or authority.
    conn.execute(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES (?,?,?,?,?)",
        (19, 1001, 5, "2026-08-01T00:00:00", "practice"),
    )
    conn.commit()
    assert load_zone_star_rows(conn, 19) == {}
    assert conn.execute(
        f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME} WHERE user_id=19"
    ).fetchone()[0] == 0
    conn.close()


def test_app_bridge_accepts_only_server_settled_adventure_answers(app_module):
    from review_contracts import EXTERNAL_AUTHORITATIVE_MAP_BATTLE

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    upgrade(conn)
    settled = {"battle_zone_key": "k26_30"}

    ignored = app_module._adventure_zone_star_from_settled_answer(
        conn,
        21,
        grade=5,
        combat_settlement_context="practice",
        authoritative_submission=settled,
        submission_id="client-practice-1",
        earned_at="2026-09-01T00:00:00",
    )
    assert ignored is None
    assert load_zone_star_rows(conn, 21) == {}

    awarded = app_module._adventure_zone_star_from_settled_answer(
        conn,
        21,
        grade=5,
        combat_settlement_context=EXTERNAL_AUTHORITATIVE_MAP_BATTLE,
        authoritative_submission=settled,
        submission_id="server-map-battle-1",
        earned_at="2026-09-01T00:00:01",
    )
    assert awarded["status"] == "awarded"
    assert awarded["stars"] == 1
    conn.close()


def test_public_projection_preserves_legacy_visible_star_without_new_authority(
    app_module, monkeypatch
):
    from adventure_progress_compatibility import populate_frozen_historical_baseline

    conn = _connection()
    questions = [
        {"id": question_id, "enabled": True, "topic": "1圍棋新手村"}
        for question_id in range(2001, 2004)
    ]
    for question in questions:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
            "VALUES (?,?,?,?,?)",
            (20, question["id"], 5, "2026-08-01T00:00:00", "practice"),
        )
    conn.execute(
        "INSERT INTO adventure_boss_progress "
        "(user_id,zone_key,cleared,stars,attempts,best_score) VALUES (?,?,?,?,?,?)",
        (20, "k26_30", 1, 2, 2, 20),
    )
    upgrade(conn)
    populate_frozen_historical_baseline(
        conn, question_ids={question["id"] for question in questions},
        captured_at="2026-09-01T00:00:00",
    )
    conn.commit()

    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: questions)
    monkeypatch.setattr(app_module, "is_premium", lambda uid=None: True)
    monkeypatch.setattr(
        app_module,
        "_resolve_adventure_effective_start_zone",
        lambda _conn, _uid, unlock_rows=None: "k26_30",
    )

    zone = next(zone for zone in app_module._adventure_state(20) if zone["key"] == "k26_30")
    assert zone["stars"] == 2
    assert zone["legacy_visible_stars"] == 2
    assert zone["zone_authority_stars"] == 0
    assert zone["cleared"] is True
    assert conn.execute(
        f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME} WHERE user_id=20"
    ).fetchone()[0] == 0
    conn.close()


def test_replenish_stars_selects_under_three_star_zone_and_quest_uses_authority(app_module):
    zones = [
        {
            "key": "k26_30", "unlocked": True, "cleared": True,
            "stars": 1, "zone_authority_stars": 1,
        },
    ]
    primary = app_module._adventure_primary_action_payload(zones, None)
    secondary = app_module._adventure_secondary_action_payload(zones, primary)
    assert primary == {"kind": "replay_completed", "zone_key": "k26_30"}
    assert secondary == {"kind": "replenish_stars", "zone_key": "k26_30"}

    script = """
const defs = require('./js/e9/quest_definitions.js');
const evaluator = require('./js/e9/quest_evaluator.js');
const storeApi = require('./js/e9/quest_store.js');
global.E9.isLifecycleCurrent = () => true;
global.E9.Adapters = {
  AdventureState: { fetchAdventureState: () => Promise.resolve({ok: true, data: {
    zones: [{stars: 3, zone_authority_stars: 0, cleared: true}]
  }}) },
  ActivityState: { fetchDailyChallenge: () => Promise.resolve({ok: true, data: {submitted: false}}) }
};
const store = storeApi.createQuestStore(1);
store.load().then(() => {
  const results = store.evaluate(defs.definitions, evaluator);
  if (results[0].completed !== true || results[1].completed !== false || results[1].current !== 0) process.exit(1);
  const completed = evaluator.evaluateQuest(defs.definitions[1], {
    adventure: { authoritativeMaxStars: 3 },
  });
  if (completed.completed !== true || completed.current !== 3) process.exit(1);
  console.log('authority quest projection passed');
}).catch(() => process.exit(1));
"""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr or result.stdout
