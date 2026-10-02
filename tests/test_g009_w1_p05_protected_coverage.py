"""Machine-readable P05 successor registration and retirement guard."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = (
    ROOT
    / "tests"
    / "fixtures"
    / "acceptance"
    / "g009_w1_p05_protected_successor_registry.json"
)
OLD_NODE = (
    "tests/test_map_battle_legacy_adapter.py::"
    "test_postgres_concurrent_map_battle_progression_is_exactly_once"
)
SUCCESSOR_NODE = (
    "tests/test_g009_w1_p05_semantic_successor.py::"
    "test_p05_one_logical_submission_has_one_authoritative_effect"
)


def _node_exists(node_id: str) -> bool:
    file_name, function_name = node_id.split("::", 1)
    path = ROOT / file_name
    if not path.is_file():
        return False
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
        for node in ast.walk(tree)
    )


def _function_is_not_skip_decorated(node_id: str) -> bool:
    file_name, function_name = node_id.split("::", 1)
    path = ROOT / file_name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ),
        None,
    )
    if function is None:
        return False
    for decorator in function.decorator_list:
        rendered = ast.unparse(decorator)
        if "skip" in rendered.lower() or "xfail" in rendered.lower():
            return False
    return True


def test_p05_protected_successor_registration_and_retirement_are_valid() -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    assert registry["schema"] == "g009_w1_p05_protected_successor_registry_v1"
    assert registry["task_id"] == "G009_W1_P05_PROTECTED_NODE_RECONCILIATION_002"
    assert registry["requirement"] == "P05"
    assert registry["contract"] == "ONE_LOGICAL_SUBMISSION = ONE_AUTHORITATIVE_EFFECT"
    assert registry["mapping"] == {"P05": SUCCESSOR_NODE}

    successor = registry["successor"]
    old = registry["old_node"]
    gate = registry["retirement_gate"]
    assert successor["node_id"] == SUCCESSOR_NODE
    assert successor["status"] == "CURRENT"
    assert {
        "first_valid_submission",
        "exact_duplicate_retry",
        "duplicate_persisted_authoritative_delta_none",
        "true_concurrent_duplicate",
        "independent_http_client_contexts",
        "real_postgresql_transaction",
        "formal_application_schema_bootstrap",
        "persisted_submission_progression_battle_state",
    } <= set(successor["coverage"])

    assert old["node_id"] == OLD_NODE
    assert old["status"] == "SUPERSEDED"
    assert old["classification"] == "STALE_IMPLEMENTATION_DETAIL"
    assert _node_exists(OLD_NODE)
    assert _node_exists(SUCCESSOR_NODE)
    assert _function_is_not_skip_decorated(OLD_NODE)

    assert gate["order"] == [
        "successor_added",
        "successor_passed",
        "p05_mapping_registered",
        "protected_coverage_validator_passed",
        "old_node_marked_superseded",
    ]
    assert gate["old_node_retained_in_repository"] is True
    assert gate["old_node_not_deleted"] is True
    assert gate["old_node_not_skipped"] is True
    assert gate["old_node_not_disabled"] is True
    assert gate["old_node_not_deselected"] is True
