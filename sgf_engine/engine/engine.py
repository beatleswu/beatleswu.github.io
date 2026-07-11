"""The only SGF tree/matcher/override/auto-reply orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass

from sgf_engine.core import autoreply, matcher, tree
from sgf_engine.core.tree import Move, SGFNode
from sgf_engine.override import override_loader


@dataclass(frozen=True, slots=True)
class EngineResult:
    status: str
    node: SGFNode | None
    matched_type: str
    auto_reply: Move | None


def log_off_tree(source: str, move_coord: str, player_color: str) -> None:
    """Persist an unmatched move; database access is confined to this module."""
    from db import get_db

    with get_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS puzzle_unmatched_moves (
                source TEXT NOT NULL,
                move_coord TEXT NOT NULL,
                player_color TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO puzzle_unmatched_moves(source, move_coord, player_color)
            VALUES(?, ?, ?)
            """,
            (source, move_coord, player_color),
        )
        connection.commit()


def apply_move(
    current_node: SGFNode,
    move_coord: str,
    player_color: str,
    source: str,
) -> EngineResult:
    """Process one player move in the locked five-step order."""
    # STEP 1 — Load override.
    override = override_loader.load_override(source)

    # STEP 2 — Match move.
    matched = matcher.match_move(current_node, move_coord, override)

    # STEP 3 — Traverse tree or record OFF_TREE.
    if matched == matcher.BRANCH:
        next_node = tree.find_child_by_move(current_node, move_coord)
        if next_node is None:
            raise ValueError(f"Matched SGF branch {move_coord} was not found.")
        current_node = next_node
    elif matched == matcher.EQUIVALENT:
        if override is None:
            raise ValueError("Equivalent match requires an override.")
        canonical_coord = override_loader.canonical_coord_for(override, move_coord)
        current_node = tree.find_child_by_move(current_node, canonical_coord)
        if current_node is None:
            raise ValueError(
                f"Override declares equivalent move {move_coord} -> "
                f"{canonical_coord}, but {canonical_coord} not found in SGF tree."
            )
    else:
        log_off_tree(source, move_coord, player_color)
        return EngineResult(
            status="off_tree",
            node=None,
            matched_type=matcher.OFF_TREE.value,
            auto_reply=None,
        )

    # STEP 4 — Auto-reply.
    reply = autoreply.get_auto_reply(current_node, player_color)
    if reply is not None:
        reply_node = tree.find_child_by_move(current_node, reply.coord)
        if reply_node is None:
            raise ValueError(f"Auto-reply {reply.coord} was not found in SGF tree.")
        current_node = reply_node

    # STEP 5 — Read node result.
    result = current_node.metadata.get("result", "continue")
    return EngineResult(
        status=result,
        node=current_node,
        matched_type=matched.value,
        auto_reply=reply,
    )

