"""Machine-readable B01-B04 successor and retirement governance."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tests" / "governance" / "g009_w1_scope_allowlist_successor_registry.json"


EXPECTED = {
    "B01": {
        "old": "tests/deployment/test_eq_f_r3_release_flag_propagation.py::test_a_normal_governed_deploy_resolves_shop_true_equipment_false",
        "successors": [
            "tests/deployment/test_eq_f_r3_release_flag_propagation.py::test_a_normal_governed_deploy_resolves_shop_false_equipment_false"
        ],
        "status": "RENAMED",
    },
    "B02": {
        "old": "tests/deployment/test_image_content_boundary.py::test_assets_not_required_at_build_time",
        "successors": [
            "tests/deployment/test_image_content_boundary.py::test_assets_tree_is_never_copied_wholesale",
            "tests/deployment/test_image_content_boundary.py::test_baked_assets_are_dual_delivery_or_image_only_runtime_support",
            "tests/deployment/test_image_content_boundary.py::test_external_only_asset_classes_are_never_baked",
        ],
        "status": "SUPERSEDED",
    },
    "B03": {
        "old": "tests/test_act_b_provider_boundary_d1.py::test_zone4_to_zone10_slots_are_not_admitted_for_new_map_battles",
        "successors": [
            "tests/test_act_b_provider_boundary_d1.py::test_zone4_to_zone10_creation_and_restore_use_the_canonical_c2a_e1a_provider",
            "tests/test_act_b_provider_boundary_d1.py::test_zone1_to_zone3_admission_is_unchanged_by_zone4_10_activation",
        ],
        "status": "SUPERSEDED",
    },
    "B04": {
        "old": "tests/test_e9_server_rollout_targeting.py::test_admin_only_scope_is_default_and_allowlist_cannot_expand_it",
        "successors": [
            "tests/test_e9_server_rollout_targeting.py::test_authenticated_scope_is_default_and_allowlist_cannot_expand_it"
        ],
        "status": "RENAMED",
    },
}


def _node_exists(node: str) -> bool:
    relative_path, function_node = node.split("::", 1)
    path = ROOT / relative_path
    if not path.is_file():
        return False
    function_name = function_node.split("[", 1)[0]
    source = path.read_text(encoding="utf-8")
    return re.search(rf"^(?:async\s+)?def\s+{re.escape(function_name)}\s*\(", source, re.M) is not None


def test_b01_b04_successor_registry_is_syntax_valid_complete_and_acyclic() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["schema"] == "g009-w1-scope-allowlist-successor-registry-v1"
    assert registry["scope"] == "test-governance-only"
    assert registry["registration_date"] == "2026-10-02"
    assert registry["resulting_commit"] == "POST_COMMIT_OUTPUT_HEAD"
    assert registry["resulting_commit_binding"]

    raw_entries = registry["entries"]
    assert isinstance(raw_entries, list)
    assert len(raw_entries) == len(EXPECTED) == 4
    entries = {entry["protected_id"]: entry for entry in raw_entries}
    assert set(entries) == set(EXPECTED)
    assert len({entry["old_protected_node_identity"] for entry in raw_entries}) == 4

    old_nodes = set()
    successor_nodes = set()
    for protected_id, expected in EXPECTED.items():
        entry = entries[protected_id]
        assert entry["old_protected_node_identity"] == expected["old"]
        assert entry["status"] == expected["status"]
        assert entry["successor_node_ids"] == expected["successors"]
        assert entry["old_node_presence"] == "ABSENT"
        assert not _node_exists(entry["old_protected_node_identity"])
        assert entry["successor_pass_required_before_retirement"] is True
        assert entry["retirement_or_supersession_reason"]
        assert entry["authority_source"]
        statuses = entry["successor_current_status"]
        assert set(statuses) == set(expected["successors"])
        assert all(status == "PASS" for status in statuses.values())
        assert all(_node_exists(node) for node in expected["successors"])
        old_nodes.add(entry["old_protected_node_identity"])
        successor_nodes.update(expected["successors"])

    # A successor cannot point back to a retired old node, and no successor
    # may itself be registered as another old node in this finite registry.
    assert not old_nodes & successor_nodes
    assert len(successor_nodes) == sum(len(item["successors"]) for item in EXPECTED.values())
