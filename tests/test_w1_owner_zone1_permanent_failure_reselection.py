"""Owner postdeploy acceptance corrective, Issue A.

Entering Zone 1 showed 「本次練習沒有其他可用題目了。」 with an empty board.

Root cause: in loadQuestion(), reselection after a PERMANENT map-battle question
failure was gated on `failure.quarantined` -- the RESULT of a bookkeeping write,
not the failure itself. SRS.quarantineQuestion() returns false whenever the id
is not an integer or the revision resolves empty, so whenever that write did not
land the client skipped reselection entirely and fell through to
_showSessionNoValidQuestion(), which only calls setMsg and never builds a board.
A single permanently-rejected question therefore stranded the whole zone.

Zone 1 (k26_30, topics '1圍棋新手村' / '2新手村的考驗') is the zone most exposed to
this: the known ambiguous-authoritative-sgf-player-color records sit in its id
band and _pickAdventureTarget takes the first unseen record in corpus order.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def _permanent_failure_branch() -> str:
    start = INDEX.index("if (_mapBattleV1PrepareFailure?.permanent === true) {")
    end = INDEX.index("if (!isCurrent() || generation !== _mapBattleV1LifecycleGeneration", start)
    return INDEX[start:end]


def test_reselection_is_not_gated_on_the_quarantine_write_result():
    branch = _permanent_failure_branch()
    # The defect was literally `if (failure.quarantined) { ...reselect... }`.
    assert not re.search(r"if\s*\(\s*failure\.quarantined\s*\)", branch), (
        "reselection must not be conditioned on the quarantine bookkeeping result"
    )
    # Reselection must be attempted unconditionally on a permanent failure.
    assert "_pickNextAdventureTarget(" in branch
    assert "SRS.findNextAvailableQuestion(" in branch


def test_failed_question_is_always_excluded_for_the_session():
    branch = _permanent_failure_branch()
    assert "_markSessionQuestionUnplayable(q)" in branch
    # ...and the exclusion must be applied BEFORE reselection, or the very same
    # question can be handed straight back.
    assert branch.index("_markSessionQuestionUnplayable(q)") < branch.index(
        "_pickNextAdventureTarget("
    )


def test_terminal_message_only_after_reselection_actually_failed():
    branch = _permanent_failure_branch()
    assert "_showSessionNoValidQuestion();" in branch
    # The terminal message must come after the reselection attempt, not before.
    assert branch.index("_pickNextAdventureTarget(") < branch.index(
        "_showSessionNoValidQuestion();"
    )
    # And the reselected question must not be the one that just failed.
    assert "Number(nextAdventureQuestion.id) !== Number(questionId)" in branch


def test_terminal_message_is_diagnosable_from_production():
    branch = _permanent_failure_branch()
    # "pool was empty" vs "pool was exhausted by exclusions" must be
    # distinguishable from the trace alone.
    assert "poolSize:" in branch
    assert "unplayableCount:" in branch
    assert "quarantined:" in branch


def test_session_exclusion_is_honoured_by_every_selector():
    # One predicate feeds _pickAdventureTarget, _pickNextAdventureTarget,
    # _nextAdventureQuestionExcludingQuarantine and the loadQuestion guard, so
    # extending it covers the whole selection surface.
    start = INDEX.index("function _isSessionQuestionQuarantined(question) {")
    end = INDEX.index("}", INDEX.index("return !!(", start))
    predicate = INDEX[start:end]
    assert "_isSessionQuestionUnplayable(question)" in predicate

    assert "const _sessionUnplayableQuestionIds = new Set();" in INDEX
    assert "function _markSessionQuestionUnplayable(question)" in INDEX
    assert "function _isSessionQuestionUnplayable(question)" in INDEX

    for selector in (
        "function _pickAdventureTarget(qs)",
        "function _pickNextAdventureTarget(qs, currentId)",
        "function _nextAdventureQuestionExcludingQuarantine(qs, currentId",
    ):
        body_start = INDEX.index(selector)
        body_end = INDEX.index("\n}", body_start)
        assert "_isSessionQuestionQuarantined(" in INDEX[body_start:body_end], selector


def test_zone_entry_never_leaves_a_revealed_empty_board():
    start = INDEX.index("async function enterAdventureZoneInPage(zone) {")
    end = INDEX.index("\n}", INDEX.index("entryGeneration", start))
    body = INDEX[start:end]
    # The no-target path reveals the board wrapper earlier in the function; if
    # it bails it must put the surface back and say something.
    no_target = body[body.index("if (!target || typeof publishAdventureShellOwner"):]
    assert "_bw.classList.add('hidden')" in no_target
    assert "_ws.classList.remove('hidden')" in no_target
    assert "本區可用題目已完成。" in no_target
    assert "ADVENTURE_ENTRY_NO_TARGET" in no_target
    # An empty zone pool must be traceable rather than silent.
    assert "ADVENTURE_ENTRY_EMPTY_POOL" in body


def test_zone1_pool_rule_is_unchanged():
    # The corrective must not quietly change which questions Zone 1 offers.
    assert "_books.has(q.topic)" in INDEX
    assert "1圍棋新手村" in INDEX or "1圍棋新手村" in (ROOT / "chapter_i18n.py").read_text(
        encoding="utf-8"
    )


def test_session_exclusion_shares_the_srs_quarantine_lifetime():
    """Independent review finding: the new set must not outlive its siblings.

    _sessionUnplayableQuestionIds joins the SRS session quarantine inside
    _isSessionQuestionQuarantined, which every selector consults -- including
    Daily Training, Premium Weekly Training and Friend Challenge. If it were not
    cleared at the same mode boundaries, a Map Battle prepare failure would keep
    excluding that question from those other modes for the rest of the page
    session, a reach this corrective never intended.
    """
    assert "function _clearSessionQuestionExclusions() {" in INDEX
    helper_start = INDEX.index("function _clearSessionQuestionExclusions() {")
    helper = INDEX[helper_start:INDEX.index("\n}", helper_start)]
    assert "_sessionUnplayableQuestionIds.clear();" in helper
    assert "SRS.clearSessionQuarantine();" in helper

    # Every reset site must go through the helper: no bare quarantine clear may
    # survive, or that site silently keeps the stale exclusion.
    bare = [
        line for line in INDEX.splitlines()
        if "SRS.clearSessionQuarantine()" in line
        and "_sessionUnplayableQuestionIds" not in line
        and "function _clearSessionQuestionExclusions" not in line
    ]
    # Only the helper's own body may call it directly.
    assert len(bare) == 1, bare
    assert bare[0].strip() == "SRS.clearSessionQuarantine();"

    # The five known boundaries all call the helper.
    assert INDEX.count("_clearSessionQuestionExclusions();") == 5


def test_sequential_fallback_cannot_undo_the_session_exclusion():
    """SRS.findNextAvailableQuestion knows only the revision-bound quarantine.

    In the exact failure mode this repairs -- the quarantine write did NOT land
    -- the fallback can hand back a question already known to be unplayable.
    """
    branch = _permanent_failure_branch()
    assert "const sequentialFallback = SRS.findNextAvailableQuestion(" in branch
    assert "_isSessionQuestionQuarantined(sequentialFallback) ? null : sequentialFallback" in branch
    assert branch.index("_markSessionQuestionUnplayable(q)") < branch.index(
        "_isSessionQuestionQuarantined(sequentialFallback)"
    )
