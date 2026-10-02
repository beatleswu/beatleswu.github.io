"""Narrow semantic successor and release-contract closure checks for G009 W1."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

F001_NODE = (
    "tests/test_future30_server_admission_and_formal_hero.py::"
    "test_formal_host_and_f009_contract_are_explicit_and_bounded"
)
F002_NODE = (
    "tests/test_future30_server_admission_and_formal_hero.py::"
    "test_authenticated_hero_passes_server_snapshot_to_formal_runtime"
)
F003_NODE = (
    "tests/test_future30_server_admission_and_formal_hero.py::"
    "test_appearance_read_model_declares_existing_wardrobe_ownership"
)
F004_NODE = (
    "tests/test_a036_equipment_effect_and_power_presentation_closure.py::"
    "test_go_stone_and_loadout_gate_are_closed_in_backpack_ui"
)


# INPUT_HEAD did not contain a formal F001-F004 registration file.  The
# existing exact nodes are therefore updated in place as semantic successors;
# this matrix is the single narrow validator, rather than a second registry.
SUCCESSOR_MATRIX = {
    "F001": {
        "old_node": F001_NODE,
        "successor_node": F001_NODE,
        "old_contract": "missing formal_3d_character_equipment_v1.json",
        "classification": "MISSING_REQUIRED_RELEASE_CONTRACT_ARTIFACT",
        "successor_contract": "formal 3D release contract schema and bounded authority checks",
        "retirement_reason": "old missing-artifact expectation replaced by materialized semantic contract",
        "authority_source": "C005 + D007 + Formal9 + formal runtime/appearance host",
        "status": "UPDATED_IN_PLACE_AS_SEMANTIC_SUCCESSOR",
    },
    "F002": {
        "old_node": F002_NODE,
        "successor_node": F002_NODE,
        "old_contract": "double-quoted fetch literal for /api/player/appearance",
        "classification": "STALE_LITERAL_EXPECTATION",
        "successor_contract": "authenticated appearance fetch and server identity handoff",
        "retirement_reason": "quote-style pin replaced by bounded source-semantic assertions",
        "authority_source": "server /api/player/appearance + player_appearance.character_key + D007 host",
        "status": "UPDATED_IN_PLACE_AS_SEMANTIC_SUCCESSOR",
    },
    "F003": {
        "old_node": F003_NODE,
        "successor_node": F003_NODE,
        "old_contract": "hard-coded 'owned': True projection",
        "classification": "STALE_LITERAL_EXPECTATION",
        "successor_contract": "entitlement/owned_ids-derived ownership projection",
        "retirement_reason": "fake ownership literal replaced by authoritative membership assertions",
        "authority_source": "player_character_entitlements + STARTER bootstrap + player_appearance",
        "status": "UPDATED_IN_PLACE_AS_SEMANTIC_SUCCESSOR",
    },
    "F004": {
        "old_node": F004_NODE,
        "successor_node": F004_NODE,
        "old_contract": "client FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED literal",
        "classification": "STALE_IMPLEMENTATION_SHAPE / TEST_CONTRACT_CLOSURE",
        "successor_contract": "server-owned capability, default-off, fail-closed equip contract",
        "retirement_reason": "client implementation-shape pin replaced by server capability assertions",
        "authority_source": "EQUIPMENT_CANONICAL_LOADOUT_ENABLED + /api/player/inventory/equip",
        "status": "UPDATED_IN_PLACE_AS_SEMANTIC_SUCCESSOR",
    },
}


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def load(relative: str) -> dict:
    return json.loads(read(relative))


def sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def _node_source(node: str) -> str:
    relative, function = node.split("::", 1)
    source = read(relative)
    assert re.search(rf"^def {re.escape(function)}\(", source, re.MULTILINE)
    return source


def test_successor_matrix_retains_exact_nodes_and_proves_in_place_semantic_successors():
    assert set(SUCCESSOR_MATRIX) == {"F001", "F002", "F003", "F004"}
    for entry in SUCCESSOR_MATRIX.values():
        assert entry["old_node"] == entry["successor_node"]
        assert entry["status"] == "UPDATED_IN_PLACE_AS_SEMANTIC_SUCCESSOR"
        source = _node_source(entry["successor_node"])
        assert "xfail" not in source.lower()
        assert "pytest.skip" not in source
        assert "deselect" not in source.lower()
        assert entry["successor_contract"]
        assert entry["authority_source"]


def test_formal3d_schema_is_valid_bound_and_fail_closed():
    schema = load("schemas/formal_3d_character_equipment_v1.json")
    c005 = load("schemas/future30_c005_real_asset_runtime_mapping_manifest.json")
    d007 = load("schemas/g009_d007_runtime_prerequisite_v1.json")
    formal9 = load("schemas/g009_formal9_rights_cleared_replacement_v1.json")

    assert schema["schema"] == "formal-3d-character-equipment-v1"
    assert schema["contract_version"] == "FORMAL_3D_CHARACTER_EQUIPMENT_V1"
    assert schema["version"] == 1
    assert schema["authority"]["server_character_identity"]["source"] == (
        "player_appearance.character_key"
    )
    assert schema["authority"]["server_character_identity"]["client_identity_authority"] is False
    assert schema["authority"]["player_appearance"]["selection_source"] == (
        "player_appearance.character_key"
    )
    assert schema["authority"]["future30"]["logical_character_count"] == 30
    assert schema["authority"]["future30"]["visual_model_count"] == 33
    assert schema["authority"]["future30"]["blue_variants_are_logical_characters"] is False
    assert c005["counts"]["logical_character_count"] == 30
    assert c005["counts"]["visual_model_count"] == 33
    assert schema["authority"]["equipment"]["mapping_source"].startswith(
        "/schemas/g009_d007_runtime_prerequisite_v1.json#"
    )
    assert d007["shared_preview_contract"]["mount_api"] == (
        "mountShared3DPreview(container, payload)"
    )
    assert schema["runtime_host"]["mount_api"] == (
        "mountShared3DPreview(container, payload)"
    )
    assert schema["runtime_host"]["server_identity_required"] is True
    assert schema["runtime_host"]["parallel_character_authority"] is False
    assert schema["socket_mount"]["MAIN_HAND"] == "hand.R"
    assert schema["socket_mount"]["OFF_HAND"] == "hand.L"
    assert schema["weapon_handling"]["two_handed"] == "UNSUPPORTED"
    assert schema["weapon_handling"]["polearm"] == "UNSUPPORTED"
    assert schema["authority"]["formal9"]["rights_status"] == formal9["rights"]["RIGHTS_STATUS"]
    assert schema["preview_semantics"] == {
        "preview_only": True,
        "mutates_ownership": False,
        "mutates_equipment": False,
        "mutates_player_state": False,
        "mutates_combat": False,
        "transaction_authority": False,
        "source_model_authority_is_production_release": False,
        "final_runtime_acceptance_is_source_completeness": False,
    }
    release = schema["release_admission"]
    assert release["fail_closed"] is True
    assert release["runtime_candidate_only"] is True
    assert release["release_eligibility"] == "NOT_CLEARED"
    for field in (
        "release_enabled",
        "shop_enabled",
        "player_selectable",
        "equip_enabled",
        "production_asset_admission",
    ):
        assert release[field] is False
    assert "acquisition_assignment" in schema["authority_scope"]["does_not_decide"]
    assert "product_enablement" in schema["authority_scope"]["does_not_decide"]
    assert "production_admission" in schema["authority_scope"]["does_not_decide"]
    assert "pricing" not in json.dumps(schema, sort_keys=True)
    assert "payment" not in json.dumps(schema, sort_keys=True)
    assert sha256("schemas/future30_c005_real_asset_runtime_mapping_manifest.json") == (
        schema["manifest_identity"]["future30_c005"]["sha256"]
    )
    assert sha256("schemas/g009_d007_runtime_prerequisite_v1.json") == (
        schema["manifest_identity"]["g009_d007"]["sha256"]
    )
    assert sha256("schemas/g009_formal9_rights_cleared_replacement_v1.json") == (
        schema["manifest_identity"]["formal9_replacement"]["sha256"]
    )


def test_f002_semantic_successor_preserves_server_identity_and_single_host():
    hero = read("hero.html")
    renderer = read("js/g008_future30_hero_renderer.js")
    host = read("js/g009_d007_shared_host_adapter.js")
    assert re.search(r"fetch\(\s*['\"]/api/player/appearance['\"]", hero)
    assert "const serverCharacter = appearance && appearance.character_key" in hero
    assert "_characterAuthorityKey = serverCharacter" in hero
    assert "_combatGear.character = serverCharacter" in hero
    assert "appearance.character_key_source !== \"player_appearance.character_key\"" in renderer
    assert "appearance.character_key_authority !== \"player_appearance.character_key\"" in renderer
    assert "runtime.character_key !== key" in renderer
    assert "renderServerSnapshot(snapshot)" in host
    assert 'authority: "player_appearance.character_key"' in host
    assert 'formal_item_mapping_created: false' in host
    assert 'fetch("/api/player/appearance"' not in hero


def test_f003_semantic_successor_uses_entitlements_and_preserves_starter_authority():
    app = read("app.py")
    service = read("future30_character_service.py")
    renderer = read("js/g008_future30_hero_renderer.js")
    catalog_start = app.index("@app.route('/api/player/character-catalog')")
    catalog_end = app.index("@app.route('/api/skills/character'", catalog_start)
    projection = app[catalog_start:catalog_end]
    assert "'owned': entitlement is not None" in projection
    assert "'acquisition_source': entitlement['acquisition_source'] if entitlement else None" in projection
    assert "'permanent': bool(entitlement)" in projection
    assert "'is_applied': entry['character_key'] == applied['character_key']" in projection
    assert "player_character_entitlements" in projection
    assert "STARTER_CHARACTER_KEYS = (\"A1\", \"R1\", \"R2\", \"R3\", \"S2\")" in service
    assert "DEFAULT_STARTER_KEY = \"A1\"" in service
    assert "source_reference=source_reference" in service
    assert "entry.owned !== true" in renderer
    assert "owned_ids" not in projection
    assert "'owned':          True" not in projection


def test_f004_semantic_successor_is_server_owned_default_off_and_read_only():
    app = read("app.py")
    inventory = read("inventory.html")
    assert "def _equipment_canonical_loadout_enabled():" in app
    assert "_env_flag_enabled(EQUIPMENT_CANONICAL_LOADOUT_FLAG, default=False)" in app
    equip_start = app.index("@app.route('/api/player/inventory/equip'")
    equip_end = app.index("@app.route", equip_start + 10)
    equip_route = app[equip_start:equip_end]
    assert "loadout_enabled = _equipment_canonical_loadout_enabled()" in equip_route
    assert "if not loadout_enabled:" in equip_route
    assert "return jsonify({'error': 'LOADOUT_DISABLED'}), 409" in equip_route
    assert "let functionalEquipmentLoadoutCapability = false;" in inventory
    assert "!!(me && me.equipment_loadout_enabled === true)" in inventory
    assert "FUNCTIONAL_EQUIPMENT_LOADOUT_ENABLED" not in inventory
    assert "CANONICAL_COIN_SHOP_PURCHASE_ENABLED" in app
    assert "functionalEquipmentLoadoutEnabled()" in inventory
    assert "action.disabled = blocked;" in inventory
    assert "/api/shop/purchase" not in inventory


def test_no_regression_surface_boundaries_remain_unchanged():
    nav = read("site-nav.js")
    hero = read("hero.html")
    shop = read("shop.html")
    service = read("future30_character_service.py")
    payment_policy = read("adventure_zone4_10_monster_reward_policy.py")

    assert 'data-g009-global-nav="7"' in nav
    assert 'data-g009-hero-nav="5"' in hero
    assert 'data-g009-shop-mode="browse-preview"' in shop
    assert 'data-purchase-enabled="false"' in shop
    assert "PAYMENT_ENABLEMENT: Final = False" in payment_policy
    assert '"source": "STARTER", "count": 5, "assignment_status": "UNASSIGNED"' in service
    assert 'STARTER_CHARACTER_KEYS = ("A1", "R1", "R2", "R3", "S2")' in service
    assert 'DEFAULT_STARTER_KEY = "A1"' in service
    assert '"source": "STAGE", "count": 10, "assignment_status": "UNASSIGNED"' in service
    assert '"source": "PREMIUM", "count": 5, "assignment_status": "UNASSIGNED"' in service
    assert '"source": "SHOP", "count": 10, "assignment_status": "UNASSIGNED"' in service
