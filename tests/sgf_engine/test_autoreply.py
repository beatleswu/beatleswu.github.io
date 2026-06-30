import pytest

from sgf_engine.core.autoreply import get_auto_reply
from sgf_engine.core.tree import Move, SGFNode


def _tree_snapshot(node):
    return (
        node.move,
        dict(node.metadata),
        [
            (
                child.move,
                child.parent is node,
                dict(child.metadata),
                len(child.children),
            )
            for child in node.children
        ],
    )


def test_single_opponent_child_returns_move():
    move = Move("W", "pp")
    node = SGFNode(children=[SGFNode(move=move)])

    assert get_auto_reply(node, "B") == move


def test_single_same_color_child_returns_none():
    node = SGFNode(children=[SGFNode(move=Move("B", "pp"))])

    assert get_auto_reply(node, "B") is None


def test_multiple_children_return_none():
    node = SGFNode(
        children=[
            SGFNode(move=Move("W", "pp")),
            SGFNode(move=Move("W", "qq")),
        ]
    )

    assert get_auto_reply(node, "B") is None


def test_metadata_child_returns_none():
    node = SGFNode(children=[SGFNode(metadata={"comment": "metadata"})])

    assert get_auto_reply(node, "B") is None


def test_invalid_player_color_raises_even_without_children():
    with pytest.raises(ValueError):
        get_auto_reply(SGFNode(), "black")


@pytest.mark.parametrize("player_color", ["B", "W"])
def test_empty_node_returns_none_for_valid_player_color(player_color):
    assert get_auto_reply(SGFNode(), player_color) is None


def test_get_auto_reply_does_not_mutate_tree():
    child = SGFNode(move=Move("W", "pp"), metadata={"result": "success"})
    node = SGFNode(children=[child], metadata={"label": "current"})
    child.parent = node
    before = _tree_snapshot(node)

    assert get_auto_reply(node, "B") == Move("W", "pp")

    assert _tree_snapshot(node) == before


def test_repeated_get_auto_reply_calls_return_identical_result():
    node = SGFNode(children=[SGFNode(move=Move("W", "pp"))])

    first = get_auto_reply(node, "B")
    second = get_auto_reply(node, "B")

    assert first == second == Move("W", "pp")
