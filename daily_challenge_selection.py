"""G114 safe Daily source selector; no new judge and no player-data mutation.

An automatic Daily question must have at least one provably correct terminal
under the SAME G065 terminal authority that grades Map Battle submissions.
Legacy unmarked branching/ambiguous SGF is held for human review, never
silently graded as correct. Explicitly curated branches retain their verdicts.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Mapping, Sequence

from sgf_engine.parser.sgf_parser import parse_sgf
from sgf_answer_authority import AnswerAuthorityUnavailable, terminal_verdict

MAX_TREE_NODES = 4096
MAX_SELECTION_PROBES = 4096


def daily_question_judgeable(question: Mapping[str, Any]) -> bool:
    """Fail closed for invalid, ambiguous, or never-correct SGF."""
    try:
        content = question.get("content")
        if not isinstance(content, str) or not content.strip():
            return False
        root = parse_sgf(content, strict=True)
        player = str(root.metadata.get("player_to_move") or "").upper()
        first = [c.move for c in root.children if c.move is not None]
        first_colors = {move.color for move in first}
        if not first or len(first_colors) != 1:
            return False
        if not player:
            player = next(iter(first_colors))
        if player not in ("B", "W") or first_colors != {player}:
            return False
        stack = [root]
        count, correct_terminals = 0, 0
        while stack:
            node = stack.pop()
            count += 1
            if count > MAX_TREE_NODES:
                return False
            children = list(getattr(node, "children", ()) or ())
            if children:
                stack.extend(children)
            elif node is not root and getattr(node, "move", None) is not None:
                # Any unresolved terminal blocks auto-selection: the request
                # can reach it, and grading must never depend on branch order.
                if terminal_verdict(question, root, node):
                    correct_terminals += 1
        return correct_terminals > 0
    except (ValueError, TypeError, KeyError, AnswerAuthorityUnavailable, AttributeError):
        return False


def choose_safe_daily_question(
    questions: Sequence[Mapping[str, Any]], date_str: str, *,
    excluding_id: Any = None,
) -> Mapping[str, Any] | None:
    """Deterministic bounded scan; require unique numeric id and trusted SGF."""
    if not questions:
        return None
    counts = Counter(str(q.get("id")) for q in questions if isinstance(q, Mapping))
    start = int(hashlib.md5(date_str.encode("utf8")).hexdigest(), 16) % len(questions)
    for offset in range(min(len(questions), MAX_SELECTION_PROBES)):
        q = questions[(start + offset) % len(questions)]
        if not isinstance(q, Mapping):
            continue
        item_id = q.get("id")
        if isinstance(item_id, bool) or not isinstance(item_id, int):
            continue
        if excluding_id is not None and str(item_id) == str(excluding_id):
            continue
        if counts[str(item_id)] != 1:
            continue
        if daily_question_judgeable(q):
            return q
    return None


__all__ = ["daily_question_judgeable", "choose_safe_daily_question"]
