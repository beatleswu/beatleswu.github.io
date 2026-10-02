"""Validator for the G009 protected-test successor registration."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tests/governance/g009_protected_test_successor_registry.json"
ENVIRONMENT = ROOT / "tests/governance/g009_w1_p09_p07_test_environment.json"


EXPECTED = {
    "P09": {
        "old": "tests/test_e10_adventure_hero_shop_backpack_information_architecture.py::test_backpack_is_an_enabled_independent_destination_with_exclusive_navigation",
        "successor_count": 2,
        "status": "SUPERSEDED_BY_SEMANTIC_SUCCESSOR",
    },
    "P07": {
        "old": "tests/test_e10_zone1_lord_trial_progress_completion.py::test_srs_review_limit_guard_exempts_only_active_boss_questions",
        "successor_count": 4,
        "status": "SUPERSEDED_BY_P01_P04_SEMANTIC_COVERAGE",
    },
}


def _node_exists(node: str) -> bool:
    relative_path, function_node = node.split("::", 1)
    path = ROOT / relative_path
    if not path.is_file():
        return False
    function_name = function_node.split("[", 1)[0]
    source = path.read_text(encoding="utf-8")
    return re.search(rf"^def\s+{re.escape(function_name)}\s*\(", source, re.M) is not None


def test_protected_successor_registry_is_machine_readable_and_complete():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["schema"] == "g009-protected-test-successor-registry-v1"
    assert registry["scope"] == "test-governance-only"
    assert registry["registration_date"] == "2026-10-02"
    assert registry["resulting_commit"] == "POST_COMMIT_OUTPUT_HEAD"
    assert registry["resulting_commit_binding"]

    entries = {entry["protected_id"]: entry for entry in registry["entries"]}
    assert set(entries) == set(EXPECTED)
    for protected_id, expected in EXPECTED.items():
        entry = entries[protected_id]
        assert entry["old_protected_node_identity"] == expected["old"]
        assert len(entry["successor_node_ids"]) == expected["successor_count"]
        assert entry["status"] == expected["status"]
        assert entry["retirement_or_supersession_reason"]
        assert entry["semantic_coverage_explanation"]
        assert entry["successor_pass_required_before_retirement"] is True
        assert _node_exists(entry["old_protected_node_identity"])
        assert all(_node_exists(node) for node in entry["successor_node_ids"])


def test_p07_registration_names_the_four_authorized_successor_nodes():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    p07 = next(entry for entry in registry["entries"] if entry["protected_id"] == "P07")
    assert p07["successor_node_ids"] == [
        "tests/test_incident_018_lord_attempt_scope.py::test_in_scope_lord_answer_is_not_rejected_by_daily_limit[A-at-cap-0-20]",
        "tests/test_incident_018_lord_attempt_scope.py::test_in_scope_lord_answer_is_not_rejected_by_daily_limit[B-candidate-A-4-16]",
        "tests/test_incident_018_lord_attempt_scope.py::test_in_scope_lord_answer_is_not_rejected_by_daily_limit[C-candidate-B-11-9]",
        "tests/test_incident_018_lord_attempt_scope.py::test_ordinary_free_practice_at_cap_is_still_rejected_by_daily_limit",
    ]


def test_task_owned_environment_manifest_is_explicitly_no_db():
    environment = json.loads(ENVIRONMENT.read_text(encoding="utf-8"))
    assert environment["task_id"] == "G009_W1_P09_P07_COVERAGE_001"
    assert environment["compose_project"] == "g009_w1_p09_p07_coverage_001"
    assert environment["db_required"] == "NO"
    assert environment["db_name"] == "NOT_APPLICABLE"
    assert environment["db_port"] == "NOT_APPLICABLE"
    assert environment["container_names"] == []
