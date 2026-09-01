"""Zone-star trigger truth under the Owner-locked progression model.

An earlier revision of this file pinned the pre-ruling behaviour, in which
``award_zone_star_from_authoritative_answer`` added one star per settled Map
answer, so three correct answers reached three stars with no Lord clear at
all. The Owner has ruled that model incorrect; it is replaced here.

The model these tests hold:

* ``adventure_zone_star_progress.earned_stars`` is the star authority.
* ``adventure_zone_star_earnings`` is the append-only event ledger; its
  ``event_id`` makes every award idempotent.
* ``adventure_boss_progress`` remains a separate Boss authority and is never
  the source of a star.

Two, and only two, writers exist:

1. ``award_zone_star_from_boss_clear`` -- reached from
   ``/api/adventure/boss/finish`` only when ``passed and is_first_clear``.
   It awards star 1 and nothing else, so a Lord clear performs 0->1 and a
   repeated clear performs nothing.
2. ``award_zone_star_up_to_map_milestone`` -- reached from the internal Map
   Battle settlement handoff for a correct, server-settled Adventure answer.
   It raises the Zone to the star its Map coverage has earned (2 at 60%, 3 at
   100%), and refuses outright while the Zone has no first star, so coverage
   can never start the sequence.
"""

from __future__ import annotations

import sqlite3

import pytest

from adventure_zone_star_progression import (
    AUTHORITATIVE_BOSS_CLEAR_SOURCE,
    AUTHORITATIVE_ZONE_STAR_SOURCE,
    MAX_ZONE_STARS,
    award_zone_star_from_boss_clear,
    award_zone_star_up_to_map_milestone,
    load_zone_star_rows,
    zone_star_value,
)
from migrations.adventure_zone_star_progression_v1 import (
    EARNINGS_TABLE_NAME,
    upgrade,
)

USER_ID = 9001
ZONE = "k26_30"
AT = "2026-09-01T10:00:00"


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    upgrade(connection)
    return connection


def _stars(connection) -> int:
    return zone_star_value(load_zone_star_rows(connection, USER_ID), ZONE)


def _ledger(connection):
    return connection.execute(
        f"SELECT star_number, source, event_id FROM {EARNINGS_TABLE_NAME}"
        " WHERE user_id=? AND zone_key=? ORDER BY star_number",
        (USER_ID, ZONE),
    ).fetchall()


# --------------------------------------------------------------------------
# 0 -> 1 belongs to the Lord alone
# --------------------------------------------------------------------------


def test_lord_first_clear_awards_star_one(conn):
    result = award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-1", AT)
    assert result["awarded"] is True
    assert result["stars"] == 1
    assert result["source"] == AUTHORITATIVE_BOSS_CLEAR_SOURCE
    assert _stars(conn) == 1

    rows = _ledger(conn)
    assert len(rows) == 1
    assert rows[0]["star_number"] == 1
    assert rows[0]["source"] == AUTHORITATIVE_BOSS_CLEAR_SOURCE


def test_lord_clear_star_award_is_idempotent_per_operation(conn):
    first = award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-1", AT)
    repeat = award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-1", AT)
    assert first["awarded"] is True
    assert repeat["awarded"] is False
    assert repeat["status"] == "duplicate"
    assert _stars(conn) == 1
    assert len(_ledger(conn)) == 1


def test_a_second_distinct_lord_clear_does_not_add_a_second_star(conn):
    award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-1", AT)
    later = award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-2", AT)
    assert later["awarded"] is False
    assert later["status"] == "already_earned"
    assert _stars(conn) == 1


def test_settled_map_answer_cannot_perform_zero_to_one(conn):
    """Coverage cannot start the sequence, however complete it is."""
    result = award_zone_star_up_to_map_milestone(
        conn, USER_ID, ZONE, "submission-1", AT, milestone_star=MAX_ZONE_STARS
    )
    assert result["awarded"] is False
    assert result["status"] == "first_star_required"
    assert _stars(conn) == 0
    assert _ledger(conn) == []


# --------------------------------------------------------------------------
# 1 -> 2 and 2 -> 3 are Map coverage milestones on top of the first star
# --------------------------------------------------------------------------


def test_stars_two_and_three_come_from_map_coverage_milestones(conn):
    award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-1", AT)
    assert _stars(conn) == 1

    second = award_zone_star_up_to_map_milestone(
        conn, USER_ID, ZONE, "submission-60", AT, milestone_star=2
    )
    assert (second["awarded"], second["stars"]) == (True, 2)

    third = award_zone_star_up_to_map_milestone(
        conn, USER_ID, ZONE, "submission-100", AT, milestone_star=3
    )
    assert (third["awarded"], third["stars"]) == (True, 3)

    assert [row["star_number"] for row in _ledger(conn)] == [1, 2, 3]
    assert [row["source"] for row in _ledger(conn)] == [
        AUTHORITATIVE_BOSS_CLEAR_SOURCE,
        AUTHORITATIVE_ZONE_STAR_SOURCE,
        AUTHORITATIVE_ZONE_STAR_SOURCE,
    ]


def test_three_stars_are_not_reachable_without_a_lord_clear(conn):
    for index in range(1, 6):
        award_zone_star_up_to_map_milestone(
            conn, USER_ID, ZONE, f"submission-{index}", AT, milestone_star=3
        )
    assert _stars(conn) == 0
    assert _ledger(conn) == []


def test_stars_are_capped_at_three(conn):
    award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-1", AT)
    for index in range(1, 6):
        award_zone_star_up_to_map_milestone(
            conn, USER_ID, ZONE, f"submission-{index}", AT, milestone_star=3
        )
    assert _stars(conn) == MAX_ZONE_STARS
    assert len(_ledger(conn)) == MAX_ZONE_STARS


# --------------------------------------------------------------------------
# Guards the progression repair must not disturb
# --------------------------------------------------------------------------


def test_boss_progress_is_not_a_star_source(conn):
    """Zone-star authority never reads adventure_boss_progress."""
    conn.execute(
        """CREATE TABLE adventure_boss_progress(
            user_id INTEGER NOT NULL, zone_key TEXT NOT NULL,
            cleared INTEGER NOT NULL DEFAULT 0, stars INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, zone_key))"""
    )
    conn.execute(
        "INSERT INTO adventure_boss_progress(user_id, zone_key, cleared, stars)"
        " VALUES (?,?,1,3)",
        (USER_ID, ZONE),
    )
    # A fully cleared, three-star Boss row grants nothing in the separate
    # Zone-star authority.
    assert _stars(conn) == 0


def test_zone_star_award_requires_an_event_identity(conn):
    award_zone_star_from_boss_clear(conn, USER_ID, ZONE, "op-1", AT)
    for bad_event in ("", "   ", None):
        with pytest.raises(ValueError):
            award_zone_star_from_boss_clear(conn, USER_ID, ZONE, bad_event, AT)
        with pytest.raises(ValueError):
            award_zone_star_up_to_map_milestone(
                conn, USER_ID, ZONE, bad_event, AT, milestone_star=3
            )
    assert _stars(conn) == 1


def test_star_writers_are_reached_only_from_the_two_traced_call_sites():
    """Pin the call graph: no third star writer, and Lord's is gated on PASS."""
    import inspect
    import re

    import app as app_module

    source = inspect.getsource(app_module)
    boss_calls = re.findall(r"award_zone_star_from_boss_clear\(", source)
    milestone_calls = re.findall(r"award_zone_star_up_to_map_milestone\(", source)
    # One import line plus one call site each.
    assert len(boss_calls) == 1
    assert len(milestone_calls) == 1
    # The retired per-answer writer must not reappear anywhere.
    assert "award_zone_star_from_authoritative_answer" not in source

    finish = inspect.getsource(app_module.adventure_boss_finish)
    # The Lord star write is gated on a genuine PASS that is also a first
    # clear; a failed or repeat clear never reaches the writer.
    assert "if passed and is_first_clear:" in finish
    assert "award_zone_star_from_boss_clear(" in finish


def test_failed_lord_cannot_reach_the_star_writer():
    """FAILED_LORD_MINTS_STAR=NO, proven from the settlement gate itself."""
    import inspect

    import app as app_module

    finish = inspect.getsource(app_module.adventure_boss_finish)
    gate_index = finish.index("if passed and is_first_clear:")
    writer_index = finish.index("award_zone_star_from_boss_clear(")
    assert gate_index < writer_index

    # And the invalid-size refusal returns before any settlement at all.
    refusal_index = finish.index("invalid_attempt_size")
    assert refusal_index < gate_index
