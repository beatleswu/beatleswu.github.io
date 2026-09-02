"""Guild answers must judge on ordinary problem SGFs that declare no PL[].

Production P0, immediately after the R3 deploy: every Guild answer failed with
the client message

    答題記錄寫入失敗，這題尚未儲存。請稍後重試或重新整理頁面。

``guild_quest_answer_service._question_board_context`` resolved whose turn it
was with a bare ``PL\\[([BW])\\]`` regex and no fallback.  Most Go problem SGFs
carry no ``PL[]`` property -- the turn is stated by the first move -- so the
lookup returned ``None`` and the service raised ``judge_unavailable`` (503).
``judge_unavailable`` is not one of the three codes ReviewTransport hands back
as a payload, so the transport threw and index.html showed the generic
save-failure message.  Nothing was ever written.

Map Battle judges the same corpus correctly because it resolves the player
from the parsed SGF and falls back to the first move's colour
(``_map_battle_question_context``, app.py).  These tests pin the Guild path to
that same derivation, and keep the fail-closed guarantee for content that is
genuinely unresolvable.

Lord Trial is NOT a second example of this pattern: it has the identical
unfixed ``PL[]``-only regex, live, in ``lord_trial_answer_service.py``. It
stays safe only because ``lord_trial_admission.py`` pre-filters unjudgeable
questions out of the pool at attempt-creation time -- a different mitigation,
applied earlier, and out of scope for this fix. See
GO_ODYSSEY_LORD_TRIAL_PLAYER_TO_MOVE_FOLLOWUP_001.
"""

from __future__ import annotations

import pathlib
import sys

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from guild_quest_answer_service import (  # noqa: E402
    GuildQuestAnswerError,
    build_guild_quest_answer_context,
    judge_guild_quest_answer,
)

QUEST_KEY = "whole_board::LV2"

# The ordinary shape of a problem: a first move, no PL[] property.
ORDINARY_PROBLEM = "(;GM[1]FF[4]SZ[19]AB[dd][pp]AW[dp][pd];B[qf])"
# The same problem with the turn stated explicitly.
EXPLICIT_PL = "(;GM[1]FF[4]SZ[19]PL[B]AB[dd][pp]AW[dp][pd];B[qf])"


def _question(content, qid=9001):
    return {"id": qid, "content": content}


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------
def test_problem_without_pl_property_is_judgeable():
    """The exact production failure: this used to raise judge_unavailable."""

    context = build_guild_quest_answer_context(_question(ORDINARY_PROBLEM), QUEST_KEY)
    assert context["player_color"] == "B"
    assert context["board_size"] == 19


def test_explicit_pl_property_still_wins():
    context = build_guild_quest_answer_context(_question(EXPLICIT_PL), QUEST_KEY)
    assert context["player_color"] == "B"


def test_guild_derivation_matches_the_map_battle_derivation():
    """Guild must resolve the same player as the canonical judged paths.

    This is the invariant whose absence caused the incident: two code paths
    judging the same corpus disagreed about whether it was judgeable at all.
    """

    from sgf_engine.parser.sgf_parser import parse_sgf

    for content in (ORDINARY_PROBLEM, EXPLICIT_PL):
        root = parse_sgf(content, strict=True)
        expected = str(root.metadata.get("player_to_move") or "").upper()
        if not expected:
            colors = {
                child.move.color
                for child in root.children
                if child.move is not None and child.move.color in ("B", "W")
            }
            assert len(colors) == 1
            expected = colors.pop()
        guild = build_guild_quest_answer_context(_question(content), QUEST_KEY)
        assert guild["player_color"] == expected, content


def test_a_correct_answer_on_a_no_pl_problem_is_judged_pass():
    """End to end through the judge: the answer now yields a real verdict."""

    _canonical, judge = judge_guild_quest_answer(
        {"moves": [{"action": "play", "x": 16, "y": 5}]},
        question=_question(ORDINARY_PROBLEM),
        quest_key=QUEST_KEY,
    )
    assert judge.result == "CORRECT"
    assert judge.authoritative_grade == 5
    assert judge.judge_version == "guild-quest-map-battle-judge-v1"


def test_a_wrong_answer_on_a_no_pl_problem_is_judged_fail_not_unavailable():
    """A wrong answer must be a judged FAIL, never a transport-style error."""

    _canonical, judge = judge_guild_quest_answer(
        {"moves": [{"action": "play", "x": 0, "y": 0}]},
        question=_question(ORDINARY_PROBLEM),
        quest_key=QUEST_KEY,
    )
    assert judge.result == "INCORRECT"
    assert judge.authoritative_grade == 0


# ---------------------------------------------------------------------------
# Fail-closed guarantees preserved
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "content,reason",
    [
        ("(;GM[1]SZ[19]AB[dp]AW[pd])", "no move states the turn"),
        ("(;GM[1]SZ[19]AB[dp](;B[dd])(;W[pq]))", "first-move colours disagree"),
        ("(;GM[1]SZ[99]PL[B]AB[dp](;B[dd]))", "board size out of range"),
        ("(;GM[1]SZ[1]PL[B])", "board size below the minimum"),
    ],
)
def test_unresolvable_content_still_fails_closed(content, reason):
    with pytest.raises(GuildQuestAnswerError) as excinfo:
        build_guild_quest_answer_context(_question(content), QUEST_KEY)
    assert excinfo.value.code == "judge_unavailable", reason
    assert excinfo.value.status == 503


def test_empty_or_missing_content_still_fails_closed():
    for content in ("", "   ", None, 123):
        with pytest.raises(GuildQuestAnswerError) as excinfo:
            build_guild_quest_answer_context({"id": 9001, "content": content}, QUEST_KEY)
        assert excinfo.value.code == "judge_unavailable"


def test_client_still_cannot_supply_the_player_colour():
    """The turn stays server-derived; a client field is still forbidden."""

    with pytest.raises(GuildQuestAnswerError) as excinfo:
        judge_guild_quest_answer(
            {"moves": [{"action": "play", "x": 16, "y": 5}], "player_color": "W"},
            question=_question(ORDINARY_PROBLEM),
            quest_key=QUEST_KEY,
        )
    assert excinfo.value.code == "forbidden_answer_field"
