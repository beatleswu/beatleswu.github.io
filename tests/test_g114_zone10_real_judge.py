"""Real frozen 7d/LV10 SGF through the unchanged G065 + Lord verdict engine.

Not a score mock: correct path is obtained only for test oracle from the
published SGF *single linear path*; production receives only user moves.
"""
import json
from pathlib import Path
import pytest
from sgf_engine.parser.sgf_parser import parse_sgf
from sgf_answer_authority import terminal_verdict
from lord_trial_answer_service import judge_lord_trial_answer
from g114_zone10_alternative import zone10_verified_player_to_move,zone10_admitted_alternative

SAMPLE=json.loads((Path(__file__).parent/"fixtures"/"g114_zone10_real_sgf_sample.json").read_text(encoding="utf8"))
Q=[q for q in SAMPLE if zone10_admitted_alternative(q)]
EXAM={"zone_key":"d7_plus","attempt_id":"g114-disposable-zone10-20"}


def solution_moves(question):
    root=parse_sgf(question["content"],strict=True)
    color=zone10_verified_player_to_move(question)
    assert color in ("B","W")
    node=root
    moves=[]
    while node.children:
        assert len(node.children)==1,(question["id"],"unexpected ambiguous SGF")
        node=node.children[0]
        move=node.move
        if move is not None and move.color==color:
            xy=move.coord
            assert isinstance(xy,str) and len(xy)==2
            moves.append({"action":"play","x":ord(xy[0])-97,"y":ord(xy[1])-97})
    assert moves and terminal_verdict(question,root,node)
    return moves


@pytest.mark.parametrize("question",Q[:25],ids=lambda q:str(q["id"]))
def test_original_source_full_answer_judged_correct_by_actual_lord_service(question):
    _canonical,verdict=judge_lord_trial_answer(
        {"moves":solution_moves(question)},question=question,exam=EXAM)
    assert verdict.result=="CORRECT"
    assert verdict.authoritative_grade==5


@pytest.mark.parametrize("question",Q[:20],ids=lambda q:str(q["id"]))
def test_off_tree_move_does_not_earn_reward(question):
    _canonical,verdict=judge_lord_trial_answer(
        {"moves":[{"action":"play","x":18,"y":18}]},
        question=question,exam=EXAM)
    assert verdict.result=="INCORRECT"
    assert verdict.authoritative_grade==0


def test_twenty_distinct_answerable_real_lord_questions_without_relabeling():
    ids=set()
    for q in Q[:20]:
        ids.add(q["id"])
        _canonical,verdict=judge_lord_trial_answer(
            {"moves":solution_moves(q)},question=q,exam=EXAM)
        assert verdict.result=="CORRECT"
    assert len(ids)==20
