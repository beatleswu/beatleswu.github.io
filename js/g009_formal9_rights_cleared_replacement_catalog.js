// Owner-selected (4/4) rights-cleared replacement visuals for the formal9
// main-hand items. Mirrors schemas/g009_formal9_rights_cleared_replacement_v1.json;
// provenance lives in provenance/g009_formal9_rights_cleared_v1/.
//
// RIGHTS_CLEARED is a rights fact only. It grants no equip, shop, purchase,
// drop, player selection, release or Production admission; those stay with
// separate product and Owner decisions.
export const G009_FORMAL9_REPLACEMENT_AUTHORITY = Object.freeze({
  task_id: "E_G009_FORMAL9_SELECTED_WEAPON_FINALIZATION_001",
  owner_selection: "4_OF_4",
  provenance: "provenance/g009_formal9_rights_cleared_v1/final_asset_manifest.json",
});

export const G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED = "RIGHTS_CLEARED_RELEASE_NOT_ADMITTED";

export const G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS = Object.freeze({
  RIGHTS_STATUS: "RIGHTS_CLEARED",
  LICENSE_TYPE: "CC0-1.0",
  EQUIP_ENABLED: false,
  SHOP_ENABLED: false,
  PURCHASE_ENABLED: false,
  DROP_ENABLED: false,
  PLAYER_SELECTABLE: false,
  RELEASE_ENABLED: false,
  PRODUCTION_ASSET_ADMISSION: false,
  // G030 Owner public 3D *visual preview* approval; no item entitlement.
  PUBLIC_3D_PREVIEW_ADMITTED: true,
});

const MAIN_HAND_TRANSFORM = Object.freeze({
  position: Object.freeze([0.1, 0.02, 0.04]),
  rotation: Object.freeze([0, 0, -1.57079633]),
  scale: Object.freeze([0.234, 0.234, 0.234]),
});

function row(serverItemId, assetId, sha256, presentationClass) {
  return Object.freeze({
    server_item_id: serverItemId,
    asset_id: assetId,
    runtime_asset: "/assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_" + sha256.slice(0, 12) + ".glb",
    runtime_sha256: sha256,
    slot: "MAIN_HAND",
    socket: "hand.R",
    presentation_class: presentationClass,
    position: MAIN_HAND_TRANSFORM.position,
    rotation: MAIN_HAND_TRANSFORM.rotation,
    scale: MAIN_HAND_TRANSFORM.scale,
    equip_capability: false,
    release_eligibility: G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED,
    rights: G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS,
  });
}

export const G009_FORMAL9_REPLACEMENT_ROWS = Object.freeze([
  row("iron_sword", "WEAPON_C43E15596CA6",
    "c43e15596ca656355553585e3ac4a398b37a0216471539e8dda6401d67b7580b", "ONE_HAND"),
  row("fox_fang", "WEAPON_6F06505A7BED",
    "6f06505a7bed0ea7681216df58d2a89696b2305f9c080b5f0fa4d9fcabc72af0", "KNIFE_SMALL"),
  row("riverstone_sabre", "WEAPON_EC86CE30E759",
    "ec86ce30e7591bc89badac98a4ed0c00b6614ac8e97b8b79ea734ba7f82c2409", "ONE_HAND"),
  row("bamboo_shadow_blade", "WEAPON_C84A8635BED2",
    "c84a8635bed2d2252a6937dbd8837c585872502a4253f549a7b94069e7b776c6", "ONE_HAND"),
]);

// Old D007 visuals replaced by this change. They stay in the D007 catalog for
// history but no active resolver may return them, and they never alias to the
// replacement bytes.
export const G009_FORMAL9_RETIRED_ASSET_IDS = Object.freeze([
  "WEAPON_A7C05D43F943",
  "WEAPON_A70FD7AB666C",
  "WEAPON_9CD401DADF4C",
  "WEAPON_2F4CB085CE4A",
]);

const RETIRED = new Set(G009_FORMAL9_RETIRED_ASSET_IDS);
const BY_ASSET_ID = new Map(G009_FORMAL9_REPLACEMENT_ROWS.map((entry) => [entry.asset_id, entry]));
const BY_SERVER_ITEM_ID = new Map(G009_FORMAL9_REPLACEMENT_ROWS.map((entry) => [entry.server_item_id, entry]));

if (BY_ASSET_ID.size !== 4 || BY_SERVER_ITEM_ID.size !== 4
  || G009_FORMAL9_REPLACEMENT_ROWS.some((entry) => RETIRED.has(entry.asset_id)
    || entry.asset_id !== "WEAPON_" + entry.runtime_sha256.slice(0, 12).toUpperCase())) {
  throw new Error("g009_formal9_replacement_catalog_invalid");
}

export function isG009RetiredFormalAssetId(assetId) {
  return typeof assetId === "string" && RETIRED.has(assetId);
}

export function g009Formal9ReplacementRowForItem(serverItemId) {
  return BY_SERVER_ITEM_ID.get(serverItemId) || null;
}

export function g009Formal9ReplacementRowForAsset(assetId) {
  return BY_ASSET_ID.get(assetId) || null;
}
