import json

import pytest

from sgf_engine.core.tree import Move, SGFNode
from sgf_engine.engine import engine
from sgf_engine.parser.sgf_parser import parse_sgf


def _attach(parent, child):
    child.parent = parent
    parent.children.append(child)
    return child


def test_apply_move_branch_then_auto_reply_then_result(monkeypatch):
    root = SGFNode()
    player_node = _attach(root, SGFNode(move=Move("B", "dd")))
    reply_node = _attach(
        player_node,
        SGFNode(move=Move("W", "pp"), metadata={"result": "success"}),
    )
    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)

    result = engine.apply_move(root, "dd", "B", "SGF/path/11.sgf")

    assert result.status == "success"
    assert result.node is reply_node
    assert result.matched_type == "branch"
    assert result.auto_reply == Move("W", "pp")


def test_apply_move_equivalent_resolves_canonical_branch(monkeypatch):
    root = SGFNode()
    canonical = _attach(
        root,
        SGFNode(move=Move("B", "dd"), metadata={"result": "continue"}),
    )
    override = {"equivalent_moves": {"dd": ["pp"]}}
    monkeypatch.setattr(
        engine.override_loader, "load_override", lambda source: override
    )

    result = engine.apply_move(root, "pp", "B", "SGF/path/11.sgf")

    assert result.status == "continue"
    assert result.node is canonical
    assert result.matched_type == "equivalent"
    assert result.auto_reply is None


def test_apply_move_defaults_missing_result_metadata_to_continue(monkeypatch):
    root = SGFNode()
    player_node = _attach(root, SGFNode(move=Move("B", "dd")))
    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)

    result = engine.apply_move(root, "dd", "B", "SGF/path/11.sgf")

    assert result.status == "continue"
    assert result.node is player_node


def test_apply_move_uses_real_json_override_loading(tmp_path, monkeypatch):
    overrides_path = tmp_path / "puzzle_variation_overrides.json"
    overrides_path.write_text(
        json.dumps(
            {
                "SGF/path/11.sgf": {
                    "equivalent_moves": {"dd": ["pp"]},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(engine.override_loader, "OVERRIDES_FILE", overrides_path)
    root = SGFNode()
    canonical = _attach(
        root,
        SGFNode(move=Move("B", "dd"), metadata={"result": "success"}),
    )

    result = engine.apply_move(root, "pp", "B", "SGF/path/11.sgf")

    assert result.status == "success"
    assert result.node is canonical
    assert result.matched_type == "equivalent"


def test_active_override_does_not_override_direct_branch_priority(monkeypatch):
    root = SGFNode()
    direct = _attach(
        root,
        SGFNode(move=Move("B", "pp"), metadata={"result": "success"}),
    )
    _attach(root, SGFNode(move=Move("B", "dd"), metadata={"result": "fail"}))
    override = {"equivalent_moves": {"dd": ["pp"]}}
    monkeypatch.setattr(
        engine.override_loader, "load_override", lambda source: override
    )

    result = engine.apply_move(root, "pp", "B", "SGF/path/11.sgf")

    assert result.status == "success"
    assert result.node is direct
    assert result.matched_type == "branch"


def test_equivalent_missing_from_tree_raises_specific_error(monkeypatch):
    root = SGFNode()
    override = {"equivalent_moves": {"cc": ["pp"]}}
    monkeypatch.setattr(
        engine.override_loader, "load_override", lambda source: override
    )

    with pytest.raises(
        ValueError,
        match=(
            r"Override declares equivalent move pp -> cc, "
            r"but cc not found in SGF tree\."
        ),
    ):
        engine.apply_move(root, "pp", "B", "SGF/path/11.sgf")


def test_off_tree_logs_and_returns_without_validity_judgment(monkeypatch):
    root = SGFNode(children=[SGFNode(move=Move("B", "dd"))])
    calls = []
    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)
    monkeypatch.setattr(
        engine,
        "log_off_tree",
        lambda source, move, color: calls.append((source, move, color)),
    )

    result = engine.apply_move(root, "cc", "B", "SGF/path/11.sgf")

    assert calls == [("SGF/path/11.sgf", "cc", "B")]
    assert result.status == "off_tree"
    assert result.node is None
    assert result.matched_type == "off_tree"
    assert result.auto_reply is None


def test_same_color_single_child_is_not_auto_replied(monkeypatch):
    root = SGFNode()
    player_node = _attach(
        root,
        SGFNode(move=Move("B", "dd"), metadata={"result": "continue"}),
    )
    _attach(player_node, SGFNode(move=Move("B", "pp"), metadata={"result": "fail"}))
    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)

    result = engine.apply_move(root, "dd", "B", "SGF/path/11.sgf")

    assert result.node is player_node
    assert result.status == "continue"
    assert result.auto_reply is None


def test_identical_inputs_produce_identical_result_values(monkeypatch):
    root = SGFNode(
        children=[
            SGFNode(
                move=Move("B", "dd"),
                metadata={"result": "success"},
            )
        ]
    )
    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)

    first = engine.apply_move(root, "dd", "B", "SGF/path/11.sgf")
    second = engine.apply_move(root, "dd", "B", "SGF/path/11.sgf")

    assert first == second


def test_apply_move_step_order_with_lightweight_spies(monkeypatch):
    root = SGFNode()
    player_node = _attach(root, SGFNode(move=Move("B", "dd")))
    reply_node = _attach(
        player_node,
        SGFNode(move=Move("W", "pp"), metadata={"result": "success"}),
    )
    calls = []
    original_find = engine.tree.find_child_by_move

    def load_override_spy(source):
        calls.append("load_override")
        return None

    def match_move_spy(current_node, move_coord, override):
        calls.append("match_move")
        return engine.matcher.BRANCH

    def find_child_spy(node, coord):
        calls.append(f"find_child_by_move:{coord}")
        return original_find(node, coord)

    def get_auto_reply_spy(current_node, player_color):
        calls.append("get_auto_reply")
        return Move("W", "pp")

    monkeypatch.setattr(engine.override_loader, "load_override", load_override_spy)
    monkeypatch.setattr(engine.matcher, "match_move", match_move_spy)
    monkeypatch.setattr(engine.tree, "find_child_by_move", find_child_spy)
    monkeypatch.setattr(engine.autoreply, "get_auto_reply", get_auto_reply_spy)

    result = engine.apply_move(root, "dd", "B", "SGF/path/11.sgf")

    assert result.node is reply_node
    assert result.status == "success"
    assert calls == [
        "load_override",
        "match_move",
        "find_child_by_move:dd",
        "get_auto_reply",
        "find_child_by_move:pp",
    ]


def test_autoreply_pass_node_current_behavior_is_characterized(monkeypatch):
    root = parse_sgf("(;B[dd];W[])")
    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)

    result = engine.apply_move(root, "dd", "B", "SGF/path/pass.sgf")

    assert result == engine.EngineResult(
        status="continue",
        node=root.children[0].children[0],
        matched_type="branch",
        auto_reply=Move("W", None, is_pass=True),
    )
