"""Deterministic P048 runtime projection and asset-integrity checks.

The canonical P047 manifest stays metadata-only and default-OFF.  This
validator proves that the P048 runtime projection is a checked-in, byte-
preserving projection of that contract rather than a second authority.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_MANIFEST_PATH = ROOT / "assets" / "3d_shop" / "p048" / "runtime_manifest.json"
FOUNDATION_MANIFEST_PATH = ROOT / "docs" / "contracts" / "3d_shop_v1_p045_presentation_reference_manifest.json"

sys.path.insert(0, str(ROOT))

from shop_3d_presentation_foundation import (  # noqa: E402
    ManifestValidationError,
    manifest_external_sha256,
    validate_manifest,
    verify_external_admission_hash,
)


EXPECTED_FOUNDATION_SHA256 = "9739f2a8d477dd0ad45174a40e3a5112d8d43d13008483d1acd74aa871e306e7"
EXPECTED_PROMOTED_IDS = (
    "P045_H06_BEANIE",
    "P045_H06_TOP_HAT",
    "P045_H06_FROG_HAT",
    "P045_H06_SANTA_HAT",
    "P045_H06_SUNGLASSES",
    "P045_B02_BACKPACK",
    "P045_C01_BUNNY",
    "P045_C04_CORGI",
    "P045_V01_CONFETTI",
)
FORBIDDEN_KEYS = {
    "item_id",
    "universal_item_id",
    "shop_sku",
    "sku",
    "product_id",
    "equipment_id",
    "functional_item_id",
    "pet_id",
    "ownership_id",
    "owner_id",
    "commerce_id",
    "inventory_id",
    "order_id",
    "payment_id",
    "transaction_id",
    "price",
    "currency",
    "purchase_url",
    "manifest_sha256",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _collect_keys(value: Any, result: set[str] | None = None) -> set[str]:
    if result is None:
        result = set()
    if isinstance(value, dict):
        result.update(str(key) for key in value)
        for child in value.values():
            _collect_keys(child, result)
    elif isinstance(value, list):
        for child in value:
            _collect_keys(child, result)
    return result


def _resolve_asset(relative_path: str) -> Path:
    candidate = (ROOT / relative_path).resolve()
    if ROOT not in candidate.parents:
        raise AssertionError(f"runtime asset escapes repository root: {relative_path}")
    return candidate


def _entry(manifest: dict[str, Any], presentation_id: str) -> dict[str, Any]:
    return next(item for item in manifest["entries"] if item["presentation_id"] == presentation_id)


def _verify_entry_asset(entry: dict[str, Any], report: dict[str, Any]) -> None:
    asset_path = _resolve_asset(entry["runtime_asset"])
    if not asset_path.is_file():
        raise AssertionError(f"missing runtime asset: {entry['runtime_asset']}")
    actual = _sha256(asset_path)
    expected = entry["runtime_sha256"].upper()
    if actual != expected:
        raise AssertionError(f"runtime hash mismatch for {entry['presentation_id']}: {actual} != {expected}")
    report["asset_hashes"][entry["presentation_id"]] = {
        "path": entry["runtime_asset"],
        "sha256": actual,
        "bytes": asset_path.stat().st_size,
    }
    for index, texture_path in enumerate(entry.get("runtime_texture_assets", [])):
        texture = _resolve_asset(texture_path)
        if not texture.is_file():
            raise AssertionError(f"missing runtime texture: {texture_path}")
        texture_hash = _sha256(texture)
        expected_textures = entry.get("runtime_texture_sha256", [])
        expected_texture = expected_textures[index].upper()
        if texture_hash != expected_texture:
            raise AssertionError(f"runtime texture hash mismatch for {entry['presentation_id']}: {texture_hash} != {expected_texture}")
        report["asset_hashes"][f"{entry['presentation_id']}:texture:{index}"] = {
            "path": texture_path,
            "sha256": texture_hash,
            "bytes": texture.stat().st_size,
        }
    if "fallback_runtime_asset" in entry:
        fallback = _resolve_asset(entry["fallback_runtime_asset"])
        if not fallback.is_file():
            raise AssertionError(f"missing fallback runtime asset: {entry['fallback_runtime_asset']}")
        fallback_hash = _sha256(fallback)
        expected_fallback = entry["fallback_runtime_sha256"].upper()
        if fallback_hash != expected_fallback:
            raise AssertionError(f"fallback hash mismatch for {entry['presentation_id']}: {fallback_hash} != {expected_fallback}")
        report["asset_hashes"][f"{entry['presentation_id']}:fallback"] = {
            "path": entry["fallback_runtime_asset"],
            "sha256": fallback_hash,
            "bytes": fallback.stat().st_size,
        }


def validate_runtime_manifest() -> dict[str, Any]:
    runtime = json.loads(RUNTIME_MANIFEST_PATH.read_text(encoding="utf-8"))
    foundation = json.loads(FOUNDATION_MANIFEST_PATH.read_text(encoding="utf-8"))

    if _collect_keys(runtime) & FORBIDDEN_KEYS:
        raise AssertionError(f"forbidden business/self-hash field in P048 runtime projection: {_collect_keys(runtime) & FORBIDDEN_KEYS}")
    validate_manifest(foundation)
    if manifest_external_sha256(foundation) != EXPECTED_FOUNDATION_SHA256:
        raise AssertionError("P047 foundation external hash changed")
    if runtime["foundation_reference"]["external_admission_sha256"] != EXPECTED_FOUNDATION_SHA256:
        raise AssertionError("P048 foundation reference hash does not match P047")
    if not verify_external_admission_hash(foundation, runtime["foundation_reference"]["external_admission_sha256"]):
        raise AssertionError("P047 foundation external admission hash does not verify")

    gate = runtime["feature_gate"]
    if gate != {
        "name": "3D_SHOP_PRESENTATION_ENABLED",
        "default_enabled": False,
        "preview_override_required": True,
        "model_request_when_off": 0,
    }:
        raise AssertionError("P048 gate is not the explicit default-OFF contract")
    if tuple(item["presentation_id"] for item in runtime["entries"]) != EXPECTED_PROMOTED_IDS:
        raise AssertionError("P048 promoted entry order or logical set changed")
    if runtime["p045_runtime_asset_promotion_deferred"] is not False:
        raise AssertionError("P048 projection did not record promotion")
    if runtime["paid_asset_purchase_count"] != 0 or runtime["paid_asset_runtime_promotion"] != 0:
        raise AssertionError("paid asset boundary changed")
    if runtime["commerce"]["product_sku_created"] != 0:
        raise AssertionError("P048 created a Product SKU")
    if runtime["commerce"]["preview_mutates_ownership"] or runtime["commerce"]["preview_mutates_equipment"]:
        raise AssertionError("preview mutation boundary changed")
    if runtime["renderer_contract"]["shop_grid_realtime_renderers"] != 0:
        raise AssertionError("P048 added grid renderers")
    if runtime["renderer_contract"]["max_active_realtime_renderers"] != 1:
        raise AssertionError("P048 renderer singleton bound changed")

    hero = runtime["hero_base"]
    hero_path = _resolve_asset(hero["runtime_asset"])
    if not hero_path.is_file() or _sha256(hero_path) != hero["runtime_sha256"].upper():
        raise AssertionError("P040 A1 Hero byte-preserving runtime input failed integrity check")

    report: dict[str, Any] = {
        "runtime_manifest": str(RUNTIME_MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"),
        "foundation_manifest": str(FOUNDATION_MANIFEST_PATH.relative_to(ROOT)).replace("\\", "/"),
        "foundation_manifest_validation": "PASS",
        "foundation_external_sha256": EXPECTED_FOUNDATION_SHA256,
        "promoted_presentation_ids": list(EXPECTED_PROMOTED_IDS),
        "asset_hashes": {
            "P040_A1_HERO_BASE": {
                "path": hero["runtime_asset"],
                "sha256": _sha256(hero_path),
                "bytes": hero_path.stat().st_size,
            }
        },
    }
    for entry in runtime["entries"]:
        _verify_entry_asset(entry, report)

    c01 = _entry(runtime, "P045_C01_BUNNY")
    if c01["animation_profile"] != "RIGID_TRANSFORM" or "subclips" in c01:
        raise AssertionError("C01 is not a rigid-transform companion")
    c04 = _entry(runtime, "P045_C04_CORGI")
    expected_subclips = [("idle", 0, 30), ("attack", 30, 60), ("dead", 60, 90), ("walk", 90, 120)]
    actual_subclips = [(item["name"], item["start_frame"], item["end_frame_exclusive"]) for item in c04["subclips"]]
    if c04["animation_profile"] != "SKINNED_SEGMENTED_TIMELINE" or c04["animation_source"] != "clip" or actual_subclips != expected_subclips:
        raise AssertionError("C04 segmented timeline contract changed")
    v01 = _entry(runtime, "P045_V01_CONFETTI")
    if v01["role"] != "VICTORY_EFFECT" or v01["timing_authority"] != "PROPOSED_ONLY" or v01["source_timing_authority"] != "NONE":
        raise AssertionError("V01 Victory/timing contract changed")
    if v01["runtime_timing_profile"]["initial_runtime_direction"] != 2048:
        raise AssertionError("V01 preferred runtime direction changed")

    report.update(
        {
            "hero_hash_validation": "PASS",
            "head_entry_count": 5,
            "back_entry_count": 1,
            "companion_entry_count": 2,
            "victory_entry_count": 1,
            "c01_profile": "RIGID_TRANSFORM",
            "c04_profile": "SKINNED_SEGMENTED_TIMELINE",
            "c04_subclips": expected_subclips,
            "v01_role": "VICTORY_EFFECT",
            "v01_timing_authority": "PROPOSED_ONLY",
            "default_off_model_request_count": 0,
            "paid_asset_purchase_count": 0,
            "paid_asset_runtime_promotion": 0,
        }
    )
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(validate_runtime_manifest(), ensure_ascii=False, indent=2, sort_keys=True))
    except (AssertionError, KeyError, ManifestValidationError) as error:
        print(f"P048_RUNTIME_VALIDATION_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
