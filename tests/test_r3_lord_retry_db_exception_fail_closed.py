"""A failed retry-state read must never unlock a pending Lord retry.

``_adventure_lord_retry_state`` used to answer a database/read failure with
``locked=False, required=0``.  ``_adventure_state`` turns that into
``cooldown_left = max(0, required - achieved) = 0``, and the Lord start
endpoint gates on exactly ``state['cooldown_left'] > 0`` -- so a player with a
recorded failed Lord attempt became immediately eligible again the moment the
retry-state read failed.  Nothing about a read failure is evidence that the
player paid off the post-failure debt.

These tests pin the Owner rule on that path:

    A RETRY-STATE EVALUATION FAILURE MUST FAIL CLOSED

The healthy 0/29/30 measurement is re-asserted here too, so the fail-closed
branch cannot be satisfied by simply locking everyone.
"""

from __future__ import annotations

import sqlite3
import sys
import types

import pytest

from adventure_zone_progression_authority import (
    LORD_RETRY_REQUIRED_NEW_CORRECT,
)
from migrations.adventure_historical_mastery_v1 import upgrade as upgrade_mastery
from migrations.adventure_zone_star_progression_v1 import upgrade as upgrade_zone_star


ZONE1 = "k26_30"
ZONE1_TOPIC = "1圍棋新手村"
ZONE1_IDS = list(range(100, 200))
FAILED_AT = "2026-09-05T00:00:00"
AFTER_FAILURE = "2026-09-10T00:00:00"

# The exact retry-state read in ``_adventure_lord_retry_state``.  Matching on
# the projection keeps the earlier ``SELECT * FROM adventure_boss_progress``
# that builds ``progress`` working, so the test exercises a failure of the
# retry evaluation specifically -- not a wholesale loss of the table.
RETRY_STATE_SELECT = "SELECT attempts, cleared, last_attempt_at"


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
        module.grimoire_bp = Blueprint("grimoire_stub_retry_failclosed", __name__)
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


class _RetryReadFailingConnection:
    """A real connection whose retry-state read raises, and nothing else.

    This is the realistic shape of the defect: the surrounding request still
    works, one bounded read inside the retry evaluation fails.
    """

    def __init__(self, conn):
        self._conn = conn
        self.injected_failures = 0

    def execute(self, sql, *args, **kwargs):
        if RETRY_STATE_SELECT in sql:
            self.injected_failures += 1
            raise sqlite3.OperationalError("injected retry-state read failure")
        return self._conn.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._conn, name)


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


def _failed_lord_attempt(conn, uid, *, at=FAILED_AT):
    """An uncleared Zone with one recorded Lord failure -- an outstanding lock."""

    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (?,?,0,1,1,10,0,?,NULL,?)",
        (uid, ZONE1, at, at),
    )
    conn.commit()


def _trusted_after(conn, uid, count, *, at=AFTER_FAILURE, start=0):
    for qid in ZONE1_IDS[start : start + count]:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context) "
            "VALUES (?,?,5,?,'mbv1:map')",
            (uid, qid, at),
        )
    conn.commit()


def _bind(app_module, monkeypatch, conn, questions):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: questions)
    monkeypatch.setattr(app_module, "is_premium", lambda uid=None: True)
    monkeypatch.setattr(
        app_module, "_resolve_adventure_effective_start_zone",
        lambda _conn, _uid, unlock_rows=None: ZONE1,
    )


def _zone(app_module, uid):
    return next(z for z in app_module._adventure_state(uid) if z["key"] == ZONE1)


def _assert_not_the_fail_open_shape(state):
    """The exact pre-repair shape must never come back."""

    assert not (
        state.get("locked") is False and int(state.get("required") or 0) == 0
    ), f"retry evaluation failed open: {state}"


# ---------------------------------------------------------------------------
# DB_FAILURE_FAILS_CLOSED -- the retry-state read itself fails
# ---------------------------------------------------------------------------
def test_retry_state_read_failure_keeps_the_player_locked(app_module):
    conn = _connection()
    _failed_lord_attempt(conn, 701)
    failing = _RetryReadFailingConnection(conn)

    state = app_module._adventure_lord_retry_state(
        failing, 701, ZONE1, set(ZONE1_IDS)
    )

    assert failing.injected_failures == 1, "the injected read was never exercised"
    _assert_not_the_fail_open_shape(state)
    assert state["locked"] is True
    assert state["required"] == LORD_RETRY_REQUIRED_NEW_CORRECT == 30
    assert state["achieved"] == 0
    conn.close()


def test_post_failure_count_failure_keeps_the_player_locked(app_module, monkeypatch):
    """The count is the whole measurement; if it cannot be read, the lock stands."""

    conn = _connection()
    _failed_lord_attempt(conn, 702)
    # Enough real post-failure work to open the lock -- it must not be assumed
    # present when the count that would prove it cannot be read.
    _trusted_after(conn, 702, 30)

    def _boom(*_args, **_kwargs):
        raise sqlite3.OperationalError("injected post-failure count failure")

    monkeypatch.setattr(app_module, "trusted_correct_count_after", _boom)

    state = app_module._adventure_lord_retry_state(conn, 702, ZONE1, set(ZONE1_IDS))

    _assert_not_the_fail_open_shape(state)
    assert state["locked"] is True
    assert state["required"] == LORD_RETRY_REQUIRED_NEW_CORRECT
    assert state["achieved"] == 0
    conn.close()


# ---------------------------------------------------------------------------
# The same failure, at the contract the Lord start endpoint actually reads
# ---------------------------------------------------------------------------
def test_request_path_reports_a_nonzero_cooldown_when_the_retry_read_fails(
    app_module, monkeypatch
):
    conn = _connection()
    _failed_lord_attempt(conn, 703)
    _trusted_after(conn, 703, 100)  # full Zone coverage, so eligibility is met
    failing = _RetryReadFailingConnection(conn)
    _bind(app_module, monkeypatch, failing, _questions())

    zone = _zone(app_module, 703)

    assert failing.injected_failures >= 1, "the injected read was never exercised"
    # app.py's start endpoint gates on exactly `cooldown_left > 0`.
    assert zone["cooldown_left"] == LORD_RETRY_REQUIRED_NEW_CORRECT
    assert zone["cooldown_left"] > 0
    assert zone["boss_ready"] is False
    assert zone["lord_retry_new_correct"] == 0
    # A read failure is not the same durable condition as a missing timestamp.
    assert zone["lord_retry_reference_unresolvable"] is False
    conn.close()


def test_request_path_reports_a_nonzero_cooldown_when_the_count_fails(
    app_module, monkeypatch
):
    conn = _connection()
    _failed_lord_attempt(conn, 704)
    _trusted_after(conn, 704, 100)

    def _boom(*_args, **_kwargs):
        raise sqlite3.OperationalError("injected post-failure count failure")

    _bind(app_module, monkeypatch, conn, _questions())
    monkeypatch.setattr(app_module, "trusted_correct_count_after", _boom)

    zone = _zone(app_module, 704)

    assert zone["cooldown_left"] == LORD_RETRY_REQUIRED_NEW_CORRECT
    assert zone["boss_ready"] is False
    conn.close()


def test_start_endpoint_cooldown_gate_refuses_a_failed_evaluation(
    app_module, monkeypatch
):
    """Mirrors the gate expression in app.py's Lord start endpoint."""

    conn = _connection()
    _failed_lord_attempt(conn, 705)
    _trusted_after(conn, 705, 100)
    failing = _RetryReadFailingConnection(conn)
    _bind(app_module, monkeypatch, failing, _questions())

    state = _zone(app_module, 705)
    is_replay = False

    refused = (not is_replay) and state.get("cooldown_left", 0) > 0

    assert refused is True, "a failed retry evaluation admitted a Lord attempt"
    conn.close()


# ---------------------------------------------------------------------------
# The healthy measurement must still work -- fail-closed is not "lock everyone"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "new_correct,expected_locked,expected_cooldown",
    [(0, True, 30), (29, True, 1), (30, False, 0)],
)
def test_healthy_path_still_measures_thirty_post_failure_answers(
    app_module, monkeypatch, new_correct, expected_locked, expected_cooldown
):
    conn = _connection()
    _failed_lord_attempt(conn, 800 + new_correct)
    _trusted_after(conn, 800 + new_correct, new_correct)
    _bind(app_module, monkeypatch, conn, _questions())

    state = app_module._adventure_lord_retry_state(
        conn, 800 + new_correct, ZONE1, set(ZONE1_IDS)
    )

    assert state["achieved"] == new_correct
    assert state["locked"] is expected_locked
    assert state["required"] == LORD_RETRY_REQUIRED_NEW_CORRECT

    zone = _zone(app_module, 800 + new_correct)
    assert zone["cooldown_left"] == expected_cooldown
    conn.close()


def test_pre_failure_trusted_answers_still_do_not_pay_the_lock(
    app_module, monkeypatch
):
    conn = _connection()
    _failed_lord_attempt(conn, 810)
    _trusted_after(conn, 810, 50, at="2026-09-04T23:59:59")  # strictly before
    _bind(app_module, monkeypatch, conn, _questions())

    state = app_module._adventure_lord_retry_state(conn, 810, ZONE1, set(ZONE1_IDS))

    assert state["achieved"] == 0
    assert state["locked"] is True
    conn.close()


def test_cleared_and_never_attempted_zones_are_untouched_by_the_repair(
    app_module, monkeypatch
):
    """The fail-closed branch must not invent a lock where none is owed."""

    conn = _connection()
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (?,?,1,3,2,20,0,?,?,?)",
        (820, ZONE1, FAILED_AT, FAILED_AT, FAILED_AT),
    )
    conn.commit()
    _bind(app_module, monkeypatch, conn, _questions())

    cleared = app_module._adventure_lord_retry_state(conn, 820, ZONE1, set(ZONE1_IDS))
    assert cleared["locked"] is False

    never = app_module._adventure_lord_retry_state(conn, 821, ZONE1, set(ZONE1_IDS))
    assert never["locked"] is False
    conn.close()
