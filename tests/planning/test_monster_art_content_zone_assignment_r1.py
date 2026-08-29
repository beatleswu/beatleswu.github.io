"""Focused tests for the F034-R1 replacement decision packet."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKET_PATH = ROOT / "docs" / "planning" / "monster_art_content_zone_assignment_r1_owner_decision_packet.json"


def load_packet():
    return json.loads(PACKET_PATH.read_text(encoding="utf-8"))


def test_candidate_pools_and_protected_ids():
    packet = load_packet()
    pools = packet["replacement_candidate_pools"]
    assert len(pools["Z6_TO_Z3"]) >= 3
    assert len(pools["Z8_TO_Z2"]) >= 3
    assert 6 <= len(pools["Z9_TO_Z1"]) <= 8

    rejected = set(packet["protected_exclusions"]["do_not_repropose"])
    all_candidates = {
        row["id"]
        for pool in pools.values()
        for row in pool
    }
    assert not (rejected & all_candidates)
    assert "M098" not in all_candidates
    assert "M101" not in all_candidates


def test_source_zones_and_target_zones():
    packet = load_packet()
    expected = {
        "Z6_TO_Z3": ("Z6", "Z3"),
        "Z8_TO_Z2": ("Z8", "Z2"),
        "Z9_TO_Z1": ("Z9", "Z1"),
    }
    for key, (source, target) in expected.items():
        for row in packet["replacement_candidate_pools"][key]:
            assert row["current"] == source
            assert row["target"] == target
            assert row["rank"] >= 1
            assert row["fit"]
            assert row["lost"]
            assert row["conflict"]


def test_owner_decision_and_approved_move_locks():
    packet = load_packet()
    assert packet["decision_state"]["total_new_replacement_candidates"] == 6
    assert packet["decision_state"]["new_owner_approved_replacements"] == 0
    assert packet["decision_state"]["exact_assignment_freeze"] is False
    assert packet["decision_state"]["f035_not_started"] is True
    assert [(x["id"], x["from"], x["to"]) for x in packet["owner_approved_existing_moves"]] == [
        ("M073", "Z7", "Z10"),
        ("M088", "Z8", "Z2"),
        ("M094", "Z8", "Z2"),
    ]


def test_owner_decision_groups_have_exact_selection_counts():
    packet = load_packet()
    groups = packet["owner_decision_groups"]
    assert [group["item_id"] for group in groups] == [
        "OD-MID-ZONE-R1-Z6Z3",
        "OD-MID-ZONE-R1-Z8Z2",
        "OD-MID-ZONE-R1-Z9Z1",
    ]
    assert [group["required_selections"] for group in groups] == [1, 1, 4]
    assert all(group["owner_decision_required"] for group in groups)
    assert groups[0]["recommended_ids"] == ["M060"]
    assert groups[1]["recommended_ids"] == ["M091"]
    assert groups[2]["recommended_ids"] == ["M107", "M100", "M106", "M105"]


def test_projected_count_contract():
    packet = load_packet()
    assert packet["projected_count_contract"]["projected_zone_counts"] == {
        "Z1": 14, "Z2": 14, "Z3": 13, "Z4": 12, "Z5": 12,
        "Z6": 12, "Z7": 12, "Z8": 11, "Z9": 10, "Z10": 10,
    }
    assert packet["projected_count_contract"]["projected_total"] == 120
    assert packet["projected_count_contract"]["count_contract_preserved"] is True


def test_authority_firewall():
    packet = load_packet()
    boundary = packet["authority_firewall"]
    assert packet["scope"] == "ART_CONTENT_PLANNING_ONLY"
    assert all(boundary[key] is False for key in (
        "gameplay_authority_changed",
        "runtime_mapping_changed",
        "monster_stats_changed",
        "art_assets_changed",
        "app_py_changed",
        "e046_scope_touched",
        "art003_scope_touched",
        "b057_scope_touched",
    ))
    assert boundary["art_content_planning_only"] is True
