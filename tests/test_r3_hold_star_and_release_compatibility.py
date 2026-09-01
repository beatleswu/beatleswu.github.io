"""R3: HOLD star invariants, the 30%/1★ seam, and release compatibility.

Grandfathered continuity may open the Lord exam.  It may never mint a star,
replay a reward, or push an existing first-star player to 2★/3★ while the
retroactive milestone policy is on HOLD.
"""

from __future__ import annotations

import sqlite3

import pytest

from adventure_progress_compatibility import (
    current_adventure_question_count,
    populate_frozen_historical_baseline,
    visible_adventure_question_count,
)
from adventure_zone_progression_authority import (
    is_lord_eligible,
    lord_eligibility_requirement,
    map_milestone_star,
)
from adventure_zone_star_progression import (
    RETROACTIVE_MILESTONE_POLICY_ENV,
    RETROACTIVE_POLICY_FULL,
    RETROACTIVE_POLICY_HOLD,
    award_zone_star_from_boss_clear,
    award_zone_star_up_to_map_milestone,
    load_zone_star_rows,
    retroactive_milestone_policy,
    zone_star_value,
)
from migrations.adventure_historical_mastery_v1 import upgrade
from migrations.adventure_zone_star_progression_v1 import (
    upgrade as upgrade_zone_star_schema,
)


ZONE = "zone1"
ZONE_IDS = set(range(1, 101))
PRE = "2026-08-01T00:00:00"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE review_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            grade INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL,
            source_context TEXT
        );
        CREATE TABLE srs_cards(
            user_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            last_grade INTEGER,
            progress_credited INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, question_id)
        );
        CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            stars INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, zone_key)
        );
        """
    )
    upgrade(conn)
    upgrade_zone_star_schema(conn)
    return conn


def _grandfather_full_zone(conn, uid):
    """Give the player 100% Tier 1 coverage and zero Tier 2 evidence."""

    for qid in ZONE_IDS:
        conn.execute(
            "INSERT INTO srs_cards(user_id,question_id,last_grade,progress_credited) "
            "VALUES (?,?,0,1)",
            (uid, qid),
        )
    conn.commit()
    populate_frozen_historical_baseline(conn, question_ids=ZONE_IDS, captured_at=PRE)
    conn.commit()


def test_full_grandfathered_coverage_still_has_no_trusted_coverage():
    conn = _conn()
    _grandfather_full_zone(conn, 1)
    assert visible_adventure_question_count(conn, 1, ZONE_IDS) == len(ZONE_IDS)
    assert current_adventure_question_count(conn, 1, ZONE_IDS) == 0


def test_grandfathered_coverage_opens_the_thirty_percent_lord_gate():
    conn = _conn()
    _grandfather_full_zone(conn, 1)
    visible = visible_adventure_question_count(conn, 1, ZONE_IDS)
    assert is_lord_eligible(visible, len(ZONE_IDS)) is True
    assert lord_eligibility_requirement(len(ZONE_IDS)) == 30
    # ... while the trusted-only view would not have opened it.
    assert is_lord_eligible(current_adventure_question_count(conn, 1, ZONE_IDS), len(ZONE_IDS)) is False


def test_grandfathered_coverage_alone_mints_no_star_under_hold():
    conn = _conn()
    _grandfather_full_zone(conn, 1)
    # 0★ player: Map coverage earns nothing without a first star, whatever the
    # coverage is.
    blocked = award_zone_star_up_to_map_milestone(
        conn, 1, ZONE, "sub-1", "2026-09-02T00:00:00", milestone_star=3
    )
    assert blocked["status"] == "first_star_required"
    assert blocked["awarded"] is False
    assert load_zone_star_rows(conn, 1) == {}


def test_first_lord_clear_moves_zero_to_one_only_even_at_full_coverage():
    conn = _conn()
    _grandfather_full_zone(conn, 1)
    result = award_zone_star_from_boss_clear(
        conn, 1, ZONE, "lord-clear-1", "2026-09-02T00:00:00"
    )
    assert result["awarded"] is True
    assert result["stars"] == 1
    assert zone_star_value(load_zone_star_rows(conn, 1), ZONE) == 1


def test_first_clear_does_not_cascade_to_two_or_three_in_the_same_transaction():
    conn = _conn()
    _grandfather_full_zone(conn, 1)
    award_zone_star_from_boss_clear(conn, 1, ZONE, "lord-clear-1", "2026-09-02T00:00:00")
    # Nothing else in the clear transaction may raise the level.
    assert zone_star_value(load_zone_star_rows(conn, 1), ZONE) == 1
    # A reload/recompute must not raise it either: under HOLD the milestone is
    # computed from trusted Map facts, which are still zero.
    trusted = current_adventure_question_count(conn, 1, ZONE_IDS)
    assert map_milestone_star(trusted, len(ZONE_IDS), has_first_star=True) == 1


def test_existing_first_star_player_cannot_auto_upgrade_under_hold(monkeypatch):
    monkeypatch.delenv(RETROACTIVE_MILESTONE_POLICY_ENV, raising=False)
    assert retroactive_milestone_policy() == RETROACTIVE_POLICY_HOLD

    conn = _conn()
    _grandfather_full_zone(conn, 1)
    award_zone_star_from_boss_clear(conn, 1, ZONE, "lord-clear-1", "2026-09-02T00:00:00")
    assert zone_star_value(load_zone_star_rows(conn, 1), ZONE) == 1

    # Repeated state recomputation, as a reload/login/answer would perform.
    for attempt in range(5):
        trusted = current_adventure_question_count(conn, 1, ZONE_IDS)
        milestone = map_milestone_star(trusted, len(ZONE_IDS), has_first_star=True)
        assert milestone == 1
        outcome = award_zone_star_up_to_map_milestone(
            conn, 1, ZONE, f"reload-{attempt}", "2026-09-02T00:00:01",
            milestone_star=milestone,
        )
        assert outcome["status"] in ("already_earned", "no_new_star", "no_milestone")
        assert outcome["awarded"] is False
        assert zone_star_value(load_zone_star_rows(conn, 1), ZONE) == 1


def test_hold_uses_trusted_facts_while_full_policy_uses_the_union():
    """The policy seam decides which count reaches the milestone writer."""

    conn = _conn()
    _grandfather_full_zone(conn, 1)
    union = visible_adventure_question_count(conn, 1, ZONE_IDS)
    trusted = current_adventure_question_count(conn, 1, ZONE_IDS)
    assert union == 100 and trusted == 0
    assert map_milestone_star(trusted, 100, has_first_star=True) == 1
    assert map_milestone_star(union, 100, has_first_star=True) == 3


def test_explicit_full_policy_is_the_only_way_to_reach_the_union(monkeypatch):
    monkeypatch.setenv(RETROACTIVE_MILESTONE_POLICY_ENV, RETROACTIVE_POLICY_FULL)
    assert retroactive_milestone_policy() == RETROACTIVE_POLICY_FULL
    monkeypatch.setenv(RETROACTIVE_MILESTONE_POLICY_ENV, "")
    assert retroactive_milestone_policy() == RETROACTIVE_POLICY_HOLD
    monkeypatch.setenv(RETROACTIVE_MILESTONE_POLICY_ENV, "FULL")
    assert retroactive_milestone_policy() == RETROACTIVE_POLICY_FULL


def test_baseline_publication_writes_no_star_or_reward_rows():
    conn = _conn()
    _grandfather_full_zone(conn, 1)
    assert load_zone_star_rows(conn, 1) == {}
    assert conn.execute(
        "SELECT COUNT(*) FROM adventure_boss_progress"
    ).fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Section 26 -- migration-before-deploy must be safe for the running old app
# ---------------------------------------------------------------------------
def deployed_reader_frozen_baseline_ready(conn, baseline_version, cutoff, frozen_status):
    """Reference transcription of the *deployed* readiness predicate.

    The 4bf/eb10 application accepted the baseline when both tables existed
    and a metadata row for **its own** ``baseline_version`` carried its own
    ``cutoff_literal`` and its own frozen status literal.  Reproduced here so
    the compatibility window is proven rather than assumed.
    """

    for table in ("adventure_historical_mastery_baseline", "adventure_historical_mastery"):
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is None:
            return False
    row = conn.execute(
        "SELECT cutoff_literal, status FROM adventure_historical_mastery_baseline "
        "WHERE baseline_version=?",
        (baseline_version,),
    ).fetchone()
    if row is None:
        return False
    return str(row[0]) == cutoff_literal_of(cutoff) and str(row[1]) == frozen_status


def cutoff_literal_of(value):
    return value


@pytest.mark.parametrize(
    "deployed_version,deployed_frozen_status",
    [
        # 4bfaf834 production baseline reader.
        ("INCIDENT019B_B050_COMPAT_V1", "FROZEN"),
        # eb10 candidate reader.
        ("INCIDENT019B_B050_COMPAT_V1", "BASELINE_READY"),
    ],
)
def test_old_app_cannot_consume_the_r3_baseline(deployed_version, deployed_frozen_status):
    conn = _conn()
    _grandfather_full_zone(conn, 1)
    # The R3 baseline is published and valid for the R3 reader ...
    assert visible_adventure_question_count(conn, 1, ZONE_IDS) == 100
    # ... and invisible to a still-running older application.
    assert deployed_reader_frozen_baseline_ready(
        conn, deployed_version, "2026-08-29T13:17:30", deployed_frozen_status
    ) is False


# ---------------------------------------------------------------------------
# Section 19 -- the settled-answer path must not compute a count it discards
# ---------------------------------------------------------------------------
def _instrument_settlement(monkeypatch, policy):
    import app as app_module

    calls = {"union": 0, "trusted": 0, "zone_ids": 0}

    def _union(conn, uid, zone_ids, **kwargs):
        calls["union"] += 1
        return 100

    def _trusted(conn, uid, zone_ids, **kwargs):
        calls["trusted"] += 1
        return 0

    def _zone_ids(zone_key, uid=None):
        calls["zone_ids"] += 1
        return set(ZONE_IDS), len(ZONE_IDS)

    monkeypatch.setattr(app_module, "visible_adventure_question_count", _union)
    monkeypatch.setattr(app_module, "current_adventure_question_count", _trusted)
    monkeypatch.setattr(app_module, "_adventure_zone_question_ids", _zone_ids)
    monkeypatch.setattr(app_module, "retroactive_milestone_policy", lambda: policy)
    monkeypatch.setattr(app_module, "_zone_by_key", lambda key: {"key": key})
    monkeypatch.setattr(app_module, "load_zone_star_rows", lambda conn, uid: {ZONE: 1})
    monkeypatch.setattr(app_module, "zone_star_value", lambda rows, key: 1)
    monkeypatch.setattr(
        app_module,
        "award_zone_star_up_to_map_milestone",
        lambda *a, **k: {"status": "no_milestone", "awarded": False},
    )
    return app_module, calls


def test_hold_settlement_computes_one_progression_count_not_two(monkeypatch):
    app_module, calls = _instrument_settlement(monkeypatch, RETROACTIVE_POLICY_HOLD)
    app_module._adventure_zone_star_from_settled_answer(
        conn=None,
        uid=1,
        grade=5,
        combat_settlement_context=app_module.EXTERNAL_AUTHORITATIVE_MAP_BATTLE,
        authoritative_submission={"battle_zone_key": ZONE},
        submission_id="sub-1",
        earned_at="2026-09-02T00:00:00",
    )
    # Under HOLD only the trusted count is needed.  eb10 computed the union
    # first and then threw the result away on every settled answer.
    assert calls["trusted"] == 1
    assert calls["union"] == 0
    # And the canonical Zone pool is resolved once, not twice.
    assert calls["zone_ids"] == 1


def test_full_policy_settlement_uses_the_union_count(monkeypatch):
    app_module, calls = _instrument_settlement(monkeypatch, RETROACTIVE_POLICY_FULL)
    app_module._adventure_zone_star_from_settled_answer(
        conn=None,
        uid=1,
        grade=5,
        combat_settlement_context=app_module.EXTERNAL_AUTHORITATIVE_MAP_BATTLE,
        authoritative_submission={"battle_zone_key": ZONE},
        submission_id="sub-1",
        earned_at="2026-09-02T00:00:00",
    )
    assert calls["union"] == 1
    assert calls["trusted"] == 0
    assert calls["zone_ids"] == 1


def test_old_app_schema_probe_is_unaffected_by_the_additive_columns():
    """The old reader selects explicit columns, so new ones cannot break it."""

    conn = _conn()
    _grandfather_full_zone(conn, 1)
    row = conn.execute(
        "SELECT cutoff_literal, status FROM adventure_historical_mastery_baseline "
        "WHERE baseline_version=?",
        ("INCIDENT019B_B050_COMPAT_V1",),
    ).fetchone()
    assert row is None  # no row under the old version, and no error raised
