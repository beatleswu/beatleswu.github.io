import pytest

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
        "(;Ab[dd])",
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
