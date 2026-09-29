import hashlib
import json
from pathlib import Path

from g009_d007_runtime_asset_mapping import (
    ADMITTED_ASSET_IDS,
    RETIRED_FORMAL9_ASSET_IDS,
    load_g009_runtime_mapping,
    resolve_current_server_item_id,
    resolve_g009_runtime_asset,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "g009_d007_runtime_prerequisite_v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_owner_admission_is_exactly_12_and_does_not_clear_asset_evidence():
    manifest = load_g009_runtime_mapping(SCHEMA_PATH)
    admission = manifest["owner_admission"]
    rows = manifest["equipment_catalog"]["items"]
    assert admission["status"] == "APPROVED_FOR_CURRENT_G009_CANDIDATE"
    assert admission["evidence_verification"] == "RETAINS_PRIOR_AUDIT_STATUS"
    assert set(admission["admitted_asset_ids"]) == ADMITTED_ASSET_IDS
    assert {row["asset_id"] for row in rows} == ADMITTED_ASSET_IDS
    assert len(rows) == 12
    assert all(row["release_eligibility"] == "NOT_CLEARED" for row in rows)
    assert all(row["equip_capability"] is False for row in rows)
    assert {
        "license_verified",
        "provenance_verified",
        "hash_lineage_verified",
        "CC0_verified",
        "legal_clearance_verified",
        "production_release_approved",
    }.issubset(set(admission["does_not_mean"]))


def test_all_12_admitted_asset_identities_resolve_to_exact_runtime_bytes():
    manifest = load_g009_runtime_mapping(SCHEMA_PATH)
    rows = manifest["equipment_catalog"]["items"]
    assert len(RETIRED_FORMAL9_ASSET_IDS) == 4
    assert RETIRED_FORMAL9_ASSET_IDS <= ADMITTED_ASSET_IDS
    for row in rows:
        resolved = resolve_g009_runtime_asset(row["asset_id"], manifest=manifest)
        path = ROOT / row["runtime_asset"].lstrip("/")
        # Retired formal9 visuals keep their exact historical bytes but never
        # resolve, by asset ID or by D007 candidate item ID.
        assert path.is_file(), row["asset_id"]
        assert sha256(path) == row["runtime_sha256"], row["asset_id"]
        if row["asset_id"] in RETIRED_FORMAL9_ASSET_IDS:
            assert resolved is None, row["asset_id"]
            if row.get("server_item_id"):
                assert resolve_g009_runtime_asset(row["server_item_id"], manifest=manifest) is None
            continue
        assert resolved is not None
        assert resolved["asset_id"] == row["asset_id"]
        assert path.is_file(), row["asset_id"]
        assert sha256(path) == row["runtime_sha256"], row["asset_id"]


def test_item_identity_is_not_invented_for_small_stick_or_granted_by_admission():
    manifest = load_g009_runtime_mapping(SCHEMA_PATH)
    rows = manifest["equipment_catalog"]["items"]
    small_stick = next(row for row in rows if row["asset_id"] == "WEAPON_AF8287295872")
    assert small_stick["server_item_id"] is None
    assert small_stick["item_mapping_status"] == "UNRESOLVED_NO_CANONICAL_ITEM_ID"
    assert resolve_g009_runtime_asset(small_stick["asset_id"], manifest=manifest) is not None
    assert resolve_current_server_item_id("wooden_sword", manifest=manifest)["asset_id"] == (
        "WEAPON_628812E9B559"
    )
    assert resolve_current_server_item_id("elf_sword", manifest=manifest) is None
    assert resolve_g009_runtime_asset("unadmitted_future_asset", manifest=manifest) is None


def test_main_hand_and_off_hand_candidate_mapping_coexist_without_two_handed_or_pet():
    manifest = load_g009_runtime_mapping(SCHEMA_PATH)
    rows = manifest["equipment_catalog"]["items"]
    main_hand = [row for row in rows if row["slot"] == "MAIN_HAND"]
    off_hand = [row for row in rows if row["slot"] == "OFF_HAND"]
    assert len(main_hand) == 8
    assert len(off_hand) == 4
    assert {row["socket"] for row in main_hand} == {"hand.R"}
    assert {row["socket"] for row in off_hand} == {"hand.L"}
    assert all(row["presentation_class"] in {"ONE_HAND", "KNIFE_SMALL"} for row in main_hand)
    assert all(row["presentation_class"] == "SHIELD" for row in off_hand)
    assert manifest["equipment_catalog"]["two_handed_supported"] is False
    assert manifest["equipment_catalog"]["production_off_hand_flag"] is False
    assert "COMPANION" not in manifest["appearance_catalog"]
    assert manifest["excluded_capabilities"]["PET_COMPANION"] == (
        "EXCLUDED_UNRESOLVED_NODE_VALIDATION"
    )


def test_future30_roster_remains_30_logical_and_33_visual_models():
    path = ROOT / "schemas" / "future30_c005_real_asset_runtime_mapping_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    roster = manifest["roster"]
    visuals = manifest["visual_models"]
    assert manifest["counts"]["logical_character_count"] == 30
    assert manifest["counts"]["visual_model_count"] == 33
    assert len(roster) == 30
    assert len({row["character_id"] for row in roster}) == 30
    assert len(visuals) == 33
    roster_ids = {row["character_id"] for row in roster}
    for row in visuals:
        path = ROOT / row["runtime_glb"]
        assert row["character_id"] in roster_ids
        assert row["asset_status"] == "PRESENT"
        assert row["placeholder_mapping"] is False
        assert path.is_file(), row["visual_model_id"]
        assert sha256(path) == row["runtime_sha256"], row["visual_model_id"]
    blue = [row for row in visuals if row.get("variant") == "BLUE"]
    assert len(blue) == 3
    assert all(row["character_id"] in roster_ids for row in blue)


def test_browser_runtime_uses_candidate_manifest_and_rejects_client_asset_authority():
    runtime = (ROOT / "js" / "formal_3d_character_equipment_runtime.js").read_text(
        encoding="utf-8"
    )
    assert 'const FORMAL_MANIFEST_URL = "/schemas/g009_d007_runtime_prerequisite_v1.json";' in runtime
    assert "export function resolveFormalEquipmentIdentity" in runtime
    assert "resolveG009RuntimeEquipmentIdentity(this.equipmentIndex, normalized" in runtime
    assert "allowAssetId: this.previewOnly" in runtime
    assert "client asset identity cannot override the server equipment item" in runtime
    companion = runtime.split("async setCompanion", 1)[1].split("async swapCharacter", 1)[0]
    assert "Pet/Companion runtime excluded pending node-validation closure" in companion
    assert "loadGLTF" not in companion
