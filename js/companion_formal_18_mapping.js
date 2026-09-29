export const COMPANION_FORMAL_18_MANIFEST_URL =
  "/assets/3d_shop/p048/companion/formal_18/mapping_manifest.json";

export const COMPANION_FORMAL_18_PET_KEYS = Object.freeze([
  "ink_drop_kelpie",
  "whispering_void_kit",
  "star_shell_hatchling",
  "starpath_antlerling",
  "fatty",
  "obsidian_bastion",
]);

const EXPECTED_AUTHORITY = Object.freeze({
  task_id: "A_G009_COMPANION_FORMAL_18_MAPPING_CLOSURE_001",
  owner_approval_sha256: "7F763F86718A5CD15193053B0C12A1D790F78801362DABCCB0ED283A78CF5AA7",
  mapping_markdown_sha256: "11A013FF35481119E2724A36BBEDB60AB5C885F44BBD81F13ABEC60A6120CC7A",
  mapping_json_sha256: "ABF2DCEB43139B022A0156F4EE8A5B15D61409E4A5949B56480BB66E86D5A24D",
  handoff_sha256: "F99769E48D4910B43B9D307A91D0FB16EFE74BC9DB0B85A94D61AA8E9812ACA0",
});

const STAGE_RULES = Object.freeze({
  I: "persistent_server_pet_level < 10",
  II: "persistent_server_pet_level >= 10 AND <= 24",
  III: "persistent_server_pet_level >= 25",
});

function fail(code, message) {
  const error = new Error(message);
  error.code = code;
  throw error;
}

export function companionStageForPersistentLevel(level) {
  if (!Number.isSafeInteger(level) || level < 1) {
    fail("INVALID_PERSISTENT_PET_LEVEL", "persistent server pet level must be a positive integer");
  }
  if (level >= 25) return "III";
  if (level >= 10) return "II";
  return "I";
}

export function validateCompanionFormal18Manifest(manifest) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    fail("COMPANION_MAPPING_MANIFEST_INVALID", "formal Companion mapping manifest is required");
  }
  for (const [key, expected] of Object.entries(EXPECTED_AUTHORITY)) {
    if (manifest[key] !== expected) {
      fail("COMPANION_MAPPING_AUTHORITY_MISMATCH", `formal Companion authority mismatch: ${key}`);
    }
  }
  if (manifest.owner_approved_18_18 !== true || manifest.mapping_count !== 18) {
    fail("COMPANION_MAPPING_AUTHORITY_MISMATCH", "formal Companion mapping is not Owner-approved 18/18");
  }
  if (JSON.stringify(manifest.canonical_pet_keys) !== JSON.stringify(COMPANION_FORMAL_18_PET_KEYS)) {
    fail("COMPANION_PET_ROSTER_MISMATCH", "formal Companion canonical pet roster changed");
  }
  if (manifest.stage_authority?.source !== "Persistent server pet level only.") {
    fail("COMPANION_STAGE_AUTHORITY_MISMATCH", "Companion stage must derive from persistent server level");
  }
  for (const [stage, rule] of Object.entries(STAGE_RULES)) {
    if (manifest.stage_authority?.rules?.[stage] !== rule) {
      fail("COMPANION_STAGE_AUTHORITY_MISMATCH", `formal Companion stage rule changed: ${stage}`);
    }
  }
  if (!Array.isArray(manifest.mappings) || manifest.mappings.length !== 18) {
    fail("COMPANION_MAPPING_COUNT_MISMATCH", "formal Companion mapping must contain exactly 18 rows");
  }

  const canonical = new Set(COMPANION_FORMAL_18_PET_KEYS);
  const tuples = new Set();
  const counts = new Map(COMPANION_FORMAL_18_PET_KEYS.map((key) => [key, new Set()]));
  for (const row of manifest.mappings) {
    if (!row || !canonical.has(row.pet_key) || !Object.hasOwn(STAGE_RULES, row.stage)) {
      fail("COMPANION_MAPPING_ROW_INVALID", "formal Companion mapping row has an unknown pet or stage");
    }
    const tuple = `${row.pet_key}|${row.stage}`;
    if (tuples.has(tuple)) fail("COMPANION_MAPPING_DUPLICATE", "duplicate canonical pet_key + stage mapping");
    tuples.add(tuple);
    counts.get(row.pet_key).add(row.stage);
    if (row.level_rule !== STAGE_RULES[row.stage]) {
      fail("COMPANION_STAGE_AUTHORITY_MISMATCH", `mapping row stage rule changed: ${tuple}`);
    }
    if (typeof row.runtime_glb !== "string"
      || !row.runtime_glb.startsWith("assets/3d_shop/p048/companion/formal_18/")
      || row.runtime_glb.split("/").includes("..")
      || row.runtime_glb.includes("\\")
      || !row.runtime_glb.endsWith(".glb")) {
      fail("COMPANION_RUNTIME_PATH_REJECTED", `formal Companion runtime path rejected: ${tuple}`);
    }
    if (typeof row.asset_sha256 !== "string" || !/^[a-f0-9]{64}$/i.test(row.asset_sha256)
      || !Number.isSafeInteger(row.asset_bytes) || row.asset_bytes <= 0) {
      fail("COMPANION_ASSET_IDENTITY_INVALID", `formal Companion asset integrity metadata invalid: ${tuple}`);
    }
  }
  for (const key of COMPANION_FORMAL_18_PET_KEYS) {
    if (counts.get(key).size !== 3 || Object.keys(STAGE_RULES).some((stage) => !counts.get(key).has(stage))) {
      fail("COMPANION_MAPPING_INCOMPLETE", `formal Companion mapping is incomplete: ${key}`);
    }
  }
  return manifest;
}

export async function fetchCompanionFormal18Manifest(fetchImpl = fetch) {
  const response = await fetchImpl(COMPANION_FORMAL_18_MANIFEST_URL, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response?.ok) {
    fail("COMPANION_MAPPING_UNAVAILABLE", `formal Companion mapping HTTP ${response?.status || "error"}`);
  }
  return validateCompanionFormal18Manifest(await response.json());
}

/** Resolve from the authenticated /api/pet/status pet projection only. */
export function resolveCompanionPresentation(serverPet, manifest) {
  validateCompanionFormal18Manifest(manifest);
  if (!serverPet || typeof serverPet !== "object" || Array.isArray(serverPet)) {
    fail("COMPANION_SERVER_PET_REQUIRED", "server pet projection is required");
  }
  const petKey = serverPet.pet_key;
  if (typeof petKey !== "string" || !COMPANION_FORMAL_18_PET_KEYS.includes(petKey)) {
    fail("UNKNOWN_COMPANION_PET_KEY", "server pet_key is not a canonical Companion identity");
  }
  const level = serverPet.level;
  const stage = companionStageForPersistentLevel(level);
  const row = manifest.mappings.find((candidate) => candidate.pet_key === petKey && candidate.stage === stage);
  if (!row) fail("COMPANION_PRESENTATION_UNMAPPED", "canonical Companion stage has no approved runtime mapping");
  return Object.freeze({
    source: "/api/pet/status.pet_key+level",
    pet_key: petKey,
    level,
    stage,
    presentation: row,
  });
}
