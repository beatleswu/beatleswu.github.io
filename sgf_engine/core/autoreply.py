"""The sole implementation of deterministic opponent auto-reply selection."""

from __future__ import annotations

from sgf_engine.core.coord_utils import opponent_of
from sgf_engine.core.tree import Move, SGFNode


def get_auto_reply(current_node: SGFNode, player_color: str) -> Move | None:
    """Return the sole opponent child move, or ``None``."""
    opponent = opponent_of(player_color)

    if len(current_node.children) != 1:
        return None

    child = current_node.children[0]
    if child.move is None:
        return None

    if child.move.color == opponent:
        return child.move

    return None

