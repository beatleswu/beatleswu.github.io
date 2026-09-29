import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  COMPANION_FORMAL_18_PET_KEYS,
  companionStageForPersistentLevel,
  resolveCompanionPresentation,
  validateCompanionFormal18Manifest,
} from "../../js/companion_formal_18_mapping.js";

const manifest = JSON.parse(await readFile(
  new URL("../../assets/3d_shop/p048/companion/formal_18/mapping_manifest.json", import.meta.url),
  "utf8",
));
assert.equal(validateCompanionFormal18Manifest(manifest), manifest);
assert.deepEqual(manifest.canonical_pet_keys, COMPANION_FORMAL_18_PET_KEYS);
assert.equal(manifest.mappings.length, 18);
assert.equal(new Set(manifest.mappings.map((row) => `${row.pet_key}|${row.stage}`)).size, 18);

for (const petKey of COMPANION_FORMAL_18_PET_KEYS) {
  for (const [level, expectedStage] of [[1, "I"], [9, "I"], [10, "II"], [24, "II"], [25, "III"], [80, "III"]]) {
    const resolved = resolveCompanionPresentation({ pet_key: petKey, level, stage: "III" }, manifest);
    assert.equal(resolved.source, "/api/pet/status.pet_key+level");
    assert.equal(resolved.pet_key, petKey);
    assert.equal(resolved.level, level);
    assert.equal(resolved.stage, expectedStage, "client stage must not override persistent level");
    assert.equal(resolved.presentation.pet_key, petKey);
    assert.equal(resolved.presentation.stage, expectedStage);
  }
}

assert.equal(companionStageForPersistentLevel(9), "I");
assert.equal(companionStageForPersistentLevel(10), "II");
assert.equal(companionStageForPersistentLevel(24), "II");
assert.equal(companionStageForPersistentLevel(25), "III");
assert.throws(
  () => resolveCompanionPresentation({ pet_key: "unknown_pet", level: 1 }, manifest),
  (error) => error?.code === "UNKNOWN_COMPANION_PET_KEY",
);
assert.throws(
  () => resolveCompanionPresentation({ level: 1 }, manifest),
  (error) => error?.code === "UNKNOWN_COMPANION_PET_KEY",
);
for (const level of [0, -1, "25", 1.5, null]) {
  assert.throws(
    () => resolveCompanionPresentation({ pet_key: "ink_drop_kelpie", level }, manifest),
    (error) => error?.code === "INVALID_PERSISTENT_PET_LEVEL",
  );
}

const duplicate = structuredClone(manifest);
duplicate.mappings[1].pet_key = duplicate.mappings[0].pet_key;
duplicate.mappings[1].stage = duplicate.mappings[0].stage;
assert.throws(
  () => validateCompanionFormal18Manifest(duplicate),
  (error) => error?.code === "COMPANION_MAPPING_DUPLICATE",
);

console.log("CANONICAL_PET_KEYS=6/6 PASS");
console.log("FORMAL_MAPPING_ROWS=18/18 PASS; duplicates=0; missing=0");
console.log("STAGE_BOUNDARIES=9:I,10:II,24:II,25:III PASS");
console.log("CLIENT_STAGE_OVERRIDE=IGNORED; persistent server level wins");
console.log("UNKNOWN_OR_MISSING_PET_KEY=FAIL_CLOSED");
