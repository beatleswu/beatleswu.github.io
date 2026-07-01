from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "planning" / "canonical_puzzle_identity_owner_decision_adr.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8").lower()


def test_owner_decision_adr_exists() -> None:
    assert DOC.exists()


def test_records_uuid_v4_owner_decision() -> None:
    text = _text()
    assert "status" in text
    assert "accepted owner decision" in text
    assert "canonical_puzzle_id" in text
    assert "ingestion-generated stable uuid v4" in text


def test_rejects_non_canonical_identity_sources() -> None:
    text = _text()
    assert "must not be used as canonical puzzle identity" in text
    for source in [
        "source_path",
        "fixture_path",
        "gold_fixture_id",
        "frontend temporary id",
        "runtime state",
        "content hash",
    ]:
        assert source in text


def test_documents_stability_rule() -> None:
    text = _text()
    assert "once a future production `canonical_puzzle_id` is generated" in text
    assert "it must remain stable" in text


def test_phase_12a_has_no_runtime_or_schema_implementation_scope() -> None:
    text = _text()
    assert "this phase 12a adr does not implement:" in text
    for non_goal in [
        "runtime ingestion",
        "db schema",
        "db migration",
        "api fields",
        "frontend fields",
    ]:
        assert non_goal in text
