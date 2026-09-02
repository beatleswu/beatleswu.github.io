"""The legacy no-timestamp cooldown fallback must not admit Tier 1.

``_adventure_state`` measures the post-Lord-failure +30 retry gate from
trusted Tier 2 evidence recorded after the failure.  A pre-existing cooldown
row that carries no usable failure reference used to fall back to the old
arithmetic, which was a delta against the *visible union* -- so grandfathered
continuity could pay off a retry lock that no new trusted work had earned.

These tests pin the Owner rule on that fallback path specifically:

    GRANDFATHERED_LEGACY_PROGRESS MUST NOT SATISFY POST_FAILURE_PLUS30
"""

from __future__ import annotations

import sqlite3
import sys
import types

import pytest

from adventure_progress_compatibility import (
    current_adventure_question_count,
    populate_frozen_historical_baseline,
    visible_adventure_question_count,
)
from migrations.adventure_historical_mastery_v1 import upgrade as upgrade_mastery
from migrations.adventure_zone_star_progression_v1 import upgrade as upgrade_zone_star


ZONE1 = "k26_30"
ZONE1_TOPIC = "1圍棋新手村"
ZONE1_IDS = list(range(100, 200))
FAILED_AT_SEEN = 40
PRE = "2026-08-01T00:00:00"


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
        module.grimoire_bp = Blueprint("grimoire_stub_no_timestamp", __name__)
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
            last_grade INTEGER, progress_credited INTEGER DEFAULT 0,
            updated_at TEXT, PRIMARY KEY (user_id, question_id));
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
    upgrade_zone_star(conn)
    upgrade_mastery(conn)
    return conn


def _questions():
    return [{"id": qid, "enabled": True, "topic": ZONE1_TOPIC} for qid in ZONE1_IDS]


def _bind_real_evidence(app_module, monkeypatch, conn, questions):
    """Bind the app to this database and leave the real evidence pipeline in place.

    The other legacy-continuity tests inject ``_adventure_correct_question_ids``
    directly, which collapses Tier 1 and Tier 2 into one injected set.  Here the
    real compatibility reader must run, because the whole question is whether
    Tier 1 leaks into the retry counter.
    """

    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: questions)
    monkeypatch.setattr(app_module, "is_premium", lambda uid=None: True)
    monkeypatch.setattr(
        app_module, "_resolve_adventure_effective_start_zone",
        lambda _conn, _uid, unlock_rows=None: ZONE1,
    )


FAILED_AT = "2026-09-05T00:00:00"


def _legacy_cooldown_row(conn, uid, *, last_attempt_at=None, updated_at=FAILED_AT):
    """A pre-existing outstanding retry lock with no ``last_attempt_at``.

    This is the realistic legacy shape: every settlement path has always
    stamped ``updated_at``, so an uncleared row with a recorded attempt still
    carries a server-owned marker of its most recent failure even when the
    dedicated attempt column is empty.
    """

    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (?,?,0,1,1,10,?,?,NULL,?)",
        (uid, ZONE1, FAILED_AT_SEEN + 30, last_attempt_at, updated_at),
    )
    conn.commit()


def _grandfather(conn, uid, count):
    for qid in ZONE1_IDS[:count]:
        conn.execute(
            "INSERT INTO srs_cards(user_id,question_id,last_grade,progress_credited) "
            "VALUES (?,?,0,1)",
            (uid, qid),
        )
    conn.commit()
    populate_frozen_historical_baseline(
        conn, question_ids=set(ZONE1_IDS), captured_at=PRE
    )
    conn.commit()


def _trusted_after(conn, uid, count, at="2026-09-10T00:00:00", start=0):
    for qid in ZONE1_IDS[start : start + count]:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
            "VALUES (?,?,5,?,'mbv1:map')",
            (uid, qid, at),
        )
    conn.commit()


def _zone(app_module, uid):
    return next(z for z in app_module._adventure_state(uid) if z["key"] == ZONE1)


# ---------------------------------------------------------------------------
# The four required cases, on a row with NO failure reference at all.
# ---------------------------------------------------------------------------
def test_case1_no_tier1_and_no_trusted_work_stays_blocked(app_module, monkeypatch):
    conn = _connection()
    _legacy_cooldown_row(conn, 601)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())
    zone = _zone(app_module, 601)
    assert zone["cooldown_left"] > 0
    assert zone["boss_ready"] is False
    conn.close()


def test_case2_large_tier1_baseline_alone_cannot_unlock_the_retry(app_module, monkeypatch):
    conn = _connection()
    _legacy_cooldown_row(conn, 602)
    # Far more than 30 grandfathered memberships, and zero trusted evidence.
    _grandfather(conn, 602, 90)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())

    assert visible_adventure_question_count(conn, 602, ZONE1_IDS) == 90
    assert current_adventure_question_count(conn, 602, ZONE1_IDS) == 0

    zone = _zone(app_module, 602)
    assert zone["seen"] == 90, "Tier 1 is visible progress"
    assert zone["cooldown_left"] > 0, (
        "grandfathered continuity must not pay off a post-failure retry lock"
    )
    assert zone["boss_ready"] is False
    conn.close()


def test_case3_tier1_baseline_plus_29_trusted_stays_blocked(app_module, monkeypatch):
    conn = _connection()
    _legacy_cooldown_row(conn, 603)
    _grandfather(conn, 603, 90)
    _trusted_after(conn, 603, 29)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())
    zone = _zone(app_module, 603)
    assert zone["lord_retry_new_correct"] == 29
    assert zone["cooldown_left"] == 1
    assert zone["boss_ready"] is False
    conn.close()


def test_case4_tier1_baseline_plus_30_trusted_opens_the_retry(app_module, monkeypatch):
    conn = _connection()
    _legacy_cooldown_row(conn, 604)
    _grandfather(conn, 604, 90)
    _trusted_after(conn, 604, 30)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())
    zone = _zone(app_module, 604)
    assert zone["lord_retry_new_correct"] == 30
    assert zone["cooldown_left"] == 0
    assert zone["boss_ready"] is True
    conn.close()


def test_counter_is_trusted_only_on_the_no_timestamp_path(app_module, monkeypatch):
    """The retry counter must never include a grandfathered membership."""

    conn = _connection()
    _legacy_cooldown_row(conn, 605)
    _grandfather(conn, 605, 90)
    _trusted_after(conn, 605, 5)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())
    zone = _zone(app_module, 605)
    # 90 visible, 5 trusted: the gate counts the 5, never the 90.
    assert zone["seen"] == 90
    assert zone["lord_retry_new_correct"] == 5
    assert zone["cooldown_left"] == 25
    conn.close()


def test_updated_at_is_used_as_the_failure_reference_when_present(app_module, monkeypatch):
    """A row stamped only with ``updated_at`` still measures failure-relative.

    Every settlement path writes ``updated_at``, so for an uncleared Zone with a
    recorded attempt it marks the most recent failure.  Trusted answers from
    before that moment must not count.
    """

    conn = _connection()
    _legacy_cooldown_row(conn, 606, updated_at="2026-09-05T00:00:00")
    _grandfather(conn, 606, 90)
    _trusted_after(conn, 606, 40, at="2026-09-01T00:00:00")   # before the failure
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())
    zone = _zone(app_module, 606)
    assert zone["lord_retry_new_correct"] == 0
    assert zone["cooldown_left"] == 30
    assert zone["boss_ready"] is False

    _trusted_after(conn, 606, 30, at="2026-09-06T00:00:00", start=40)
    assert _zone(app_module, 606)["cooldown_left"] == 0
    conn.close()


def test_cleared_zone_is_not_subject_to_the_retry_gate(app_module, monkeypatch):
    conn = _connection()
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (607,?,1,1,2,20,0,NULL,NULL,NULL)",
        (ZONE1,),
    )
    conn.commit()
    _grandfather(conn, 607, 90)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())
    zone = _zone(app_module, 607)
    assert zone["cooldown_left"] == 0
    conn.close()


def test_row_with_no_failure_reference_at_all_fails_closed_and_is_surfaced(
    app_module, monkeypatch
):
    """A row carrying neither timestamp cannot be measured, so it stays locked.

    "30 answers after that failure" is not computable without a failure
    moment.  Falling back to the old union arithmetic is precisely how
    grandfathered continuity would buy the retry, so the gate fails closed and
    flags the row rather than choosing a weaker rule on the Owner's behalf.
    Every settlement path stamps ``updated_at``, so this shape is not expected
    from rows this application wrote.
    """

    conn = _connection()
    _legacy_cooldown_row(conn, 608, updated_at=None)
    _grandfather(conn, 608, 90)
    _trusted_after(conn, 608, 50)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())

    zone = _zone(app_module, 608)
    assert zone["lord_retry_reference_unresolvable"] is True
    assert zone["lord_retry_measured_from_failure"] is False
    assert zone["cooldown_left"] == 30
    assert zone["boss_ready"] is False
    conn.close()


def test_zone_never_attempted_is_not_gated_by_a_stale_legacy_column(
    app_module, monkeypatch
):
    """No recorded attempt means nothing is owed, whatever Tier 1 contains."""

    conn = _connection()
    _grandfather(conn, 609, 90)
    _bind_real_evidence(app_module, monkeypatch, conn, _questions())
    zone = _zone(app_module, 609)
    assert zone["cooldown_left"] == 0
    assert zone["lord_retry_reference_unresolvable"] is False
    conn.close()
