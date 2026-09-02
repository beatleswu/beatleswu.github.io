"""The Lord start endpoint must use the canonical 30% ceiling eligibility.

``POST /api/adventure/boss/start`` used to re-derive its own admission gate
from ``state['pct']``, the rounded, display-oriented percentage:

    if not is_replay and state.get('pct', 0) < BOSS_UNLOCK_PCT:

``pct`` is ``round(seen / total * 100)``, so it reads 30 from 29.5% upward.
In Zone 1 (1939 questions, requirement ``ceil(1939 * 0.30) == 582``) that
admitted **573 through 581** -- up to nine questions early -- while
``_adventure_state`` correctly reported ``boss_ready=False`` for exactly those
players. The state authority and the endpoint disagreed.

These tests drive the real ``_adventure_state`` rather than a hand-written
zone dict, so a future divergence between what the state reports and what the
endpoint admits fails here rather than reaching a player.
"""

from __future__ import annotations

import sqlite3
import sys
import types

import pytest

from adventure_zone_progression_authority import lord_eligibility_requirement

JUDGEABLE_SGF = "(;GM[1]FF[4]CA[UTF-8]SZ[19]PL[B]AB[dp]AW[pd](;B[dd]C[stub]))"

# (zone_key, topic, canonical pool size, ceil(total * 0.30))
ZONE1 = ("k26_30", "1圍棋新手村", 1939, 582)
ZONE2 = ("k21_25", "3史萊姆平原", 1617, 486)
ZONE9 = ("d5_6", "18諸神黃昏", 598, 180)


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
        module.grimoire_bp = Blueprint("grimoire_stub_start_gate", __name__)
        sys.modules["grimoire_api"] = module


@pytest.fixture(scope="module")
def app_module():
    _install_app_import_stubs()
    import app as module

    return module


@pytest.fixture()
def client(app_module):
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


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
    return conn


def _pool(topic, size, first_id):
    return [
        {"id": first_id + i, "enabled": True, "topic": topic, "content": JUDGEABLE_SGF}
        for i in range(size)
    ]


def _bind(app_module, monkeypatch, conn, questions, correct_ids):
    monkeypatch.setattr(app_module, "get_db", lambda: _DbContext(conn))
    monkeypatch.setattr(app_module, "_load_questions", lambda: questions)
    monkeypatch.setattr(app_module, "is_premium", lambda uid=None: True)
    monkeypatch.setattr(
        app_module, "_resolve_adventure_effective_start_zone",
        lambda _conn, _uid, unlock_rows=None: ZONE1[0],
    )
    monkeypatch.setattr(
        app_module, "_adventure_correct_question_ids",
        lambda _conn, _uid, _cards: set(correct_ids),
    )
    monkeypatch.setattr(
        app_module, "_adventure_trusted_question_ids",
        lambda _conn, _uid: set(correct_ids),
    )
    # Adventure state is cached per user; keep every scenario independent.
    app_module._ADVENTURE_STATE_CACHE.clear()


def _scenario(app_module, monkeypatch, zone, correct_count, uid, first_id=100000):
    """Build a Zone at *correct_count* distinct correct answers.

    Zones after the first are opened by the preceding Zone's first star, which
    is not what these tests are about, so they are opened here with an
    explicit placement unlock row -- a separate, already-reviewed authority.
    """
    zone_key, topic, total, _required = zone
    conn = _connection()
    questions = _pool(topic, total, first_id)
    ids = [q["id"] for q in questions][:correct_count]
    if zone_key != app_module.ADVENTURE_ZONES[0]["key"]:
        conn.execute(
            "INSERT INTO adventure_zone_unlocks"
            "(user_id,zone_key,source,start_zone_key,unlocked_at) VALUES (?,?,?,?,?)",
            (uid, zone_key, "placement", zone_key, "2026-08-01T00:00:00"),
        )
        conn.commit()
    _bind(app_module, monkeypatch, conn, questions, set(ids))
    return conn, zone_key


def _login(client, uid):
    with client.session_transaction() as session:
        session["user_id"] = uid


def _state_zone(app_module, uid, zone_key):
    return next(z for z in app_module._adventure_state(uid) if z["key"] == zone_key)


def _start(client, zone_key, **extra):
    return client.post(
        "/api/adventure/boss/start", json={"zone_key": zone_key, **extra}
    )


# --------------------------------------------------------------------------
# The exact reported boundary
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "correct,expected_allowed",
    [(571, False), (572, False), (580, False), (581, False), (582, True), (583, True)],
)
def test_zone1_start_boundary_uses_the_ceiling_requirement(
    client, app_module, monkeypatch, correct, expected_allowed
):
    zone_key, _topic, total, required = ZONE1
    assert required == lord_eligibility_requirement(total) == 582

    uid = 5000 + correct
    conn, _ = _scenario(app_module, monkeypatch, ZONE1, correct, uid)
    _login(client, uid)

    response = _start(client, zone_key)
    if expected_allowed:
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert len(body["question_ids"]) == 20
        assert body["pass_score"] == 16
    else:
        assert response.status_code == 400
        body = response.get_json()
        assert body["error"] == "progress_not_enough"
        assert body["correct"] == correct
        assert body["required_correct"] == required
        # No attempt may exist after a refusal.
        with client.session_transaction() as session:
            assert "adventure_boss_exam" not in session
    conn.close()


def test_the_old_rounded_gate_would_have_admitted_the_blocked_range(
    client, app_module, monkeypatch
):
    """Pin the defect: 572-581 all read as 30% but are below the requirement."""
    _zone_key, _topic, total, required = ZONE1
    for correct in (573, 575, 581):
        assert round(correct / total * 100) >= app_module.BOSS_UNLOCK_PCT
        assert correct < required


# --------------------------------------------------------------------------
# State and endpoint may never disagree
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zone", [ZONE1, ZONE2, ZONE9])
@pytest.mark.parametrize("offset", [-2, -1, 0, 1])
def test_state_and_start_endpoint_never_disagree(
    client, app_module, monkeypatch, zone, offset
):
    zone_key, _topic, total, required = zone
    assert required == lord_eligibility_requirement(total)

    correct = required + offset
    uid = 6000 + total + offset
    conn, _ = _scenario(app_module, monkeypatch, zone, correct, uid)
    _login(client, uid)

    state_ready = _state_zone(app_module, uid, zone_key)["boss_ready"]
    started = _start(client, zone_key).status_code == 200

    # The canonical state is the authority; the endpoint must match it exactly.
    assert state_ready == (offset >= 0)
    assert started == state_ready
    conn.close()


@pytest.mark.parametrize(
    "zone,correct,expected_allowed",
    [
        (ZONE2, 485, False), (ZONE2, 486, True),
        (ZONE9, 179, False), (ZONE9, 180, True),
    ],
)
def test_other_zone_boundaries(
    client, app_module, monkeypatch, zone, correct, expected_allowed
):
    uid = 7000 + correct
    conn, zone_key = _scenario(app_module, monkeypatch, zone, correct, uid)
    _login(client, uid)
    assert (_start(client, zone_key).status_code == 200) is expected_allowed
    conn.close()


# --------------------------------------------------------------------------
# The gate is server-owned
# --------------------------------------------------------------------------


def test_client_cannot_forge_eligibility(client, app_module, monkeypatch):
    """Request-body progress claims are never consulted."""
    conn, zone_key = _scenario(app_module, monkeypatch, ZONE1, 581, 8000)
    _login(client, 8000)
    for forged in (
        {"pct": 100},
        {"progress": 100},
        {"boss_ready": True},
        {"correct": 582, "seen": 582},
        {"required_correct": 0},
        {"total": 1, "correct_count": 582},
    ):
        response = _start(client, zone_key, **forged)
        assert response.status_code == 400
        assert response.get_json()["error"] == "progress_not_enough"
    conn.close()


# --------------------------------------------------------------------------
# The other Lord gates are untouched
# --------------------------------------------------------------------------


def test_post_failure_cooldown_still_blocks_an_eligible_player(
    client, app_module, monkeypatch
):
    """Coverage eligibility must not bypass the 30-new-correct retry gate."""
    zone_key, topic, total, required = ZONE1
    conn = _connection()
    questions = _pool(topic, total, 100000)
    ids = [q["id"] for q in questions][:required]
    # Failed the Lord at `required` correct: 30 further correct answers needed.
    # The retry gate is measured in trusted Tier 2 answers recorded strictly
    # after the failure, so the row carries the moment it failed.
    failed_at = "2026-09-05T00:00:00"
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,updated_at) VALUES (?,?,0,0,1,10,?,?,?)",
        (8100, zone_key, required + app_module.BOSS_FAIL_COOLDOWN, failed_at, failed_at),
    )
    conn.commit()
    _bind(app_module, monkeypatch, conn, questions, set(ids))
    _login(client, 8100)

    # Comfortably past the 30% coverage gate, still inside the retry lock.
    assert _state_zone(app_module, 8100, zone_key)["cooldown_left"] == 30
    response = _start(client, zone_key)
    assert response.status_code == 400
    assert response.get_json()["error"] == "cooldown"

    # Growing *visible* coverage does not pay the lock off -- only new trusted
    # work after the failure does.
    _bind(
        app_module, monkeypatch, conn, questions,
        set([q["id"] for q in questions][: required + app_module.BOSS_FAIL_COOLDOWN]),
    )
    assert _state_zone(app_module, 8100, zone_key)["cooldown_left"] == 30
    assert _start(client, zone_key).status_code == 400

    # Exactly 30 distinct trusted answers after the failure releases it.
    for question_id in [q["id"] for q in questions][:app_module.BOSS_FAIL_COOLDOWN]:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
            " VALUES (?,?,5,?,'mbv1:map')",
            (8100, question_id, "2026-09-06T00:00:00"),
        )
    conn.commit()
    app_module._ADVENTURE_STATE_CACHE.clear()
    assert _state_zone(app_module, 8100, zone_key)["cooldown_left"] == 0
    assert _start(client, zone_key).status_code == 200
    conn.close()


def test_an_admitted_attempt_is_exactly_twenty_questions_at_sixteen_to_pass(
    client, app_module, monkeypatch
):
    conn, zone_key = _scenario(app_module, monkeypatch, ZONE1, ZONE1[3], 8200)
    _login(client, 8200)
    body = _start(client, zone_key).get_json()
    assert len(body["question_ids"]) == 20
    assert body["total"] == 20
    assert body["pass_score"] == 16
    assert len(set(body["question_ids"])) == 20
    conn.close()


def test_start_endpoint_has_no_second_percentage_authority(app_module):
    """There must be exactly one eligibility rule, and it must be the shared one."""
    import inspect

    source = inspect.getsource(app_module.adventure_boss_start)
    assert "is_lord_eligible(" in source
    # Strip comments, then assert no executable line compares a percentage.
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )
    assert "BOSS_UNLOCK_PCT" not in code
    assert "round(" not in code
    # `pct` may still be echoed back for display, but never compared.
    assert "pct" not in code.replace("'progress': state.get('pct', 0),", "")
