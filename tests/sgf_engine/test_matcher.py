import pytest

from sgf_engine.core.matcher import BRANCH, EQUIVALENT, OFF_TREE, match_move
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


def test_branch_is_checked_before_equivalent():
    root = SGFNode(children=[SGFNode(move=Move("B", "dd"))])
    override = {"equivalent_moves": {"pp": ["dd"]}}

    assert match_move(root, "dd", override) == BRANCH


def test_declared_alternative_is_equivalent():
    root = SGFNode(children=[SGFNode(move=Move("B", "dd"))])
    override = {"equivalent_moves": {"dd": ["pp", "qq"]}}

    assert match_move(root, "pp", override) == EQUIVALENT


def test_unknown_move_is_off_tree():
    root = SGFNode(children=[SGFNode(move=Move("B", "dd"))])

    assert match_move(root, "cc", None) == OFF_TREE


def test_matcher_does_not_read_result_metadata():
    root = SGFNode(
        children=[SGFNode(move=Move("B", "dd"), metadata={"result": "fail"})]
    )

    assert match_move(root, "dd", None) == BRANCH


def test_matcher_rejects_invalid_coordinate():
    with pytest.raises(ValueError):
        match_move(SGFNode(), "DD", None)


def test_pass_node_never_matches_a_player_coordinate_move():
    root = SGFNode(children=[SGFNode(move=Move("B", None, is_pass=True))])

    assert match_move(root, "dd", None) == OFF_TREE


def test_match_move_does_not_mutate_tree_or_override():
    child = SGFNode(move=Move("B", "dd"), metadata={"result": "success"})
    root = SGFNode(children=[child], metadata={"label": "root"})
    child.parent = root
    override = {"equivalent_moves": {"pp": ["dd"]}}
    before_tree = _tree_snapshot(root)
    before_override = {"equivalent_moves": {"pp": ["dd"]}}

    assert match_move(root, "dd", override) == BRANCH

    assert _tree_snapshot(root) == before_tree
    assert override == before_override


def test_repeated_match_move_calls_return_identical_result():
    root = SGFNode(children=[SGFNode(move=Move("B", "dd"))])
    override = {"equivalent_moves": {"dd": ["pp"]}}

    first = match_move(root, "pp", override)
    second = match_move(root, "pp", override)

    assert first == second == EQUIVALENT


def test_missing_equivalent_moves_behaves_like_no_equivalent_override():
    root = SGFNode(children=[SGFNode(move=Move("B", "dd"))])

    assert match_move(root, "pp", {}) == OFF_TREE
