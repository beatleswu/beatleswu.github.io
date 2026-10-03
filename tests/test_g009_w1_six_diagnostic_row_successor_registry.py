"""Validator for the W1 six-row diagnostic successor closure.

This is governance-only: the historical diagnostic nodes remain present and
are registered with current semantic successors. No product/runtime contract
is changed by this validator.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tests/governance/g009_w1_six_diagnostic_row_successor_registry.json"
EXISTING = ROOT / "tests/governance/g009_protected_test_successor_registry.json"
ALLOWED_CLASSES = {
    "STALE_TEST_EXPECTATION",
    "STALE_FIXTURE_OR_HARNESS",
    "SEMANTIC_SUCCESSOR_ALREADY_PROVES_BEHAVIOR",
}
EXPECTED_ROWS = {1, 4, 6, 11, 13, 15}


def _node_exists(node: str) -> bool:
    relative_path, function_node = node.split("::", 1)
    path = ROOT / relative_path
    if not path.is_file():
        return False
    function_name = function_node.split("[", 1)[0]
    source = path.read_text(encoding="utf-8")
    return re.search(rf"^def\s+{re.escape(function_name)}\s*\(", source, re.M) is not None


def test_six_diagnostic_rows_are_machine_readable_and_complete():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["schema"] == "g009-w1-six-diagnostic-row-successor-registry-v1"
    assert registry["scope"] == "test-governance-only"
    assert registry["task_id"] == "G009_W1_SIX_DIAGNOSTIC_ROWS_RELEASE_GATE_CLOSURE_001"
    assert registry["parent_head"] == "8e0b0b518654aa2fc1623db921d11ef568bd1df7"
    assert registry["parent_tree"] == "57b2a07079f354389dffaa389f73c5399337e577"

    entries = {int(entry["row_id"]): entry for entry in registry["entries"]}
    assert set(entries) == EXPECTED_ROWS
    assert sum(len(entry["old_node_ids"]) for entry in entries.values()) == 36
    all_successors = []
    for row_id, entry in entries.items():
        assert entry["diagnostic_id"]
        assert entry["old_contract"]
        assert entry["current_failure_signature"]
        assert entry["classification"] in ALLOWED_CLASSES
        assert entry["status"] == "SUPERSEDED_BY_SEMANTIC_SUCCESSOR"
        assert entry["retirement_or_supersession_reason"]
        assert entry["current_authority_sources"]
        assert entry["successor_evidence"]
        assert entry["successor_pass_required_before_retirement"] is True
        assert entry["old_node_ids"]
        assert entry["successor_node_ids"]
        assert all(_node_exists(node) for node in entry["old_node_ids"])
        assert all(_node_exists(node) for node in entry["successor_node_ids"])
        all_successors.extend(entry["successor_node_ids"])
    assert len(all_successors) == len(set(all_successors))


def test_existing_p09_p07_governance_is_reused_for_rows_four_and_eleven():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    existing = json.loads(EXISTING.read_text(encoding="utf-8"))
    existing_ids = {entry["protected_id"] for entry in existing["entries"]}
    by_row = {int(entry["row_id"]): entry for entry in registry["entries"]}
    assert by_row[4]["existing_governance_reference"] == "P09"
    assert by_row[11]["existing_governance_reference"] == "P07"
    assert {by_row[4]["existing_governance_reference"], by_row[11]["existing_governance_reference"]} <= existing_ids


def test_historical_nodes_are_retained_and_successor_contracts_are_nonempty():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for entry in registry["entries"]:
        assert all(_node_exists(node) for node in entry["old_node_ids"])
        assert all(_node_exists(node) for node in entry["successor_node_ids"])
