"""G076 internal-only, server-side, multi-step SGF authority kernel.

This PURE step evaluator deliberately exposes no Flask route and writes no DB.
It must only be used inside a transactional service that commits an issued,
owner-scoped, nonce-bound attempt step BEFORE returning a verdict/reply. Never
accept client-supplied history as authoritative: history belongs to the server.
"""
from dataclasses import dataclass

from map_battle_runtime import _find_child, _question_answer_tree
from sgf_answer_authority import AnswerAuthorityUnavailable, terminal_verdict


class StepAuthorityUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class StepDecision:
    status: str  # CONTINUE, CORRECT, INCORRECT
    opponent_reply: tuple[int, int] | None = None
    reason: str = ""


def _coordinate(pair, size):
    if (
        not isinstance(pair, (tuple, list))
        or len(pair) != 2
        or any(type(v) is not int or not 0 <= v < size for v in pair)
    ):
        raise StepAuthorityUnavailable("invalid_authoritative_coordinate")
    return "".join(chr(ord("a") + value) for value in pair)


def _reply_coord(move, size):
    if move is None or not isinstance(move.coord, str) or len(move.coord) != 2:
        raise StepAuthorityUnavailable("invalid_opponent_reply")
    result = tuple(ord(c) - ord("a") for c in move.coord)
    if len(result) != 2 or any(not 0 <= v < size for v in result):
        raise StepAuthorityUnavailable("invalid_opponent_reply")
    return result


def _advance(question, root, node, player_color, pair, size):
    answer = _coordinate(pair, size)
    child = _find_child(node, player_color, answer)
    if child is None:
        return StepDecision("INCORRECT", reason="off_answer_tree"), None

    reply = None
    next_node = child
    children = list(getattr(child, "children", ()) or ())
    opponent = "W" if player_color == "B" else "B"
    if len(children) == 1 and getattr(children[0], "move", None) is not None:
        candidate = children[0].move
        if candidate.color == opponent:
            reply = _reply_coord(candidate, size)
            next_node = children[0]
    elif len(children) > 1 and any(
        getattr(getattr(c, "move", None), "color", None) == opponent
        for c in children
    ):
        raise StepAuthorityUnavailable("ambiguous_opponent_reply_needs_owner_policy")

    following = list(getattr(next_node, "children", ()) or ())
    if not following:
        try:
            is_correct = terminal_verdict(question, root, next_node)
        except AnswerAuthorityUnavailable as error:
            raise StepAuthorityUnavailable(str(error)) from error
        return StepDecision(
            "CORRECT" if is_correct else "INCORRECT", reply,
            "terminal_solution" if is_correct else "explicit_failure_terminal",
        ), next_node

    if any(getattr(getattr(c, "move", None), "color", None) != player_color
           for c in following):
        raise StepAuthorityUnavailable("unsupported_nonplayer_continuation")
    return StepDecision("CONTINUE", reply, "server_authorized_prefix"), next_node


def adjudicate_next_step(question, *, player_color, board_size,
                         trusted_history, move):
    """Adjudicate one step based on server-stored history and canonical SGF.

    The result intentionally omits future player-answer candidates. This
    helper alone does not implement nonce/commit/idempotency/entitlements.
    """
    if player_color not in ("B", "W") or type(board_size) is not int or not 2 <= board_size <= 25:
        raise StepAuthorityUnavailable("invalid_attempt_authority")
    if not isinstance(trusted_history, (tuple, list)) or len(trusted_history) > 100:
        raise StepAuthorityUnavailable("invalid_server_history")
    content = question.get("content")
    if not isinstance(content, str) or not content:
        raise StepAuthorityUnavailable("question_unavailable")
    try:
        root = _question_answer_tree(content)
    except Exception as error:
        raise StepAuthorityUnavailable("canonical_sgf_unavailable") from error
    node = root
    for history_move in trusted_history:
        earlier, node = _advance(
            question, root, node, player_color, history_move, board_size
        )
        if earlier.status != "CONTINUE" or node is None:
            raise StepAuthorityUnavailable("invalid_server_history")
    result, _ = _advance(question, root, node, player_color, move, board_size)
    return result
