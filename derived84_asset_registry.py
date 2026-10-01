"""Runtime consumer for the Owner-accepted G009 Derived84 assets.

The registry is a projection of the finalized control-plane authority.  It
does not create a second identity authority: Future30 uses ``visual_model_id``
and Companion uses the existing server-owned ``pet_key`` plus persistent
level-derived stage.  Runtime use is fail-closed when the manifest or any
accepted byte is missing or has a different SHA-256.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent
DERIVED84_RUNTIME_MANIFEST_PATH = _ROOT / "assets" / "world-map-identity" / "runtime_manifest.json"
DERIVED84_OWNER_DECISION_SHA256 = (
    "3d2bbcc6f8cda56a83c5f819cbde62db9fdfe8852e6f6be2ae6c3a505bd53d64"
)
DERIVED84_SOURCE_MANIFEST_SHA256 = (
    "d92c2c6bcd54ab0a7b1488acacb0fb183a49ce41b59fa53e9a3991ed6d5523b9"
)
DERIVED84_EXPECTED_COUNTS = {"AVATAR": 33, "STANDING": 33, "COMPANION": 18}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_path(relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative.startswith("assets/"):
        return None
    if "\\" in relative or ".." in relative.split("/"):
        return None
    candidate = (_ROOT / Path(*relative.split("/"))).resolve()
    try:
        candidate.relative_to(_ROOT)
    except ValueError:
        return None
    return candidate


def _load_registry() -> tuple[dict[str, Any] | None, str | None]:
    try:
        manifest = json.loads(DERIVED84_RUNTIME_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"manifest_unavailable:{type(exc).__name__}"

    authority = manifest.get("authority")
    if not isinstance(authority, dict):
        return None, "authority_metadata_missing"
    if authority.get("owner_decision_record_sha256", "").lower() != DERIVED84_OWNER_DECISION_SHA256:
        return None, "owner_decision_hash_mismatch"
    if authority.get("source_manifest_sha256", "").lower() != DERIVED84_SOURCE_MANIFEST_SHA256:
        return None, "source_manifest_hash_mismatch"
    if manifest.get("manifest_version") != "G009_DERIVED84_RUNTIME_MANIFEST_V1":
        return None, "manifest_version_mismatch"
    if manifest.get("derived_84_asset_visual_authority") != "LOCKED":
        return None, "asset_authority_not_locked"
    if manifest.get("owner_acceptance_complete") is not True:
        return None, "owner_acceptance_incomplete"
    if manifest.get("runtime_consumed") is not True:
        return None, "runtime_consume_not_recorded"
    entries = manifest.get("entries")
    if not isinstance(entries, list) or len(entries) != 84:
        return None, "entry_count_mismatch"

    counts = {"AVATAR": 0, "STANDING": 0, "COMPANION": 0}
    identities: set[tuple[str, str, str | None]] = set()
    companion_by_stage: dict[tuple[str, str], str] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("owner_decision") != "PASS":
            return None, "unapproved_entry"
        role = entry.get("asset_role")
        if role not in counts:
            return None, "unknown_asset_role"
        runtime_path = _runtime_path(entry.get("target_runtime_path"))
        expected = entry.get("expected_runtime_sha256")
        if runtime_path is None or not isinstance(expected, str) or len(expected) != 64:
            return None, "runtime_identity_invalid"
        if not runtime_path.is_file() or _sha256(runtime_path).lower() != expected.lower():
            return None, "runtime_hash_mismatch"
        counts[role] += 1
        if role in {"AVATAR", "STANDING"}:
            identity = entry.get("visual_model_id")
            if not isinstance(identity, str) or not identity:
                return None, "visual_model_identity_missing"
            tuple_key = (role, identity, None)
        else:
            pet_key = entry.get("pet_key")
            stage = entry.get("stage")
            if not isinstance(pet_key, str) or not isinstance(stage, str):
                return None, "companion_identity_missing"
            tuple_key = (role, pet_key, stage)
            companion_by_stage[(pet_key, stage)] = "/" + entry["target_runtime_path"]
        if tuple_key in identities:
            return None, "duplicate_identity"
        identities.add(tuple_key)

    if counts != DERIVED84_EXPECTED_COUNTS:
        return None, "role_count_mismatch"
    if len(identities) != 84:
        return None, "identity_count_mismatch"
    return {"manifest": manifest, "companion_by_stage": companion_by_stage}, None


_REGISTRY, DERIVED84_RUNTIME_ERROR = _load_registry()
DERIVED84_RUNTIME_AVAILABLE = _REGISTRY is not None


def derived84_companion_asset(pet_key: str, stage: int | str) -> str:
    """Return the accepted Companion stage path or an empty fail-closed value."""

    if not DERIVED84_RUNTIME_AVAILABLE or _REGISTRY is None:
        return ""
    stage_name = {1: "I", 2: "II", 3: "III"}.get(stage, stage)
    return _REGISTRY["companion_by_stage"].get((pet_key, str(stage_name)), "")


__all__ = [
    "DERIVED84_RUNTIME_AVAILABLE",
    "DERIVED84_RUNTIME_ERROR",
    "DERIVED84_RUNTIME_MANIFEST_PATH",
    "derived84_companion_asset",
]
