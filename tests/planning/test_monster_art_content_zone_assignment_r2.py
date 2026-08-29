"""Focused tests for the F034-R2 Z9-to-Z1 owner decision packet."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKET_PATH = ROOT / "docs" / "planning" / "monster_art_content_zone_assignment_r2_z9_to_z1_owner_decision_packet.json"


def load_packet():
    return json.loads(PACKET_PATH.read_text(encoding="utf-8"))


def test_candidate_identity_and_source_zone():
    packet = load_packet()
    candidates = packet["z9_to_z1_eligible_candidates"]
    assert len(candidates) == 9
    assert [row["rank"] for row in candidates] == list(range(1, 10))
    assert all(row["id"] and row["name"] and row["concept"] for row in candidates)
    assert all(row["current_zone"] == "Z9" and row["target_zone"] == "Z1" for row in candidates)
    assert len({row["id"] for row in candidates}) == len(candidates)


def test_exclusions_and_locked_moves():
    packet = load_packet()
    candidate_ids = {row["id"] for row in packet["z9_to_z1_eligible_candidates"]}
    assert not candidate_ids.intersection({"M064", "M086", "M099", "M102", "M104", "M109", "M098"})
    assert [(row["id"], row["from"], row["to"]) for row in packet["owner_approved_locked_moves"]] == [
        ("M073", "Z7", "Z10"),
        ("M088", "Z8", "Z2"),
        ("M094", "Z8", "Z2"),
        ("M060", "Z6", "Z3"),
        ("M091", "Z8", "Z2"),
    ]
    assert packet["protected_exclusions"]["do_not_repropose"] == [
        "M064", "M086", "M099", "M102", "M104", "M109"
    ]


def test_recommendation_and_alternates():
    packet = load_packet()
    candidates = {row["id"] for row in packet["z9_to_z1_eligible_candidates"]}
    recommended = packet["z9_to_z1_recommended_four"]
    assert recommended == ["M107", "M106", "M100", "M105"]
    assert len(recommended) == 4
    assert len(set(recommended)) == 4
    assert set(recommended).issubset(candidates)
    assert packet["first_alternate"] == "M110"
    assert packet["second_alternate"] == "M111"
    assert packet["decision_state"]["r1_recommendation_reevaluated"] is True
    assert packet["decision_state"]["new_owner_approved_z9_to_z1"] == 0
    assert packet["decision_state"]["exact_assignment_freeze"] is False
    assert packet["decision_state"]["f035_started"] is False


def test_projected_count_contract():
    packet = load_packet()
    projection = packet["projected_count_contract"]
    assert projection["approved_moves_plus_recommended_z9_to_z1"] == {
        "Z1": 14, "Z2": 14, "Z3": 13, "Z4": 12, "Z5": 12,
        "Z6": 12, "Z7": 12, "Z8": 11, "Z9": 10, "Z10": 10,
    }
    assert projection["projected_total"] == 120
    assert projection["count_contract_preserved"] is True


def test_authority_firewall():
    packet = load_packet()
    boundary = packet["authority_firewall"]
    assert packet["scope"] == "ART_CONTENT_PLANNING_ONLY"
    for key in (
        "gameplay_authority_changed",
        "runtime_mapping_changed",
        "monster_stats_changed",
        "art_assets_changed",
        "app_py_changed",
        "a043_scope_touched",
        "b057_scope_touched",
        "c050_scope_touched",
        "e046_scope_touched",
        "art003_scope_touched",
        "lc015_scope_touched",
    ):
        assert boundary[key] is False
    assert boundary["art_content_planning_only"] is True
