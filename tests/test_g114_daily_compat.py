"""G114 regression: today's 15483, G065 fail closed, deterministic safe Daily."""
from daily_challenge_selection import (
    daily_question_judgeable,
    choose_safe_daily_question,
)

QUESTION_15483_SGF = (
    "(;AB[kp][ko][er][fr][gq][hq][hp][ho][hn][gn][fl][fm][dm][co][dp][kq]"
    "AW[jp][iq][hr][gm][hm][im][in][gr][fq][fp][go][fn][en]"
    "AP[MultiGo:3.7.0]SZ[19]"
    "(;B[ir];W[jr](;B[jo];W[io];B[ip];W[jq])"
    "(;B[jq];W[is];B[jo];W[ip];B[io]))"
    "(;B[jo];W[io];B[ip];W[jq]))"
)
SAFE_LINEAR = "(;SZ[19];B[aa];W[bb];B[cc])"
MARKED_BRANCHES = (
    "(;SZ[19](;B[aa]C[G065:CORRECT])(;B[bb]C[G065:INCORRECT]))"
)
UNMARKED_BRANCHES = "(;SZ[19](;B[aa])(;B[bb]))"


def test_real_question_15483_is_ambiguous_not_auto_awarded():
    assert not daily_question_judgeable({"id": 15483, "content": QUESTION_15483_SGF})


def test_linear_legacy_remains_available_without_defaulting_bad_answers():
    assert daily_question_judgeable({"id": 1, "content": SAFE_LINEAR})


def test_reviewed_g065_positive_and_negative_branches_allowed():
    assert daily_question_judgeable({
        "id": 2, "answer_policy": "g065-explicit-v1", "content": MARKED_BRANCHES,
    })


def test_unreviewed_branching_and_unknown_dialect_held():
    assert not daily_question_judgeable({"id": 3, "content": UNMARKED_BRANCHES})
    assert not daily_question_judgeable({
        "id": 4, "content": SAFE_LINEAR, "answer_policy": "unknown",
    })


def test_fail_closed_missing_and_never_correct():
    assert not daily_question_judgeable({"id": 4, "content": ""})
    all_wrong = "(;SZ[19];B[aa]C[G065:INCORRECT])"
    assert not daily_question_judgeable({
        "id": 5, "answer_policy": "g065-explicit-v1", "content": all_wrong,
    })


def test_daily_selection_skips_15483_and_duplicate_ids():
    records = [
        {"id": 15483, "content": QUESTION_15483_SGF},
        {"id": 7, "content": SAFE_LINEAR},
        {"id": 8, "content": SAFE_LINEAR},
        {"id": 8, "content": SAFE_LINEAR},
    ]
    result = choose_safe_daily_question(records, "2026-10-26")
    assert result is not None and result["id"] == 7
    assert choose_safe_daily_question(records[:1], "2026-10-26") is None
    assert choose_safe_daily_question(records[1:2], "2026-10-26", excluding_id=7) is None


def test_untrusted_question_metadata_not_used_for_verdict():
    unreviewed = {"id": 5, "content": UNMARKED_BRANCHES,
                  "client_correct": True, "answer": "correct"}
    assert not daily_question_judgeable(unreviewed)
