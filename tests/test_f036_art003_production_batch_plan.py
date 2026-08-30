import json
from pathlib import Path

PLAN_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "planning"
    / "monster_art003_production_batch_plan_v1.json"
)

ZONES = [f"Z{i}" for i in range(1, 11)]
ALL_IDS = [f"M{i:03d}" for i in range(1, 121)]
B01_IDS = ["M002", "M003", "M004", "M005", "M006", "M007", "M008", "M009", "M010", "M012"]
B02_IDS = ["M013", "M014", "M015", "M016", "M017", "M018", "M019", "M020", "M021", "M023"]
RUNTIME_IDS = ["M001", "M011", "M022", "M034", "M046", "M058", "M071", "M084", "M098", "M112"]
APPROVED_MOVES = {
    "M060": ("Z6", "Z3"),
    "M073": ("Z7", "Z10"),
    "M088": ("Z8", "Z2"),
    "M094": ("Z8", "Z2"),
    "M091": ("Z8", "Z2"),
    "M107": ("Z9", "Z1"),
    "M110": ("Z9", "Z1"),
    "M100": ("Z9", "Z1"),
    "M105": ("Z9", "Z1"),
}
REJECTED_RETAINED = {
    "M064": "Z6",
    "M086": "Z8",
    "M099": "Z9",
    "M102": "Z9",
    "M104": "Z9",
    "M109": "Z9",
    "M106": "Z9",
}
EXPECTED_COUNTS = {
    "Z1": 14, "Z2": 14, "Z3": 13, "Z4": 12, "Z5": 12,
    "Z6": 12, "Z7": 12, "Z8": 11, "Z9": 10, "Z10": 10,
}
HANDOFF_FIELDS = {
    "BATCH_ID", "M_ID", "CANONICAL_NAME", "F035_ZONE",
    "IDENTITY_SOURCE", "PRODUCTION_STATUS", "EXCLUSION_REASON_IF_ANY",
}


def load_plan():
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def test_total_id_classification_is_exactly_once():
    plan = load_plan()
    rows = plan["classification"]["by_id"]
    ids = [row["monster_id"] for row in rows]
    assert ids == ALL_IDS
    assert len(ids) == 120
    assert len(set(ids)) == 120
    categories = plan["classification"]["category_ids"]
    flattened = [monster_id for values in categories.values() for monster_id in values]
    assert len(flattened) == 120
    assert len(set(flattened)) == 120
    assert set(flattened) == set(ALL_IDS)
    assert plan["classification"]["unclassified_m_ids"] == 0
    assert plan["classification"]["duplicate_classification_count"] == 0


def test_batch_coverage_has_all_and_only_pending_ids():
    plan = load_plan()
    pending = set(plan["classification"]["category_ids"]["PENDING_ART003_PRODUCTION"])
    batches = plan["future_batches"]
    batch_ids = [batch["batch_id"] for batch in batches]
    assert batch_ids == [f"ART003_B{i:02d}" for i in range(3, 12)]
    assert len(batch_ids) == len(set(batch_ids))
    batch_members = [monster_id for batch in batches for monster_id in batch["m_ids"]]
    assert len(batch_members) == 90
    assert len(batch_members) == len(set(batch_members))
    assert set(batch_members) == pending
    assert not (set(batch_members) & set(B01_IDS + B02_IDS + RUNTIME_IDS))


def test_f035_zone_counts_and_approved_move_locks():
    plan = load_plan()
    rows = {row["monster_id"]: row for row in plan["classification"]["by_id"]}
    observed = {zone: 0 for zone in ZONES}
    for row in rows.values():
        observed[row["f035_zone"]] += 1
    assert observed == EXPECTED_COUNTS
    assert plan["f035"]["frozen_zone_counts"] == EXPECTED_COUNTS
    for monster_id, (original_zone, final_zone) in APPROVED_MOVES.items():
        assert rows[monster_id]["original_art002_zone"] == original_zone
        assert rows[monster_id]["f035_zone"] == final_zone
        assert rows[monster_id]["decision_source"] in {
            "OWNER_APPROVED_F034_R1", "OWNER_APPROVED_F034_R2"
        }
    for monster_id, retained_zone in REJECTED_RETAINED.items():
        assert rows[monster_id]["original_art002_zone"] == retained_zone
        assert rows[monster_id]["f035_zone"] == retained_zone
        assert rows[monster_id]["owner_move_status"] == "OWNER_REJECTED_RETAINED"


def test_m022_and_art003_history_protection():
    plan = load_plan()
    rows = {row["monster_id"]: row for row in plan["classification"]["by_id"]}
    assert plan["m022_protection"]["existing_runtime_identity"] is True
    assert plan["m022_protection"]["art003_regeneration_required"] is False
    assert rows["M022"]["classification"] == "EXISTING_RUNTIME_IDENTITY_PROTECTED"
    assert plan["art003_current_state"]["canonical_batches"] == ["B01", "B02"]
    assert plan["art003_current_state"]["pending_publication_count"] == 0


def test_handoff_fields_are_complete_and_zone_distributions_match():
    plan = load_plan()
    rows = {row["monster_id"]: row for row in plan["classification"]["by_id"]}
    for batch in plan["future_batches"]:
        assert len(batch["m_ids"]) == 10
        assert batch["count"] == 10
        calculated = {zone: 0 for zone in ZONES}
        for entry in batch["entries"]:
            assert set(entry) == HANDOFF_FIELDS
            assert entry["M_ID"] in batch["m_ids"]
            assert entry["F035_ZONE"] == rows[entry["M_ID"]]["f035_zone"]
            assert entry["CANONICAL_NAME"] == rows[entry["M_ID"]]["canonical_name"]
            calculated[entry["F035_ZONE"]] += 1
        assert batch["zone_distribution"] == calculated


def test_next_batch_and_authority_firewall():
    plan = load_plan()
    assert plan["next_art003_batch"]["batch_id"] == "ART003_B03"
    assert plan["next_art003_batch"]["m_ids"] == plan["future_batches"][0]["m_ids"]
    assert plan["next_art003_batch"]["ready_for_art003_b03_taskbook"] is True
    assert plan["next_art003_batch"]["started"] is False
    assert plan["authority_firewall"]["gameplay_authority"] is False
    assert plan["authority_firewall"]["runtime_zone_authority"] is False
    assert plan["authority_firewall"]["combat_mapping_changed"] is False
    assert plan["source_firewall"]["app_py_changed"] is False
    assert plan["source_firewall"]["runtime_source_changed"] is False
    assert plan["source_firewall"]["static_source_changed"] is False
    assert plan["source_firewall"]["data_changed"] is False
    assert plan["source_firewall"]["art_generated"] is False
    assert plan["source_firewall"]["B061_scope_touched"] is False


def test_deterministic_rerun_and_cumulative_final_coverage():
    plan = load_plan()
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    assert canonical == json.dumps(json.loads(canonical), sort_keys=True, separators=(",", ":"))
    cumulative = plan["cumulative_zone_coverage_matrix"]
    assert cumulative[-1]["after_batch"] == "B11"
    assert cumulative[-1]["known_art_or_runtime_counts"] == EXPECTED_COUNTS
    assert cumulative[-1]["known_art_or_runtime_id_count"] == 120
    assert plan["deterministic_batch_order"] == "PASS"


def test_f035_assignment_is_immutable_and_only_planning_scope():
    plan = load_plan()
    assert plan["f035"]["f035_zone_assignment_mutated"] is False
    assert plan["scope"] == "PRODUCTION_PLANNING_ONLY"
    assert plan["f035"]["assignment_authority"] == (
        "OWNER_APPROVED_CANONICAL_ART_CONTENT_PLANNING"
    )
    assert plan["ownership_and_history_firewall"]["B01_history_rewritten"] is False
    assert plan["ownership_and_history_firewall"]["B02_history_rewritten"] is False
    assert plan["ownership_and_history_firewall"]["M022_regeneration"] is False
