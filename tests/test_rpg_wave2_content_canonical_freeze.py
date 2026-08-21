"""Deterministic contracts for the Wave 2 content canonical freeze."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNING = ROOT / "docs" / "planning"


def _load(name):
    return json.loads((PLANNING / name).read_text(encoding="utf-8"))


def _asset(path):
    return ROOT.joinpath(*path.lstrip("/").split("/"))


def test_canonical_non_equipment_items_are_exactly_24_and_asset_closed():
    manifest = _load("go_odyssey_wave2_item_inventory.json")
    audit = _load("go_odyssey_wave2_legacy_reference_audit.json")
    ids = [record["item_id"] for record in manifest["records"]]

    assert manifest["canonical_registry_record_count"] == 24
    assert manifest["record_count"] == 24
    assert len(ids) == 24
    assert len(set(ids)) == 24
    assert audit["legacy_key"] not in ids
    assert manifest["unknown_canonical_item_ids"] == []
    assert manifest["taxonomy_counts"] == {"CONSUMABLE": 22, "MATERIAL": 2}
    assert manifest["item_asset_closure"] == {
        "expected": 24,
        "present": 24,
        "status": "24_OF_24",
    }

    for record in manifest["records"]:
        assert record["status"] == "READY"
        assert record["current_asset"]
        asset = _asset(record["current_asset"])
        assert asset.is_file(), record["item_id"]
        assert asset.suffix[1:].upper() == record["asset_format"]


def test_legacy_key_is_fail_closed_and_excluded_from_new_canonical_surfaces():
    audit = _load("go_odyssey_wave2_legacy_reference_audit.json")
    legacy_key = audit["legacy_key"]

    assert audit["canonical_wave2"] is False
    assert audit["status"] == "LEGACY_REJECTED"
    assert audit["fail_closed"] is True
    assert audit["legacy_runtime_reference_count"] == 8
    assert audit["legacy_reference_only_count"] == 4
    assert audit["baseline_exact_token_hit_count"] == 18
    assert audit["canonical_references_after_freeze"] == 0
    assert audit["new_reward_contract"] == "NONE_CREATED"
    assert audit["new_monetization_catalog"] == "NONE_CREATED"
    assert {entry["kind"] for entry in audit["references"]} == {
        "LEGACY_RUNTIME_REFERENCE",
        "LEGACY_REFERENCE_ONLY",
    }

    token_pattern = re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(legacy_key)}(?![A-Za-z0-9_])"
    )
    for surface in audit["forbidden_new_surfaces"]:
        text = (ROOT / surface["path"]).read_text(encoding="utf-8")
        assert not token_pattern.search(text), surface["path"]


def test_effect_bearing_appearances_are_explicitly_quarantined():
    cosmetics = _load("go_odyssey_wave2_cosmetic_inventory.json")
    quarantine = _load(
        "go_odyssey_wave2_effect_bearing_appearance_quarantine.json"
    )
    by_id = {record["cosmetic_id"]: record for record in cosmetics["records"]}

    assert cosmetics["effect_bearing_appearance_count"] == 20
    assert quarantine["effect_bearing_appearance_count"] == 20
    assert quarantine["monetizable_effect_bearing_count"] == 0
    assert len(quarantine["records"]) == 20

    for entry in quarantine["records"]:
        record = by_id[entry["appearance_id"]]
        assert record["canonical_category"] == (
            "EFFECT_BEARING_APPEARANCE_QUARANTINED"
        )
        assert entry["current_legacy_effect"] == record["non_combat_effects"]
        assert entry["functional_power"] == "NO"
        assert entry["cosmetic_monetization"] == "NO"
        assert entry["monetization_allowed"] == "NO"
        assert entry["separation_required"] is True
        assert record["monetization_allowed"] == "NO"
        assert record["monetization_eligible_in_principle"] == "NO"


def test_pure_presentation_and_stone_board_taxonomy_is_frozen():
    cosmetics = _load("go_odyssey_wave2_cosmetic_inventory.json")
    pure = [
        record
        for record in cosmetics["records"]
        if record["canonical_category"] == "PURE_PRESENTATION"
        and not record["cosmetic_id"].startswith(("stone.", "board."))
    ]
    skins = [
        record
        for record in cosmetics["records"]
        if record["cosmetic_id"].startswith(("stone.", "board."))
    ]

    assert len(pure) == 44
    assert cosmetics["pure_presentation_cosmetic_count"] == 44
    assert len(skins) == 10
    assert cosmetics["stone_board_skin_count"] == 10
    assert cosmetics["stone_board_functional_effect_count"] == 0

    for record in pure:
        assert record["functional_power"] == "NO"
        assert record["non_combat_effects"] == {}
        assert record["monetization_allowed"] == "YES"
        assert record["selection_authority"] == "presentation-only"

    assert {record["slot"] for record in skins} == {"stone", "board"}
    for record in skins:
        assert record["canonical_id"] == record["cosmetic_id"]
        assert record["canonical_category"] == "PURE_PRESENTATION"
        assert record["functional_power"] == "NO"
        assert record["selection_authority"] == "presentation-only"
        assert record["ownership_authority"].startswith(
            "server-authoritative cosmetic ownership"
        )
        assert record["non_combat_effects"] == {}
        assert record["asset_closure"] == "COMPLETE"
        assert record["asset_paths"]
        for asset_path in record["asset_paths"]:
            assert _asset(asset_path).is_file(), record["cosmetic_id"]


def test_commerce_eligibility_is_separate_from_current_commerce():
    cosmetics = _load("go_odyssey_wave2_cosmetic_inventory.json")
    monetization = cosmetics["monetization"]
    products = monetization["current_commerce_products"]

    assert monetization["current_commerce_product_count"] == 3
    assert monetization["monetization_eligible_in_principle_count"] == 54
    assert monetization["monetizable_effect_bearing_count"] == 0
    assert monetization["pay_to_win_product_count"] == 0
    assert monetization["no_launch_pricing_hardcoded"] is True
    assert all("price" not in product for product in products)
    premium = next(
        product
        for product in products
        if product["cosmetic_id"] == "robe_premium"
    )
    assert premium["current_commerce_product"] == "YES"
    assert premium["monetization_eligible_in_principle"] == "NO"
    assert premium["monetization_allowed"] == "NO"


def test_authority_boundaries_and_collection_runtime_remain_frozen():
    items = _load("go_odyssey_wave2_item_inventory.json")
    cosmetics = _load("go_odyssey_wave2_cosmetic_inventory.json")
    collections = _load("go_odyssey_wave2_collection_contract.json")

    assert items["canonicalization"]["functional_equipment_authority"] == (
        "player_inventory + server EQUIPMENT_DEFS"
    )
    assert items["canonicalization"]["client_combat_authority"] == "NO"
    assert items["authority_invariants"]["functional_equipment_taxonomy_conflicts"] == 0
    assert cosmetics["direct_combat_power_audit"]["cosmetics_grant_combat_power"] == "NO"
    assert cosmetics["direct_combat_power_audit"]["client_combat_authority"] == "NO"

    assert collections["collection_runtime_implementation"] == "NO"
    assert collections["collection_discovery_db"] == "NO"
    assert collections["collection_writer"] == "NO"
    assert collections["collection_authority"] == "WAVE3_DEFERRED"
    assert collections["authority_invariants"]["generic_discovery_writer"] is False
