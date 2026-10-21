"""Bind the four selected Formal9 GLBs to the isolated package candidate."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = ROOT / "provenance/g009_formal9_rights_cleared_v1"
PACK = ROOT / "deploy/g009-formal9-replacement-static-pack-manifest.json"
ROLLBACK = ROOT / "deploy/g009-formal9-replacement-asset-rollback-inventory.json"
SOURCE_COMMIT = "2c0ae67fb5b1761c62e82df55a02e73dbb3879a6"
PREFIX = "assets/3d_shop/formal9_rights_cleared_v1/weapons/"
EXPECTED = {
    "iron_sword": (
        "WEAPON_C43E15596CA6",
        "c43e15596ca656355553585e3ac4a398b37a0216471539e8dda6401d67b7580b",
    ),
    "fox_fang": (
        "WEAPON_6F06505A7BED",
        "6f06505a7bed0ea7681216df58d2a89696b2305f9c080b5f0fa4d9fcabc72af0",
    ),
    "riverstone_sabre": (
        "WEAPON_EC86CE30E759",
        "ec86ce30e7591bc89badac98a4ed0c00b6614ac8e97b8b79ea734ba7f82c2409",
    ),
    "bamboo_shadow_blade": (
        "WEAPON_C84A8635BED2",
        "c84a8635bed2d2252a6937dbd8837c585872502a4253f549a7b94069e7b776c6",
    ),
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_static_pack_matches_selected_authority_and_actual_glb_bytes():
    authority = read_json(PROVENANCE / "final_asset_manifest.json")
    pack = read_json(PACK)
    owner_receipt = PROVENANCE / "owner_selection_receipt.json"
    assert hashlib.sha256(owner_receipt.read_bytes()).hexdigest() == pack["owner_receipt_sha256"]
    assert pack["source_commit"] == SOURCE_COMMIT
    assert pack["prefix"] == PREFIX
    assert pack["total_files"] == len(EXPECTED) == 4
    assert pack["product_release_admission"] is False
    assert pack["production_asset_admission"] is False
    assert pack["public_3d_preview_admission"] is True

    source_by_path = {entry["FINAL_GLB"]: entry for entry in authority["assets"]}
    pack_by_path = {entry["path"]: entry for entry in pack["files"]}
    assert len(source_by_path) == len(pack_by_path) == 4
    assert set(pack_by_path) == set(source_by_path)
    assert pack["total_bytes"] == sum(entry["size"] for entry in pack["files"])
    for relative_path, packaged in pack_by_path.items():
        source = source_by_path[relative_path]
        item_key = source["GAME_ITEM_KEY"]
        expected_id, expected_sha = EXPECTED[item_key]
        assert source["NEW_ASSET_ID"] == expected_id
        assert source["FINAL_GLB_SHA256"] == packaged["sha256"] == expected_sha
        assert source["FINAL_GLB_BYTES"] == packaged["size"]
        assert source["OWNER_SELECTED"] == "YES"
        assert source["RIGHTS_STATUS"] == "RIGHTS_CLEARED"
        for policy in ("SHOP_ENABLED", "PURCHASE_ENABLED", "DROP_ENABLED", "PLAYER_SELECTABLE",
                       "RELEASE_ENABLED", "PRODUCTION_ASSET_ADMISSION"):
            assert source["product_policy"][policy] is False
        assert packaged["source_commit"] == SOURCE_COMMIT
        assert packaged["mime"] == "model/gltf-binary"
        assert relative_path.startswith(PREFIX) and relative_path.endswith(".glb")
        actual = (ROOT / relative_path).read_bytes()
        assert len(actual) == packaged["size"]
        assert hashlib.sha256(actual).hexdigest() == expected_sha


def test_static_inventory_stages_only_new_paths_without_duplicate_ownership():
    inventory = read_json(ROOT / "deploy/live-static-asset-inventory.json")
    entries = inventory["required_subtrees"]["entries"]
    selected = [entry for entry in entries if entry["prefix"] == PREFIX]
    assert len(selected) == 1
    assert selected[0]["manifest"] == "deploy/g009-formal9-replacement-static-pack-manifest.json"

    owners: dict[str, str] = {}
    for declaration in entries:
        manifest = read_json(ROOT / declaration["manifest"])
        for record in manifest["files"]:
            assert record["path"] not in owners, record["path"]
            owners[record["path"]] = declaration["manifest"]
    assert {path for path in owners if path.startswith(PREFIX)} == {
        entry["path"] for entry in read_json(PACK)["files"]
    }
    assert all("provenance/" not in path and not path.endswith(".zip") for path in owners)


def test_docker_build_and_service_worker_exclude_retired_bytes():
    authority = read_json(PROVENANCE / "final_asset_manifest.json")
    retired = read_json(PROVENANCE / "old_asset_retirement_map.json")["retired"]
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    build = read_json(ROOT / "deploy/build-manifest.json")
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    tracked = set(build["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    verified = set(build["post_build_verification_files"])
    copies = {
        line.strip() for line in dockerfile.splitlines()
        if line.startswith("COPY " + PREFIX)
    }
    new_paths = {entry["FINAL_GLB"] for entry in authority["assets"]}
    assert copies == {f"COPY {item} ./{item}" for item in new_paths}
    assert new_paths <= tracked
    assert {"/app/" + item for item in new_paths} <= verified
    assert "COPY provenance/" not in dockerfile
    for entry in retired:
        old_path = entry["old_runtime_asset"]
        assert old_path not in {item["path"] for item in read_json(PACK)["files"]}
        assert f"COPY {old_path}" not in dockerfile
        assert old_path not in tracked
        assert "/app/" + old_path not in verified
        assert old_path not in sw and entry["old_asset_id"] not in sw
    for new_path in new_paths:
        assert new_path not in sw  # No stale or unversioned GLB precache.


def test_formal9_runtime_dependency_closure_is_packaged():
    runtime_paths = {
        "g009_d007_runtime_asset_mapping.py",
        "js/formal_3d_character_equipment_runtime.js",
        "js/player_character_3d_runtime_bridge.js",
        "js/player_appearance_3d_attachment_adapter.js",
        "js/g009_d007_runtime_identity_resolver.mjs",
        "js/g009_formal9_rights_cleared_replacement_catalog.js",
        "js/g009_owner_approved_formal_equipment_mapping.js",
        "js/g009_d_r2_shared_host_bootstrap.js",
        "js/g009_equipment_inventory_projection.js",
        "js/hero_equipment_attachment_adapter.js",
        "js/g009_d007_shared_host_bootstrap.js",
        "js/g009_d007_shared_host_adapter.js",
        "js/g009_shared_hero_attachment_host.js",
        "schemas/g009_d007_runtime_prerequisite_v1.json",
        "schemas/g009_formal9_rights_cleared_replacement_v1.json",
        "assets/3d_shop/p048/runtime_manifest.json",
    }
    prerequisite = read_json(ROOT / "schemas/g009_d007_runtime_prerequisite_v1.json")
    retired_paths = {entry["old_runtime_asset"].lstrip("/") for entry in
                     read_json(PROVENANCE / "old_asset_retirement_map.json")["retired"]}
    head_back = {url.lstrip("/") for slot in ("HEAD", "BACK")
                 for url in prerequisite["appearance_catalog"]["slots"][slot].values()}
    admitted_preview = {entry["runtime_asset"].lstrip("/") for entry in
                        prerequisite["equipment_catalog"]["items"]
                        if entry["runtime_asset"].lstrip("/") not in retired_paths}
    assert len(head_back) == 6
    assert len(admitted_preview) == 8
    runtime_paths |= head_back | admitted_preview
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    copy_sources = {
        source
        for line in dockerfile.replace("\\\n", " ").splitlines()
        if line.startswith("COPY ")
        for source in line.split()[1:-1]
    }
    build = read_json(ROOT / "deploy/build-manifest.json")
    tracked = set(build["build_inputs"]["tracked_in_canonical_branch_this_sprint"])
    verified = set(build["post_build_verification_files"])
    def copied(path: str) -> bool:
        return any(source == path or (source.endswith("/") and path.startswith(source))
                   for source in copy_sources)

    assert all(copied(path) for path in runtime_paths)
    assert runtime_paths <= tracked
    assert {"/app/" + path for path in runtime_paths} <= verified
    assert all((ROOT / path).is_file() for path in runtime_paths)
    assert not retired_paths & copy_sources
    assert not retired_paths & tracked
    assert not {"/app/" + path for path in retired_paths} & verified
    assert hashlib.sha256((ROOT / "js/player_character_3d_runtime_bridge.js").read_bytes()).hexdigest() == (
        "1cbaef3439e52933cca7d6504515ed0889a88745a30faa6b85d367a115e58094"
    )


def test_rollback_inventory_never_restores_uncleared_payloads():
    retired = read_json(PROVENANCE / "old_asset_retirement_map.json")["retired"]
    rollback = read_json(ROLLBACK)
    assert rollback["rollback_scope"] == "UNRELEASED_CANDIDATE_ASSET_SET"
    assert rollback["prior_safe_release_binding"] == "NOT_BOUND_TO_PRODUCTION_RELEASE"
    assert rollback["production_image_rollback_verified"] is False
    assert len(rollback["replacements"]) == 4
    by_item = {record["logical_item_key"]: record for record in rollback["replacements"]}
    assert set(by_item) == set(EXPECTED)
    for old in retired:
        record = by_item[old["former_formal9_item"]]
        assert record["retired_asset_id"] == old["old_asset_id"]
        assert record["retired_path"] == old["old_runtime_asset"]
        assert record["retired_sha256"] == old["old_runtime_sha256"]
        assert record["replacement_asset_id"] == old["replaced_by_asset_id"]
        assert record["replacement_sha256"] == old["replaced_by_sha256"]
        assert record["retired_release_admission"] is False
        assert old["alias_to_new_bytes"] is False
        assert old["active_mapping"] is False
        assert old["runtime_reachable"] is False
        assert old["release_included"] is False
