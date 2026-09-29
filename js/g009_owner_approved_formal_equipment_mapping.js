import { resolveG009RuntimeEquipmentIdentity } from "./g009_d007_runtime_identity_resolver.mjs";
import {
  G009_FORMAL9_REPLACEMENT_AUTHORITY,
  G009_FORMAL9_REPLACEMENT_ROWS,
  G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS,
  G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED,
  isG009RetiredFormalAssetId,
} from "./g009_formal9_rights_cleared_replacement_catalog.js";

// The original Owner item-to-item table (which formal9 items are mapped at
// all) is unchanged. The visuals behind the four mapped items were replaced by
// the Owner-selected rights-cleared assets in
// E_G009_FORMAL9_SELECTED_WEAPON_FINALIZATION_001.
export const G009_OWNER_FORMAL_MAPPING_AUTHORITY = Object.freeze({
  task_id: "D_G009_OWNER_APPROVED_9ROW_FORMAL_MAPPING_AUTHORITY_001",
  md_sha256: "6b521ab04b0d2bcafe1496d63e8304123a7298f4d94d6661088cdc60a10403f3",
  json_sha256: "7a529c0d6ca15f41647e416d78949a2f8056f17dc149477cc805709a0cdd75aa",
  visual_replacement_task_id: G009_FORMAL9_REPLACEMENT_AUTHORITY.task_id,
});

// Kept for historical descriptors only (Wooden Sword and retired D007 rows).
export const G009_UNCLEARED_FORMAL_ASSET_RIGHTS = Object.freeze({
  RIGHTS_STATUS: "NOT_CLEARED",
  EQUIP_ENABLED: false,
  SHOP_ENABLED: false,
  PURCHASE_ENABLED: false,
  DROP_ENABLED: false,
  PLAYER_SELECTABLE: false,
  RELEASE_ENABLED: false,
  PRODUCTION_ASSET_ADMISSION: false,
});

export { G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS };

export const G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS = Object.freeze(
  G009_FORMAL9_REPLACEMENT_ROWS.map((entry) => Object.freeze({
    server_item_id: entry.server_item_id,
    asset_id: entry.asset_id,
    runtime_asset: entry.runtime_asset,
    runtime_sha256: entry.runtime_sha256,
    rights: entry.rights,
  })),
);

export const G009_OWNER_INTENTIONALLY_UNMAPPED_ITEM_IDS = Object.freeze([
  "dragon_claw",
  "celestial_blade",
  "moonstar_rapier",
  "emberline_cutlass",
  "starglass_needle",
]);

const BY_SERVER_ITEM_ID = new Map(
  G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS.map((row) => [row.server_item_id, row]),
);
const INTENTIONALLY_UNMAPPED = new Set(G009_OWNER_INTENTIONALLY_UNMAPPED_ITEM_IDS);
const EXISTING_WOODEN_SWORD = Object.freeze({
  asset_id: "WEAPON_628812E9B559",
  runtime_asset: "/assets/3d_shop/formal_character_equipment_v1/weapons/01_wooden_sword.glb",
  runtime_sha256: "628812e9b559b3282c5cac39aeee1f52be5f4134b44c81ae87a91c16f3d509ec",
});

function hasUniqueBindings(rows) {
  return new Set(rows.map((row) => row.server_item_id)).size === rows.length
    && new Set(rows.map((row) => row.asset_id)).size === rows.length;
}

if (!hasUniqueBindings(G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS)) {
  throw new Error("duplicate_owner_formal_equipment_binding");
}

function safeReplacementRow(binding, requestedSlot) {
  if (requestedSlot !== "MAIN_HAND" || isG009RetiredFormalAssetId(binding.asset_id)) return null;
  const source = G009_FORMAL9_REPLACEMENT_ROWS.find((entry) => entry.server_item_id === binding.server_item_id);
  if (!source || source.asset_id !== binding.asset_id
    || source.runtime_asset !== binding.runtime_asset
    || source.runtime_sha256 !== binding.runtime_sha256
    || source.slot !== "MAIN_HAND" || source.socket !== "hand.R"
    || !["ONE_HAND", "KNIFE_SMALL"].includes(source.presentation_class)
    || source.equip_capability !== false
    || source.release_eligibility !== G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED
    || source.rights !== G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS) {
    return null;
  }
  return source;
}

/**
 * Resolve only Owner-approved server item IDs. The four mapped formal9 items
 * resolve to the Owner-selected rights-cleared replacement catalog; Wooden
 * Sword keeps its exact D007 row. Retired D007 visuals, candidate item names,
 * filenames, display names, and similarity are never consulted as mapping
 * evidence, and nothing falls back to another model.
 */
export function resolveG009OwnerApprovedRuntimeEquipmentIdentity(index, itemId, requestedSlot) {
  if (typeof itemId !== "string" || !itemId.trim()) return null;

  if (itemId === "wooden_sword") {
    const source = resolveG009RuntimeEquipmentIdentity(index, itemId, { allowAssetId: false });
    if (!source || source.item_mapping_status !== "CURRENT_SERVER_ID"
      || source.server_item_id !== "wooden_sword" || requestedSlot !== "MAIN_HAND"
      || source.asset_id !== EXISTING_WOODEN_SWORD.asset_id
      || source.runtime_asset !== EXISTING_WOODEN_SWORD.runtime_asset
      || String(source.runtime_sha256 || "").toLowerCase() !== EXISTING_WOODEN_SWORD.runtime_sha256
      || source.slot !== "MAIN_HAND" || source.equip_capability !== false
      || source.release_eligibility !== "NOT_CLEARED") return null;
    return Object.freeze({
      ...source,
      presentation_id: source.asset_id,
      slot: source.slot,
      authority_route: "D007_CURRENT_SERVER_ID_UNCHANGED",
    });
  }

  if (INTENTIONALLY_UNMAPPED.has(itemId)) return null;
  const binding = BY_SERVER_ITEM_ID.get(itemId);
  if (!binding) return null;
  const source = safeReplacementRow(binding, requestedSlot);
  if (!source) return null;

  return Object.freeze({
    ...source,
    server_item_id: itemId,
    item_mapping_status: "OWNER_APPROVED_FORMAL_MAPPING",
    presentation_id: source.asset_id,
    slot: source.slot,
    authority_route: G009_OWNER_FORMAL_MAPPING_AUTHORITY.task_id,
    authority_md_sha256: G009_OWNER_FORMAL_MAPPING_AUTHORITY.md_sha256,
    authority_json_sha256: G009_OWNER_FORMAL_MAPPING_AUTHORITY.json_sha256,
    visual_authority_route: G009_FORMAL9_REPLACEMENT_AUTHORITY.task_id,
    rights: source.rights,
  });
}
