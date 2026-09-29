import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  createG009RuntimeEquipmentIndex,
  resolveG009RuntimeEquipmentIdentity,
} from "../../js/g009_d007_runtime_identity_resolver.mjs";

const manifest = JSON.parse(await readFile(
  new URL("../../schemas/g009_d007_runtime_prerequisite_v1.json", import.meta.url),
  "utf8",
));
const index = createG009RuntimeEquipmentIndex(manifest);
assert.equal(index.items.length, 12);
assert.equal(index.byAssetId.size, 12);
assert.equal(index.byServerItemId.size, 1);
assert.equal(index.byCandidateItemId.size, 10);
assert.equal(index.items.filter((row) => row.slot === "MAIN_HAND").length, 8);
assert.equal(index.items.filter((row) => row.slot === "OFF_HAND").length, 4);

for (const assetId of manifest.owner_admission.admitted_asset_ids) {
  const row = resolveG009RuntimeEquipmentIdentity(index, assetId);
  assert.ok(row, `admitted asset must resolve: ${assetId}`);
  assert.equal(row.release_eligibility, "NOT_CLEARED");
  assert.equal(row.equip_capability, false);
}

assert.equal(
  resolveG009RuntimeEquipmentIdentity(index, "wooden_sword", { allowAssetId: false })?.asset_id,
  "WEAPON_628812E9B559",
);
assert.equal(
  resolveG009RuntimeEquipmentIdentity(index, "elf_sword", { allowAssetId: false }),
  null,
  "D007 candidate item IDs are not current server item authority",
);
assert.equal(
  resolveG009RuntimeEquipmentIdentity(index, "WEAPON_AF8287295872")?.asset_id,
  "WEAPON_AF8287295872",
  "Small Stick remains resolvable by admitted asset identity only",
);
assert.equal(resolveG009RuntimeEquipmentIdentity(index, "unadmitted_asset"), null);

const altered = structuredClone(manifest);
altered.equipment_catalog.items[0].release_eligibility = "ELIGIBLE";
assert.equal(resolveG009RuntimeEquipmentIdentity(altered, "WEAPON_628812E9B559"), null);

console.log("G009_D007_RUNTIME_IDENTITY_RESOLVER=PASS");
console.log("OWNER_ADMITTED_ASSET_IDS=12/12");
console.log("CURRENT_SERVER_ITEM_IDS=1; D007_CANDIDATE_IDS=10; UNRESOLVED_ITEM_IDS=1");
console.log("RELEASE_OR_EQUIP_AUTHORITY=UNCHANGED");
