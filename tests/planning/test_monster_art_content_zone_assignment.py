"""Focused integrity tests for the F034 art/content-only assignment contract."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "planning" / "monster_art_content_zone_assignment_v1.json"


def load_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_assignment_integrity():
    contract = load_contract()
    assignments = contract["assignments"]
    ids = [row["monster_id"] for row in assignments]
    assert ids == [f"M{i:03d}" for i in range(1, 121)]
    assert len(ids) == 120
    assert len(set(ids)) == 120
    assert all(row["planning_zone"] in {f"Z{i}" for i in range(1, 11)} for row in assignments)
    assert all(row["evidence_class"] for row in assignments)
    assert all("owner_decision_required" in row for row in assignments)


def test_exact_owner_counts_and_delta():
    contract = load_contract()
    expected = {"Z1": 14, "Z2": 14, "Z3": 13, "Z4": 12, "Z5": 12, "Z6": 12, "Z7": 12, "Z8": 11, "Z9": 10, "Z10": 10}
    actual = {zone: sum(row["planning_zone"] == zone for row in contract["assignments"]) for zone in expected}
    assert actual == expected
    assert contract["zone_count_sum"] == 120
    assert contract["integrity"]["proposed_zone_counts"] == expected
    assert contract["source"]["art002_old_distribution_status"] == "SUPERSEDED_FOR_ART_CONTENT_PLANNING"


def test_authority_firewall_and_boundaries():
    contract = load_contract()
    boundary = contract["authority_boundary"]
    assert contract["scope"] == "ART_CONTENT_PLANNING_ONLY"
    assert boundary["gameplay_authority_changed"] is False
    assert boundary["combat_authority_changed"] is False
    assert boundary["runtime_mapping_changed"] is False
    assert boundary["art_content_count_used_for_combat"] is False
    assert boundary["exact_id_assignment_owner_approved"] is False
    assert boundary["exact_id_assignment_status"] == "PENDING_CONTENT_RECONCILIATION"
    assert boundary["boss_included_in_120_count"] is False
    assert boundary["lord_included_in_120_count"] is False
    assert contract["art003"]["may_use_exact_planning_assignment_for_batch_planning"] is True
    assert contract["art003"]["may_infer_gameplay_zone_from_count_or_assignment"] is False
    assert contract["art003"]["may_renumber_ids"] is False
    assert contract["art003"]["b01_asset_mutations"] == 0
    assert contract["integrity"]["no_unlabeled_assignments"] is True


def test_runtime_rows_and_ambiguous_packet():
    contract = load_contract()
    runtime = contract["runtime_monsters"]
    assert len(runtime) == 10
    assert all(row["planning_zone"] == row["runtime_zone"] for row in runtime)
    ambiguous = [row for row in contract["assignments"] if row["evidence_class"] == "AMBIGUOUS"]
    assert len(ambiguous) == 9
    assert len(contract["owner_decision_packet"]) == 9
    assert all(row["owner_decision_required"] for row in ambiguous)
    assert all(row["owner_decision_required"] is True for row in contract["owner_decision_packet"])


def test_deterministic_count_preserving_move_set():
    contract = load_contract()
    expected_moves = {
        "M064": ("Z6", "Z3"),
        "M073": ("Z7", "Z10"),
        "M086": ("Z8", "Z2"),
        "M088": ("Z8", "Z2"),
        "M094": ("Z8", "Z2"),
        "M099": ("Z9", "Z1"),
        "M102": ("Z9", "Z1"),
        "M104": ("Z9", "Z1"),
        "M109": ("Z9", "Z1"),
    }
    actual_moves = {
        row["monster_id"]: (row["art002_candidate_zone"], row["planning_zone"])
        for row in contract["assignments"]
        if row["art002_candidate_zone"] != row["planning_zone"]
    }
    assert actual_moves == expected_moves
    assert contract["count_preserving_swap_plan"]["hidden_cascade"] is False
    assert len(contract["count_preserving_swap_plan"]["moves"]) == 9


def test_boss_lord_and_rarity_exclusion():
    contract = load_contract()
    boundary = contract["authority_boundary"]
    assert boundary["f009_enabled"] is False
    assert boundary["rarity_used_for_zone_assignment"] is False
    assert boundary["boss_included_in_120_count"] is False
    assert boundary["lord_included_in_120_count"] is False
