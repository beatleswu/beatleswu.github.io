"""G114 Zone 10 source-pinned 7d alternative; no SGF answer relabeling."""
import json
from pathlib import Path

import app
from g114_zone10_alternative import (
    zone10_admitted_alternative,
    zone10_verified_player_to_move,
)
from daily_challenge_selection import daily_question_judgeable
from lord_trial_admission import question_is_lord_judgeable, select_admissible_lord_questions

ROOT=Path(__file__).resolve().parent
SAMPLE=json.loads((ROOT/"fixtures"/"g114_zone10_real_sgf_sample.json").read_text(encoding="utf8"))
ALTS=[q for q in SAMPLE if q.get("topic")=="逆天改命：終焉戰場的修羅考驗"]
ORIGINAL=[q for q in SAMPLE if q not in ALTS]


def test_verified_30_original_7d_sources_no_new_answer_labels():
    assert len(ALTS)==30
    assert all(q.get("rank")=="7d" and q.get("stage")=="LV10" for q in ALTS)
    assert all(zone10_admitted_alternative(q) for q in ALTS)
    assert all(daily_question_judgeable(q) for q in ALTS)
    assert all(zone10_verified_player_to_move(q) in ("B","W") for q in ALTS)


def test_original_sgf_provenance_enforced_not_guesswork():
    q=dict(ALTS[0])
    assert zone10_admitted_alternative(q)
    q["content"]+=" "
    assert not zone10_admitted_alternative(q)
    assert zone10_verified_player_to_move(q) is None
    forged=dict(ALTS[0], rank="5d")
    assert not zone10_admitted_alternative(forged)
    unrelated=dict(ORIGINAL[0])
    assert not zone10_admitted_alternative(unrelated)


def test_full_20_lord_question_selection_from_original_7d_sources():
    import random
    assert all(question_is_lord_judgeable(q) for q in ALTS)
    selected=select_admissible_lord_questions(ALTS,20,rng=random.Random(114))
    assert len(selected)==20 and len({q["id"] for q in selected})==20
    assert all(zone10_verified_player_to_move(q) in ("B","W") for q in selected)


def test_new_zone_pool_uses_real_safe_denominator():
    zone=app._zone_by_key("d7_plus")
    pool=app._questions_for_adventure_zone(SAMPLE,zone,True)
    assert {q["id"] for q in pool}=={q["id"] for q in SAMPLE}
    assert app._g114_adventure_zone_denominator(zone,pool)==len(ALTS)
    assert len(ORIGINAL)==5 and not any(daily_question_judgeable(q) for q in ORIGINAL)
    assert app._g114_adventure_zone_denominator(app._zone_by_key("k26_30"),ALTS)==len(ALTS)


def test_map_server_accepts_only_provenance_bound_same_rank():
    zone="d7_plus"
    for q in ALTS:
        app._map_battle_require_question_in_zone(q,zone)
        assert app._map_battle_question_context(q)["player_color"] in ("B","W")
    import pytest
    from map_battle_runtime import RequestRejected
    with pytest.raises(RequestRejected):
        app._map_battle_require_question_in_zone(dict(ALTS[0],rank="3d"),zone)


def test_old_zone10_ambiguous_original_remains_unrewardable():
    from map_battle_runtime import JudgeUnavailable
    import pytest
    bad=ORIGINAL[0]
    assert not daily_question_judgeable(bad)
    with pytest.raises(app._MapBattleQuestionIncompatible):
        app._g114_require_judgeable_map_question(bad)


def test_frontend_both_entry_paths_include_same_7d_source():
    page=(ROOT.parent/"index.html").read_text(encoding="utf8")
    assert page.count("q.topic === '逆天改命：終焉戰場的修羅考驗'")==2
    assert page.count("q.rank === '7d' && q.stage === 'LV10'")==2


def test_twenty_distinct_original_7d_full_lord_correct_wrong_judgments():
    """No AI guesses, use exact first-to-terminal line and existing G065."""
    from sgf_engine.parser.sgf_parser import parse_sgf
    from lord_trial_answer_service import judge_lord_trial_answer
    from map_battle_runtime import JudgeUnavailable
    import random
    selected=select_admissible_lord_questions(ALTS,20,rng=random.Random(114))
    assert len({q["id"] for q in selected})==20
    for q in selected:
        root=parse_sgf(q["content"],strict=True)
        player=zone10_verified_player_to_move(q)
        assert player in ("B","W")
        sequence=[]
        node=root.children[0]
        while node:
            if node.move and node.move.color==player:
                xy=node.move.coord
                assert len(xy)==2 and isinstance(xy,str)
                sequence.append({"x":ord(xy[0])-97,"y":ord(xy[1])-97})
            node=node.children[0] if node.children else None
        exam={"attempt_id":f"g114-lord-test-{q['id']}","zone_key":"d7_plus"}
        canonical,judge=judge_lord_trial_answer({"moves":sequence},question=q,exam=exam)
        assert judge.result=="CORRECT", (q["id"],judge)
        assert judge.authoritative_grade==5
        wrong=dict(x=18,y=18)
        if sequence and wrong==sequence[0]: wrong={"x":0,"y":0}
        _bad_canonical,bad=judge_lord_trial_answer({"moves":[wrong]},question=q,exam=exam)
        assert bad.result=="INCORRECT", (q["id"],bad)
        assert bad.authoritative_grade==0
