"""Owner-locked Adventure Zone progression thresholds.

The RPG V1 Zone contract is:

* Map progress is measured in **distinct server-authoritative correct**
  questions for the Zone, against the Zone's canonical question pool.
* At >= 30% correct the first Lord Challenge becomes available.
* The first Lord clear -- and nothing else -- grants the first star, which is
  what unlocks the next Zone.
* With a first star already earned, >= 60% correct grants the second star and
  100% correct grants the third.  Map coverage alone never grants a star.
* A repeated Lord clear grants no further star.

This module owns only the arithmetic and the ordering rules.  It holds no
database access, no reward logic and no identity handling, so the thresholds
can be tested exhaustively without a runtime.

Percentages round **up**: a player must genuinely reach the stated share of
the Zone before the milestone opens.  The previous runtime compared a
``round()``-ed percentage, which admitted a player slightly below the stated
threshold (e.g. 576 of 1939 correct is 29.7%, displayed as 30%).
"""

from __future__ import annotations

# Share of a Zone's canonical question pool that must be answered correctly.
LORD_ELIGIBILITY_PERCENT = 30
SECOND_STAR_PERCENT = 60
THIRD_STAR_PERCENT = 100

MAX_ZONE_STARS = 3
FIRST_STAR = 1
SECOND_STAR = 2
THIRD_STAR = 3

# Distinct additional correct Map questions required after a Lord failure.
LORD_RETRY_REQUIRED_NEW_CORRECT = 30


def required_correct_for_percent(total, percent):
    """Return the correct-answer count that first reaches *percent* of *total*.

    Uses ceiling division so the requirement is never satisfied below the
    stated percentage.  ``percent=100`` is exactly ``total``.
    """

    total = max(0, int(total))
    percent = int(percent)
    if total <= 0 or percent <= 0:
        return 0
    if percent >= 100:
        return total
    return -(-total * percent // 100)


def lord_eligibility_requirement(total):
    """Distinct correct answers needed before the first Lord Challenge."""

    return required_correct_for_percent(total, LORD_ELIGIBILITY_PERCENT)


def second_star_requirement(total):
    return required_correct_for_percent(total, SECOND_STAR_PERCENT)


def third_star_requirement(total):
    return required_correct_for_percent(total, THIRD_STAR_PERCENT)


def is_lord_eligible(correct_count, total):
    """Return whether Map coverage opens the Lord Challenge.

    This is the coverage gate only.  Zone unlock, the post-failure retry gate
    and the already-cleared state are separate conditions applied by the
    caller.
    """

    total = max(0, int(total))
    if total <= 0:
        return False
    return max(0, int(correct_count)) >= lord_eligibility_requirement(total)


def map_milestone_star(correct_count, total, *, has_first_star):
    """Return the star level Map coverage justifies for this Zone.

    Map coverage is never a substitute for the Lord: without a first star the
    result is always ``0``, no matter how complete the coverage is.  With a
    first star the result rises to 2 at 60% and 3 at 100%.

    A player may cross straight from below 60% to 100% -- the 60% milestone
    does not have to be observed separately for the third star to be correct.
    """

    if not has_first_star:
        return 0
    total = max(0, int(total))
    correct = max(0, int(correct_count))
    if total <= 0:
        return FIRST_STAR
    if correct >= third_star_requirement(total):
        return THIRD_STAR
    if correct >= second_star_requirement(total):
        return SECOND_STAR
    return FIRST_STAR


def next_zone_is_unlocked_by(effective_stars):
    """Return whether a Zone's star state unlocks the following Zone.

    The first star is the unlock event.  Map coverage, starting a Lord
    Challenge, and failing one all leave this ``False``.
    """

    return max(0, int(effective_stars or 0)) >= FIRST_STAR


__all__ = [
    "FIRST_STAR",
    "LORD_ELIGIBILITY_PERCENT",
    "LORD_RETRY_REQUIRED_NEW_CORRECT",
    "MAX_ZONE_STARS",
    "SECOND_STAR",
    "SECOND_STAR_PERCENT",
    "THIRD_STAR",
    "THIRD_STAR_PERCENT",
    "is_lord_eligible",
    "lord_eligibility_requirement",
    "map_milestone_star",
    "next_zone_is_unlocked_by",
    "required_correct_for_percent",
    "second_star_requirement",
    "third_star_requirement",
]
