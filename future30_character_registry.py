"""Server-side Future30 character admission from the canonical asset manifest.

This module is intentionally a read-only registry adapter.  It does not create
character identities, inspect GLB filenames, or accept a client asset id as an
authority.  The existing C005 manifest is the single roster source for the
30 logical keys and 33 visual models.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path


FUTURE30_MANIFEST_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "future30_c005_real_asset_runtime_mapping_manifest.json"
)
FUTURE30_EXPECTED_LOGICAL_COUNT = 30
FUTURE30_EXPECTED_VISUAL_COUNT = 33
FUTURE30_C005_MANIFEST_SHA256 = (
    "35746c1168152cbd3fd166fd0ba5a319f3bf1ba8916fed3a8669f487a2a83c1d"
)
# The Owner supplied product-authority artifact is not present as a file in
# this D worktree.  Keep its exact binding as provenance only; the C005
# runtime manifest remains the sole local roster/mapping source.
FUTURE30_PRODUCT_MANIFEST_SHA256 = (
    "849386e00ae9ff253f27b4f9ed394ea421aeae86575fee65afea192e7e5df966"
)


class Future30RegistryError(ValueError):
    """Raised only while validating the canonical Future30 manifest."""


def _validate_manifest(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise Future30RegistryError("Future30 manifest is not an object")
    if raw.get("contract_version") != "FUTURE30_CHARACTER_RUNTIME_MANIFEST_V1":
        raise Future30RegistryError("Future30 manifest contract_version is invalid")

    counts = raw.get("counts") or {}
    if counts.get("logical_character_count") != FUTURE30_EXPECTED_LOGICAL_COUNT:
        raise Future30RegistryError("Future30 logical count is not 30")
    if counts.get("visual_model_count") != FUTURE30_EXPECTED_VISUAL_COUNT:
        raise Future30RegistryError("Future30 visual count is not 33")

    roster = raw.get("roster")
    visual_models = raw.get("visual_models")
    if not isinstance(roster, list) or len(roster) != FUTURE30_EXPECTED_LOGICAL_COUNT:
        raise Future30RegistryError("Future30 roster must contain exactly 30 logical characters")
    if not isinstance(visual_models, list) or len(visual_models) != FUTURE30_EXPECTED_VISUAL_COUNT:
        raise Future30RegistryError("Future30 visual model list must contain exactly 33 models")

    logical_keys = []
    roster_by_key = {}
    for entry in roster:
        if not isinstance(entry, dict):
            raise Future30RegistryError("Future30 roster entry is invalid")
        key = entry.get("character_id")
        if not isinstance(key, str) or not key.strip():
            raise Future30RegistryError("Future30 roster entry has no character_id")
        if key in logical_keys:
            raise Future30RegistryError(f"duplicate Future30 logical key: {key}")
        if entry.get("admission_state") != "ENABLED":
            raise Future30RegistryError(f"Future30 key is not enabled: {key}")
        default_variant = entry.get("default_variant")
        variants = entry.get("variants")
        if default_variant != "RED" or not isinstance(variants, dict):
            raise Future30RegistryError(f"Future30 default variant is invalid: {key}")
        default_visual_id = (variants.get(default_variant) or {}).get("visual_model_id")
        if not isinstance(default_visual_id, str) or not default_visual_id.strip():
            raise Future30RegistryError(f"Future30 default runtime mapping is missing: {key}")
        logical_keys.append(key)
        roster_by_key[key] = entry

    visual_ids = []
    visual_by_id = {}
    visual_rows = []
    for entry in visual_models:
        if not isinstance(entry, dict):
            raise Future30RegistryError("Future30 visual model entry is invalid")
        visual_id = entry.get("visual_model_id")
        runtime_glb = entry.get("runtime_glb")
        if not isinstance(visual_id, str) or not visual_id.strip():
            raise Future30RegistryError("Future30 visual model has no visual_model_id")
        if visual_id in visual_ids:
            raise Future30RegistryError(f"duplicate Future30 visual model: {visual_id}")
        if not isinstance(runtime_glb, str) or not runtime_glb.endswith(".glb"):
            raise Future30RegistryError(f"Future30 runtime mapping is missing: {visual_id}")
        if entry.get("asset_status") != "PRESENT" or entry.get("placeholder_mapping") is not False:
            raise Future30RegistryError(f"Future30 runtime mapping is not admitted: {visual_id}")
        if not isinstance(entry.get("character_id"), str) or not entry["character_id"].strip():
            raise Future30RegistryError(f"Future30 visual model has no character_id: {visual_id}")
        runtime_sha256 = entry.get("runtime_sha256")
        if not isinstance(runtime_sha256, str) or len(runtime_sha256) != 64:
            raise Future30RegistryError(f"Future30 runtime hash is missing: {visual_id}")
        runtime_path = FUTURE30_MANIFEST_PATH.parent.parent / runtime_glb
        if not runtime_path.is_file():
            raise Future30RegistryError(f"Future30 runtime asset is missing: {runtime_glb}")
        if hashlib.sha256(runtime_path.read_bytes()).hexdigest() != runtime_sha256.lower():
            raise Future30RegistryError(f"Future30 runtime hash mismatch: {visual_id}")
        visual_ids.append(visual_id)
        visual_by_id[visual_id] = entry
        legal = entry.get("legal_provenance") or {}
        visual_rows.append({
            "visual_model_id": visual_id,
            "character_key": entry["character_id"],
            "variant": entry.get("variant"),
            "character_asset_id": entry.get("character_asset_id"),
            "runtime_glb": runtime_glb,
            "runtime_sha256": runtime_sha256.lower(),
            "mapping_status": "CONFIRMED",
            "license_status": legal.get("license_status"),
            "provenance_status": legal.get("provenance_status"),
        })

    default_rows = []
    for key in logical_keys:
        entry = roster_by_key[key]
        visual_id = entry["variants"][entry["default_variant"]]["visual_model_id"]
        visual = visual_by_id.get(visual_id)
        if not visual or visual.get("character_id") != key or visual.get("variant") != "RED":
            raise Future30RegistryError(f"Future30 default mapping does not resolve: {key}")
        default_rows.append({
            "character_key": key,
            "display_name": entry.get("display_name", key),
            "default_variant": entry["default_variant"],
            "visual_model_id": visual["visual_model_id"],
            "character_asset_id": visual["character_asset_id"],
            "runtime_glb": visual["runtime_glb"],
            "runtime_sha256": visual["runtime_sha256"].lower(),
            "admission_state": entry["admission_state"],
            "license_status": (entry.get("legal_provenance") or {}).get("license_status"),
            "provenance_status": (entry.get("legal_provenance") or {}).get("provenance_status"),
            "authority_ref": (entry.get("legal_provenance") or {}).get("authority_ref"),
        })

    return {
        "manifest": raw,
        "logical_keys": frozenset(logical_keys),
        "logical_key_order": tuple(logical_keys),
        "visual_model_ids": frozenset(visual_ids),
        "visual_by_id": visual_by_id,
        "visual_rows": tuple(visual_rows),
        "default_rows": tuple(default_rows),
    }


def _load_registry() -> tuple[dict | None, str | None]:
    try:
        if hashlib.sha256(FUTURE30_MANIFEST_PATH.read_bytes()).hexdigest() != FUTURE30_C005_MANIFEST_SHA256:
            raise Future30RegistryError("Future30 C005 manifest SHA256 is not the Owner-bound value")
        with FUTURE30_MANIFEST_PATH.open("r", encoding="utf-8") as handle:
            return _validate_manifest(json.load(handle)), None
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # Legacy players remain serviceable if the optional Future30 package is
        # absent from an older deployment.  Future30 admission then fails closed.
        return None, f"{type(exc).__name__}: {exc}"


_REGISTRY, FUTURE30_CHARACTER_REGISTRY_ERROR = _load_registry()
FUTURE30_CHARACTER_REGISTRY_VALID = _REGISTRY is not None
FUTURE30_CHARACTER_KEYS = _REGISTRY["logical_keys"] if _REGISTRY else frozenset()
FUTURE30_CHARACTER_KEY_ORDER = _REGISTRY["logical_key_order"] if _REGISTRY else ()
FUTURE30_VISUAL_MODEL_IDS = _REGISTRY["visual_model_ids"] if _REGISTRY else frozenset()
FUTURE30_CHARACTER_CATALOG = _REGISTRY["default_rows"] if _REGISTRY else ()
FUTURE30_VISUAL_MODEL_REGISTRY = _REGISTRY["visual_by_id"] if _REGISTRY else {}
FUTURE30_VISUAL_MODEL_ROWS = _REGISTRY["visual_rows"] if _REGISTRY else ()


def is_future30_character_key(value: object) -> bool:
    """Return true only for an exact key admitted by the canonical roster."""

    return isinstance(value, str) and value in FUTURE30_CHARACTER_KEYS


def future30_character_record(value: object) -> dict | None:
    """Return the canonical default RED projection for one logical key."""

    if not is_future30_character_key(value):
        return None
    for row in FUTURE30_CHARACTER_CATALOG:
        if row["character_key"] == value:
            return dict(row)
    return None


def future30_catalog_rows() -> tuple[dict, ...]:
    """Return copies of the exact 30 logical default mappings."""

    return tuple(dict(row) for row in FUTURE30_CHARACTER_CATALOG)


def future30_visual_model_rows() -> tuple[dict, ...]:
    """Return the exact 33 manifest-bound visual mappings in source order."""

    return tuple(dict(row) for row in FUTURE30_VISUAL_MODEL_ROWS)


def future30_registry_diagnostics() -> dict:
    """Small read-only diagnostic projection for tests and acceptance tooling."""

    return {
        "manifest_path": str(FUTURE30_MANIFEST_PATH),
        "valid": FUTURE30_CHARACTER_REGISTRY_VALID,
        "logical_count": len(FUTURE30_CHARACTER_KEYS),
        "visual_count": len(FUTURE30_VISUAL_MODEL_IDS),
        "manifest_sha256": FUTURE30_C005_MANIFEST_SHA256 if FUTURE30_CHARACTER_REGISTRY_VALID else None,
        "product_manifest_sha256": FUTURE30_PRODUCT_MANIFEST_SHA256,
        "error": FUTURE30_CHARACTER_REGISTRY_ERROR,
    }
