"""SGF data structures and pure tree lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from sgf_engine.core.coord_utils import opponent_of, sgf_to_xy


@dataclass(frozen=True, slots=True)
class Move:
    color: str
    coord: str

    def __post_init__(self) -> None:
        # Validation only; Move remains a data value and contains no game logic.
        opponent_of(self.color)
        sgf_to_xy(self.coord)


@dataclass(slots=True)
class SGFNode:
    move: Move | None = None
    children: list["SGFNode"] = field(default_factory=list)
    parent: "SGFNode | None" = field(default=None, repr=False)
    metadata: dict = field(default_factory=dict)


def find_child_by_move(node: SGFNode, coord: str) -> SGFNode | None:
    """Return the first child whose move coordinate equals ``coord``."""
    for child in node.children:
        if child.move is not None and child.move.coord == coord:
            return child
    return None

