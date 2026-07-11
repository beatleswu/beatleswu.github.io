"""Structural move classification only."""

from __future__ import annotations

from enum import Enum

from sgf_engine.core.coord_utils import sgf_to_xy
from sgf_engine.core.tree import SGFNode, find_child_by_move


class MatchResult(str, Enum):
    BRANCH = "branch"
    EQUIVALENT = "equivalent"
    OFF_TREE = "off_tree"


BRANCH = MatchResult.BRANCH
EQUIVALENT = MatchResult.EQUIVALENT
OFF_TREE = MatchResult.OFF_TREE


def match_move(
    current_node: SGFNode,
    move_coord: str,
    override: dict | None,
) -> MatchResult:
    """Classify a move as a tree branch, declared equivalent, or off-tree."""
    sgf_to_xy(move_coord)

    # Locked precedence: an SGF branch remains BRANCH even if also overridden.
    if find_child_by_move(current_node, move_coord) is not None:
        return BRANCH

    equivalent_moves = (override or {}).get("equivalent_moves") or {}
    for alternatives in equivalent_moves.values():
        if move_coord in alternatives:
            return EQUIVALENT

    return OFF_TREE

