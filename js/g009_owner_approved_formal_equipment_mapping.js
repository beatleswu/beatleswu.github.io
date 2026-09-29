import { resolveG009RuntimeEquipmentIdentity } from "./g009_d007_runtime_identity_resolver.mjs";

export const G009_OWNER_FORMAL_MAPPING_AUTHORITY = Object.freeze({
  task_id: "D_G009_OWNER_APPROVED_9ROW_FORMAL_MAPPING_AUTHORITY_001",
  md_sha256: "6b521ab04b0d2bcafe1496d63e8304123a7298f4d94d6661088cdc60a10403f3",
  json_sha256: "7a529c0d6ca15f41647e416d78949a2f8056f17dc149477cc805709a0cdd75aa",
});

// Mapping approval establishes identity only. No rights or release grant has
// been admitted for these GLBs; this policy is per resolved asset, not equip
// capability inferred from an item name or catalog filename.
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

export const G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS = Object.freeze([
  Object.freeze({
    server_item_id: "iron_sword",
    asset_id: "WEAPON_A7C05D43F943",
    runtime_asset: "/assets/3d_shop/formal_character_equipment_v1/weapons/21_adventure_sword.glb",
    runtime_sha256: "a7c05d43f9434a6cfd0304908c68ac2a97975c6bc641516c55e1380c5f81d2fc",
    rights: G009_UNCLEARED_FORMAL_ASSET_RIGHTS,
  }),
  Object.freeze({
    server_item_id: "fox_fang",
    asset_id: "WEAPON_A70FD7AB666C",
    runtime_asset: "/assets/3d_shop/formal_character_equipment_v1/weapons/15_hunting_knife.glb",
    runtime_sha256: "a70fd7ab666cd2551520146b0a8cff7fe24c67f0cebde8d685fb273d3540f8f8",
    rights: G009_UNCLEARED_FORMAL_ASSET_RIGHTS,
  }),
  Object.freeze({
    server_item_id: "riverstone_sabre",
    asset_id: "WEAPON_9CD401DADF4C",
    runtime_asset: "/assets/3d_shop/formal_character_equipment_v1/weapons/12_katana.glb",
    runtime_sha256: "9cd401dadf4cf49fc404eb30e1715a898eb6895dc32dba7c56dd8a7fd0b190c4",
    rights: G009_UNCLEARED_FORMAL_ASSET_RIGHTS,
  }),
  Object.freeze({
    server_item_id: "bamboo_shadow_blade",
    asset_id: "WEAPON_2F4CB085CE4A",
    runtime_asset: "/assets/3d_shop/formal_character_equipment_v1/weapons/14_army_sword.glb",
    runtime_sha256: "20979ea75b6bdcaade2187de81274136d56bbad31a3860ca12373ff24dde89b8",
    rights: G009_UNCLEARED_FORMAL_ASSET_RIGHTS,
  }),
]);

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

function safeCatalogRow(index, binding, requestedSlot) {
  if (!(index?.byAssetId instanceof Map) || requestedSlot !== "MAIN_HAND") return null;
  const source = index.byAssetId.get(binding.asset_id);
  if (!source || source.asset_id !== binding.asset_id
    || source.runtime_asset !== binding.runtime_asset
    || String(source.runtime_sha256 || "").toLowerCase() !== binding.runtime_sha256
    || source.slot !== "MAIN_HAND" || source.socket !== "hand.R"
    || !["ONE_HAND", "KNIFE_SMALL"].includes(source.presentation_class)
    || source.g009_owner_admission !== "APPROVED_FOR_CURRENT_G009_CANDIDATE"
    || source.evidence_verification !== "RETAINS_PRIOR_AUDIT_STATUS"
    || source.equip_capability !== false || source.release_eligibility !== "NOT_CLEARED") {
    return null;
  }
  return source;
}

/**
 * Resolve only Owner-approved server item IDs against the already-admitted
 * D007 asset catalog. The Owner table supplies item-to-asset authority; D007
 * supplies the exact asset row/transform. Candidate item names, filenames,
 * display names, and similarity are never consulted as mapping evidence.
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
  const source = safeCatalogRow(index, binding, requestedSlot);
  if (!source) return null;

  return Object.freeze({
    ...source,
    server_item_id: itemId,
    source_candidate_server_item_id: source.server_item_id,
    item_mapping_status: "OWNER_APPROVED_FORMAL_MAPPING",
    presentation_id: source.asset_id,
    slot: source.slot,
    authority_route: G009_OWNER_FORMAL_MAPPING_AUTHORITY.task_id,
    authority_md_sha256: G009_OWNER_FORMAL_MAPPING_AUTHORITY.md_sha256,
    authority_json_sha256: G009_OWNER_FORMAL_MAPPING_AUTHORITY.json_sha256,
    rights: binding.rights,
  });
}
