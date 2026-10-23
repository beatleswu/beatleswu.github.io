"""G076 internal SGF step authority: no answers leaked before step settlement."""
from dataclasses import asdict
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from g076_server_step_authority import (
    StepAuthorityUnavailable, adjudicate_next_step,
)

LINEAR = {"id": 1, "content": "(;SZ[9]PL[B];B[aa];W[bb];B[cc])"}
BRANCH = {
    "id": 2, "answer_policy": "g065-explicit-v1",
    "content": "(;SZ[9]PL[B](;B[aa]C[G065:CORRECT])(;B[bb]C[G065:INCORRECT]))",
}


def judge(q, history=(), move=(0, 0), side="B", size=9):
    return adjudicate_next_step(
        q, player_color=side, board_size=size,
        trusted_history=history, move=move,
    )


def test_correct_prefix_is_continue_not_wrong_and_only_returns_forced_reply():
    result = judge(LINEAR, move=(0, 0))
    assert result.status == "CONTINUE"
    assert result.opponent_reply == (1, 1)
    assert result.reason == "server_authorized_prefix"
    assert set(asdict(result)) == {"status", "opponent_reply", "reason"}
    assert "(2, 2)" not in str(asdict(result))


def test_full_second_player_move_resolves_correctly():
    result = judge(LINEAR, history=((0, 0),), move=(2, 2))
    assert result.status == "CORRECT"
    assert result.opponent_reply is None


def test_wrong_first_or_second_move_never_returns_solution():
    for result in (judge(LINEAR, move=(3, 3)),
                   judge(LINEAR, history=((0, 0),), move=(4, 4))):
        assert result.status == "INCORRECT"
        assert result.opponent_reply is None
        assert result.reason == "off_answer_tree"


def test_explicit_policy_verdicts_do_not_assume_all_branches_correct():
    good = judge(BRANCH, move=(0, 0))
    bad = judge(BRANCH, move=(1, 1))
    assert good.status == "CORRECT"
    assert bad.status == "INCORRECT"
    assert bad.reason == "explicit_failure_terminal"


def test_invalid_history_does_not_open_an_answer_oracle():
    with pytest.raises(StepAuthorityUnavailable, match="invalid_server_history"):
        judge(LINEAR, history=((3, 3),), move=(2, 2))
    with pytest.raises(StepAuthorityUnavailable, match="invalid_server_history"):
        judge(LINEAR, history=((0, 0), (2, 2)), move=(0, 0))


def test_ambiguous_opponent_reply_requires_owner_authority():
    question = {
        "content": "(;SZ[9]PL[B];B[aa](;W[bb];B[cc])(;W[dd];B[ee]))"
    }
    with pytest.raises(StepAuthorityUnavailable, match="ambiguous_opponent_reply"):
        judge(question, move=(0, 0))


def test_unannotated_ambiguous_terminal_rejected_instead_of_awarded():
    question = {"content": "(;SZ[9]PL[B](;B[aa])(;B[bb]))"}
    with pytest.raises(StepAuthorityUnavailable, match="legacy_ambiguous"):
        judge(question, move=(0, 0))


@pytest.mark.parametrize("history,move,side,size", [
    ((),(0,0),"X",9), ((),(0,0),"B",26), ((),(-1,0),"B",9),
    ((),(0,True),"B",9), ((),(0,0),"B",True),
    ((),(9,0),"B",9), ("user supplied",(0,0),"B",9),
])
def test_invalid_or_malformed_step_authority_is_rejected(history,move,side,size):
    with pytest.raises(StepAuthorityUnavailable):
        judge(LINEAR, history=history, move=move, side=side, size=size)


def test_internal_step_protocol_has_no_http_or_persistence_side_effects():
    src=(ROOT/"g076_server_step_authority.py").read_text(encoding="utf-8")
    assert "@app.route" not in src
    assert "conn.execute" not in src
    assert "get_db(" not in src
    assert "future_player_move" not in src
