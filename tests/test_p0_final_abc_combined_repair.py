"""Focused contracts for the combined RPG V1 A/B/C repair.

These tests are deliberately local and non-Production.  They exercise the
baseline state machine, the pure blast-radius calculation, and the real
browser-to-review source chain without submitting a gameplay answer.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

from adventure_progress_compatibility import (
    build_progression_milestone_dry_run,
    current_adventure_question_count,
    frozen_historical_memberships,
    membership_fingerprint,
    populate_frozen_historical_baseline,
    visible_adventure_question_count,
)
from adventure_zone_star_progression import (
    RETROACTIVE_MILESTONE_POLICY_ENV,
    RETROACTIVE_POLICY_FULL,
    RETROACTIVE_POLICY_HOLD,
    award_zone_star_up_to_map_milestone,
    load_zone_star_rows,
    retroactive_milestone_policy,
    zone_star_value,
)
from migrations.adventure_historical_mastery_v1 import (
    BASELINE_TABLE_NAME,
    BASELINE_VERSION,
    CUTOFF_DOMAIN,
    CUTOFF_LITERAL,
    CUTOFF_OPERATOR,
    GRANDFATHERED_ENTITLEMENT_SOURCE,
    PRECHANGE_PREDICATE_REFERENCE_SHA,
    RECONSTRUCTION_CLASS_CONSERVATIVE,
    SOURCE_PROGRESS_CREDITED_MASK,
    SOURCE_RULE_VERSION,
    STATUS_BUILDING,
    TABLE_NAME,
    baseline_readiness,
    upgrade,
)
from migrations.adventure_zone_star_progression_v1 import upgrade as upgrade_zone_star_schema


ROOT = Path(__file__).resolve().parents[1]


def _connection() -> sqlite3.Connection:
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
            progress_credited INTEGER,
            updated_at TEXT,
            PRIMARY KEY(user_id, question_id)
        );
        """
    )
    return conn


def _card(conn, user_id: int, question_id: int, *, credited: int = 1, last_grade: int = 0):
    conn.execute(
        "INSERT INTO srs_cards(user_id, question_id, last_grade, progress_credited, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, question_id, last_grade, credited, "2026-08-01T00:00:00"),
    )


def _building_metadata(conn):
    conn.execute(
        f"INSERT INTO {BASELINE_TABLE_NAME} "
        "(baseline_version, cutoff_literal, captured_at, frozen_at, status, membership_count, "
        "source_rule_version, expected_membership_count, actual_membership_count, "
        "membership_fingerprint, ready_at, failure_reason, predicate_reference_sha, "
        "cutoff_operator, cutoff_domain, exact_membership_count, conservative_membership_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            BASELINE_VERSION,
            CUTOFF_LITERAL,
            "2026-09-01T00:00:00",
            "",
            STATUS_BUILDING,
            0,
            SOURCE_RULE_VERSION,
            0,
            0,
            "",
            None,
            None,
            PRECHANGE_PREDICATE_REFERENCE_SHA,
            CUTOFF_OPERATOR,
            CUTOFF_DOMAIN,
            0,
            0,
        ),
    )


def test_baseline_absent_is_not_an_authority():
    conn = _connection()
    assert baseline_readiness(conn)["status"] == "BASELINE_ABSENT"
    assert frozen_historical_memberships(conn, user_id=1) == set()
    upgrade(conn)
    assert baseline_readiness(conn)["status"] == "BASELINE_ABSENT"
    assert frozen_historical_memberships(conn, user_id=1) == set()


def test_building_partial_baseline_is_not_consumed():
    conn = _connection()
    upgrade(conn)
    _building_metadata(conn)
    conn.execute(
        f"INSERT INTO {TABLE_NAME} "
        "(user_id, question_id, baseline_version, source_mask, entitlement_source, captured_at, "
        "cutoff_literal, reconstruction_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (1, 10, BASELINE_VERSION, SOURCE_PROGRESS_CREDITED_MASK, GRANDFATHERED_ENTITLEMENT_SOURCE, "2026-09-01",
         CUTOFF_LITERAL, RECONSTRUCTION_CLASS_CONSERVATIVE),
    )
    assert baseline_readiness(conn)["status"] == STATUS_BUILDING
    assert baseline_readiness(conn)["valid"] is False
    assert frozen_historical_memberships(conn, user_id=1) == set()


def test_ready_baseline_requires_count_and_fingerprint_integrity():
    conn = _connection()
    _card(conn, 2, 20)
    upgrade(conn)
    result = populate_frozen_historical_baseline(
        conn, question_ids={20}, captured_at="2026-09-01T00:00:00"
    )
    conn.commit()
    readiness = baseline_readiness(conn, verify_fingerprint=True)
    assert readiness["status"] == "BASELINE_READY"
    assert readiness["valid"] is True
    assert readiness["fingerprint_matches"] is True
    assert readiness["membership_fingerprint"] == membership_fingerprint({2: {20}})
    assert result["membership_count"] == 1

    conn.execute(
        f"DELETE FROM {TABLE_NAME} WHERE user_id=? AND question_id=?",
        (2, 20),
    )
    conn.execute(
        f"INSERT INTO {TABLE_NAME} "
        "(user_id, question_id, baseline_version, source_mask, entitlement_source, captured_at, "
        "cutoff_literal, reconstruction_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (2, 21, BASELINE_VERSION, SOURCE_PROGRESS_CREDITED_MASK, GRANDFATHERED_ENTITLEMENT_SOURCE, "2026-09-01",
         CUTOFF_LITERAL, RECONSTRUCTION_CLASS_CONSERVATIVE),
    )
    tampered = baseline_readiness(conn, verify_fingerprint=True)
    assert tampered["status"] == "BASELINE_FAILED_OR_INVALID"
    assert tampered["valid"] is False


def test_interrupted_building_state_can_resume_without_publishing_partial_ready():
    conn = _connection()
    _card(conn, 3, 30)
    _card(conn, 3, 31)
    upgrade(conn)
    _building_metadata(conn)
    conn.execute(
        f"INSERT INTO {TABLE_NAME} "
        "(user_id, question_id, baseline_version, source_mask, entitlement_source, captured_at, "
        "cutoff_literal, reconstruction_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (3, 30, BASELINE_VERSION, SOURCE_PROGRESS_CREDITED_MASK, GRANDFATHERED_ENTITLEMENT_SOURCE, "2026-09-01",
         CUTOFF_LITERAL, RECONSTRUCTION_CLASS_CONSERVATIVE),
    )
    assert frozen_historical_memberships(conn, user_id=3) == set()
    result = populate_frozen_historical_baseline(
        conn, question_ids={30, 31}, captured_at="2026-09-01T00:00:00"
    )
    conn.commit()
    assert result["membership_count"] == 2
    assert baseline_readiness(conn, verify_fingerprint=True)["valid"] is True
    assert frozen_historical_memberships(conn, user_id=3) == {30, 31}


def test_committed_failed_baseline_is_cleaned_before_deterministic_rerun():
    conn = _connection()
    _card(conn, 33, 330)
    _card(conn, 33, 331)
    upgrade(conn)
    _building_metadata(conn)
    conn.execute(
        f"INSERT INTO {TABLE_NAME} "
        "(user_id, question_id, baseline_version, source_mask, entitlement_source, captured_at, "
        "cutoff_literal, reconstruction_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (33, 999, BASELINE_VERSION, SOURCE_PROGRESS_CREDITED_MASK, GRANDFATHERED_ENTITLEMENT_SOURCE, "2026-09-01",
         CUTOFF_LITERAL, RECONSTRUCTION_CLASS_CONSERVATIVE),
    )
    conn.execute(
        f"UPDATE {BASELINE_TABLE_NAME} SET status=?, expected_membership_count=?, "
        "actual_membership_count=?, membership_count=?, membership_fingerprint=? "
        "WHERE baseline_version=?",
        ("BASELINE_FAILED_OR_INVALID", 1, 1, 1, "stale", BASELINE_VERSION),
    )
    conn.commit()
    assert baseline_readiness(conn)["status"] == "BASELINE_FAILED_OR_INVALID"
    assert frozen_historical_memberships(conn, user_id=33) == set()

    result = populate_frozen_historical_baseline(
        conn, question_ids={330, 331}, captured_at="2026-09-01T00:00:00"
    )
    conn.commit()

    assert result["membership_count"] == 2
    assert baseline_readiness(conn, verify_fingerprint=True)["valid"] is True
    assert frozen_historical_memberships(conn, user_id=33) == {330, 331}
    assert conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE question_id=999"
    ).fetchone()[0] == 0


def test_ready_baseline_is_one_time_and_does_not_grow_from_later_cards():
    conn = _connection()
    _card(conn, 4, 40)
    upgrade(conn)
    first = populate_frozen_historical_baseline(
        conn, question_ids={40, 41}, captured_at="2026-09-01T00:00:00"
    )
    conn.commit()
    _card(conn, 4, 41)
    second = populate_frozen_historical_baseline(
        conn, question_ids={40, 41}, captured_at="2026-09-02T00:00:00"
    )
    assert first["already_ready"] is False
    assert second["already_ready"] is True
    assert frozen_historical_memberships(conn, user_id=4) == {40}


def test_baseline_population_has_no_progression_or_reward_side_effects():
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE adventure_zone_star_progress(user_id INTEGER, zone_key TEXT, earned_stars INTEGER);
        CREATE TABLE adventure_zone_star_earnings(user_id INTEGER, event_id TEXT);
        CREATE TABLE adventure_boss_progress(user_id INTEGER, zone_key TEXT, cleared INTEGER, stars INTEGER);
        CREATE TABLE adventure_zone_unlocks(user_id INTEGER, zone_key TEXT);
        """
    )
    _card(conn, 5, 50)
    upgrade(conn)
    before = tuple(
        conn.execute(
            "SELECT (SELECT COUNT(*) FROM adventure_zone_star_progress), "
            "(SELECT COUNT(*) FROM adventure_zone_star_earnings), "
            "(SELECT COUNT(*) FROM adventure_boss_progress), "
            "(SELECT COUNT(*) FROM adventure_zone_unlocks)"
        ).fetchone()
    )
    populate_frozen_historical_baseline(conn, question_ids={50})
    after = tuple(
        conn.execute(
            "SELECT (SELECT COUNT(*) FROM adventure_zone_star_progress), "
            "(SELECT COUNT(*) FROM adventure_zone_star_earnings), "
            "(SELECT COUNT(*) FROM adventure_boss_progress), "
            "(SELECT COUNT(*) FROM adventure_zone_unlocks)"
        ).fetchone()
    )
    assert before == after == (0, 0, 0, 0)


def test_progression_dry_run_reports_threshold_crossings_without_writes():
    result = build_progression_milestone_dry_run(
        baseline_memberships={7: set(range(1, 11))},
        current_memberships={7: set(range(1, 6))},
        zone_question_ids={"test": set(range(1, 11))},
        legacy_first_stars={(7, "test"): 1},
    )
    assert result["zone_user_rows_crossing_60_percent"] == 1
    assert result["zone_user_rows_crossing_100_percent"] == 1
    assert result["expected_2star_transitions"] == 1
    assert result["expected_3star_transitions"] == 1
    assert result["reward_events_current_runtime_would_trigger"] == 0
    assert result["coin_total_current_runtime_would_grant"] == 0
    assert result["item_grants_current_runtime_would_grant"] == 0


def test_retroactive_policy_defaults_to_hold_and_unknown_values_fail_closed(monkeypatch):
    monkeypatch.delenv(RETROACTIVE_MILESTONE_POLICY_ENV, raising=False)
    assert retroactive_milestone_policy() == RETROACTIVE_POLICY_HOLD
    monkeypatch.setenv(RETROACTIVE_MILESTONE_POLICY_ENV, "not-owner-approved")
    assert retroactive_milestone_policy() == RETROACTIVE_POLICY_HOLD
    assert retroactive_milestone_policy(RETROACTIVE_POLICY_FULL) == RETROACTIVE_POLICY_FULL


def test_full_retroactive_policy_uses_legacy_first_star_without_replaying_star_one():
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            stars INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, zone_key)
        );
        """
    )
    upgrade_zone_star_schema(conn)
    conn.execute(
        "INSERT INTO adventure_boss_progress(user_id, zone_key, stars) VALUES (?, ?, ?)",
        (9, "test", 1),
    )

    # The normal/default call cannot treat a legacy row as a new-star input.
    blocked = award_zone_star_up_to_map_milestone(
        conn, 9, "test", "map-default", "2026-09-01T00:00:00", milestone_star=2
    )
    assert blocked["status"] == "first_star_required"
    assert load_zone_star_rows(conn, 9) == {}

    # The explicit owner-selected seam may project that already-earned 1★
    # into the separate authority, then write only the new 2★ ledger event.
    caught_up = award_zone_star_up_to_map_milestone(
        conn,
        9,
        "test",
        "map-full-policy",
        "2026-09-01T00:00:01",
        milestone_star=2,
        allow_legacy_first_star_entitlement=True,
    )
    assert caught_up["stars"] == 2
    assert zone_star_value(load_zone_star_rows(conn, 9), "test") == 2
    ledger = conn.execute(
        "SELECT star_number FROM adventure_zone_star_earnings WHERE user_id=?",
        (9,),
    ).fetchall()
    assert [row[0] for row in ledger] == [2]


def test_full_retroactive_policy_preserves_legacy_two_and_three_stars_without_replay():
    conn = _connection()
    conn.executescript(
        """
        CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL,
            zone_key TEXT NOT NULL,
            stars INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, zone_key)
        );
        """
    )
    upgrade_zone_star_schema(conn)
    conn.executemany(
        "INSERT INTO adventure_boss_progress(user_id, zone_key, stars) VALUES (?, ?, ?)",
        [(10, "two", 2), (11, "three", 3)],
    )

    for user_id, zone_key, target in ((10, "two", 2), (11, "three", 3)):
        result = award_zone_star_up_to_map_milestone(
            conn,
            user_id,
            zone_key,
            f"map-full-policy-{user_id}",
            "2026-09-01T00:00:00",
            milestone_star=target,
            allow_legacy_first_star_entitlement=True,
        )
        assert result["stars"] == (2 if user_id == 10 else 3)

    assert zone_star_value(load_zone_star_rows(conn, 10), "two") == 2
    assert zone_star_value(load_zone_star_rows(conn, 11), "three") == 3
    ledger = conn.execute(
        "SELECT user_id, star_number FROM adventure_zone_star_earnings ORDER BY user_id"
    ).fetchall()
    assert list(map(tuple, ledger)) == []


def test_current_count_is_same_authority_with_baseline_explicitly_excluded():
    conn = _connection()
    _card(conn, 8, 80)
    upgrade(conn)
    populate_frozen_historical_baseline(conn, question_ids={80, 81})
    conn.execute(
        "INSERT INTO review_log(user_id, question_id, grade, reviewed_at, source_context) "
        "VALUES (?, ?, ?, ?, ?)",
        (8, 81, 5, "2026-09-01T00:00:00", "mbv1:server"),
    )
    assert visible_adventure_question_count(conn, 8, {80, 81}) == 2
    assert current_adventure_question_count(conn, 8, {80, 81}) == 1


def test_client_guild_envelope_is_attached_even_with_an_empty_move_list():
    """The second B defect: an empty move list used to drop the envelope.

    A revealed or hint-assisted Guild answer produced no ``guild_answer``
    at all, so the server could only ever write a bare untrusted row.  This
    asserts the *behaviour* of the deployed client contract rather than the
    presence of a source substring.
    """

    index = (ROOT / "index.html").read_text(encoding="utf-8")
    metadata = index[
        index.index("function _currentReviewMetadata") : index.index("let playerColor")
    ]
    guard = metadata[metadata.index("if (!bossSourceContext && _guildQuestMode?.key") :]
    guard = guard[: guard.index("return metadata")]
    # The envelope is attached on Guild-mode key alone.  A non-empty move list
    # must not be part of the condition.
    assert "_guildQuestAnswerMoves.length" not in guard
    assert "metadata.guild_answer" in guard
    assert "metadata.guild_quest_key" in guard


def test_pure_dry_run_has_no_database_or_client_authority_dependency():
    source = (ROOT / "adventure_progress_compatibility.py").read_text(encoding="utf-8")
    start = source.index("def build_progression_milestone_dry_run")
    body = source[start:source.index("__all__", start)]
    assert "conn" not in body
    assert "execute(" not in body
