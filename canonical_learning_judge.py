"""LC003 — canonical server-authoritative learning judgement.

One place decides whether a submitted Go answer is correct. The client may
supply question identity, the attempted move sequence, and presentation
context; it may NOT supply the verdict, the grade, an accepted-variation
declaration, a terminal SGF verdict, or the transform interpretation.

Design constraints (LC003 task, sections 2 / 7 / 8 / 9 / 14):

* LEAF_SEMANTICS = FAIL_CLOSED_UNTIL_EXPLICIT_VERDICT — a childless SGF node
  is not, by itself, evidence of correctness. A terminal CORRECT requires an
  explicit authoritative marker on the node (RE / TE / a success comment
  token). Bare answer-tree leaves resolve to UNVERIFIABLE by design; making
  the corpus carry explicit markers is a content/review task, not this one.
* AMBIGUOUS_AUTOREPLY = FAIL_CLOSED_NO_BLIND_CHILD0 — if more than one
  opponent continuation is possible, return AMBIGUOUS. Never pick children[0].
* Player colour is enforced against the authored tree — coordinate-only
  matching is insufficient.
* All eight geometric transforms resolve consistently: the authored tree,
  the client's display-space move, and any accepted alternative are compared
  in the same (display) coordinate space, reusing the one transform helper
  that already handles this correctly (map_battle_runtime).
* SGF parse failure NEVER falls back to a client boolean. Malformed input is
  MALFORMED; unjudgeable-but-well-formed input is UNVERIFIABLE. Neither can
  become CORRECT from client input.
* KataGo additive-accept is deliberately OFF here (it stays a rating-test
  behaviour pending a separate product decision).

This module wraps sound sgf_engine primitives (parser, matcher, autoreply)
and a new orchestration layer. It does NOT use sgf_engine.engine.apply_move
(LC002 defects: missing puzzle_variation_overrides.json, unreachable
"result" metadata, Postgres-bound OFF_TREE logger).

No Flask, no DB, no network. Pure and unit-testable.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from sgf_engine.core.autoreply import get_auto_reply
from sgf_engine.core.coord_utils import opponent_of
from sgf_engine.core.tree import SGFNode
from sgf_engine.parser.sgf_parser import parse_sgf

# Reuse the ONE transform implementation that LC002 proved handles the
# tree / display / accepted-move relationship correctly. These helpers are
# pure (regex + arithmetic) and carry no app.py or DB dependency.
from map_battle_runtime import (
    _transform_index as _mb_transform_index,
    _transform_point as _mb_transform_point,
    _transform_sgf as _mb_transform_sgf,
)

# v2 == LC009: owner-approved explicit terminal-verdict marker contract
# (LC007 RECOMMENDED). See docs/planning/lc009_approved_terminal_verdict_semantics.md.
CANONICAL_JUDGE_VERSION = "canonical-learning-judge-v2"

# Node-level markers that count as an explicit authoritative "this terminal
# is a correct solution". A bare leaf without one of these is UNVERIFIABLE,
# never CORRECT.
_SUCCESS_COMMENT_TOKENS = ("正解", "正確", "成功", "correct", "success", "✓", "✔")
_FAILURE_RESULT_TOKENS = ("fail", "wrong", "incorrect", "失敗", "錯誤", "×")

# LC009 / owner-approved (LC007 RECOMMENDED) explicit terminal-verdict contract.
# A reached terminal node is CORRECT / INCORRECT only from an approved marker
# ON THAT NODE, in this order:
#   1. a move-node RE whose value is a DECISIVE winning-side result
#      (``B+`` / ``W+`` optionally with a standard score or reason) -- a
#      non-decisive / unknown RE (``0`` ``Draw`` ``Void`` ``?`` ``right`` ...)
#      is NOT a verdict; a failure token in the RE is INCORRECT;
#   2. a ``TE`` property on the node;
#   3. a comment (``C[...]``) that, after decoration + trailing-punctuation
#      normalisation, is EXACTLY a success / failure marker token -- never an
#      unanchored substring, so 正解 inside explanatory prose is not a verdict;
#   4. a node name (``N[...]``) that is EXACTLY a success / failure marker token.
# Anything else -> None -> the caller fails closed (UNVERIFIABLE).
_EXTRA_FAILURE_TOKENS = ("不正解", "不正確", "不正确", "错误", "错", "失败")
_SUCCESS_MARKER_SET = frozenset(t.strip().lower() for t in _SUCCESS_COMMENT_TOKENS)
_FAILURE_MARKER_SET = frozenset(
    t.strip().lower() for t in (_FAILURE_RESULT_TOKENS + _EXTRA_FAILURE_TOKENS)
)
# Trimmed from both ends of a comment / node name before the exact-token match.
# '?' / '？' are deliberately absent: an interrogative ("正解？" = "correct?")
# is a question, not an assertion, and must stay fail-closed.
_MARKER_WRAP_CHARS = "　 \t\r\n【】〔〕［］[]（）()「」『』〈〉《》\"'“”‘’*_#-—―·・"
_MARKER_TRAIL_PUNCT = "。．.!！:：;；、,，…~〜　 \t\r\n"

# SGF FF[4] Result grammar, restricted to a DECISIVE outcome (a side won):
# ``B+`` / ``W+`` then optionally { resign | time | forfeit | a positive score }.
# Rejects ``0`` ``Draw`` ``Void`` ``?`` ``B`` ``+R`` ``B+0`` ``B+-3`` ``B+?``
# ``B+Q`` ``B+ R`` ``B++R`` ``3.5`` ``correct`` and any trailing junk.
_RE_DECISIVE_SHAPE = re.compile(
    r"[bw]\+(?:r|resign|t|time|f|forfeit|(?!0+(?:\.0+)?\Z)\d+(?:\.\d+)?)?",
    re.IGNORECASE | re.ASCII,
)


def _re_is_decisive(value: Any) -> bool | None:
    """True  -> a decisive winning-side RE result (an explicit solve);
    False -> the RE value carries an explicit failure token;
    None  -> not an authoritative decisive result (caller fails closed)."""
    text = str(value or "").strip()
    if not text:
        return None
    if any(tok in text.lower() for tok in _FAILURE_RESULT_TOKENS):
        return False
    if _RE_DECISIVE_SHAPE.fullmatch(text):
        return True
    return None


def _strip_marker_decoration(text: str) -> str:
    return (
        text.strip(_MARKER_WRAP_CHARS)
        .strip(_MARKER_TRAIL_PUNCT)
        .strip(_MARKER_WRAP_CHARS)
    )


def _exact_marker_verdict(raw: Any) -> bool | None:
    """True / False iff ``raw``, lower-cased and stripped of wrapping decoration
    and trailing punctuation, is EXACTLY a success / failure marker token.
    Never a substring match -> explanatory prose that merely mentions 正解
    returns None."""
    core = _strip_marker_decoration(str(raw or "").strip().lower())
    if not core:
        return None
    if core in _FAILURE_MARKER_SET:
        return False
    if core in _SUCCESS_MARKER_SET:
        return True
    return None


def _terminal_name_verdict(n_values: Any) -> bool | None:
    """First exact success / failure marker among a node's ``N[...]`` values."""
    if n_values is None:
        return None
    values = n_values if isinstance(n_values, (list, tuple)) else [n_values]
    for raw in values:
        verdict = _exact_marker_verdict(raw)
        if verdict is not None:
            return verdict
    return None


class JudgeStatus(str, Enum):
    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    CONTINUE = "CONTINUE"
    AMBIGUOUS = "AMBIGUOUS"
    UNVERIFIABLE = "UNVERIFIABLE"
    MALFORMED = "MALFORMED"


# Statuses that are a definitive server verdict on the submitted answer.
_VERDICT_STATUSES = frozenset({JudgeStatus.CORRECT, JudgeStatus.INCORRECT, JudgeStatus.CONTINUE})
# Statuses that must fail closed — the review is not recorded and the client
# grade/boolean is never consulted.
_FAIL_CLOSED_STATUSES = frozenset(
    {JudgeStatus.AMBIGUOUS, JudgeStatus.UNVERIFIABLE, JudgeStatus.MALFORMED}
)


@dataclass(frozen=True, slots=True)
class JudgeResult:
    status: JudgeStatus
    reason_code: str
    judge_version: str = CANONICAL_JUDGE_VERSION
    transform_index: int | None = None
    matched_path: tuple[str, ...] = ()          # coord sequence actually walked
    player_color: str | None = None

    @property
    def is_verdict(self) -> bool:
        return self.status in _VERDICT_STATUSES

    @property
    def is_fail_closed(self) -> bool:
        return self.status in _FAIL_CLOSED_STATUSES

    @property
    def is_correct(self) -> bool:
        return self.status is JudgeStatus.CORRECT


class JudgeInputError(ValueError):
    """The attempt block itself is structurally invalid (client's fault)."""


_FORBIDDEN_ATTEMPT_FIELDS = frozenset(
    {"grade", "correct", "is_correct", "result", "verdict", "judge_result",
     "authoritative_grade", "server_correct", "matched_variation"}
)
_MAX_MOVES = 256


@dataclass(frozen=True, slots=True)
class Attempt:
    """The client-supplied attempt. Carries no authority fields."""

    moves: tuple[tuple[int, int], ...]
    player_color: str
    transform_id: str = "identity"
    board_size: int | None = None

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> "Attempt":
        if not isinstance(payload, Mapping):
            raise JudgeInputError("attempt must be an object")
        forbidden = sorted(_FORBIDDEN_ATTEMPT_FIELDS.intersection(payload))
        if forbidden:
            raise JudgeInputError(f"forbidden client authority field: {forbidden[0]}")

        raw_color = str(payload.get("player_color") or payload.get("playerColor") or "").strip().upper()
        if raw_color not in ("B", "W"):
            raise JudgeInputError("player_color must be 'B' or 'W'")

        raw_moves = payload.get("moves")
        if not isinstance(raw_moves, Sequence) or isinstance(raw_moves, (str, bytes)):
            raise JudgeInputError("moves must be a list")
        if len(raw_moves) > _MAX_MOVES:
            raise JudgeInputError("moves list is too long")
        moves: list[tuple[int, int]] = []
        for entry in raw_moves:
            if not isinstance(entry, Mapping):
                raise JudgeInputError("each move must be an object with x, y")
            x, y = entry.get("x"), entry.get("y")
            if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, int) or not isinstance(y, int):
                raise JudgeInputError("move x and y must be integers")
            moves.append((x, y))

        transform_id = str(
            payload.get("transform") or payload.get("transform_id") or "identity"
        ).strip() or "identity"

        board_size = payload.get("board_size") or payload.get("boardSize")
        if board_size is not None:
            if isinstance(board_size, bool) or not isinstance(board_size, int) or not (2 <= board_size <= 25):
                raise JudgeInputError("board_size out of range")

        return Attempt(
            moves=tuple(moves),
            player_color=raw_color,
            transform_id=transform_id,
            board_size=board_size,
        )


# ---------------------------------------------------------------------------
# tree helpers
# ---------------------------------------------------------------------------

def _sgf_board_size(content: str) -> int:
    match = re.search(r"SZ\[(\d+)\]", content or "")
    return int(match.group(1)) if match else 19


def _server_expected_player_color(root: SGFNode) -> str | None:
    """LC004: the expected player colour is SERVER-AUTHORED from the question
    SGF -- the root ``PL[...]`` if present, else the colour of the first
    authored move. Returns None only when the SGF carries neither signal."""
    meta = root.metadata or {}
    declared = str(meta.get("player_to_move") or "").strip().upper()
    if declared in ("B", "W"):
        return declared
    for child in root.children:
        if child.move is not None and child.move.color in ("B", "W"):
            return child.move.color
    return None


def _xy_to_sgf_coord(x: int, y: int, size: int) -> str | None:
    if not (0 <= x < size and 0 <= y < size and size <= 26):
        return None
    return chr(97 + x) + chr(97 + y)


def _child_for_colour_and_coord(node: SGFNode, colour: str, coord: str) -> SGFNode | None:
    for child in node.children:
        move = child.move
        if move is not None and move.color == colour and move.coord == coord:
            return child
    return None


def _is_leaf(node: SGFNode) -> bool:
    return not node.children


def _explicit_terminal_is_correct(node: SGFNode) -> bool | None:
    """Owner-approved (LC009 / LC007 RECOMMENDED) explicit terminal-verdict for
    the reached terminal node. Returns True (an approved SUCCESS marker sits ON
    this node), False (an approved FAILURE marker sits ON this node), or None
    (no approved marker -> the caller fails closed to UNVERIFIABLE).

    Approved channels, in order (see the _SUCCESS_MARKER_SET / _re_is_decisive
    contract block near the top of this module):
      1. move-node RE / game_result -- only a DECISIVE winning-side result;
      2. a TE property on this node;
      3. a comment that is EXACTLY a marker token (never a substring);
      4. a node name N[...] that is EXACTLY a marker token.

    Callers only ever pass the terminal of the walked line, so an earlier
    move-node N[正解] is never seen here."""
    meta = node.metadata or {}
    props = meta.get("properties") or {}

    # 1. structured move-node RE -- decisive winning-side shape only
    re_verdict = _re_is_decisive(meta.get("game_result"))
    if re_verdict is not None:
        return re_verdict

    # 2. TE (tesuji / "good move") property on the terminal
    if "TE" in props:
        return True

    # 3. terminal comment -- an EXACT marker token, never a prose substring
    comment_verdict = _exact_marker_verdict(meta.get("comment"))
    if comment_verdict is not None:
        return comment_verdict

    # 4. terminal node name N[...] -- an EXACT marker token
    return _terminal_name_verdict(props.get("N"))


def _accepted_display_points(
    accepted_moves: Any, *, size: int, transform_index: int
) -> set[tuple[int, int]]:
    """Reviewer-authorised alternatives, moved into the same display space the
    client's move arrives in. Content/server authority only."""
    if isinstance(accepted_moves, Mapping):
        accepted_moves = [accepted_moves]
    result: set[tuple[int, int]] = set()
    for entry in accepted_moves or []:
        if not isinstance(entry, Mapping):
            continue
        try:
            x, y = int(entry["x"]), int(entry["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= x < size and 0 <= y < size:
            result.add(_mb_transform_point(x, y, size, transform_index))
    return result


# ---------------------------------------------------------------------------
# the judge
# ---------------------------------------------------------------------------

def judge_answer(
    *,
    question_content: str,
    attempt: Attempt,
    accepted_moves: Any = None,
) -> JudgeResult:
    """Server-authoritative verdict on one submitted answer sequence."""

    if not isinstance(question_content, str) or not question_content.strip():
        return JudgeResult(JudgeStatus.UNVERIFIABLE, "no_question_content")

    # 1. transform id — client does not own the interpretation; an
    #    unrecognised value is unverifiable, never a pass.
    try:
        t = _mb_transform_index(attempt.transform_id)
    except Exception:
        return JudgeResult(JudgeStatus.UNVERIFIABLE, "unsupported_transform")

    size = attempt.board_size or _sgf_board_size(question_content)

    # 2. transform + strict parse — NO client fallback on failure.
    try:
        transformed = _mb_transform_sgf(question_content, t)
    except Exception:
        return JudgeResult(JudgeStatus.UNVERIFIABLE, "transform_failed", transform_index=t)
    try:
        root = parse_sgf(transformed, strict=True)
    except ValueError:
        return JudgeResult(JudgeStatus.MALFORMED, "strict_parse_failed", transform_index=t)
    except Exception:
        return JudgeResult(JudgeStatus.MALFORMED, "parser_error", transform_index=t)

    if not attempt.moves:
        return JudgeResult(JudgeStatus.UNVERIFIABLE, "no_moves_submitted", transform_index=t)

    # LC004: the colour the judge enforces is server-authored from the SGF.
    # A client-transported colour is only a fact to validate; if it
    # contradicts the server's, the attempt is for the wrong side -> INCORRECT.
    server_colour = _server_expected_player_color(root)
    if server_colour is not None and attempt.player_color != server_colour:
        return JudgeResult(
            JudgeStatus.INCORRECT, "player_color_contradicts_server",
            transform_index=t, player_color=server_colour,
        )
    colour = server_colour or attempt.player_color
    opponent = opponent_of(colour)

    # 3. accepted-alternative fast path — compared in display space, exactly
    #    like the client's move. Single-move alternatives only (mirrors the
    #    reviewer-authorised first-move alternative model).
    accepted_display = _accepted_display_points(accepted_moves, size=size, transform_index=t)
    if len(attempt.moves) == 1 and attempt.moves[0] in accepted_display:
        return JudgeResult(
            JudgeStatus.CORRECT, "accepted_authoritative_alternative",
            transform_index=t, player_color=colour,
        )

    # 4. authored-tree walk with colour enforcement + fail-closed auto-reply
    #    + fail-closed leaf.
    node = root
    walked: list[str] = []
    for (x, y) in attempt.moves:
        coord = _xy_to_sgf_coord(x, y, size)
        if coord is None:
            return JudgeResult(
                JudgeStatus.MALFORMED, "move_coordinate_out_of_bounds",
                transform_index=t, matched_path=tuple(walked), player_color=colour,
            )
        child = _child_for_colour_and_coord(node, colour, coord)
        if child is None:
            # a played move that the authored tree does not contain for this
            # colour is a genuine wrong answer, not "unverifiable".
            return JudgeResult(
                JudgeStatus.INCORRECT, "off_answer_tree",
                transform_index=t, matched_path=tuple(walked), player_color=colour,
            )
        walked.append(coord)
        node = child

        if _is_leaf(node):
            verdict = _explicit_terminal_is_correct(node)
            if verdict is True:
                return JudgeResult(
                    JudgeStatus.CORRECT, "explicit_terminal_verdict",
                    transform_index=t, matched_path=tuple(walked), player_color=colour,
                )
            if verdict is False:
                return JudgeResult(
                    JudgeStatus.INCORRECT, "explicit_terminal_failure",
                    transform_index=t, matched_path=tuple(walked), player_color=colour,
                )
            return JudgeResult(
                JudgeStatus.UNVERIFIABLE, "leaf_without_explicit_verdict",
                transform_index=t, matched_path=tuple(walked), player_color=colour,
            )

        # opponent auto-reply — fail closed if not uniquely determined.
        opp_children = [
            c for c in node.children
            if c.move is not None and c.move.color == opponent
        ]
        if len(node.children) != 1 or len(opp_children) != 1:
            return JudgeResult(
                JudgeStatus.AMBIGUOUS, "ambiguous_autoreply",
                transform_index=t, matched_path=tuple(walked), player_color=colour,
            )
        reply = get_auto_reply(node, colour)   # sole opponent child, else None
        if reply is None or reply.coord is None:
            return JudgeResult(
                JudgeStatus.AMBIGUOUS, "no_unique_autoreply",
                transform_index=t, matched_path=tuple(walked), player_color=colour,
            )
        node = _child_for_colour_and_coord(node, opponent, reply.coord)
        if node is None:  # defensive; get_auto_reply already proved it exists
            return JudgeResult(
                JudgeStatus.UNVERIFIABLE, "autoreply_node_missing",
                transform_index=t, matched_path=tuple(walked), player_color=colour,
            )
        walked.append(reply.coord)

        if _is_leaf(node):
            verdict = _explicit_terminal_is_correct(node)
            if verdict is True:
                return JudgeResult(
                    JudgeStatus.CORRECT, "explicit_terminal_verdict_after_reply",
                    transform_index=t, matched_path=tuple(walked), player_color=colour,
                )
            if verdict is False:
                return JudgeResult(
                    JudgeStatus.INCORRECT, "explicit_terminal_failure_after_reply",
                    transform_index=t, matched_path=tuple(walked), player_color=colour,
                )
            return JudgeResult(
                JudgeStatus.UNVERIFIABLE, "reply_leaf_without_explicit_verdict",
                transform_index=t, matched_path=tuple(walked), player_color=colour,
            )

    # player's moves exhausted without reaching any terminal — a valid but
    # incomplete line. Not a pass; not an off-tree error.
    return JudgeResult(
        JudgeStatus.CONTINUE, "valid_partial_sequence",
        transform_index=t, matched_path=tuple(walked), player_color=colour,
    )


# ---------------------------------------------------------------------------
# /api/srs/review authority adapter
# ---------------------------------------------------------------------------

# LC003 grade mapping for the public /api/srs/review compatibility path.
# The historical public client only ever sends 0 or 3 (LC001); the internal
# Map Battle handoff keeps its own correct->5 mapping and is untouched here.
_SERVER_GRADE_CORRECT = 3
_SERVER_GRADE_NOT_CORRECT = 0

# LC004 no-attempt policy. Default 'legacy' preserves the LC003 behaviour
# exactly (a no-attempt request passes the client's self-reported grade
# through, explicitly labelled non-authoritative). 'fail_closed' is the
# cutover: a no-attempt request gets an explicit compatibility error and
# records no review -- the client self-report can no longer drive
# scheduling or progress. The cutover is BLOCKED on corpus terminal-verdict
# coverage (see docs/planning/lc004_*) and must stay 'legacy' until the
# corpus carries explicit terminal verdicts.
_NO_ATTEMPT_POLICY_ENV = "SRS_REVIEW_NO_ATTEMPT_POLICY"
_NO_ATTEMPT_POLICY_LEGACY = "legacy"
_NO_ATTEMPT_POLICY_FAIL_CLOSED = "fail_closed"


def no_attempt_policy() -> str:
    value = str(os.environ.get(_NO_ATTEMPT_POLICY_ENV, _NO_ATTEMPT_POLICY_LEGACY)).strip().lower()
    return value if value in (_NO_ATTEMPT_POLICY_LEGACY, _NO_ATTEMPT_POLICY_FAIL_CLOSED) else _NO_ATTEMPT_POLICY_LEGACY


class GradeBasis(str, Enum):
    SERVER_JUDGE_CORRECT = "SERVER_JUDGE_CORRECT"
    SERVER_JUDGE_INCORRECT = "SERVER_JUDGE_INCORRECT"
    SERVER_JUDGE_CONTINUE_NOT_A_PASS = "SERVER_JUDGE_CONTINUE_NOT_A_PASS"
    CLIENT_SELF_REPORT_NO_SERVER_JUDGE = "CLIENT_SELF_REPORT_NO_SERVER_JUDGE"


@dataclass(frozen=True, slots=True)
class AuthorityResolution:
    """What the /api/srs/review route should do next."""

    # when set, the route returns this immediately; the review is NOT recorded
    fail_closed_status: int | None = None
    fail_closed_body: Mapping[str, Any] = field(default_factory=dict)
    # when fail_closed_status is None:
    server_authoritative: bool = False   # True => client grade/correct ignored
    grade: int | None = None             # the grade the route must use
    grade_basis: GradeBasis = GradeBasis.CLIENT_SELF_REPORT_NO_SERVER_JUDGE
    judge_result: JudgeResult | None = None
    identity_fallback_used: bool = False

    @property
    def is_fail_closed(self) -> bool:
        return self.fail_closed_status is not None


def _load_question_by_id(load_questions: Callable[[], Sequence[Mapping[str, Any]]], qid: Any):
    """Resolve the compatibility identity (legacy integer id). Returns
    (question | None, ambiguous: bool). Ambiguous == the legacy id maps to
    more than one corpus record (LC002/E1: 11 duplicate-legacy-id groups in
    the snapshot). No source_record_uuid is available at runtime, so this is
    the identity fallback."""
    try:
        rows = list(load_questions() or [])
    except Exception:
        return None, False
    matches = [q for q in rows if isinstance(q, Mapping) and q.get("id") == qid]
    if len(matches) > 1:
        return None, True
    return (matches[0] if matches else None), False


def resolve_srs_review_authority(
    data: Mapping[str, Any],
    *,
    load_questions: Callable[[], Sequence[Mapping[str, Any]]],
    accepted_moves_reader: Callable[[Mapping[str, Any]], Any] | None = None,
) -> AuthorityResolution:
    """Decide the correctness basis for one public /api/srs/review call.

    * No ``attempt`` block  -> policy-dependent (LC004):
        - ``legacy`` (default): the client grade is a labelled scheduling
          self-report; NOT a server correctness verdict and cannot reach any
          authoritative-handoff consumer (``server_authoritative`` is False).
        - ``fail_closed`` (cutover, BLOCKED on corpus coverage): an explicit
          HTTP 409 compatibility error; no review is recorded; the client
          self-report drives nothing.
    * ``attempt`` block present -> the canonical judge is authoritative. The
      client's grade / correctness fields are ignored. AMBIGUOUS /
      UNVERIFIABLE / MALFORMED fail closed (the review is not recorded and
      the client input is never consulted).
    """
    attempt_payload = data.get("attempt")
    if not isinstance(attempt_payload, Mapping):
        if no_attempt_policy() == _NO_ATTEMPT_POLICY_FAIL_CLOSED:
            # LC004 cutover: no factual attempt -> no authoritative progress,
            # no server correctness claim, no client-grade fallback.
            return AuthorityResolution(
                fail_closed_status=409,
                fail_closed_body={
                    "error": "attempt_required",
                    "code": "srs_attempt_required",
                    "message": "client refresh required: send an attempt payload",
                    "retryable": False,
                    "refresh_required": True,
                },
            )
        # legacy no-attempt path: pass the client's self-reported grade
        # through unchanged, explicitly labelled as non-authoritative.
        return AuthorityResolution(
            server_authoritative=False,
            grade=data.get("grade"),
            grade_basis=GradeBasis.CLIENT_SELF_REPORT_NO_SERVER_JUDGE,
        )

    # --- attempt path: server owns the verdict ---
    try:
        attempt = Attempt.from_payload(attempt_payload)
    except JudgeInputError as error:
        return AuthorityResolution(
            fail_closed_status=400,
            fail_closed_body={
                "error": "invalid_attempt",
                "code": "invalid_attempt",
                "reason": str(error),
                "retryable": False,
            },
        )

    qid = data.get("question_id")
    question, ambiguous = _load_question_by_id(load_questions, qid)
    if ambiguous:
        return AuthorityResolution(
            fail_closed_status=409,
            fail_closed_body={
                "error": "ambiguous_question_identity",
                "code": "ambiguous_question_identity",
                "message": "legacy question id resolves to more than one record",
                "retryable": False,
            },
            identity_fallback_used=True,
        )
    if question is None:
        return AuthorityResolution(
            fail_closed_status=422,
            fail_closed_body={
                "error": "question_not_verifiable",
                "code": "question_not_found",
                "retryable": False,
            },
            identity_fallback_used=True,
        )

    accepted = (
        accepted_moves_reader(question) if accepted_moves_reader is not None
        else (question.get("accepted_moves") or question.get("accepted_answers"))
    )
    result = judge_answer(
        question_content=question.get("content") or "",
        attempt=attempt,
        accepted_moves=accepted,
    )

    if result.is_fail_closed:
        status = 400 if result.status is JudgeStatus.MALFORMED else 422
        return AuthorityResolution(
            fail_closed_status=status,
            fail_closed_body={
                "error": result.status.value.lower(),
                "code": result.reason_code,
                "judge_version": result.judge_version,
                "retryable": False,
            },
            judge_result=result,
            identity_fallback_used=True,
        )

    if result.status is JudgeStatus.CORRECT:
        grade, basis = _SERVER_GRADE_CORRECT, GradeBasis.SERVER_JUDGE_CORRECT
    elif result.status is JudgeStatus.INCORRECT:
        grade, basis = _SERVER_GRADE_NOT_CORRECT, GradeBasis.SERVER_JUDGE_INCORRECT
    else:  # CONTINUE
        grade, basis = _SERVER_GRADE_NOT_CORRECT, GradeBasis.SERVER_JUDGE_CONTINUE_NOT_A_PASS

    return AuthorityResolution(
        server_authoritative=True,
        grade=grade,
        grade_basis=basis,
        judge_result=result,
        identity_fallback_used=True,   # no source_record_uuid at runtime
    )


__all__ = [
    "CANONICAL_JUDGE_VERSION",
    "JudgeStatus",
    "JudgeResult",
    "JudgeInputError",
    "Attempt",
    "judge_answer",
    "GradeBasis",
    "AuthorityResolution",
    "resolve_srs_review_authority",
]
