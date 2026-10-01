"""Focused contracts for the finalized G009 Derived84 runtime consume."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from derived84_asset_registry import (
    DERIVED84_RUNTIME_AVAILABLE,
    derived84_companion_asset,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MANIFEST = ROOT / "assets/world-map-identity/runtime_manifest.json"
COMPANION_MANIFEST = ROOT / "assets/3d_shop/p048/companion/formal_18/mapping_manifest.json"
OWNER_DECISION_SHA256 = "3d2bbcc6f8cda56a83c5f819cbde62db9fdfe8852e6f6be2ae6c3a505bd53d64"
OLD_STARPATH_HASHES = {
    "0ab3dd577dc2f5c42010c72f99b3e14d8344712fd30d324080e0b4b4a1f3fc69",
    "3fa2edac2f3995dda9f40e815b65aef0a506799e4b02dd577c1927489d94a22c",
    "a9e98a34150d6bbcc6d5209c2bb00dc2ebeb5524d1ad83a18a78f59bcac10390",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_runtime_manifest_is_exactly_84_owner_accepted_rows():
    manifest = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["authority"]["owner_decision_record_sha256"] == OWNER_DECISION_SHA256
    assert manifest["derived_84_asset_visual_authority"] == "LOCKED"
    assert manifest["owner_acceptance_complete"] is True
    assert manifest["runtime_consumed"] is True
    assert manifest["derived_84_total"] == 84
    assert manifest["owner_accepted_authority_rows"] == 84
    assert manifest["counts"] == {"avatar": 33, "standing": 33, "companion_stage": 18}

    entries = manifest["entries"]
    assert len(entries) == 84
    identities = set()
    for entry in entries:
        assert entry["owner_decision"] == "PASS"
        assert "assets-candidate/" not in entry["target_runtime_path"]
        target = ROOT / Path(*entry["target_runtime_path"].split("/"))
        assert target.is_file()
        assert _sha256(target) == entry["expected_runtime_sha256"]
        if entry["asset_role"] in {"AVATAR", "STANDING"}:
            identity = (entry["asset_role"], entry["visual_model_id"])
        else:
            identity = (entry["asset_role"], entry["pet_key"], entry["stage"])
        assert identity not in identities
        identities.add(identity)
    assert len(identities) == 84


def test_companion_runtime_registry_uses_server_pet_key_and_stage():
    assert DERIVED84_RUNTIME_AVAILABLE is True
    for pet_key in (
        "ink_drop_kelpie",
        "whispering_void_kit",
        "star_shell_hatchling",
        "starpath_antlerling",
        "fatty",
        "obsidian_bastion",
    ):
        for stage, suffix in ((1, "stage1.png"), (2, "stage2.png"), (3, "stage3.png")):
            path = derived84_companion_asset(pet_key, stage)
            assert path == f"/assets/world-map-identity/companion/pet_{pet_key}_{suffix}"


def test_corrected_starpath_glb_authority_is_selected_and_old_bytes_are_absent():
    manifest = json.loads(COMPANION_MANIFEST.read_text(encoding="utf-8"))
    rows = [row for row in manifest["mappings"] if row["pet_key"] == "starpath_antlerling"]
    assert len(rows) == 3
    expected = {
        "I": ("019cb8591a72d07a05815a21f6baa6f81bb25eac4fa4b3d402d50d150390ac0b", 17945412),
        "II": ("fcf74157606886a5e4635cd908b4f603cf3c8a602db4a9f67034691757b378b7", 18144272),
        "III": ("a7608ca9bca793509a9946ba2711ce132f3d587cf7edce9f81e1308236e0a4b7", 19323560),
    }
    for row in rows:
        assert (row["stage"], (row["asset_sha256"].lower(), row["asset_bytes"])) in {
            (stage, values) for stage, values in expected.items()
        }
        assert row["asset_sha256"].lower() not in OLD_STARPATH_HASHES
        target = ROOT / Path(*row["runtime_glb"].split("/"))
        assert _sha256(target) == row["asset_sha256"].lower()
