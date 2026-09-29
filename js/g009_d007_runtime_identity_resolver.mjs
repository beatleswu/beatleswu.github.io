const OWNER_ADMISSION = "APPROVED_FOR_CURRENT_G009_CANDIDATE";
const CONTRACT = "GO_ODYSSEY_G009_D007_RUNTIME_PREREQUISITE_V1";
const SHA256 = /^[a-f0-9]{64}$/i;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function isRecord(value) {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function finiteArray(value, length) {
  return Array.isArray(value) && value.length === length
    && value.every((entry) => Number.isFinite(Number(entry)));
}

export function createG009RuntimeEquipmentIndex(manifest) {
  assert(isRecord(manifest) && manifest.contract_version === CONTRACT,
    "G009 runtime mapping contract mismatch");
  assert(manifest.owner_admission?.status === OWNER_ADMISSION,
    "current G009 Owner admission is missing");
  assert(manifest.owner_admission?.evidence_verification === "RETAINS_PRIOR_AUDIT_STATUS",
    "prior asset evidence status must be retained");
  const admitted = manifest.owner_admission?.admitted_asset_ids;
  const rows = manifest.equipment_catalog?.items;
  assert(Array.isArray(admitted) && admitted.length === 12 && new Set(admitted).size === 12,
    "Owner admission must contain exactly 12 distinct asset identities");
  assert(Array.isArray(rows) && rows.length === 12,
    "runtime mapping must contain exactly 12 equipment rows");
  assert(manifest.equipment_catalog?.two_handed_supported === false,
    "two-handed weapons are outside this runtime contract");
  assert(manifest.equipment_catalog?.production_off_hand_flag === false,
    "Production off-hand flag must remain disabled");
  assert(manifest.excluded_capabilities?.PET_COMPANION === "EXCLUDED_UNRESOLVED_NODE_VALIDATION",
    "unresolved Pet/Companion node validation must remain excluded");
  assert(!manifest.appearance_catalog?.COMPANION,
    "Pet/Companion runtime mapping must not be included");

  const allowedIds = new Set(admitted);
  const byAssetId = new Map();
  const byServerItemId = new Map();
  const byCandidateItemId = new Map();
  for (const row of rows) {
    assert(isRecord(row) && typeof row.asset_id === "string" && allowedIds.has(row.asset_id),
      "unknown or non-admitted equipment asset rejected");
    assert(!byAssetId.has(row.asset_id), "duplicate equipment asset identity");
    assert(row.g009_owner_admission === OWNER_ADMISSION,
      "equipment row lacks current-candidate Owner admission");
    assert(row.evidence_verification === "RETAINS_PRIOR_AUDIT_STATUS",
      "equipment evidence status was modified");
    assert(row.release_eligibility === "NOT_CLEARED" && row.equip_capability === false,
      "candidate admission cannot clear release or grant equip capability");
    assert(typeof row.runtime_asset === "string"
      && row.runtime_asset.startsWith("/assets/3d_shop/formal_character_equipment_v1/weapons/")
      && !row.runtime_asset.split("/").includes("..")
      && row.runtime_asset.endsWith(".glb"), "unsafe or unsupported runtime asset path");
    assert(typeof row.runtime_sha256 === "string" && SHA256.test(row.runtime_sha256),
      "runtime asset hash is missing or invalid");
    assert(finiteArray(row.position, 3) && finiteArray(row.rotation, 3)
      && finiteArray(row.scale, 3), "equipment transform is incomplete");
    if (row.slot === "MAIN_HAND") {
      assert(row.socket === "hand.R" && ["ONE_HAND", "KNIFE_SMALL"].includes(row.presentation_class),
        "main-hand item violates the one-hand socket/class contract");
    } else if (row.slot === "OFF_HAND") {
      assert(row.socket === "hand.L" && row.presentation_class === "SHIELD",
        "off-hand item must be a shield on hand.L");
    } else {
      throw new Error("unsupported equipment slot");
    }
    byAssetId.set(row.asset_id, row);
    if (row.server_item_id === null) {
      assert(row.item_mapping_status === "UNRESOLVED_NO_CANONICAL_ITEM_ID",
        "missing item ID must remain explicitly unresolved");
    } else {
      assert(typeof row.server_item_id === "string" && row.server_item_id.trim(),
        "invalid server item identifier");
      assert(["CURRENT_SERVER_ID", "D007_SOURCE_CANDIDATE_ONLY"].includes(row.item_mapping_status),
        "unsupported item ID provenance status");
      const destination = row.item_mapping_status === "CURRENT_SERVER_ID"
        ? byServerItemId
        : byCandidateItemId;
      assert(!destination.has(row.server_item_id), "duplicate item identifier");
      destination.set(row.server_item_id, row);
    }
  }
  assert(byAssetId.size === allowedIds.size
    && [...allowedIds].every((assetId) => byAssetId.has(assetId)),
  "runtime rows do not exactly match the 12 admitted asset identities");
  return { manifest, items: rows, byAssetId, byServerItemId, byCandidateItemId };
}

export function resolveG009RuntimeEquipmentIdentity(
  indexOrManifest,
  identifier,
  { allowAssetId = true } = {},
) {
  if (typeof identifier !== "string" || !identifier.trim()) return null;
  let index;
  try {
    index = indexOrManifest?.byAssetId instanceof Map
      ? indexOrManifest
      : createG009RuntimeEquipmentIndex(indexOrManifest);
  } catch (_) {
    return null;
  }
  const row = index.byServerItemId.get(identifier)
    || (allowAssetId ? index.byAssetId.get(identifier) : null);
  return row ? { ...row } : null;
}
