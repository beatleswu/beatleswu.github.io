"""Owner-locked RPG V1 Zone progression: 30% / Lord / 60% / 100%.

The contract these tests hold:

* Map progress is distinct **correct** questions over the Zone's canonical
  pool; percentages round **up**.
* >= 30% correct opens the first Lord Challenge.
* The first Lord clear -- and only that -- grants the first star, and the
  first star is what unlocks the next Zone.
* With a first star, >= 60% grants the second and 100% grants the third.
  Coverage alone never grants a star.
* A repeated Lord clear grants no further star.
* After a Lord failure, 30 further distinct correct Map questions are
  required before a retry.
"""

from __future__ import annotations

import math
import sqlite3

import pytest

from adventure_zone_progression_authority import (
    FIRST_STAR,
    LORD_ELIGIBILITY_PERCENT,
    LORD_RETRY_REQUIRED_NEW_CORRECT,
    SECOND_STAR,
    SECOND_STAR_PERCENT,
    THIRD_STAR,
    THIRD_STAR_PERCENT,
    is_lord_eligible,
    lord_eligibility_requirement,
    map_milestone_star,
    next_zone_is_unlocked_by,
    required_correct_for_percent,
    second_star_requirement,
    third_star_requirement,
)
from adventure_zone_star_progression import (
    award_zone_star_from_boss_clear,
    award_zone_star_up_to_map_milestone,
    load_zone_star_rows,
    zone_star_value,
)
from migrations.adventure_zone_star_progression_v1 import (
    EARNINGS_TABLE_NAME,
    upgrade,
)

ZONE = "k26_30"
AT = "2026-09-01T10:00:00"

# Deliberately awkward totals: none divides evenly by 3 or 5.
NON_ROUND_TOTALS = [1, 7, 13, 97, 101, 598, 683, 1186, 1591, 1939]


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    upgrade(connection)
    return connection


# --------------------------------------------------------------------------
# Thresholds round up
# --------------------------------------------------------------------------


@pytest.mark.parametrize("total", NON_ROUND_TOTALS)
@pytest.mark.parametrize(
    "percent", [LORD_ELIGIBILITY_PERCENT, SECOND_STAR_PERCENT, THIRD_STAR_PERCENT]
)
def test_thresholds_use_ceiling(total, percent):
    required = required_correct_for_percent(total, percent)
    assert required == math.ceil(total * percent / 100)
    # The requirement genuinely reaches the stated share, and one fewer does not.
    assert required / total >= percent / 100
    if required > 0:
        assert (required - 1) / total < percent / 100


def test_hundred_percent_is_exactly_the_whole_pool():
    for total in NON_ROUND_TOTALS:
        assert third_star_requirement(total) == total


def test_the_old_rounded_percentage_admitted_players_below_thirty_percent():
    """Regression for the specific defect this repair removes."""
    total, correct = 1939, 576
    assert round(correct / total * 100) == 30  # what the old gate compared
    assert correct / total < 0.30  # but the player is short of 30%
    assert is_lord_eligible(correct, total) is False
    assert lord_eligibility_requirement(total) == 582


# --------------------------------------------------------------------------
# 30% Lord eligibility
# --------------------------------------------------------------------------


@pytest.mark.parametrize("total", NON_ROUND_TOTALS)
def test_lord_eligibility_boundary(total):
    required = lord_eligibility_requirement(total)
    assert is_lord_eligible(required - 1, total) is False
    assert is_lord_eligible(required, total) is True
    assert is_lord_eligible(total, total) is True


def test_lord_eligibility_needs_a_pool():
    assert is_lord_eligible(0, 0) is False
    assert is_lord_eligible(5, 0) is False


# --------------------------------------------------------------------------
# Milestone star selection
# --------------------------------------------------------------------------


@pytest.mark.parametrize("total", NON_ROUND_TOTALS)
def test_map_coverage_without_a_first_star_never_earns_a_star(total):
    for correct in (0, lord_eligibility_requirement(total), second_star_requirement(total), total):
        assert map_milestone_star(correct, total, has_first_star=False) == 0


@pytest.mark.parametrize("total", NON_ROUND_TOTALS)
def test_milestone_boundaries_with_a_first_star(total):
    second = second_star_requirement(total)
    assert map_milestone_star(0, total, has_first_star=True) == FIRST_STAR
    assert map_milestone_star(second - 1, total, has_first_star=True) == FIRST_STAR
    # On a one-question Zone the 60% and 100% marks are the same answer, so
    # reaching the second milestone is also reaching the third.
    expected_at_second = THIRD_STAR if second >= total else SECOND_STAR
    assert map_milestone_star(second, total, has_first_star=True) == expected_at_second
    if total > 1:
        assert map_milestone_star(total - 1, total, has_first_star=True) in (
            SECOND_STAR, FIRST_STAR
        )
    assert map_milestone_star(total, total, has_first_star=True) == THIRD_STAR


def test_next_zone_unlock_is_the_first_star():
    assert next_zone_is_unlocked_by(0) is False
    assert next_zone_is_unlocked_by(1) is True
    assert next_zone_is_unlocked_by(2) is True
    assert next_zone_is_unlocked_by(3) is True
    assert next_zone_is_unlocked_by(None) is False


# --------------------------------------------------------------------------
# Star ledger behaviour under the milestone rules
# --------------------------------------------------------------------------


def _stars(connection, user_id):
    return zone_star_value(load_zone_star_rows(connection, user_id), ZONE)


def test_zero_star_plus_full_map_coverage_grants_nothing(conn):
    result = award_zone_star_up_to_map_milestone(
        conn, 1, ZONE, "sub-1", AT, milestone_star=THIRD_STAR
    )
    assert result["status"] == "first_star_required"
    assert result["awarded"] is False
    assert _stars(conn, 1) == 0
    # No progress row is even created for a Zone that has earned nothing.
    assert load_zone_star_rows(conn, 1) == {}


def test_first_lord_clear_grants_exactly_one_star(conn):
    result = award_zone_star_from_boss_clear(conn, 2, ZONE, "lord-1", AT)
    assert result["awarded"] is True
    assert result["stars"] == FIRST_STAR
    assert _stars(conn, 2) == 1


def test_repeated_lord_clear_adds_no_star(conn):
    award_zone_star_from_boss_clear(conn, 3, ZONE, "lord-1", AT)
    award_zone_star_up_to_map_milestone(
        conn, 3, ZONE, "sub-60", AT, milestone_star=SECOND_STAR
    )
    assert _stars(conn, 3) == 2

    # Second and third distinct Lord clears must not move the star count.
    for event in ("lord-2", "lord-3"):
        repeat = award_zone_star_from_boss_clear(conn, 3, ZONE, event, AT)
        assert repeat["awarded"] is False
        assert _stars(conn, 3) == 2


def test_one_star_plus_sixty_percent_grants_two(conn):
    award_zone_star_from_boss_clear(conn, 4, ZONE, "lord-1", AT)
    result = award_zone_star_up_to_map_milestone(
        conn, 4, ZONE, "sub-60", AT, milestone_star=SECOND_STAR
    )
    assert result["stars"] == SECOND_STAR
    assert _stars(conn, 4) == 2


def test_one_star_plus_full_coverage_reaches_three_without_replay(conn):
    award_zone_star_from_boss_clear(conn, 5, ZONE, "lord-1", AT)
    result = award_zone_star_up_to_map_milestone(
        conn, 5, ZONE, "sub-100", AT, milestone_star=THIRD_STAR
    )
    assert result["stars"] == THIRD_STAR
    assert result["awarded_stars"] == [SECOND_STAR, THIRD_STAR]
    assert _stars(conn, 5) == 3


def test_milestone_awards_are_idempotent(conn):
    award_zone_star_from_boss_clear(conn, 6, ZONE, "lord-1", AT)
    for _ in range(4):
        award_zone_star_up_to_map_milestone(
            conn, 6, ZONE, "sub-60", AT, milestone_star=SECOND_STAR
        )
    assert _stars(conn, 6) == 2
    assert conn.execute(
        f"SELECT COUNT(*) FROM {EARNINGS_TABLE_NAME} WHERE user_id=6"
    ).fetchone()[0] == 2


def test_stars_never_exceed_three(conn):
    award_zone_star_from_boss_clear(conn, 7, ZONE, "lord-1", AT)
    for index in range(6):
        award_zone_star_up_to_map_milestone(
            conn, 7, ZONE, f"sub-{index}", AT, milestone_star=THIRD_STAR
        )
    assert _stars(conn, 7) == 3
    assert conn.execute(
        f"SELECT COUNT(*) FROM {EARNINGS_TABLE_NAME} WHERE user_id=7"
    ).fetchone()[0] == 3


def test_a_star_is_never_awarded_without_an_event_identity(conn):
    award_zone_star_from_boss_clear(conn, 8, ZONE, "lord-1", AT)
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            award_zone_star_up_to_map_milestone(
                conn, 8, ZONE, bad, AT, milestone_star=THIRD_STAR
            )
    assert _stars(conn, 8) == 1


def test_retry_requirement_constant_matches_the_owner_contract():
    assert LORD_RETRY_REQUIRED_NEW_CORRECT == 30
