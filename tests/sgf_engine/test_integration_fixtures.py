from pathlib import Path

import pytest

from sgf_engine.parser.sgf_parser import parse_sgf


FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "sgf_engine" / "data" / "fixtures"
)
GOLD_FIXTURES = sorted(FIXTURE_DIR.glob("*.sgf")) if FIXTURE_DIR.exists() else []


@pytest.mark.integration
@pytest.mark.pending
@pytest.mark.skipif(
    len(GOLD_FIXTURES) < 10,
    reason=(
        "PENDING: requires 10 manually verified real gold SGFs; "
        f"found {len(GOLD_FIXTURES)}. Synthetic SGFs are forbidden."
    ),
)
def test_all_gold_fixtures_parse_as_complete_trees():
    assert len(GOLD_FIXTURES) == 10
    for fixture in GOLD_FIXTURES:
        root = parse_sgf(fixture.read_text(encoding="utf-8"))
        assert root.parent is None

