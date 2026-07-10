from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DOC = ROOT / "docs" / "planning" / "shadow_judging_readiness_audit.md"


def _audit_text() -> str:
    return AUDIT_DOC.read_text(encoding="utf-8").lower()


def test_shadow_judging_readiness_audit_doc_exists() -> None:
    assert AUDIT_DOC.exists()


def test_shadow_judging_readiness_audit_keeps_required_sections() -> None:
    text = _audit_text()

    required_phrases = [
        "sgf observe-1 shadow judging readiness audit",
        "purpose",
        "evidence base",
        "current entry points",
        "jsonl schema",
        "dashboard readiness",
        "mvp metrics",
        "data quality",
        "roadmap",
        "summary",
        "current verdict: not ready",
        "status: not ready",
    ]

    for phrase in required_phrases:
        assert phrase in text


def test_shadow_judging_readiness_audit_documents_entry_points() -> None:
    text = _audit_text()

    required_routes = [
        "/api/daily-challenge/submit",
        "/api/challenges/friend/<id>/answer",
        "/api/rating_test/answer",
    ]

    for route in required_routes:
        assert route in text

    required_sentences = [
        "there is no checked-in production shadow judging hook in this repository",
        "this audit cannot prove that production still only observes",
        "this repository cannot prove the observation entry still routes through the existing shadow judging hook",
    ]

    for sentence in required_sentences:
        assert sentence in text


def test_shadow_judging_readiness_audit_covers_every_schema_field() -> None:
    text = _audit_text()

    required_fields = [
        "event_id",
        "legacy_question_id",
        "canonical_puzzle_id",
        "player_color",
        "player_move_sgf",
        "player_move_board_coordinate",
        "created_at",
        "source_judgement",
        "shadow_judgement",
        "classification",
        "review_recommended",
        "owner_decision_required",
        "candidate_only_detected",
        "gf003_related",
        "invalid_identity",
        "legacy_unknown",
        "user_facing_judgement_changed",
        "legacy_reason",
        "shadow_reason",
    ]

    for field in required_fields:
        assert field in text

    for section in ["identity", "runtime", "engine comparison", "diagnostics"]:
        assert section in text


def test_shadow_judging_readiness_audit_lists_mvp_metric_statuses() -> None:
    text = _audit_text()

    expected_statuses = {
        "total events": "partial",
        "successful comparisons": "partial",
        "identical verdicts": "partial",
        "mismatches": "partial",
        "parser failures": "not available",
        "exceptions": "not available",
        "latency average": "not available",
        "latency p50": "not available",
        "latency p95": "not available",
        "top mismatch puzzles": "partial",
        "top parser failures": "not available",
        "daily event count": "partial",
    }

    for metric, status in expected_statuses.items():
        assert metric in text
        assert status in text


def test_shadow_judging_readiness_audit_keeps_roadmap_phases() -> None:
    text = _audit_text()

    for phase in ["observe-2", "observe-3", "observe-4"]:
        match = re.search(
            rf"### {phase}\n(.*?)(?=\n### observe-\d+|\Z)",
            text,
            flags=re.S,
        )
        assert match is not None
        block = match.group(1)

        for phrase in ["objective", "scope", "excluded scope", "estimated risk"]:
            assert phrase in block

