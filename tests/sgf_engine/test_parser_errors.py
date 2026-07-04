import pytest

from sgf_engine.core.tree import Move
from sgf_engine.parser.sgf_parser import parse_sgf


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "not sgf",
        "()",
        "(;B[dd]",
        "(;B[DD])",
        "(;B[dd]W[pp])",
        "(;PL[black])",
        "(;SZ[nineteen])",
        "(;C[unterminated)",
        "(;B[dd]) trailing",
        "(;b[dd])",
        "(;B)",
        "(;B[dd]())",
        "(;B[dd](;W[pp])",
        "(;B[dd][pp])",
        "(;C[abc\\",
    ],
)
def test_structurally_invalid_sgf_raises_without_partial_tree(malformed):
    with pytest.raises(ValueError):
        parse_sgf(malformed)


def test_failed_parse_does_not_poison_later_valid_parse():
    with pytest.raises(ValueError):
        parse_sgf("(;B[dd]())")

    root = parse_sgf("(;B[dd])")

    assert root.children[0].move.coord == "dd"


def test_empty_pass_builds_explicit_pass_move_and_diagnostic():
    root = parse_sgf("(;B[])")

    child = root.children[0]

    assert child.move == Move("B", None, is_pass=True)
    assert child.metadata["pass"] is True
    assert child.metadata["raw_move"] == "B[]"
    assert root.metadata["diagnostics"] == [
        {"code": "EMPTY_PASS", "detail": "node=1 offset=1 raw=B[]"}
    ]


def test_legacy_tt_pass_builds_explicit_pass_move_and_diagnostic():
    root = parse_sgf("(;W[tt])")

    child = root.children[0]

    assert child.move == Move("W", None, is_pass=True)
    assert child.metadata["pass"] is True
    assert child.metadata["raw_move"] == "W[tt]"
    assert root.metadata["diagnostics"] == [
        {"code": "LEGACY_PASS_TT", "detail": "node=1 offset=1 raw=W[tt]"}
    ]


def test_ff3_long_form_property_is_canonicalized_without_unknown_diagnostic():
    root = parse_sgf("(;AddBlack[dd])")

    assert root.metadata["properties"]["AB"] == ["dd"]
    assert root.metadata.get("diagnostics", []) == []


def test_mixed_case_identifier_without_known_alias_is_tolerated_as_unknown_property():
    root = parse_sgf("(;Ab[dd])")

    assert root.metadata["properties"]["A"] == ["dd"]
    assert root.metadata["diagnostics"] == [
        {"code": "UNKNOWN_PROPERTY", "detail": "node=1 offset=2 raw=Ab[dd]"}
    ]


def test_unknown_well_formed_property_is_kept_with_diagnostic():
    root = parse_sgf("(;Foo[bar])")

    assert root.metadata["properties"]["F"] == ["bar"]
    assert root.metadata["diagnostics"] == [
        {"code": "UNKNOWN_PROPERTY", "detail": "node=1 offset=2 raw=Foo[bar]"}
    ]


def test_strict_invalid_coordinate_still_raises_same_error():
    with pytest.raises(ValueError, match=r"Invalid SGF move B\[zz\]\."):
        parse_sgf("(;B[zz])")


def test_tolerant_invalid_coordinate_records_diagnostic_and_keeps_parsing():
    root = parse_sgf("(;B[zz];W[dd])", strict=False)

    assert root.move is None
    assert root.metadata["raw_move"] == "B[zz]"
    assert root.children[0].move == Move("W", "dd")
    assert root.metadata["diagnostics"] == [
        {"code": "INVALID_MOVE_COORD", "detail": "node=1 offset=1 raw=B[zz]"}
    ]


def test_unsupported_board_size_strict_raises():
    with pytest.raises(ValueError, match="unsupported board size"):
        parse_sgf("(;SZ[20];B[dd])")


def test_unsupported_board_size_tolerant_records_diagnostic_and_stops_tree():
    root = parse_sgf("(;SZ[20];B[dd])", strict=False)

    assert root.metadata["size"] == 20
    assert root.children == []
    assert root.metadata["diagnostics"] == [
        {
            "code": "UNSUPPORTED_BOARD_SIZE",
            "detail": "node=1 offset=1 raw=SZ[20]",
        }
    ]
