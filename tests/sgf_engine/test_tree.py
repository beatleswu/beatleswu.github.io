import pytest

from sgf_engine.core.tree import Move, SGFNode, find_child_by_move


def test_find_child_by_move_returns_first_match():
    first = SGFNode(move=Move("B", "dd"))
    second = SGFNode(move=Move("W", "dd"))
    root = SGFNode(children=[first, second])

    assert find_child_by_move(root, "dd") is first


def test_find_child_by_move_ignores_metadata_node_and_missing_coord():
    root = SGFNode(children=[SGFNode(metadata={"comment": "metadata"})])

    assert find_child_by_move(root, "dd") is None


@pytest.mark.parametrize(
    "args",
    [
        ("black", "dd"),
        ("B", "DD"),
        ("W", "tt"),
    ],
)
def test_move_rejects_invalid_data(args):
    with pytest.raises(ValueError):
        Move(*args)

