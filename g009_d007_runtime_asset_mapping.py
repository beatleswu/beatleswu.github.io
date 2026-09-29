"""Scoped G009 server-side identity-to-runtime lookup for D007 assets.

The JSON manifest is the sole mapping source.  This module projects its
explicit 12-asset Owner admission into presentation metadata only; it does
not register inventory, grant ownership, enable equipment, or clear release
eligibility.  Item identifiers marked D007_SOURCE_CANDIDATE_ONLY are not
asserted to exist in the current server equipment registry.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_MAPPING_PATH = ROOT / "schemas" / "g009_d007_runtime_prerequisite_v1.json"
CONTRACT = "GO_ODYSSEY_G009_D007_RUNTIME_PREREQUISITE_V1"
OWNER_ADMISSION = "APPROVED_FOR_CURRENT_G009_CANDIDATE"
ADMITTED_ASSET_IDS = frozenset(
    {
        "WEAPON_628812E9B559",
        "WEAPON_EF825DA22339",
        "WEAPON_9CD401DADF4C",
        "WEAPON_711BD826F45C",
        "WEAPON_2F4CB085CE4A",
        "WEAPON_A70FD7AB666C",
        "WEAPON_AF8287295872",
        "WEAPON_A7C05D43F943",
        "WEAPON_30DF9E13DB7E",
        "WEAPON_DB8098EC9B88",
        "WEAPON_0A0C54EBD78F",
        "WEAPON_1B004BE1E816",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class G009RuntimeMappingError(ValueError):
    """The bounded candidate mapping is malformed or outside admission."""


def load_g009_runtime_mapping(
    path: Path | str = DEFAULT_MAPPING_PATH,
) -> dict[str, Any]:
    """Load and validate the exact candidate-only 12-asset mapping."""

    mapping_path = Path(path)
    try:
        manifest = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise G009RuntimeMappingError("runtime mapping manifest unavailable") from exc
    if not isinstance(manifest, dict) or manifest.get("contract_version") != CONTRACT:
        raise G009RuntimeMappingError("runtime mapping contract mismatch")
    admission = manifest.get("owner_admission")
    if not isinstance(admission, Mapping):
        raise G009RuntimeMappingError("Owner admission block is missing")
    if admission.get("status") != OWNER_ADMISSION:
        raise G009RuntimeMappingError("current G009 Owner admission is missing")
    if admission.get("evidence_verification") != "RETAINS_PRIOR_AUDIT_STATUS":
        raise G009RuntimeMappingError("prior evidence status must be retained")
    if set(admission.get("admitted_asset_ids", ())) != ADMITTED_ASSET_IDS:
        raise G009RuntimeMappingError("admission roster is not exactly the 12 assets")

    equipment = manifest.get("equipment_catalog")
    rows = equipment.get("items") if isinstance(equipment, Mapping) else None
    if not isinstance(rows, list) or len(rows) != 12:
        raise G009RuntimeMappingError("equipment roster must contain exactly 12 rows")
    by_asset: dict[str, dict[str, Any]] = {}
    by_candidate_item: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise G009RuntimeMappingError("equipment mapping row is malformed")
        asset_id = row.get("asset_id")
        runtime_asset = row.get("runtime_asset")
        digest = row.get("runtime_sha256")
        if not isinstance(asset_id, str) or asset_id not in ADMITTED_ASSET_IDS:
            raise G009RuntimeMappingError("non-admitted or unknown asset identity")
        if asset_id in by_asset:
            raise G009RuntimeMappingError("duplicate asset identity")
        if (
            not isinstance(runtime_asset, str)
            or not runtime_asset.startswith(
                "/assets/3d_shop/formal_character_equipment_v1/weapons/"
            )
            or ".." in runtime_asset.split("/")
            or not runtime_asset.endswith(".glb")
        ):
            raise G009RuntimeMappingError("runtime path is outside the D007 equipment root")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise G009RuntimeMappingError("runtime SHA-256 is missing or invalid")
        if row.get("g009_owner_admission") != OWNER_ADMISSION:
            raise G009RuntimeMappingError("asset-specific Owner admission is missing")
        if row.get("release_eligibility") != "NOT_CLEARED":
            raise G009RuntimeMappingError("candidate admission cannot clear release eligibility")
        if row.get("equip_capability") is not False:
            raise G009RuntimeMappingError("candidate admission cannot grant equip capability")
        if row.get("slot") == "MAIN_HAND":
            if row.get("socket") != "hand.R" or row.get("presentation_class") not in {
                "ONE_HAND",
                "KNIFE_SMALL",
            }:
                raise G009RuntimeMappingError("main-hand mapping violates the V1 socket/class")
        elif row.get("slot") == "OFF_HAND":
            if row.get("socket") != "hand.L" or row.get("presentation_class") != "SHIELD":
                raise G009RuntimeMappingError("off-hand mapping must be a shield on hand.L")
        else:
            raise G009RuntimeMappingError("unsupported equipment slot")

        by_asset[asset_id] = row
        item_id = row.get("server_item_id")
        if item_id is not None:
            if not isinstance(item_id, str) or not item_id.strip():
                raise G009RuntimeMappingError("server item identifier is malformed")
            if item_id in by_candidate_item:
                raise G009RuntimeMappingError("duplicate candidate item identifier")
            by_candidate_item[item_id] = row

    if set(by_asset) != ADMITTED_ASSET_IDS:
        raise G009RuntimeMappingError("runtime mapping does not resolve all 12 admitted assets")
    if equipment.get("two_handed_supported") is not False:
        raise G009RuntimeMappingError("two-handed support must remain disabled")
    if equipment.get("production_off_hand_flag") is not False:
        raise G009RuntimeMappingError("Production off-hand flag must remain disabled")
    if manifest.get("excluded_capabilities", {}).get("PET_COMPANION") != (
        "EXCLUDED_UNRESOLVED_NODE_VALIDATION"
    ):
        raise G009RuntimeMappingError("unresolved Pet capability must stay excluded")
    return manifest


def resolve_g009_runtime_asset(
    identifier: str,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve an admitted item/asset identity to presentation-only metadata.

    Candidate-only item identifiers are useful for D3 integration fixtures,
    but this resolver is not an inventory or ownership check. Unknown IDs fail
    closed, and Small Stick remains asset-ID-only until a canonical item ID
    exists in server-owned definitions.
    """

    if not isinstance(identifier, str) or not identifier.strip():
        return None
    source = load_g009_runtime_mapping()
    if manifest is not None and manifest != source:
        return None
    equipment = source.get("equipment_catalog")
    rows = equipment.get("items") if isinstance(equipment, Mapping) else None
    if not isinstance(rows, list):
        return None
    match = next(
        (
            row
            for row in rows
            if isinstance(row, Mapping)
            and identifier in {row.get("asset_id"), row.get("server_item_id")}
            and row.get("g009_owner_admission") == OWNER_ADMISSION
            and row.get("release_eligibility") == "NOT_CLEARED"
        ),
        None,
    )
    return dict(match) if match is not None else None


def resolve_current_server_item_id(
    item_id: str,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve only an item ID confirmed in current server definitions."""

    row = resolve_g009_runtime_asset(item_id, manifest=manifest)
    return row if row is not None and row.get("item_mapping_status") == "CURRENT_SERVER_ID" else None


__all__ = [
    "ADMITTED_ASSET_IDS",
    "G009RuntimeMappingError",
    "load_g009_runtime_mapping",
    "resolve_current_server_item_id",
    "resolve_g009_runtime_asset",
]
