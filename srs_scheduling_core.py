"""The one canonical SRS scheduling persistence core.

This module is the sole owner of SM-2 state calculation and the sole writer
of ``srs_cards``.  Every domain that needs to advance a learner's spaced
repetition schedule -- Map Battle settlement, the public review route,
and the server-judged practice answer path -- performs its own domain
validation first and then calls :func:`apply_srs_scheduling` here.

Deliberately free of Flask, of any database connection lifecycle, and of
any domain knowledge.  It is handed an already-open connection and always
operates inside the caller's transaction, exactly like
``question_idempotency.insert_review_log_with_identity`` (the equivalent
single primitive for ``review_log``) already does.

What this module does NOT own, by design:

* deciding whether an answer was correct (each domain's own judge does);
* minting question identity, answer-event identity, or trust markers;
* any reward or progression side effect -- XP, rank, combo, pets,
  monsters, quests, grimoire, loot, badges, Elo, mistake log, Zone stars.
  Those remain with the caller and are gated on the sticky
  ``progress_credited`` flag this module resolves and reports back.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ProgressCreditPolicy(str, Enum):
    """Who may set the sticky anti-farming ``progress_credited`` flag.

    This replaces the historical implicit coupling ``if internal``, which
    conflated "this caller is trusted" with "this caller is Map Battle".
    The policy is now an explicit, caller-declared value so a trusted
    caller that must not mint progression credit (the server-judged
    practice path) can say so without inheriting Map Battle's semantics.
    """

    #: SRS scheduling still advances, but no progression credit is minted.
    #: Used by the public review route (a self-reported grade is never
    #: progression authority) and by the server-judged practice path
    #: (trusted evidence, but deliberately not a progression grant).
    NEVER = "NEVER"

    #: Grant credit on the first-ever passing review of a (user, question)
    #: pair, sticky thereafter.  Used by the server-settled Map Battle
    #: progression handoff.
    FIRST_PASS_ONLY = "FIRST_PASS_ONLY"


@dataclass(frozen=True, slots=True)
class SrsSchedulingOutcome:
    """The committed scheduling state plus the progression decision.

    ``progress_credit_granted`` is what a caller's reward layer must gate
    on -- it is True only when *this* call newly set the sticky flag, never
    merely because the flag was already set by an earlier review.
    """

    ease_factor: float
    interval: int
    repetitions: int
    due_date: str
    last_grade: int
    progress_credited: int
    progress_credit_granted: bool
    #: Whether a row already existed for this (user, question) before this
    #: call.  Callers use it for "first time answering this question"
    #: presentation decisions; it is not a progression authority.
    existed: bool


def sm2_update(ef, iv, rp, grade):
    q = grade
    if q < 3:
        rp, iv = 0, 1
    else:
        iv = 1 if rp==0 else (6 if rp==1 else round(iv*ef))
        rp += 1
    iv = min(iv, 3650)
    ef  = max(1.3, ef + 0.1 - (5-q)*(0.08+(5-q)*0.02))
    due = (datetime.date.today() + datetime.timedelta(days=iv)).isoformat()
    return ef, iv, rp, due


def should_grant_review_progress(existing_srs_row, grade):
    """Phase 4D anti-farming: True only for the first-ever passing review
    of a (user, question) pair. Progression side effects (XP, pet XP,
    monster/boss damage, kills, loot, SP, daily-quest credit) must gate on
    this, not on `last_grade` -- last_grade flips on every submission and
    can be reset by an intentional fail/pass toggle to re-farm rewards,
    while `progress_credited` is sticky once set. SRS scheduling itself
    (ease_factor/interval/due_date/last_grade) is unaffected and still
    updates on every review regardless of this check."""
    if grade < 3:
        return False
    if not existing_srs_row:
        return True
    try:
        credited = existing_srs_row['progress_credited']
    except (KeyError, IndexError, TypeError):
        credited = existing_srs_row.get('progress_credited')
    return not bool(credited)


def apply_srs_scheduling(
    conn: Any,
    *,
    user_id: int,
    question_id: int,
    grade: int,
    now: str,
    progress_credit_policy: ProgressCreditPolicy = ProgressCreditPolicy.NEVER,
) -> SrsSchedulingOutcome:
    """Advance SM-2 and write the one canonical ``srs_cards`` row.

    Reads the pre-existing row, applies the SM-2 transition, resolves
    progression credit under the caller's declared policy, and upserts --
    preserving the sticky ``GREATEST(progress_credited, ...)`` semantics so
    a later review can never clear a credit an earlier one earned.

    Never commits and never rolls back: the caller owns the transaction.
    """

    row = conn.execute(
        'SELECT * FROM srs_cards WHERE user_id=? AND question_id=?',
        (user_id, question_id),
    ).fetchone()

    ef, iv, rp = (
        (row['ease_factor'], row['interval'], row['repetitions'])
        if row else (2.5, 0, 0)
    )
    ef, iv, rp, due = sm2_update(ef, iv, rp, grade)

    # Phase 4D anti-farming: computed from the row as it existed BEFORE
    # this submission. Once true for a (user, question) pair, stays true
    # forever via progress_credited (see should_grant_review_progress).
    # A caller declaring NEVER continues to update SM-2 below, but is never
    # allowed to become progression/reward/combat authority.
    should_grant_progress = (
        should_grant_review_progress(row, grade)
        if progress_credit_policy is ProgressCreditPolicy.FIRST_PASS_ONLY
        else False
    )
    existing_progress_credited = row['progress_credited'] if row else 0
    progress_credited_flag = 1 if (
        should_grant_progress or existing_progress_credited
    ) else 0

    conn.execute('''INSERT INTO srs_cards(user_id,question_id,ease_factor,interval,repetitions,due_date,last_grade,updated_at,progress_credited)
        VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,question_id) DO UPDATE SET
        ease_factor=excluded.ease_factor, interval=excluded.interval,
        repetitions=excluded.repetitions, due_date=excluded.due_date,
        last_grade=excluded.last_grade, updated_at=excluded.updated_at,
        progress_credited=GREATEST(srs_cards.progress_credited, excluded.progress_credited)''',
        (user_id, question_id, ef, iv, rp, due, grade, now, progress_credited_flag))

    return SrsSchedulingOutcome(
        ease_factor=ef,
        interval=iv,
        repetitions=rp,
        due_date=due,
        last_grade=grade,
        progress_credited=progress_credited_flag,
        progress_credit_granted=bool(should_grant_progress),
        existed=bool(row),
    )


__all__ = [
    "ProgressCreditPolicy",
    "SrsSchedulingOutcome",
    "apply_srs_scheduling",
    "should_grant_review_progress",
    "sm2_update",
]
