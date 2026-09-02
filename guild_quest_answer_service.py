"""Server-owned answer judging and trusted evidence for Guild Quest answers.

Guild Quest answers travel through the public SRS review transport.  On that
transport ``grade`` is an SM-2 scheduling signal supplied by the client, and
``source_context`` is a free-text client label -- the browser simply sends
``guild_quest`` when it happens to be in Guild mode.  Neither carries any
server authority, which is exactly why the leaderboard's trusted-evidence
boundary excludes them: any client could post ``grade=5`` with
``source_context='guild_quest'`` for any question and mint leaderboard credit.

This module supplies the missing authority instead of widening the boundary.
It mirrors the already accepted Lord Trial pattern: the server judges the
submitted moves with the same server-only SGF judge, then writes a compact
``guild_quest:v1:`` envelope into ``review_log.source_context``.  The public
request parser rejects that prefix as a reserved authority field, so the
envelope can only ever have been written by the server after a real judging.

Guild *eligibility* is likewise a server fact and never a client claim.  The
caller resolves it from the server-owned quest catalog and the user's own
accepted-quest rows, and passes the result in; this module refuses to build a
verdict without it.

What stays unchanged:

* Quest does not judge Go correctness -- quest progress keeps its existing
  "practiced" semantics over ``srs_cards``.
* The leaderboard does not become a judge -- it only decodes and validates an
  envelope the canonical judge already settled.
* The canonical judge/review settlement remains the correctness authority.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from map_battle_runtime import (
    CanonicalAnswer,
    JudgeOutcome,
    JudgeUnavailable,
    MapBattleRuntimeError,
    canonicalize_answer,
    judge_map_battle_answer_v1,
    question_revision_for,
)


# The untrusted client label.  Recognising it selects the server-judged path;
# it never by itself grants any authority.
GUILD_QUEST_SOURCE_CONTEXT = "guild_quest"

GUILD_QUEST_RESULT_SOURCE_PREFIX = "guild_quest:v1:"
GUILD_QUEST_JUDGE_VERSION = "guild-quest-map-battle-judge-v1"

_GUILD_QUEST_RESULT_KEYS = frozenset({
    "schema",
    "quest_key",
    "question_id",
    "verdict",
    "authoritative_grade",
    "judge_version",
    "reason_code",
})
_GUILD_QUEST_VERDICTS = frozenset({"AUTHORITATIVE_PASS", "AUTHORITATIVE_FAIL"})
_SIZE_RE = re.compile(r"SZ\[(\d+)\]", re.IGNORECASE)
_PLAYER_RE = re.compile(r"PL\[([BW])\]", re.IGNORECASE)

_MAX_QUEST_KEY_LENGTH = 120


class GuildQuestAnswerError(ValueError):
    """Expected fail-closed answer error exposed by the review route."""

    def __init__(self, code: str, *, status: int = 400, retryable: bool = False):
        self.code = code
        self.status = status
        self.retryable = retryable
        super().__init__(code)


class GuildQuestVerdictPersistenceError(RuntimeError):
    """A judged Guild result could not be encoded for durable storage."""


def normalize_guild_quest_key(quest_key: Any) -> str:
    """Return the server-resolved quest key, or fail closed."""

    if not isinstance(quest_key, str):
        raise GuildQuestAnswerError("invalid_guild_quest_context")
    value = quest_key.strip()
    if not value or len(value) > _MAX_QUEST_KEY_LENGTH or "::" not in value:
        raise GuildQuestAnswerError("invalid_guild_quest_context")
    return value


def _question_player_to_move(content: str) -> str | None:
    """Resolve whose turn it is, exactly as the canonical judged paths do.

    A ``PL[]`` property is authoritative when the SGF carries one, but most
    problem SGFs express the turn through their first move instead.  This used
    to be a ``PL\\[([BW])\\]`` regex with no fallback, so every ordinary Guild
    question without that literal tag resolved to ``None`` and was reported as
    ``judge_unavailable`` -- the answer could never be judged, and therefore
    never written.  Map Battle and Lord Trial have always used the first-move
    fallback (see ``_map_battle_question_context`` in app.py), which is why the
    same corpus judges correctly there.

    Ambiguity still fails closed: if the SGF declares no player and its first
    moves are not a single colour, this returns ``None`` and the caller rejects
    the answer rather than guessing.
    """

    try:
        from sgf_engine.parser.sgf_parser import parse_sgf

        root = parse_sgf(content, strict=True)
    except Exception:
        # Unparseable content cannot be judged either way; fall back to the
        # original literal lookup so nothing previously accepted regresses.
        match = _PLAYER_RE.search(content)
        return match.group(1).upper() if match else None

    declared = str(root.metadata.get("player_to_move") or "").upper()
    if declared in {"B", "W"}:
        return declared
    first_colors = {
        child.move.color
        for child in getattr(root, "children", ()) or ()
        if getattr(child, "move", None) is not None
        and child.move.color in ("B", "W")
    }
    if len(first_colors) == 1:
        return first_colors.pop()
    return None


def _question_board_context(question: Mapping[str, Any]) -> tuple[int, str]:
    content = question.get("content")
    if not isinstance(content, str) or not content.strip():
        raise GuildQuestAnswerError("judge_unavailable", status=503, retryable=True)
    size_match = _SIZE_RE.search(content)
    try:
        board_size = int(size_match.group(1)) if size_match else 19
    except (AttributeError, TypeError, ValueError) as error:
        raise GuildQuestAnswerError(
            "judge_unavailable", status=503, retryable=True
        ) from error
    player_color = _question_player_to_move(content)
    if not (2 <= board_size <= 25) or player_color not in {"B", "W"}:
        raise GuildQuestAnswerError("judge_unavailable", status=503, retryable=True)
    return board_size, player_color


def build_guild_quest_answer_context(
    question: Mapping[str, Any], quest_key: str
) -> dict[str, Any]:
    """Build the server-owned subset required by the existing SGF judge.

    The identity fields are synthesized deterministically from the server's
    own quest key and question id.  They exist only to satisfy the shared
    canonicalizer; none of them is persisted or accepted from the client.
    """

    if not isinstance(question, Mapping):
        raise GuildQuestAnswerError("invalid_guild_quest_context")
    key = normalize_guild_quest_key(quest_key)
    question_id = question.get("id")
    if isinstance(question_id, bool) or not isinstance(question_id, int):
        raise GuildQuestAnswerError("unknown_question")
    board_size, player_color = _question_board_context(question)
    try:
        revision = question_revision_for(question)
    except MapBattleRuntimeError as error:
        raise GuildQuestAnswerError(
            "judge_unavailable", status=503, retryable=True
        ) from error
    return {
        "battle_id": f"guild-quest:{key}",
        "attempt_id": f"guild-quest:{key}:{question_id}",
        "question_id": question_id,
        "question_revision": revision,
        "board_size": board_size,
        "player_color": player_color,
        "transform_id": "identity",
        "transform_version": "guild-quest-v1",
        "battle_revision": 0,
        "pass_allowed": False,
    }


def canonicalize_guild_quest_answer(
    answer: Mapping[str, Any],
    *,
    question: Mapping[str, Any],
    quest_key: str,
) -> CanonicalAnswer:
    """Canonicalize only player moves; all judge context is server-derived."""

    if not isinstance(answer, Mapping):
        raise GuildQuestAnswerError("guild_answer_required")
    unexpected = sorted(set(answer).difference({"moves"}))
    if unexpected:
        raise GuildQuestAnswerError("forbidden_answer_field")
    if "moves" not in answer:
        raise GuildQuestAnswerError("guild_answer_required")

    context = build_guild_quest_answer_context(question, quest_key)
    payload = {
        "battle_id": context["battle_id"],
        "attempt_id": context["attempt_id"],
        "submission_nonce": context["attempt_id"],
        "battle_revision": context["battle_revision"],
        "question_revision": context["question_revision"],
        "player_color": context["player_color"],
        "transform_id": context["transform_id"],
        "transform_version": context["transform_version"],
        "moves": answer.get("moves"),
    }
    try:
        canonical = canonicalize_answer(payload, context)
    except MapBattleRuntimeError as error:
        raise GuildQuestAnswerError("malformed_answer") from error
    if canonical.is_invalid:
        raise GuildQuestAnswerError("malformed_answer")
    return canonical


def judge_guild_quest_answer(
    answer: Mapping[str, Any],
    *,
    question: Mapping[str, Any],
    quest_key: str,
) -> tuple[CanonicalAnswer, JudgeOutcome]:
    """Return a server-only SGF verdict for one Guild Quest answer."""

    canonical = canonicalize_guild_quest_answer(
        answer, question=question, quest_key=quest_key
    )
    context = build_guild_quest_answer_context(question, quest_key)
    try:
        judge = judge_map_battle_answer_v1(question, context, canonical)
    except JudgeUnavailable as error:
        raise GuildQuestAnswerError(
            "judge_unavailable", status=503, retryable=True
        ) from error
    if judge.result == "INVALID" or judge.authoritative_grade not in {0, 5}:
        raise GuildQuestAnswerError("malformed_answer")
    return canonical, JudgeOutcome(
        result=judge.result,
        authoritative_grade=judge.authoritative_grade,
        judge_version=GUILD_QUEST_JUDGE_VERSION,
        reason_code=judge.reason_code,
    )


def build_guild_quest_verdict(
    *,
    quest_key: str,
    question_id: int,
    judge: JudgeOutcome,
    guild_eligible: bool,
) -> dict[str, Any]:
    """Build the exact server-owned replay envelope.

    ``guild_eligible`` is the caller's server-side resolution of "this
    question belongs to a Guild Quest this user actually accepted".  A verdict
    is never built without it, so the envelope cannot exist for an answer the
    server did not itself place inside a Guild Quest.
    """

    if not guild_eligible:
        raise GuildQuestVerdictPersistenceError("answer is not Guild-eligible")
    key = normalize_guild_quest_key(quest_key)
    if judge.result == "CORRECT" and judge.authoritative_grade == 5:
        verdict = "AUTHORITATIVE_PASS"
    elif judge.result == "INCORRECT" and judge.authoritative_grade == 0:
        verdict = "AUTHORITATIVE_FAIL"
    else:
        raise GuildQuestVerdictPersistenceError("judge result is not persistable")
    return {
        "schema": "guild_quest_verdict_v1",
        "quest_key": key,
        "question_id": int(question_id),
        "verdict": verdict,
        "authoritative_grade": int(judge.authoritative_grade),
        "judge_version": str(judge.judge_version),
        "reason_code": str(judge.reason_code),
    }


def encode_guild_quest_verdict(verdict: Mapping[str, Any]) -> str:
    payload = dict(verdict)
    if set(payload) != _GUILD_QUEST_RESULT_KEYS:
        raise GuildQuestVerdictPersistenceError("invalid Guild Quest verdict envelope")
    if payload.get("schema") != "guild_quest_verdict_v1":
        raise GuildQuestVerdictPersistenceError("invalid Guild Quest verdict schema")
    if payload.get("verdict") not in _GUILD_QUEST_VERDICTS:
        raise GuildQuestVerdictPersistenceError("invalid Guild Quest verdict state")
    return GUILD_QUEST_RESULT_SOURCE_PREFIX + json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def decode_guild_quest_verdict(source_context: Any) -> dict[str, Any] | None:
    """Recover a server-written Guild verdict, or ``None`` for anything else.

    Every field is re-validated.  A truncated, hand-written, or internally
    inconsistent envelope decodes to ``None`` and therefore carries no
    leaderboard authority at all.
    """

    if not isinstance(source_context, str) or not source_context.startswith(
        GUILD_QUEST_RESULT_SOURCE_PREFIX
    ):
        return None
    encoded = source_context[len(GUILD_QUEST_RESULT_SOURCE_PREFIX) :]
    if not encoded:
        return None
    try:
        payload = json.loads(encoded)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, Mapping) or set(payload) != _GUILD_QUEST_RESULT_KEYS:
        return None
    if payload.get("schema") != "guild_quest_verdict_v1":
        return None
    if payload.get("verdict") not in _GUILD_QUEST_VERDICTS:
        return None
    quest_key = payload.get("quest_key")
    if (
        not isinstance(quest_key, str)
        or not quest_key.strip()
        or len(quest_key) > _MAX_QUEST_KEY_LENGTH
        or "::" not in quest_key
    ):
        return None
    if isinstance(payload.get("question_id"), bool) or not isinstance(
        payload.get("question_id"), int
    ):
        return None
    if payload.get("authoritative_grade") not in {0, 5}:
        return None
    if (
        payload["verdict"] == "AUTHORITATIVE_PASS"
        and payload["authoritative_grade"] != 5
    ) or (
        payload["verdict"] == "AUTHORITATIVE_FAIL"
        and payload["authoritative_grade"] != 0
    ):
        return None
    if not isinstance(payload.get("judge_version"), str) or not isinstance(
        payload.get("reason_code"), str
    ):
        return None
    return dict(payload)


__all__ = [
    "GUILD_QUEST_JUDGE_VERSION",
    "GUILD_QUEST_RESULT_SOURCE_PREFIX",
    "GUILD_QUEST_SOURCE_CONTEXT",
    "GuildQuestAnswerError",
    "GuildQuestVerdictPersistenceError",
    "build_guild_quest_answer_context",
    "build_guild_quest_verdict",
    "canonicalize_guild_quest_answer",
    "decode_guild_quest_verdict",
    "encode_guild_quest_verdict",
    "judge_guild_quest_answer",
    "normalize_guild_quest_key",
]
