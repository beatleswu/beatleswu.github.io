"""Lord Trial queue admission: only judgeable questions may enter an attempt.

A Lord Trial answer is settled by the server-only SGF judge reached through
``lord_trial_answer_service.judge_lord_trial_answer``.  That judge fails
closed with ``judge_unavailable`` (HTTP 503) when a question cannot supply
the authority it needs -- most commonly a missing ``PL[B/W]`` root property,
and less commonly SGF content the canonical strict parser rejects.

Historically that check happened only at answer time, so a malformed question
was admitted into a signed 20-question attempt and the attempt died partway
through with a 503 the player could not clear or retry past.  This module
moves the same decision to attempt-creation time.

The admission predicate deliberately does not re-implement the judge's
preconditions.  Re-stating them here would drift from the judge the moment
either side changed.  Instead it *runs the real judge* over a throwaway probe
move and admits the question only when the judge produced a verdict rather
than declaring itself unavailable.  The probe verdict is discarded; only the
availability of judging is observed.

This module never repairs, infers, or synthesizes question metadata.  A
question whose canonical content lacks an authoritative player colour stays
unjudgeable; it is excluded from the Lord-admissible pool, not guessed at.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lord_trial_answer_service import (
    LordTrialAnswerError,
    judge_lord_trial_answer,
)


# A single in-bounds play.  It exercises every judge precondition that can
# raise ``judge_unavailable`` (content presence, board size, player colour,
# question revision, board transform, canonical strict SGF parse) while
# remaining a legal answer shape for any board size this judge accepts.
_PROBE_ANSWER: Mapping[str, Any] = {"moves": [{"action": "play", "x": 0, "y": 0}]}

# The probe needs a syntactically valid attempt context.  These values are
# never persisted and never reach a review row; they exist only so the real
# judge can be invoked out of band.
_PROBE_EXAM: Mapping[str, Any] = {
    "attempt_id": "lord-trial-admission-probe",
    "zone_key": "lord-trial-admission-probe",
}


class LordTrialAdmissionError(ValueError):
    """Raised when a Lord attempt cannot be built from judgeable questions."""

    def __init__(self, code: str, *, status: int = 503, retryable: bool = False):
        self.code = code
        self.status = status
        self.retryable = retryable
        super().__init__(code)


def question_is_lord_judgeable(question: Any) -> bool:
    """Return whether the canonical Lord judge can settle *question* today.

    ``judge_unavailable`` is the only outcome that excludes a question: it is
    the code the answer route turns into the 503 that strands an attempt.
    Every other ``LordTrialAnswerError`` describes a bad *answer* (the probe's
    own shape) rather than an unjudgeable *question*, and a question that can
    reject a malformed answer is by definition judgeable.
    """

    if not isinstance(question, Mapping):
        return False
    try:
        judge_lord_trial_answer(
            _PROBE_ANSWER, question=question, exam=_PROBE_EXAM
        )
    except LordTrialAnswerError as error:
        if error.code == "judge_unavailable":
            return False
        return True
    except Exception:
        # An unexpected failure is not evidence of judgeability.  Fail closed
        # rather than admitting a question whose judge behaviour is unknown.
        return False
    return True


def partition_lord_admissible(questions: Sequence[Any]) -> tuple[list[Any], list[Any]]:
    """Split *questions* into (judgeable, unjudgeable), preserving order."""

    admissible: list[Any] = []
    rejected: list[Any] = []
    for question in questions or ():
        (admissible if question_is_lord_judgeable(question) else rejected).append(question)
    return admissible, rejected


def select_admissible_lord_questions(pool, exam_size, *, rng=None):
    """Return exactly ``exam_size`` judgeable questions, or refuse the attempt.

    A Lord Challenge is a fixed 20-question examination passed at 16 correct.
    The size is part of the product contract, not a function of how much
    usable content a zone happens to hold, so this never returns a short list:
    a shorter Lord Trial would be a materially easier Boss clear and would
    drag the pass threshold down with it.

    When fewer than ``exam_size`` judgeable questions exist the attempt is
    refused outright, so the player meets one honest, recoverable error at
    start instead of a dead attempt at answer N or a cheapened clear.

    Questions are probed lazily in shuffled order, so an ordinary zone parses
    roughly ``exam_size`` questions rather than its whole pool.
    """

    candidates = list(pool or ())
    target = int(exam_size)
    if target <= 0:
        raise LordTrialAdmissionError("no_questions", status=400)
    if rng is not None:
        rng.shuffle(candidates)

    selected: list[Any] = []
    for question in candidates:
        if question_is_lord_judgeable(question):
            selected.append(question)
            if len(selected) >= target:
                return selected
    raise LordTrialAdmissionError("insufficient_judgeable_questions")


__all__ = [
    "LordTrialAdmissionError",
    "partition_lord_admissible",
    "question_is_lord_judgeable",
    "select_admissible_lord_questions",
]
