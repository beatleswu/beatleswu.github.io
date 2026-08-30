"""Focused tests for the F035 owner-approved exact planning assignment."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "docs" / "planning" / "monster_art_content_zone_assignment_v1.json"


def load_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_final_assignment_integrity_and_counts():
    contract = load_contract()
    assignments = contract["assignments"]
    ids = [row["monster_id"] for row in assignments]
    assert ids == [f"M{i:03d}" for i in range(1, 121)]
    assert len(ids) == 120
    assert len(set(ids)) == 120
    assert all(row["final_planning_zone"] in {f"Z{i}" for i in range(1, 11)} for row in assignments)
    assert all(row["scope"] == "ART_CONTENT_PLANNING_ONLY" for row in assignments)
    expected = {
        "Z1": 14, "Z2": 14, "Z3": 13, "Z4": 12, "Z5": 12,
        "Z6": 12, "Z7": 12, "Z8": 11, "Z9": 10, "Z10": 10,
    }
    actual = {
        zone: sum(row["final_planning_zone"] == zone for row in assignments)
        for zone in expected
    }
    assert actual == expected
    assert contract["total"] == 120
    assert contract["validation"]["unassigned_m_id_count"] == 0
    assert contract["validation"]["duplicate_assignment_count"] == 0


def test_exact_owner_approved_moves():
    contract = load_contract()
    rows = {row["monster_id"]: row for row in contract["assignments"]}
    expected = {
        "M060": ("Z6", "Z3", "OWNER_APPROVED_F034_R1"),
        "M073": ("Z7", "Z10", "OWNER_APPROVED_F034_R1"),
        "M088": ("Z8", "Z2", "OWNER_APPROVED_F034_R1"),
        "M094": ("Z8", "Z2", "OWNER_APPROVED_F034_R1"),
        "M091": ("Z8", "Z2", "OWNER_APPROVED_F034_R1"),
        "M107": ("Z9", "Z1", "OWNER_APPROVED_F034_R2"),
        "M110": ("Z9", "Z1", "OWNER_APPROVED_F034_R2"),
        "M100": ("Z9", "Z1", "OWNER_APPROVED_F034_R2"),
        "M105": ("Z9", "Z1", "OWNER_APPROVED_F034_R2"),
    }
    assert len(contract["owner_approved_moves"]) == 9
    assert len(contract["owner_approved_moves"]) == len(expected)
    for monster_id, (original, final, source) in expected.items():
        row = rows[monster_id]
        assert row["original_art002_zone"] == original
        assert row["final_planning_zone"] == final
        assert row["owner_move_status"] == "OWNER_APPROVED_MOVE"
        assert row["decision_source"] == source


def test_rejected_and_unselected_moves_are_locked():
    contract = load_contract()
    rows = {row["monster_id"]: row for row in contract["assignments"]}
    rejected = {
        "M064": "Z6",
        "M086": "Z8",
        "M099": "Z9",
        "M102": "Z9",
        "M104": "Z9",
        "M109": "Z9",
        "M106": "Z9",
    }
    assert len(contract["owner_rejected_retained"]) == 7
    for monster_id, zone in rejected.items():
        row = rows[monster_id]
        assert row["original_art002_zone"] == zone
        assert row["final_planning_zone"] == zone
        assert row["owner_move_status"] == "OWNER_REJECTED_RETAINED"
    for monster_id in ("M111", "M103", "M108", "M101"):
        assert rows[monster_id]["final_planning_zone"] == "Z9"
    assert contract["unselected_r2_candidates_moved"] is False


def test_runtime_anchors_and_authority_boundary():
    contract = load_contract()
    rows = {row["monster_id"]: row for row in contract["assignments"]}
    assert contract["runtime_anchor_count"] == 10
    assert contract["runtime_anchor_planning_divergence"] == 0
    assert all(
        rows[row["monster_id"]]["final_planning_zone"] == row["runtime_zone"]
        for row in contract["runtime_anchors"]
    )
    assert contract["owner_approved_exact_assignment"] is True
    assert contract["exact_m_id_zone_assignment_status"] == (
        "OWNER_APPROVED_CANONICAL_ART_CONTENT_PLANNING"
    )
    assert contract["gameplay_authority"] is False
    assert contract["runtime_zone_authority"] is False
    assert contract["art_content_count_used_for_combat"] is False
    assert contract["f009_enabled"] is False
    assert contract["rarity_used_for_zone_assignment"] is False
    assert contract["boss_included_in_120_count"] is False
    assert contract["lord_included_in_120_count"] is False


def test_lineage_art003_and_change_firewall():
    contract = load_contract()
    assert contract["validation"]["owner_decision_trace_count"] == 9
    assert contract["validation"]["owner_rejected_decision_trace_count"] == 7
    assert contract["history"]["decision_lineage_documented"] is True
    assert contract["art003"]["may_use_exact_assignment_for_planning"] is True
    assert contract["art003"]["may_use_for_gameplay_mapping"] is False
    assert contract["art003"]["art_assets_changed"] is False
    boundary = contract["change_boundary"]
    for key in (
        "app_py_changed",
        "runtime_source_changed",
        "runtime_mapping_changed",
        "monster_stats_changed",
        "combat_profile_mapping_changed",
        "art_assets_changed",
        "schema_changed",
        "migration_changed",
        "e047_scope_touched",
        "b058_scope_touched",
        "f035_included_in_b058",
        "a044_scope_touched",
        "lc015_scope_touched",
        "art003_asset_scope_touched",
    ):
        assert boundary[key] is False

