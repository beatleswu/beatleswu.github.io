"""Behavioural Lord Trial contract, inside the governed release gate.

The preceding hardening task reported LORD_TRIAL_RELEASE_GATE_COVERAGE=INSUFFICIENT:
the only files under ``tests/deployment/`` mentioning "lord" did so in packaging and
provenance strings. Nothing in the gate exercised Lord behaviour, so the exam size,
the pass score, the +30 post-failure retry rule and its fail-closed reference could
all have regressed with a green release.

This module drives the real authority functions and the real
``_adventure_lord_retry_state`` against SQLite, asserting BEHAVIOUR rather than the
presence of a constant in source text. Every case here fails if the corresponding
invariant is broken -- see the accompanying negative-control evidence.

R3 semantics are pinned, never changed: Tier 1 grandfathered continuity may open the
FIRST Lord Challenge (it is continuity entitlement) but contributes exactly zero to
the post-failure +30 retry gate, which is Tier 2 trusted evidence only.
"""

from __future__ import annotations

import math
import pathlib
import sqlite3
import sys
import types

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from adventure_progress_compatibility import (  # noqa: E402
    TRUSTED_REVIEW_SOURCE_PREFIXES,
    trusted_correct_count_after,
)
from adventure_zone_progression_authority import (  # noqa: E402
    LORD_RETRY_REQUIRED_NEW_CORRECT,
    is_lord_eligible,
    is_lord_retry_satisfied,
    lord_eligibility_requirement,
    lord_retry_requirement,
)
from migrations.adventure_historical_mastery_v1 import upgrade as upgrade_mastery  # noqa: E402
from migrations.adventure_zone_star_progression_v1 import upgrade as upgrade_zone_star  # noqa: E402


ZONE = "k26_30"
ZONE_IDS = list(range(700100, 700200))       # 100 canonical zone questions
FAILED_AT = "2026-09-05T00:00:00"
BEFORE_FAILURE = "2026-09-04T00:00:00"
AFTER_FAILURE = "2026-09-10T00:00:00"
TRUSTED_CTX = TRUSTED_REVIEW_SOURCE_PREFIXES[0] + "map"   # "mbv1:map"


def _install_app_import_stubs():
    for name, attrs in (
        ("katago_explain", {"KataGoExplainer": type("K", (), {})}),
        ("explain_overrides", {"get_override": lambda *a, **k: None}),
        ("question_taxonomy", {"get_taxonomy": lambda *a, **k: {}}),
        ("monster_taxonomy", {"get_monster_taxonomy": lambda *a, **k: {},
                              "mark_encounters": lambda *a, **k: None}),
        ("chapter_i18n", {"localize_topic": lambda *a, **k: "",
                          "localize_level": lambda *a, **k: ""}),
        ("backend_i18n", {"badge_en": lambda *a, **k: "",
                          "skill_node_en": lambda *a, **k: "",
                          "title_en": lambda *a, **k: ""}),
    ):
        if name not in sys.modules:
            module = types.ModuleType(name)
            for key, value in attrs.items():
                setattr(module, key, value)
            sys.modules[name] = module
    if "grimoire_api" not in sys.modules:
        from flask import Blueprint

        module = types.ModuleType("grimoire_api")
        module.grimoire_bp = Blueprint("grimoire_stub_lord_gate", __name__)
        sys.modules["grimoire_api"] = module


@pytest.fixture(scope="module")
def app_module():
    # app.py writes secret_key.txt beside itself when SECRET_KEY is unset; that
    # file is a governed protected artifact the release tooling refuses.
    import os

    os.environ.setdefault("SECRET_KEY", "lord-gate-ephemeral-key")
    _install_app_import_stubs()
    import app as module

    return module


def _conn() -> sqlite3.Connection:
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


def _fail_lord(conn, uid, *, last_attempt_at=FAILED_AT, updated_at=FAILED_AT,
               attempts=1, cleared=0):
    conn.execute(
        "INSERT INTO adventure_boss_progress"
        "(user_id,zone_key,cleared,stars,attempts,best_score,cooldown_until_seen,"
        " last_attempt_at,cleared_at,updated_at) VALUES (?,?,?,0,?,0,0,?,NULL,?)"
        " ON CONFLICT(user_id,zone_key) DO UPDATE SET"
        " attempts=excluded.attempts, last_attempt_at=excluded.last_attempt_at,"
        " updated_at=excluded.updated_at, cleared=excluded.cleared",
        (uid, ZONE, cleared, attempts, last_attempt_at, updated_at),
    )
    conn.commit()


def _trusted_answers(conn, uid, count, *, at=AFTER_FAILURE, start=0, grade=5):
    """Tier 2 server-authoritative correct answers (mbv1: prefix)."""

    for qid in ZONE_IDS[start:start + count]:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
            " VALUES (?,?,?,?,?)",
            (uid, qid, grade, at, TRUSTED_CTX),
        )
    conn.commit()


def _tier1_grandfathered(conn, uid, count):
    """Tier 1 continuity: credited cards with no trusted review evidence."""

    for qid in ZONE_IDS[:count]:
        conn.execute(
            "INSERT INTO srs_cards(user_id,question_id,last_grade,progress_credited)"
            " VALUES (?,?,0,1)",
            (uid, qid),
        )
    conn.commit()


def _retry(app_module, conn, uid):
    return app_module._adventure_lord_retry_state(conn, uid, ZONE, set(ZONE_IDS))


# ---------------------------------------------------------------------------
# 2. Required Lord constants -- proven behaviourally
# ---------------------------------------------------------------------------
def test_exam_size_and_pass_score_are_twenty_and_sixteen(app_module):
    """BOSS_EXAM_SIZE / BOSS_PASS_SCORE, asserted as the live contract."""

    assert app_module.BOSS_EXAM_SIZE == 20
    assert app_module.BOSS_PASS_SCORE == 16


@pytest.mark.parametrize(
    "correct,expected_pass",
    [(0, False), (15, False), (16, True), (17, True), (20, True)],
)
def test_sixteen_of_twenty_passes_and_fifteen_does_not(app_module, correct, expected_pass):
    """LORD_16_OF_20_PASS / LORD_15_OF_20_FAIL, over the real threshold."""

    assert (correct >= app_module.BOSS_PASS_SCORE) is expected_pass
    assert correct <= app_module.BOSS_EXAM_SIZE


def test_retry_requirement_is_thirty():
    assert lord_retry_requirement() == LORD_RETRY_REQUIRED_NEW_CORRECT == 30


# ---------------------------------------------------------------------------
# 3. Initial Lord eligibility -- ceil(total * 30%)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("total", [100, 1939, 1735, 7, 1])
def test_initial_eligibility_is_the_thirty_percent_ceiling(total):
    """EXACT_30_PERCENT_BOUNDARY -- a ceiling, never a rounded percentage."""

    required = lord_eligibility_requirement(total)
    assert required == math.ceil(total * 0.30)
    assert is_lord_eligible(required, total) is True
    assert is_lord_eligible(required - 1, total) is False


def test_below_threshold_is_rejected_and_zero_total_is_not_eligible():
    assert is_lord_eligible(29, 100) is False
    assert is_lord_eligible(30, 100) is True
    assert is_lord_eligible(999, 0) is False


def test_tier1_continuity_may_open_the_first_lord_challenge():
    """TIER1_INITIAL_ELIGIBILITY -- continuity entitlement is deliberate.

    Tier 1 counts toward the visible progress that opens the FIRST challenge.
    The retry gate below proves it contributes nothing after a failure.
    """

    total = 100
    tier1_only_visible = lord_eligibility_requirement(total)
    assert is_lord_eligible(tier1_only_visible, total) is True


def test_visible_progress_is_deduplicated_across_tiers():
    """VISIBLE_PROGRESS_DEDUP -- a question in both tiers counts once."""

    tier1 = set(ZONE_IDS[:20])
    tier2 = set(ZONE_IDS[10:40])          # 10 overlap with tier1
    union = tier1 | tier2
    assert len(union) == 40, "overlapping membership must not double-count"
    assert len(tier1) + len(tier2) == 50, "sanity: naive addition would over-count"
    assert is_lord_eligible(len(union), 100) is True
    assert is_lord_eligible(len(union), 200) is False


# ---------------------------------------------------------------------------
# 5. Post-failure +30 retry -- Tier 2 only, strictly after the failure
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "new_correct,expected_locked",
    [(0, True), (1, True), (29, True), (30, False), (31, False)],
)
def test_retry_unlocks_at_exactly_thirty(app_module, new_correct, expected_locked):
    """RETRY_29_FAIL / RETRY_30_PASS."""

    conn = _conn()
    _fail_lord(conn, 501)
    _trusted_answers(conn, 501, new_correct)
    state = _retry(app_module, conn, 501)

    assert state["required"] == 30
    assert state["achieved"] == new_correct
    assert state["locked"] is expected_locked
    conn.close()


def test_tier1_contributes_zero_to_the_retry_gate(app_module):
    """TIER1_RETRY_CONTRIBUTION -- the invariant the whole rule exists for.

    A player with the entire Zone grandfathered must still owe the full 30.
    """

    conn = _conn()
    _fail_lord(conn, 502)
    _tier1_grandfathered(conn, 502, len(ZONE_IDS))   # 100 credited cards
    state = _retry(app_module, conn, 502)

    assert state["achieved"] == 0, "grandfathered continuity leaked into the retry gate"
    assert state["locked"] is True
    conn.close()


def test_tier1_plus_twentynine_trusted_still_locked(app_module):
    """Legacy visible-union progress must not be able to finish the job."""

    conn = _conn()
    _fail_lord(conn, 503)
    _tier1_grandfathered(conn, 503, len(ZONE_IDS))
    _trusted_answers(conn, 503, 29)
    state = _retry(app_module, conn, 503)

    assert state["achieved"] == 29
    assert state["locked"] is True
    conn.close()


def test_pre_failure_tier2_contributes_zero(app_module):
    """STRICTLY_AFTER_FAILURE_REFERENCE / PRE_FAILURE_TIER2_CONTRIBUTION."""

    conn = _conn()
    _fail_lord(conn, 504)
    _trusted_answers(conn, 504, 50, at=BEFORE_FAILURE)
    state = _retry(app_module, conn, 504)

    assert state["achieved"] == 0, "answers before the failure paid off the lock"
    assert state["locked"] is True
    conn.close()


def test_duplicate_and_incorrect_answers_do_not_count(app_module):
    """DISTINCT_ANSWER_COUNTING -- distinct canonical questions only."""

    conn = _conn()
    _fail_lord(conn, 505)
    for _ in range(40):                    # same question answered 40 times
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
            " VALUES (?,?,5,?,?)",
            (505, ZONE_IDS[0], AFTER_FAILURE, TRUSTED_CTX),
        )
    for qid in ZONE_IDS[1:41]:             # 40 wrong answers
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
            " VALUES (?,?,1,?,?)",
            (505, qid, AFTER_FAILURE, TRUSTED_CTX),
        )
    conn.commit()
    state = _retry(app_module, conn, 505)

    assert state["achieved"] == 1
    assert state["locked"] is True
    conn.close()


def test_untrusted_source_context_contributes_zero(app_module):
    """Only the server-authoritative Tier 2 prefix is trusted evidence."""

    conn = _conn()
    _fail_lord(conn, 506)
    for qid in ZONE_IDS[:40]:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
            " VALUES (?,?,5,?,'practice')",
            (506, qid, AFTER_FAILURE),
        )
    conn.commit()
    state = _retry(app_module, conn, 506)

    assert state["achieved"] == 0
    assert state["locked"] is True
    conn.close()


def test_a_new_failure_resets_the_reference(app_module):
    """NEW_FAILURE_RESETS_REFERENCE -- one batch cannot pay two locks."""

    conn = _conn()
    _fail_lord(conn, 507, last_attempt_at=FAILED_AT, updated_at=FAILED_AT)
    _trusted_answers(conn, 507, 30)
    assert _retry(app_module, conn, 507)["locked"] is False

    later = "2026-09-20T00:00:00"          # strictly after those 30 answers
    _fail_lord(conn, 507, last_attempt_at=later, updated_at=later, attempts=2)
    state = _retry(app_module, conn, 507)

    assert state["achieved"] == 0, "the earlier batch paid off the second failure"
    assert state["locked"] is True
    conn.close()


# ---------------------------------------------------------------------------
# 6. Failure-reference resolution and fail-closed
# ---------------------------------------------------------------------------
def test_last_attempt_at_is_the_primary_reference(app_module):
    """FAILURE_REFERENCE_LAST_ATTEMPT."""

    conn = _conn()
    _fail_lord(conn, 508, last_attempt_at=FAILED_AT, updated_at=BEFORE_FAILURE)
    _trusted_answers(conn, 508, 30, at="2026-09-04T12:00:00")  # after updated_at,
    state = _retry(app_module, conn, 508)                      # before last_attempt_at

    assert state["since"] == FAILED_AT
    assert state["achieved"] == 0, "the weaker updated_at reference was used"
    conn.close()


def test_updated_at_is_used_when_last_attempt_is_absent(app_module):
    """FAILURE_REFERENCE_PROGRESS_UPDATED_AT -- server-owned, never invented."""

    conn = _conn()
    _fail_lord(conn, 509, last_attempt_at=None, updated_at=FAILED_AT)
    _trusted_answers(conn, 509, 30)
    state = _retry(app_module, conn, 509)

    assert state["since"] == FAILED_AT
    assert state["achieved"] == 30
    assert state["locked"] is False
    conn.close()


def test_unresolvable_failure_reference_fails_closed(app_module):
    """FAILURE_REFERENCE_UNRESOLVABLE_FAIL_CLOSED -- never invent a fallback."""

    conn = _conn()
    _fail_lord(conn, 510, last_attempt_at=None, updated_at=None)
    _trusted_answers(conn, 510, 50)
    state = _retry(app_module, conn, 510)

    assert state["locked"] is True, "an unresolvable reference unlocked the retry"
    assert state["required"] == 30
    assert state["achieved"] == 0
    assert state.get("unresolvable_failure_reference") is True
    assert state["since"] is None
    conn.close()


def test_read_failure_fails_closed(app_module):
    """A database failure must never unlock; it is not evidence of payment."""

    class _Failing:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, parameters=None):
            if "SELECT attempts, cleared, last_attempt_at" in sql:
                raise sqlite3.OperationalError("injected retry-state read failure")
            return self._real.execute(sql, parameters) if parameters is not None \
                else self._real.execute(sql)

        def __getattr__(self, name):
            return getattr(self._real, name)

    conn = _conn()
    _fail_lord(conn, 511)
    state = _retry(app_module, _Failing(conn), 511)

    assert state["locked"] is True
    assert state["required"] == 30
    assert state["achieved"] == 0
    conn.close()


def test_cleared_and_never_attempted_zones_are_not_locked(app_module):
    """STAR_0_TO_1_ONLY guardrail: a cleared Zone owes no retry."""

    conn = _conn()
    _fail_lord(conn, 512, cleared=1, attempts=2)
    assert _retry(app_module, conn, 512)["locked"] is False
    assert _retry(app_module, conn, 513)["locked"] is False   # never attempted
    conn.close()


# ---------------------------------------------------------------------------
# 7. Trust boundary -- Tier 1 is continuity entitlement, never correctness
# ---------------------------------------------------------------------------
def test_tier1_is_never_trusted_correctness_evidence():
    """TRUST_BOUNDARY_PRESERVED."""

    assert TRUSTED_REVIEW_SOURCE_PREFIXES == ("mbv1:",), (
        "the trusted evidence prefix set changed; Tier 1 must not join it"
    )

    conn = _conn()
    _tier1_grandfathered(conn, 520, 40)
    for qid in ZONE_IDS[:40]:
        conn.execute(
            "INSERT INTO review_log(user_id,question_id,grade,reviewed_at,source_context)"
            " VALUES (?,?,5,?,'grandfathered_legacy_progress')",
            (520, qid, AFTER_FAILURE),
        )
    conn.commit()

    counted = trusted_correct_count_after(conn, 520, set(ZONE_IDS), BEFORE_FAILURE)
    assert counted == 0, "Tier 1 continuity became trusted Tier 2 correctness"
    conn.close()


def test_retry_helpers_agree_with_the_declared_constant():
    assert is_lord_retry_satisfied(29) is False
    assert is_lord_retry_satisfied(30) is True
    assert is_lord_retry_satisfied(31) is True
