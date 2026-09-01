"""Focused Incident 019B progression-continuity compatibility contracts."""

from __future__ import annotations

import os
import sqlite3
import sys
import types

import pytest

from adventure_progress_compatibility import (
    BASELINE_VERSION,
    build_compatibility_census,
    frozen_historical_memberships,
    frozen_reconstruction_classes,
    frozen_source_masks,
    populate_frozen_historical_baseline,
    trusted_current_memberships,
    visible_adventure_question_ids,
)
from migrations.adventure_historical_mastery_v1 import (
    BASELINE_TABLE_NAME,
    CUTOFF_DOMAIN,
    CUTOFF_LITERAL,
    CUTOFF_OPERATOR,
    GRANDFATHERED_ENTITLEMENT_SOURCE,
    PRECHANGE_PREDICATE_REFERENCE_SHA,
    RECONSTRUCTION_CLASS_CONSERVATIVE,
    RECONSTRUCTION_CLASS_EXACT,
    SOURCE_LAST_GRADE_MASK,
    SOURCE_PROGRESS_CREDITED_MASK,
    SOURCE_REVIEW_GRADE_MASK,
    STATUS_CAPTURING,
    TABLE_NAME,
    upgrade,
    validate_schema,
)


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
    return conn


def _review(conn, user_id, question_id, grade=3, reviewed_at="2026-08-01T00:00:00", source_context="practice"):
    conn.execute(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) VALUES (?,?,?,?,?)",
        (user_id, question_id, grade, reviewed_at, source_context),
    )


def _card(conn, user_id, question_id, last_grade=0, progress_credited=0):
    conn.execute(
        "INSERT INTO srs_cards(user_id,question_id,last_grade,progress_credited,updated_at) VALUES (?,?,?,?,?)",
        (user_id, question_id, last_grade, progress_credited, "2026-09-01T00:00:00"),
    )


@pytest.fixture()
def conn():
    value = _connection()
    yield value
    value.close()


def test_additive_schema_is_valid_and_idempotent(conn):
    first = upgrade(conn)
    second = upgrade(conn)

    assert first["valid"] is True
    assert second["valid"] is True
    assert validate_schema(conn)["valid"] is True
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?,?)",
        ("adventure_historical_mastery", "adventure_historical_mastery_baseline"),
    ).fetchall()


def test_capture_reconstructs_prechange_predicate_with_strict_cutoff(conn):
    # 10: qualifying review strictly before the cutoff -> exactly reconstructable.
    _review(conn, 1, 10, reviewed_at="2026-08-29T13:17:29")
    # 11: review lands exactly ON the cutoff.  The operator is strict ``<``, so
    # this is current-side evidence and the card flag it produced must not be
    # grandfathered.
    _review(conn, 1, 11, reviewed_at=CUTOFF_LITERAL)
    _card(conn, 1, 11, last_grade=0, progress_credited=1)
    # 12: only qualifying evidence is after the cutoff -> POST_CUTOFF_ONLY.
    _review(conn, 1, 12, reviewed_at="2026-08-29T13:17:31", source_context="mbv1:future")
    _card(conn, 1, 12, last_grade=3, progress_credited=0)
    # 13: never qualified under any branch.
    _card(conn, 1, 13, last_grade=2, progress_credited=0)
    conn.commit()

    result = populate_frozen_historical_baseline(conn, question_ids={10, 11, 12, 13}, captured_at="2026-09-01T00:00:00")
    conn.commit()

    assert result["membership_count"] == 1
    assert result["exact_membership_count"] == 1
    assert result["conservative_membership_count"] == 0
    assert result["post_cutoff_only_count"] == 2
    assert frozen_historical_memberships(conn, user_id=1) == {10}
    masks = frozen_source_masks(conn)
    assert masks[(1, 10)] == SOURCE_REVIEW_GRADE_MASK
    assert (1, 11) not in masks
    assert (1, 12) not in masks
    assert (1, 13) not in masks
    classes = frozen_reconstruction_classes(conn)
    assert classes[(1, 10)] == RECONSTRUCTION_CLASS_EXACT


def test_overlap_is_deduplicated_and_every_source_branch_is_preserved(conn):
    _review(conn, 2, 20, reviewed_at="2026-08-01T00:00:00")
    _card(conn, 2, 20, last_grade=3, progress_credited=1)
    conn.commit()

    populate_frozen_historical_baseline(conn, question_ids={20}, captured_at="2026-09-01T00:00:00")
    conn.commit()

    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_historical_mastery WHERE user_id=2 AND question_id=20",
    ).fetchone()[0] == 1
    # Deduplicated to one visible membership, but all three historical branches
    # remain independently auditable.
    assert frozen_source_masks(conn)[(2, 20)] == (
        SOURCE_REVIEW_GRADE_MASK
        | SOURCE_PROGRESS_CREDITED_MASK
        | SOURCE_LAST_GRADE_MASK
    )


def test_orphan_card_memberships_are_conservative_not_exact(conn):
    # No review row at all: undated legacy compatibility state.  Preserved by
    # explicit Owner continuity policy, but never called exact.
    _card(conn, 6, 60, last_grade=0, progress_credited=1)
    _card(conn, 6, 61, last_grade=5, progress_credited=0)
    conn.commit()

    result = populate_frozen_historical_baseline(conn, question_ids={60, 61}, captured_at="2026-09-01T00:00:00")
    conn.commit()

    assert result["exact_membership_count"] == 0
    assert result["conservative_membership_count"] == 2
    assert frozen_historical_memberships(conn, user_id=6) == {60, 61}
    classes = frozen_reconstruction_classes(conn)
    assert classes[(6, 60)] == RECONSTRUCTION_CLASS_CONSERVATIVE
    assert classes[(6, 61)] == RECONSTRUCTION_CLASS_CONSERVATIVE
    masks = frozen_source_masks(conn)
    assert masks[(6, 60)] == SOURCE_PROGRESS_CREDITED_MASK
    assert masks[(6, 61)] == SOURCE_LAST_GRADE_MASK


def test_frozen_runner_is_one_time_and_future_cards_cannot_grow_baseline(conn):
    _card(conn, 3, 30, progress_credited=1)
    conn.commit()
    first = populate_frozen_historical_baseline(conn, question_ids={30, 31}, captured_at="2026-09-01T00:00:00")
    conn.commit()

    _card(conn, 3, 31, last_grade=3)
    conn.commit()
    second = populate_frozen_historical_baseline(conn, question_ids={30, 31}, captured_at="2026-09-02T00:00:00")

    assert first["already_frozen"] is False
    assert second["already_frozen"] is True
    assert frozen_historical_memberships(conn, user_id=3) == {30}


def test_request_read_path_never_uses_live_qualifying_cards_as_historical_fallback(conn):
    upgrade(conn)
    _card(conn, 4, 40, last_grade=5, progress_credited=1)
    conn.commit()

    assert visible_adventure_question_ids(conn, 4) == set()


def test_request_read_path_ignores_incomplete_or_unfrozen_baseline(conn):
    upgrade(conn)
    conn.execute(
        f"INSERT INTO {BASELINE_TABLE_NAME} "
        "(baseline_version, cutoff_literal, captured_at, frozen_at, status, membership_count, "
        "source_rule_version, expected_membership_count, actual_membership_count, "
        "membership_fingerprint, ready_at, failure_reason, predicate_reference_sha, "
        "cutoff_operator, cutoff_domain, exact_membership_count, conservative_membership_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (BASELINE_VERSION, CUTOFF_LITERAL, "2026-09-01T00:00:00", "", STATUS_CAPTURING, 0,
         "prechange_display_predicate_v1", 0, 0, "", None, None,
         PRECHANGE_PREDICATE_REFERENCE_SHA, CUTOFF_OPERATOR, CUTOFF_DOMAIN, 0, 0),
    )
    conn.execute(
        f"INSERT INTO {TABLE_NAME} "
        "(user_id, question_id, baseline_version, source_mask, entitlement_source, "
        "captured_at, cutoff_literal, reconstruction_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (4, 41, BASELINE_VERSION, SOURCE_PROGRESS_CREDITED_MASK,
         GRANDFATHERED_ENTITLEMENT_SOURCE, "2026-09-01T00:00:00", CUTOFF_LITERAL,
         RECONSTRUCTION_CLASS_CONSERVATIVE),
    )
    conn.commit()

    assert frozen_historical_memberships(conn, user_id=4) == set()
    assert visible_adventure_question_ids(conn, 4) == set()


def test_trusted_current_set_is_preserved_and_unions_with_frozen_baseline(conn):
    _card(conn, 5, 50, progress_credited=1)
    _review(conn, 5, 51, reviewed_at="2026-09-01T00:00:00", source_context="mbv1:server")
    _review(conn, 5, 52, reviewed_at="2026-09-01T00:00:00", source_context="practice")
    conn.commit()
    populate_frozen_historical_baseline(conn, question_ids={50, 51, 52}, captured_at="2026-09-01T00:00:00")
    conn.commit()

    assert trusted_current_memberships(conn, user_id=5) == {51}
    assert visible_adventure_question_ids(conn, 5) == {50, 51}


def test_census_is_set_aware_and_r1_equivalent_union_is_419(conn):
    for question_id in range(1, 420):
        _review(conn, 7, question_id, reviewed_at="2026-08-01T00:00:00", source_context="practice")
    for question_id in range(1, 24):
        _review(conn, 7, question_id, reviewed_at="2026-09-01T00:00:00", source_context="mbv1:r1")
    for question_id in range(1, 420):
        _card(conn, 7, question_id, progress_credited=1)
    conn.commit()
    populate_frozen_historical_baseline(conn, question_ids=set(range(1, 420)), captured_at="2026-09-01T00:00:00")
    conn.commit()

    census = build_compatibility_census(
        conn,
        {"d3_4": set(range(1, 2288))},
        historical_mode="frozen",
    )

    assert census["zone_denominators"]["d3_4"] == 2287
    assert census["total_frozen_historical_memberships"] == 419
    assert census["total_trusted_current_memberships"] == 23
    assert census["total_overlap"] == 23
    assert census["total_historical_only"] == 396
    assert census["total_visible_union"] == 419
    assert census["visible_decrease_count_after_fix"] == 0


def test_census_reports_sticky_ceiling_memberships_without_double_counting(conn):
    _card(conn, 8, 80, last_grade=3, progress_credited=1)
    _card(conn, 8, 81, progress_credited=1)
    _card(conn, 8, 82, last_grade=5)
    conn.commit()

    census = build_compatibility_census(
        conn,
        {"d3_4": {80, 81, 82}},
        historical_mode="preview",
    )

    assert census["sticky_ceiling_memberships_included"] == 2
    assert census["total_frozen_historical_memberships"] == 2
    assert census["total_visible_union"] == 2


def test_frozen_census_ignores_cards_created_after_baseline(conn):
    _card(conn, 81, 810, progress_credited=1)
    conn.commit()
    populate_frozen_historical_baseline(conn, question_ids={810, 811}, captured_at="2026-09-01T00:00:00")
    conn.commit()
    _card(conn, 81, 811, last_grade=5)
    conn.commit()

    census = build_compatibility_census(
        conn,
        {"d3_4": {810, 811}},
        historical_mode="frozen",
    )

    assert census["total_frozen_historical_memberships"] == 1
    assert census["sticky_ceiling_memberships_included"] == 1


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
        module.grimoire_bp = Blueprint("incident019b_grimoire_stub", __name__)
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
    os.environ.setdefault("SECRET_KEY", "incident019b-test-only-secret")
    _install_app_import_stubs()
    import app

    app.app.config["TESTING"] = True
    return app


def test_compatibility_mastery_does_not_synthesize_defeat_or_stars(app_module, monkeypatch):
    conn = _connection()
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
    questions = [
        {"id": question_id, "enabled": True, "topic": "1圍棋新手村"}
        for question_id in range(1, 11)
    ]
    for question in questions:
        _card(conn, 9, question["id"], progress_credited=1)
    conn.commit()
    populate_frozen_historical_baseline(conn, question_ids={q["id"] for q in questions}, captured_at="2026-09-01T00:00:00")
    conn.commit()

    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: questions)
    monkeypatch.setattr(app_module, "is_premium", lambda uid=None: True)
    monkeypatch.setattr(
        app_module,
        "_resolve_adventure_effective_start_zone",
        lambda _conn, _uid, unlock_rows=None: "k26_30",
    )

    zone = next(zone for zone in app_module._adventure_state(9) if zone["key"] == "k26_30")
    assert zone["seen"] == 10
    assert zone["defeated"] == 0
    assert zone["stars"] == 0
    assert zone["cleared"] is False
    assert zone["boss_ready"] is True
    conn.close()
