import hashlib
import json
from pathlib import Path

import pytest

from sgf_engine.core.tree import Move, find_child_by_move
from sgf_engine.engine import engine
from sgf_engine.parser.sgf_parser import parse_sgf


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).parent / "data" / "gold_fixtures"
MANIFEST_PATH = FIXTURE_DIR / "fixtures.json"

READY_IDS = {
    "GF-001",
    "GF-002",
    "GF-005",
    "GF-008",
    "GF-009",
    "GF-010",
}
EXCLUDED_IDS = {"GF-003", "GF-004", "GF-006", "GF-007"}
GF003_SHA256 = "0713176F21C7A23133014A5956D935311B9AA8AA5A483A87CCF8100FEA5C7D29"


@pytest.fixture(scope="module")
def gold_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records_by_id(gold_manifest):
    return {record["gf_id"]: record for record in gold_manifest["fixtures"]}


def _fixture_path(record):
    return REPO_ROOT / record["fixture_path"]


def _decode_fixture(record):
    raw = _fixture_path(record).read_bytes()
    declared = record["encoding"]
    if declared == "gb18030":
        candidates = ("gb18030",)
    elif declared == "utf-8-or-unknown":
        candidates = ("utf-8", "gb18030")
    else:
        raise AssertionError(f"Unsupported fixture encoding policy: {declared}")

    for encoding in candidates:
        try:
            return raw.decode(encoding, errors="strict"), encoding
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"Unable to decode fixture {record['sgf_file']}")


def test_gold_fixture_manifest_integrity(gold_manifest):
    assert MANIFEST_PATH.is_file()
    assert gold_manifest["schema_version"] == 1

    records = gold_manifest["fixtures"]
    assert {record["gf_id"] for record in records} == READY_IDS
    assert all(record["owner_status"] == "READY" for record in records)
    assert all(record["ready_for_next_test_commit"] is True for record in records)
    excluded = {
        record["gf_id"]: record for record in gold_manifest["excluded_fixtures"]
    }
    assert set(excluded) == EXCLUDED_IDS
    assert excluded["GF-003"]["status"] == "CANDIDATE_REQUIRES_OVERRIDE"
    assert excluded["GF-004"]["status"] == "PENDING"
    assert excluded["GF-006"]["status"] == "PENDING"
    assert excluded["GF-007"]["status"] == "PENDING"

    for record in records:
        fixture = _fixture_path(record)
        assert fixture.is_file()
        assert fixture.parent == FIXTURE_DIR
        assert hashlib.sha256(fixture.read_bytes()).hexdigest().upper() == record[
            "sha256"
        ]

    gf003_fixture = REPO_ROOT / excluded["GF-003"]["fixture_path"]
    assert gf003_fixture.is_file()
    assert gf003_fixture.parent == FIXTURE_DIR
    assert hashlib.sha256(gf003_fixture.read_bytes()).hexdigest().upper() == GF003_SHA256

    by_id = {record["gf_id"]: record for record in records}
    assert by_id["GF-001"]["sgf_file"] == by_id["GF-005"]["sgf_file"] == "163.sgf"
    assert by_id["GF-001"]["sha256"] == by_id["GF-005"]["sha256"]
    assert by_id["GF-002"]["coordinate_status"] == (
        "owner_truth_uses_no_skip_i_coordinate_notation"
    )
    assert by_id["GF-002"]["player_move_owner_coordinate"] == "白 O14"
    assert by_id["GF-002"]["auto_reply_owner_coordinate"] == "黑 N15"
    assert "no-skip-I" in by_id["GF-002"]["coordinate_note"]
    assert "白 P14" in by_id["GF-002"]["coordinate_note"]
    assert "黑 O15" in by_id["GF-002"]["coordinate_note"]
    assert by_id["GF-008"]["encoding"] == "gb18030"
    assert by_id["GF-008"]["encoding_policy"] == (
        "preserve_original_bytes_and_decode_by_manifest_in_future_tests"
    )
    assert excluded["GF-003"]["sgf_file"] == "431.sgf"
    assert excluded["GF-003"]["fixture_path"] == (
        "tests/sgf_engine/data/gold_fixtures/431.sgf"
    )
    assert excluded["GF-003"]["sha256"] == GF003_SHA256
    assert excluded["GF-003"]["player_move_sgf"] == "B[sd]"
    assert excluded["GF-003"]["player_move_owner_coordinate"] == "黑 T16"
    assert excluded["GF-003"]["canonical_move_sgf"] == "B[sf]"
    assert excluded["GF-003"]["canonical_move_owner_coordinate"] == "黑 T14"
    assert excluded["GF-003"]["expected_without_active_override"] == "OFF_TREE"
    assert excluded["GF-003"]["override_required"] is True
    assert excluded["GF-003"]["active_test_added"] is False
    assert excluded["GF-003"]["test_only_override_validation"] is True
    assert excluded["GF-003"]["runtime_override_active"] is False
    assert excluded["GF-003"]["ready_activation"] is False
    assert excluded["GF-003"]["proposed_override"] == {
        "source_key": "tests/sgf_engine/data/gold_fixtures/431.sgf",
        "equivalent_moves": {"sf": ["sd"]},
    }
    assert excluded["GF-003"]["ready_for_next_test_commit"] is False


@pytest.mark.parametrize(
    ("sgf_file", "gf_id", "expected_encoding"),
    [
        pytest.param("163.sgf", "GF-001", "utf-8", id="163"),
        pytest.param("35.sgf", "GF-002", "utf-8", id="35"),
        pytest.param("186.sgf", "GF-008", "gb18030", id="186"),
        pytest.param("881.sgf", "GF-009", "utf-8", id="881"),
        pytest.param("19.sgf", "GF-010", "utf-8", id="19"),
    ],
)
def test_unique_gold_fixture_decodes_and_parses(
    records_by_id,
    sgf_file,
    gf_id,
    expected_encoding,
):
    record = records_by_id[gf_id]
    assert record["sgf_file"] == sgf_file

    text, actual_encoding = _decode_fixture(record)
    root = parse_sgf(text)

    assert actual_encoding == expected_encoding
    assert root.parent is None
    assert root.children


@pytest.mark.parametrize(
    (
        "gf_id",
        "expected_behavior",
        "move_coord",
        "player_color",
        "expected_status",
        "expected_match",
        "expected_auto_reply",
        "expected_final_move",
    ),
    [
        pytest.param(
            "GF-001",
            "BRANCH_CONTINUE_NO_AUTO_REPLY",
            "sb",
            "B",
            "continue",
            "branch",
            None,
            Move("B", "sb"),
            id="GF-001",
        ),
        pytest.param(
            "GF-002",
            "BRANCH_CONTINUE_AUTO_REPLY",
            "of",
            "W",
            "continue",
            "branch",
            Move("B", "ne"),
            Move("B", "ne"),
            id="GF-002",
        ),
        pytest.param(
            "GF-005",
            "OFF_TREE_WITH_LOGGING",
            "sa",
            "B",
            "off_tree",
            "off_tree",
            None,
            None,
            id="GF-005",
        ),
        pytest.param(
            "GF-008",
            "MISSING_RESULT_DEFAULTS_TO_CONTINUE_NO_OVERRIDE",
            "ea",
            "B",
            "continue",
            "branch",
            None,
            Move("B", "ea"),
            id="GF-008",
        ),
        pytest.param(
            "GF-009",
            "BRANCH_CONTINUE_NO_AUTO_REPLY_MULTIPLE_OPPONENT_CHILDREN",
            "gb",
            "B",
            "continue",
            "branch",
            None,
            Move("B", "gb"),
            id="GF-009",
        ),
        pytest.param(
            "GF-010",
            "NO_AUTO_REPLY_FOR_SAME_COLOR_CHILD",
            "co",
            "B",
            "continue",
            "branch",
            None,
            Move("B", "co"),
            id="GF-010",
        ),
    ],
)
def test_ready_gold_fixture_behavior(
    monkeypatch,
    records_by_id,
    gf_id,
    expected_behavior,
    move_coord,
    player_color,
    expected_status,
    expected_match,
    expected_auto_reply,
    expected_final_move,
):
    record = records_by_id[gf_id]
    text, _ = _decode_fixture(record)
    root = parse_sgf(text)
    native_player_node = find_child_by_move(root, move_coord)

    assert record["expected_behavior"] == expected_behavior
    assert record["player_color"] == player_color
    assert record["player_move_sgf"] == f"{player_color}[{move_coord}]"

    if gf_id == "GF-005":
        assert native_player_node is None
        assert find_child_by_move(root, "sb").move == Move("B", "sb")
    else:
        assert native_player_node is not None
        assert native_player_node.move == Move(player_color, move_coord)

    if gf_id == "GF-002":
        assert len(native_player_node.children) == 1
        assert native_player_node.children[0].move == Move("B", "ne")
    elif gf_id == "GF-008":
        assert "result" not in native_player_node.metadata
        assert native_player_node.children == []
    elif gf_id == "GF-009":
        assert [child.move for child in native_player_node.children] == [
            Move("W", "ga"),
            Move("W", "dc"),
        ]
    elif gf_id == "GF-010":
        assert [child.move for child in native_player_node.children] == [
            Move("B", "cj")
        ]

    logged = []
    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)
    monkeypatch.setattr(
        engine,
        "log_off_tree",
        lambda source, move, color: logged.append((source, move, color)),
    )

    result = engine.apply_move(
        root,
        move_coord,
        player_color,
        record["fixture_path"],
    )

    assert result.status == expected_status
    assert result.matched_type == expected_match
    assert result.auto_reply == expected_auto_reply
    if expected_final_move is None:
        assert result.node is None
    else:
        assert result.node is not None
        assert result.node.move == expected_final_move

    if gf_id == "GF-005":
        assert logged == [(record["fixture_path"], "sa", "B")]
    else:
        assert logged == []


def test_gf003_without_override_remains_off_tree(gold_manifest, monkeypatch):
    excluded = {
        record["gf_id"]: record for record in gold_manifest["excluded_fixtures"]
    }
    record = excluded["GF-003"]
    text = _fixture_path(record).read_text(encoding="utf-8")
    root = parse_sgf(text)
    logged = []

    monkeypatch.setattr(engine.override_loader, "load_override", lambda source: None)
    monkeypatch.setattr(
        engine,
        "log_off_tree",
        lambda source, move, color: logged.append((source, move, color)),
    )

    result = engine.apply_move(root, "sd", "B", record["fixture_path"])

    assert result.matched_type == "off_tree"
    assert result.status == "off_tree"
    assert result.node is None
    assert result.auto_reply is None
    assert logged == [(record["fixture_path"], "sd", "B")]


def test_gf003_test_only_override_maps_equivalent_to_canonical(
    gold_manifest, tmp_path, monkeypatch
):
    excluded = {
        record["gf_id"]: record for record in gold_manifest["excluded_fixtures"]
    }
    record = excluded["GF-003"]
    text = _fixture_path(record).read_text(encoding="utf-8")
    root = parse_sgf(text)
    override_path = tmp_path / "puzzle_variation_overrides.json"
    override_path.write_text(
        json.dumps(
            {
                record["fixture_path"]: {
                    "equivalent_moves": {
                        "sf": ["sd"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(engine.override_loader, "OVERRIDES_FILE", override_path)

    result = engine.apply_move(root, "sd", "B", record["fixture_path"])

    assert result.matched_type == "equivalent"
    assert result.status == "continue"
    assert result.auto_reply is None
    assert result.node is not None
    assert result.node.move == Move("B", "sf")
