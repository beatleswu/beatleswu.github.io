"""Legacy continuity across the Owner-locked Zone progression change.

The Owner lock is that no legitimate historical progress may disappear
because the authority model changed. Two facts make this safe without any
schema change or backfill:

* The public ``stars`` field is already ``max(zone_authority_stars,
  legacy_visible_stars)``, where the legacy value is the grandfathered
  read-only projection of ``adventure_boss_progress.stars``.
* A legacy Boss clear always wrote ``stars = GREATEST(stars, 1)``, so every
  historically cleared Zone still projects at least one star. Moving the
  next-Zone unlock from "previous Zone cleared" to "previous Zone has its
  first star" therefore cannot re-lock anything that was already open.

These tests exercise ``_adventure_state`` -- the real public projection -- so
the continuity claim is proven on the surface players actually see.
"""

from __future__ import annotations

import sqlite3
import sys
import types

import pytest

from migrations.adventure_zone_star_progression_v1 import (
    PROGRESS_TABLE_NAME,
    upgrade,
)

ZONE1 = "k26_30"
ZONE2 = "k21_25"
ZONE1_TOPIC = "1圍棋新手村"
ZONE2_TOPIC = "3史萊姆平原"


def _install_app_import_stubs():
    for name, attrs in (
        ("katago_explain", {"KataGoExplainer": type("K", (), {})}),
        ("explain_overrides", {"get_override": lambda *a, **k: None}),
        ("question_taxonomy", {"get_taxonomy": lambda *a, **k: {}}),
        ("monster_taxonomy", {
            "get_monster_taxonomy": lambda *a, **k: {},
            "mark_encounters": lambda *a, **k: None,
        }),
        ("chapter_i18n", {
            "localize_topic": lambda *a, **k: "",
            "localize_level": lambda *a, **k: "",
        }),
        ("backend_i18n", {
            "badge_en": lambda *a, **k: "",
            "skill_node_en": lambda *a, **k: "",
            "title_en": lambda *a, **k: "",
        }),
    ):
        if name not in sys.modules:
            module = types.ModuleType(name)
            for key, value in attrs.items():
                setattr(module, key, value)
            sys.modules[name] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("grimoire_stub_continuity", __name__)
        sys.modules["grimoire_api"] = module


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as module

    return module


class _DbContext:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc):
        return False


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE review_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL, grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL, source_context TEXT);
        CREATE TABLE srs_cards(
            user_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
            last_grade INTEGER, progress_credited INTEGER, updated_at TEXT,
            PRIMARY KEY (user_id, question_id));
        CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL, zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0, stars INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0, best_score INTEGER NOT NULL DEFAULT 0,
            cooldown_until_seen INTEGER NOT NULL DEFAULT 0, last_attempt_at TEXT,
            cleared_at TEXT, updated_at TEXT, PRIMARY KEY (user_id, zone_key));
        CREATE TABLE adventure_zone_unlocks(
            user_id INTEGER NOT NULL, zone_key TEXT NOT NULL, source TEXT,
            start_zone_key TEXT, unlocked_at TEXT, PRIMARY KEY (user_id, zone_key));
        """
    )
    upgrade(conn)
    return conn


def _questions(zone1_count=10, zone2_count=10):
    questions = [
        {"id": 100 + i, "enabled": True, "topic": ZONE1_TOPIC}
        for i in range(zone1_count)
    ]
    questions += [
        {"id": 500 + i, "enabled": True, "topic": ZONE2_TOPIC}
        for i in range(zone2_count)
    ]
    return questions


def _bind(app_module, monkeypatch, conn, questions, *, correct_ids=frozenset()):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: questions)
    monkeypatch.setattr(app_module, "is_premium", lambda uid=None: True)
    monkeypatch.setattr(
        app_module, "_resolve_adventure_effective_start_zone",
        lambda _conn, _uid, unlock_rows=None: ZONE1,
    )
    # Distinct correct Map coverage is server evidence; inject it directly so
    # these tests exercise progression rather than the evidence pipeline.
    monkeypatch.setattr(
        app_module, "_adventure_correct_question_ids",
        lambda _conn, _uid, _cards: set(correct_ids),
    )
    monkeypatch.setattr(
        app_module, "_adventure_trusted_question_ids",
        lambda _conn, _uid: set(correct_ids),
    )


def _zone(app_module, uid, key):
    return next(z for z in app_module._adventure_state(uid) if z["key"] == key)


def _set_boss_row(conn, uid, zone_key, *, cleared, stars):
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score) VALUES (?,?,?,?,1,20)",
        (uid, zone_key, int(cleared), int(stars)),
    )
    conn.commit()


def _set_zone_star(conn, uid, zone_key, stars):
    conn.execute(
        f"INSERT INTO {PROGRESS_TABLE_NAME}(user_id, zone_key, earned_stars, updated_at)"
        " VALUES (?,?,?,?)",
        (uid, zone_key, int(stars), "2026-09-01T00:00:00"),
    )
    conn.commit()


# --------------------------------------------------------------------------
# Legacy stars are never downgraded
# --------------------------------------------------------------------------


@pytest.mark.parametrize("legacy_stars", [0, 1, 2, 3])
def test_legacy_visible_stars_are_never_reduced(
    app_module, monkeypatch, legacy_stars
):
    conn = _connection()
    questions = _questions()
    uid = 300 + legacy_stars
    _set_boss_row(conn, uid, ZONE1, cleared=legacy_stars > 0, stars=legacy_stars)
    _bind(app_module, monkeypatch, conn, questions)

    zone = _zone(app_module, uid, ZONE1)
    # New authority holds nothing yet, but the visible value never drops.
    assert zone["zone_authority_stars"] == 0
    assert zone["legacy_visible_stars"] == legacy_stars
    assert zone["stars"] == legacy_stars
    conn.close()


def test_new_authority_can_raise_but_never_lower_the_visible_value(
    app_module, monkeypatch
):
    conn = _connection()
    questions = _questions()
    _set_boss_row(conn, 310, ZONE1, cleared=True, stars=2)
    _set_zone_star(conn, 310, ZONE1, 1)
    _bind(app_module, monkeypatch, conn, questions)

    zone = _zone(app_module, 310, ZONE1)
    assert zone["stars"] == 2  # grandfathered value wins over lower authority

    _set_zone_star(conn, 311, ZONE1, 3)
    _set_boss_row(conn, 311, ZONE1, cleared=True, stars=1)
    assert _zone(app_module, 311, ZONE1)["stars"] == 3
    conn.close()


# --------------------------------------------------------------------------
# Legacy unlocks survive the star-based unlock rule
# --------------------------------------------------------------------------


def test_legacy_cleared_zone_still_unlocks_the_next_zone(app_module, monkeypatch):
    """A historically cleared Zone always carried stars >= 1, so it still opens."""
    conn = _connection()
    questions = _questions()
    _set_boss_row(conn, 320, ZONE1, cleared=True, stars=1)
    _bind(app_module, monkeypatch, conn, questions)

    assert _zone(app_module, 320, ZONE1)["stars"] >= 1
    assert _zone(app_module, 320, ZONE2)["unlocked"] is True
    conn.close()


def test_zone_without_a_first_star_does_not_unlock_the_next_zone(
    app_module, monkeypatch
):
    conn = _connection()
    questions = _questions()
    _bind(app_module, monkeypatch, conn, questions)

    assert _zone(app_module, 330, ZONE1)["stars"] == 0
    assert _zone(app_module, 330, ZONE2)["unlocked"] is False
    conn.close()


def test_full_map_coverage_alone_does_not_unlock_the_next_zone(
    app_module, monkeypatch
):
    """Coverage is not a progression event: only the first star opens a Zone."""
    conn = _connection()
    questions = _questions()
    zone1_ids = {q["id"] for q in questions if q["topic"] == ZONE1_TOPIC}
    _bind(app_module, monkeypatch, conn, questions, correct_ids=zone1_ids)

    zone1 = _zone(app_module, 340, ZONE1)
    assert zone1["pct"] == 100
    assert zone1["stars"] == 0
    assert zone1["path_shines_to_next"] is False
    assert _zone(app_module, 340, ZONE2)["unlocked"] is False
    conn.close()


def test_explicit_placement_unlock_still_opens_a_zone(app_module, monkeypatch):
    """Placement unlocks are a separate authority and are not regressed."""
    conn = _connection()
    questions = _questions()
    conn.execute(
        "INSERT INTO adventure_zone_unlocks"
        "(user_id,zone_key,source,start_zone_key,unlocked_at) VALUES (?,?,?,?,?)",
        (350, ZONE2, "placement", ZONE2, "2026-08-01T00:00:00"),
    )
    conn.commit()
    _bind(app_module, monkeypatch, conn, questions)

    assert _zone(app_module, 350, ZONE2)["unlocked"] is True
    conn.close()


# --------------------------------------------------------------------------
# Lord eligibility on the real projection
# --------------------------------------------------------------------------


def test_lord_becomes_ready_exactly_at_the_ceiling_threshold(
    app_module, monkeypatch
):
    conn = _connection()
    questions = _questions(zone1_count=7)
    zone1_ids = sorted(q["id"] for q in questions if q["topic"] == ZONE1_TOPIC)
    # ceil(7 * 0.30) == 3
    _bind(app_module, monkeypatch, conn, questions, correct_ids=set(zone1_ids[:2]))
    below = _zone(app_module, 360, ZONE1)
    assert below["lord_required_correct"] == 3
    assert below["boss_ready"] is False

    _bind(app_module, monkeypatch, conn, questions, correct_ids=set(zone1_ids[:3]))
    at = _zone(app_module, 360, ZONE1)
    assert at["boss_ready"] is True
    conn.close()


def test_zone_publishes_server_owned_milestone_requirements(
    app_module, monkeypatch
):
    conn = _connection()
    questions = _questions(zone1_count=10)
    _bind(app_module, monkeypatch, conn, questions)
    zone = _zone(app_module, 370, ZONE1)
    assert zone["total"] == 10
    assert zone["lord_required_correct"] == 3
    assert zone["second_star_required_correct"] == 6
    assert zone["third_star_required_correct"] == 10
    conn.close()


def test_path_shines_only_once_the_first_star_exists(app_module, monkeypatch):
    conn = _connection()
    questions = _questions()
    _bind(app_module, monkeypatch, conn, questions)
    assert _zone(app_module, 380, ZONE1)["path_shines_to_next"] is False

    _set_zone_star(conn, 381, ZONE1, 1)
    assert _zone(app_module, 381, ZONE1)["path_shines_to_next"] is True
    conn.close()


# --------------------------------------------------------------------------
# No historical reward replay
# --------------------------------------------------------------------------


def test_reconciliation_writes_nothing_and_replays_no_reward(
    app_module, monkeypatch
):
    """Reading the projection is pure: continuity needs no backfill at all."""
    conn = _connection()
    questions = _questions()
    _set_boss_row(conn, 390, ZONE1, cleared=True, stars=3)
    _bind(app_module, monkeypatch, conn, questions)

    before_boss = conn.execute(
        "SELECT cleared,stars,attempts,best_score FROM adventure_boss_progress"
        " WHERE user_id=390"
    ).fetchall()
    assert _zone(app_module, 390, ZONE1)["stars"] == 3
    after_boss = conn.execute(
        "SELECT cleared,stars,attempts,best_score FROM adventure_boss_progress"
        " WHERE user_id=390"
    ).fetchall()

    assert [tuple(r) for r in before_boss] == [tuple(r) for r in after_boss]
    # The grandfathered value is never promoted into the new star authority.
    assert conn.execute(
        f"SELECT COUNT(*) FROM {PROGRESS_TABLE_NAME} WHERE user_id=390"
    ).fetchone()[0] == 0
    conn.close()


# --------------------------------------------------------------------------
# The first star persists the next-Zone unlock
# --------------------------------------------------------------------------


def test_first_star_persists_exactly_one_next_zone_unlock(app_module):
    conn = _connection()
    granted = app_module._persist_next_zone_unlock(conn, 400, ZONE1, "2026-09-01T00:00:00")
    conn.commit()
    assert granted == ZONE2

    rows = conn.execute(
        "SELECT zone_key, source, start_zone_key FROM adventure_zone_unlocks"
        " WHERE user_id=400"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["zone_key"] == ZONE2
    assert rows[0]["source"] == app_module.ADVENTURE_FIRST_STAR_UNLOCK_SOURCE
    assert rows[0]["start_zone_key"] == ZONE1
    conn.close()


def test_repeated_first_star_unlock_is_idempotent(app_module):
    conn = _connection()
    for _ in range(3):
        app_module._persist_next_zone_unlock(conn, 401, ZONE1, "2026-09-01T00:00:00")
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_zone_unlocks WHERE user_id=401"
    ).fetchone()[0] == 1
    conn.close()


def test_unlock_never_skips_ahead_or_opens_the_whole_map(app_module):
    conn = _connection()
    app_module._persist_next_zone_unlock(conn, 402, ZONE1, "2026-09-01T00:00:00")
    conn.commit()
    unlocked = {row["zone_key"] for row in conn.execute(
        "SELECT zone_key FROM adventure_zone_unlocks WHERE user_id=402"
    ).fetchall()}
    assert unlocked == {ZONE2}
    conn.close()


def test_last_zone_and_unknown_zone_unlock_nothing(app_module):
    conn = _connection()
    last_zone = app_module.ADVENTURE_ZONES[-1]["key"]
    assert app_module._persist_next_zone_unlock(conn, 403, last_zone, "t") is None
    assert app_module._persist_next_zone_unlock(conn, 403, "not-a-zone", "t") is None
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_zone_unlocks WHERE user_id=403"
    ).fetchone()[0] == 0
    conn.close()


# --------------------------------------------------------------------------
# Lord retry gate counts distinct correct Map questions
# --------------------------------------------------------------------------


def test_retry_gate_counts_distinct_correct_map_questions(app_module, monkeypatch):
    """After a failure the gate is 30 further distinct correct answers."""
    conn = _connection()
    questions = _questions(zone1_count=100)
    zone1_ids = sorted(q["id"] for q in questions if q["topic"] == ZONE1_TOPIC)

    # The player failed the Lord with 40 distinct correct answers, so the row
    # records the seen-count at which a retry becomes available.
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen)"
        " VALUES (?,?,0,0,1,10,?)",
        (410, ZONE1, 40 + app_module.BOSS_FAIL_COOLDOWN),
    )
    conn.commit()

    for answered, expected_left in (
        (40, 30), (41, 29), (69, 1), (70, 0), (75, 0),
    ):
        _bind(
            app_module, monkeypatch, conn, questions,
            correct_ids=set(zone1_ids[:answered]),
        )
        zone = _zone(app_module, 410, ZONE1)
        assert zone["cooldown_left"] == expected_left, answered
        assert zone["cooldown_required"] == app_module.BOSS_FAIL_COOLDOWN
        # Coverage is well past 30%, so the gate is the only thing blocking.
        assert zone["boss_ready"] is (expected_left == 0)
    conn.close()


def test_retry_gate_ignores_incorrect_and_duplicate_answers(app_module, monkeypatch):
    """Only the distinct correct set moves the gate; repeats do not."""
    conn = _connection()
    questions = _questions(zone1_count=100)
    zone1_ids = sorted(q["id"] for q in questions if q["topic"] == ZONE1_TOPIC)
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen)"
        " VALUES (?,?,0,0,1,10,?)",
        (411, ZONE1, 40 + app_module.BOSS_FAIL_COOLDOWN),
    )
    conn.commit()

    # The distinct correct set is a set: re-answering the same questions, and
    # answering incorrectly (never entering the set), cannot advance the gate.
    _bind(app_module, monkeypatch, conn, questions, correct_ids=set(zone1_ids[:40]))
    assert _zone(app_module, 411, ZONE1)["cooldown_left"] == 30
    conn.close()


def test_retry_gate_uses_trusted_post_failure_evidence_when_the_failure_is_dated(
    app_module, monkeypatch
):
    """Grandfathered continuity must never pay off a pending retry lock.

    The gate used to be a delta against ``seen`` -- the visible union -- so
    publishing the historical baseline would have cleared every outstanding
    retry lock for free.  When the failure moment is recorded, the same 30 is
    measured in trusted Tier 2 answers written strictly after it.
    """

    conn = _connection()
    questions = _questions(zone1_count=100)
    zone1_ids = sorted(q["id"] for q in questions if q["topic"] == ZONE1_TOPIC)
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at) VALUES (?,?,0,0,1,10,?,?)",
        (412, ZONE1, 40 + app_module.BOSS_FAIL_COOLDOWN, "2026-09-01T00:00:00"),
    )
    conn.commit()

    # A huge visible set -- as a restored baseline would produce -- but no
    # trusted evidence after the failure.
    _bind(app_module, monkeypatch, conn, questions, correct_ids=set(zone1_ids))
    zone = _zone(app_module, 412, ZONE1)
    assert zone["lord_retry_measured_from_failure"] is True
    assert zone["cooldown_left"] == app_module.BOSS_FAIL_COOLDOWN
    assert zone["boss_ready"] is False

    # 29 trusted answers after the failure: still locked.
    for offset in range(29):
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
            "VALUES (?,?,?,?,?)",
            (412, zone1_ids[offset], 5, "2026-09-02T00:00:00", "mbv1:map"),
        )
    conn.commit()
    assert _zone(app_module, 412, ZONE1)["cooldown_left"] == 1

    # The thirtieth opens it.
    conn.execute(
        "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
        "VALUES (?,?,?,?,?)",
        (412, zone1_ids[29], 5, "2026-09-02T00:00:00", "mbv1:map"),
    )
    conn.commit()
    reopened = _zone(app_module, 412, ZONE1)
    assert reopened["cooldown_left"] == 0
    assert reopened["boss_ready"] is True
    conn.close()
