from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "planning" / "shadow_integration_gap_audit.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8").lower()


def test_shadow_integration_gap_audit_exists() -> None:
    assert DOC.exists()


def test_shadow_integration_gap_audit_keeps_required_sections() -> None:
    text = _text()

    required_sections = [
        "entry-point inventory",
        "production schema",
        "canonical comparison",
        "pipeline",
        "dashboard readiness",
        "next implementation batch",
    ]

    for section in required_sections:
        assert section in text


def test_shadow_integration_gap_audit_keeps_route_and_readiness_assertions() -> None:
    text = _text()

    for phrase in [
        "/api/rating_test/answer",
        "/api/daily-challenge/submit",
        "/api/challenges/friend/<int:cid>/answer",
        "shadow-v3",
        "current verdict: partial",
        "production currently observes shadow judging in all three answer routes",
        "read-only aggregation layer",
    ]:
        assert phrase in text


def test_shadow_integration_gap_audit_keeps_canonical_comparison_statuses() -> None:
    text = _text()

    for status in [
        "match",
        "missing",
        "production_only",
        "renamed",
        "type_mismatch",
        "semantic_mismatch",
    ]:
        assert status in text


def test_shadow_integration_gap_audit_keeps_pipeline_steps() -> None:
    text = _text()

    match = re.search(r"## pipeline\n(.*?)(?=\n## |\Z)", text, flags=re.S)
    assert match is not None
    block = match.group(1)

    for phrase in [
        "http route",
        "validation",
        "legacy judgement",
        "shadow judgement",
        "comparison",
        "event creation",
        "persistence / jsonl sink",
    ]:
        assert phrase in block


def test_shadow_integration_gap_audit_keeps_next_batch_contract() -> None:
    text = _text()

    for phrase in [
        "objective",
        "exact production files likely involved",
        "fields to add",
        "routes covered",
        "risk level",
        "required tests",
        "deployment required",
        "db backup required",
    ]:
        assert phrase in text

