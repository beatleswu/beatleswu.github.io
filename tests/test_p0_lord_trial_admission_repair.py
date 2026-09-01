"""P0-1: a Lord Trial attempt may only contain judgeable questions.

The Production failure this covers: a Lord Trial reached 4/20 and died on
question 31194 with HTTP 503 ``judge_unavailable``.  That question's canonical
SGF carries no ``PL[B/W]`` root property, so the server-only Lord judge cannot
establish whose move it is and correctly refuses to judge.  Because
admissibility was only decided at answer time, the malformed question had
already been signed into the 20-question attempt and the player could neither
skip nor retry past it.

The fixtures here are extracted from the real frozen catalog rather than
authored by hand -- this defect class is precisely what synthetic fixtures
missed.  ``tests/fixtures/p0_repair/lord_catalog_defect_shapes.json`` holds
the actual 31194 record shape, a real strict-parser failure, and a real
judgeable neighbour from the same book.
"""

from __future__ import annotations

import json
import os
import pathlib
import random

import pytest

from lord_trial_admission import (
    LordTrialAdmissionError,
    partition_lord_admissible,
    question_is_lord_judgeable,
    select_admissible_lord_questions,
)
from lord_trial_answer_service import LordTrialAnswerError, judge_lord_trial_answer

_FIXTURE = (
    pathlib.Path(__file__).parent
    / "fixtures"
    / "p0_repair"
    / "lord_catalog_defect_shapes.json"
)
_SHAPES = json.loads(_FIXTURE.read_text(encoding="utf-8"))

MISSING_PL = _SHAPES["missing_pl_question"]
PARSE_FAILURE = _SHAPES["sgf_parse_failure_question"]
JUDGEABLE = _SHAPES["judgeable_question"]

BOSS_EXAM_SIZE = 20


def _exam(attempt_id: str = "attempt-1", zone_key: str = "k26_30") -> dict:
    return {"attempt_id": attempt_id, "zone_key": zone_key}


def _clone(question: dict, question_id: int) -> dict:
    clone = dict(question)
    clone["id"] = question_id
    return clone


# --------------------------------------------------------------------------
# The exact Production defect
# --------------------------------------------------------------------------


def test_question_31194_is_the_real_missing_pl_shape():
    """Guard the fixture itself: this must stay the actual reported record."""
    assert MISSING_PL["id"] == 31194
    assert "PL[" not in MISSING_PL["content"]
    assert "SZ[8]" in MISSING_PL["content"]


def test_question_31194_still_fails_closed_outside_admission():
    """The judge is unchanged: a malformed question is still never judged."""
    with pytest.raises(LordTrialAnswerError) as excinfo:
        judge_lord_trial_answer(
            {"moves": [{"action": "play", "x": 3, "y": 3}]},
            question=MISSING_PL,
            exam=_exam(),
        )
    assert excinfo.value.code == "judge_unavailable"
    assert excinfo.value.status == 503


def test_question_31194_cannot_enter_a_lord_attempt():
    """The 503 is now unreachable from a created attempt: it is never admitted."""
    assert question_is_lord_judgeable(MISSING_PL) is False

    pool = [MISSING_PL] + [_clone(JUDGEABLE, 900_000 + i) for i in range(BOSS_EXAM_SIZE)]
    selected = select_admissible_lord_questions(
        pool, BOSS_EXAM_SIZE, rng=random.Random(1)
    )
    assert len(selected) == BOSS_EXAM_SIZE
    assert MISSING_PL["id"] not in {q["id"] for q in selected}


def test_real_strict_parser_failure_is_also_excluded():
    """Missing PL is not the only unjudgeable class in the real catalog."""
    assert question_is_lord_judgeable(PARSE_FAILURE) is False
    admissible, rejected = partition_lord_admissible([PARSE_FAILURE, JUDGEABLE])
    assert [q["id"] for q in admissible] == [JUDGEABLE["id"]]
    assert [q["id"] for q in rejected] == [PARSE_FAILURE["id"]]


def test_valid_questions_remain_eligible():
    assert question_is_lord_judgeable(JUDGEABLE) is True


# --------------------------------------------------------------------------
# Attempt construction
# --------------------------------------------------------------------------


def test_twenty_question_attempt_still_constructs_from_a_healthy_pool():
    pool = [_clone(JUDGEABLE, 900_000 + i) for i in range(120)]
    selected = select_admissible_lord_questions(
        pool, BOSS_EXAM_SIZE, rng=random.Random(7)
    )
    assert len(selected) == BOSS_EXAM_SIZE
    assert len({q["id"] for q in selected}) == BOSS_EXAM_SIZE


def test_every_admitted_question_is_judgeable():
    """LORD_QUEUE_ADMISSION_IMPLIES_JUDGEABLE."""
    pool = []
    for i in range(60):
        pool.append(_clone(JUDGEABLE, 900_000 + i))
        pool.append(_clone(MISSING_PL, 800_000 + i))
    selected = select_admissible_lord_questions(
        pool, BOSS_EXAM_SIZE, rng=random.Random(11)
    )
    assert len(selected) == BOSS_EXAM_SIZE
    assert all(question_is_lord_judgeable(q) for q in selected)


def test_filtering_never_silently_shortens_an_attempt():
    """A short Lord Trial is an easier Boss clear, so it must fail closed.

    This is the zone-scale case: the real catalog has a zone whose eligible
    pool is large but almost entirely unjudgeable.  Quietly building a
    one-question Lord Trial there would hand out a Zone clear.
    """
    pool = [_clone(MISSING_PL, 800_000 + i) for i in range(60)]
    pool.append(_clone(JUDGEABLE, 900_001))
    with pytest.raises(LordTrialAdmissionError) as excinfo:
        select_admissible_lord_questions(pool, BOSS_EXAM_SIZE, rng=random.Random(3))
    assert excinfo.value.code == "insufficient_judgeable_questions"
    assert excinfo.value.status == 503


def test_small_healthy_pool_keeps_its_existing_shorter_exam():
    """Pools that were already shorter than the exam size are unaffected."""
    pool = [_clone(JUDGEABLE, 900_000 + i) for i in range(3)]
    selected = select_admissible_lord_questions(
        pool, BOSS_EXAM_SIZE, rng=random.Random(5)
    )
    assert len(selected) == 3


def test_empty_pool_reports_no_questions():
    with pytest.raises(LordTrialAdmissionError) as excinfo:
        select_admissible_lord_questions([], BOSS_EXAM_SIZE)
    assert excinfo.value.code == "no_questions"


def test_admission_introduces_no_fallback_judge():
    """Admission only observes the real judge; it never substitutes one."""
    import inspect

    import lord_trial_admission as module

    source = inspect.getsource(module)
    assert "judge_lord_trial_answer" in source
    for banned in ("fallback", "PL[B]", "PL[W]", "player_color ="):
        assert banned not in source


# --------------------------------------------------------------------------
# Real catalog scan
# --------------------------------------------------------------------------


def _real_catalog_path():
    configured = os.environ.get("QUESTIONS_JSON_PATH", "questions.json")
    path = pathlib.Path(configured)
    return path if path.is_file() else None


@pytest.mark.skipif(
    _real_catalog_path() is None,
    reason="frozen canonical catalog is not present in this environment",
)
def test_real_catalog_admissibility_scan():
    """Scan the actual frozen catalog, not a synthetic stand-in.

    Every Lord-eligible record is probed with the real judge.  The assertion
    is the invariant, not a count: whatever the catalog holds, admission and
    judgeability must agree exactly, and 31194 must be on the excluded side.
    """
    questions = json.loads(_real_catalog_path().read_text(encoding="utf-8"))
    assert isinstance(questions, list) and questions

    by_id = {q["id"]: q for q in questions if isinstance(q, dict) and "id" in q}
    admissible, rejected = partition_lord_admissible(
        [q for q in questions if isinstance(q, dict)]
    )

    # Admission and judgeability are the same predicate, over real data.
    assert all(question_is_lord_judgeable(q) for q in admissible)
    assert not any(question_is_lord_judgeable(q) for q in rejected)

    if 31194 in by_id:
        assert question_is_lord_judgeable(by_id[31194]) is False
        assert 31194 not in {q["id"] for q in admissible if "id" in q}

    # A malformed record must never be able to reach the judge through an
    # attempt, no matter how large the surrounding pool is.
    if rejected and len(admissible) >= BOSS_EXAM_SIZE:
        pool = rejected[:50] + admissible[:50]
        selected = select_admissible_lord_questions(
            pool, BOSS_EXAM_SIZE, rng=random.Random(23)
        )
        assert all(question_is_lord_judgeable(q) for q in selected)
