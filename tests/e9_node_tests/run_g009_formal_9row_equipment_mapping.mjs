import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import * as THREE from "../../assets/3d_shop/p048/vendor/three.module.js";
import { createG009SharedHeroAttachmentHost } from "../../js/g009_shared_hero_attachment_host.js";
import { createG009RuntimeEquipmentIndex } from "../../js/g009_d007_runtime_identity_resolver.mjs";
import {
  G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS,
  G009_OWNER_FORMAL_MAPPING_AUTHORITY,
  G009_OWNER_INTENTIONALLY_UNMAPPED_ITEM_IDS,
  G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS,
  resolveG009OwnerApprovedRuntimeEquipmentIdentity,
} from "../../js/g009_owner_approved_formal_equipment_mapping.js";
import {
  G009_FORMAL9_RETIRED_ASSET_IDS,
  G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED,
} from "../../js/g009_formal9_rights_cleared_replacement_catalog.js";
import { projectServerEquippedHandItems } from "../../js/g009_equipment_inventory_projection.js";
import { createHeroEquipmentAttachmentAdapter } from "../../js/hero_equipment_attachment_adapter.js";

const rootPath = fileURLToPath(new URL("../../", import.meta.url));
const schema = JSON.parse(await readFile(
  new URL("../../schemas/g009_d007_runtime_prerequisite_v1.json", import.meta.url),
  "utf8",
));
const g008 = JSON.parse(await readFile(
  new URL("../../schemas/future30_c005_real_asset_runtime_mapping_manifest.json", import.meta.url),
  "utf8",
));
const equipmentIndex = createG009RuntimeEquipmentIndex(schema);
const canonicalKeys = new Set(g008.roster.map((row) => row.character_id));
assert(canonicalKeys.has("A1"), "fixture character must use a canonical G008 character key");
assert.equal(G009_OWNER_FORMAL_MAPPING_AUTHORITY.task_id,
  "D_G009_OWNER_APPROVED_9ROW_FORMAL_MAPPING_AUTHORITY_001");
assert.equal(G009_OWNER_FORMAL_MAPPING_AUTHORITY.md_sha256,
  "6b521ab04b0d2bcafe1496d63e8304123a7298f4d94d6661088cdc60a10403f3");
assert.equal(G009_OWNER_FORMAL_MAPPING_AUTHORITY.json_sha256,
  "7a529c0d6ca15f41647e416d78949a2f8056f17dc149477cc805709a0cdd75aa");

const expectedMapped = [
  ["iron_sword", "WEAPON_C43E15596CA6", "/assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_c43e15596ca6.glb", "c43e15596ca656355553585e3ac4a398b37a0216471539e8dda6401d67b7580b"],
  ["fox_fang", "WEAPON_6F06505A7BED", "/assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_6f06505a7bed.glb", "6f06505a7bed0ea7681216df58d2a89696b2305f9c080b5f0fa4d9fcabc72af0"],
  ["riverstone_sabre", "WEAPON_EC86CE30E759", "/assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_ec86ce30e759.glb", "ec86ce30e7591bc89badac98a4ed0c00b6614ac8e97b8b79ea734ba7f82c2409"],
  ["bamboo_shadow_blade", "WEAPON_C84A8635BED2", "/assets/3d_shop/formal9_rights_cleared_v1/weapons/weapon_c84a8635bed2.glb", "c84a8635bed2d2252a6937dbd8837c585872502a4253f549a7b94069e7b776c6"],
];
const retiredByItem = {
  iron_sword: "WEAPON_A7C05D43F943",
  fox_fang: "WEAPON_A70FD7AB666C",
  riverstone_sabre: "WEAPON_9CD401DADF4C",
  bamboo_shadow_blade: "WEAPON_2F4CB085CE4A",
};
assert.equal(G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS.length, 4);
assert.equal(new Set(G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS.map((row) => row.server_item_id)).size, 4,
  "formal owner mapping must reject duplicate server IDs");
assert.equal(new Set(G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS.map((row) => row.asset_id)).size, 4,
  "formal owner mapping must reject duplicate asset bindings");

const formalDescriptors = new Map();
for (const [itemId, assetId, runtimeAsset, runtimeSha256] of expectedMapped) {
  const descriptor = resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, itemId, "MAIN_HAND");
  assert(descriptor, itemId + " must resolve from explicit Owner authority");
  assert.equal(descriptor.server_item_id, itemId);
  assert.equal(descriptor.asset_id, assetId);
  assert.equal(descriptor.presentation_id, assetId);
  assert.equal(descriptor.runtime_asset, runtimeAsset);
  assert.equal(descriptor.runtime_sha256, runtimeSha256);
  assert.equal(descriptor.item_mapping_status, "OWNER_APPROVED_FORMAL_MAPPING");
  assert.equal(descriptor.authority_md_sha256, G009_OWNER_FORMAL_MAPPING_AUTHORITY.md_sha256);
  assert.equal(descriptor.authority_json_sha256, G009_OWNER_FORMAL_MAPPING_AUTHORITY.json_sha256);
  assert.equal(descriptor.slot, "MAIN_HAND");
  assert.equal(descriptor.equip_capability, false);
  assert.equal(descriptor.release_eligibility, G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED);
  assert.deepEqual(descriptor.rights, G009_RIGHTS_CLEARED_FORMAL_ASSET_RIGHTS);
  assert.equal(descriptor.rights.RIGHTS_STATUS, "RIGHTS_CLEARED");
  assert.notEqual(descriptor.asset_id, retiredByItem[itemId], itemId + " must not keep its retired visual");
  assert(!G009_FORMAL9_RETIRED_ASSET_IDS.includes(descriptor.asset_id));
  for (const field of ["EQUIP_ENABLED", "SHOP_ENABLED", "PURCHASE_ENABLED", "DROP_ENABLED",
    "PLAYER_SELECTABLE", "RELEASE_ENABLED", "PRODUCTION_ASSET_ADMISSION"]) {
    assert.equal(descriptor.rights[field], false, `${itemId} ${field} must remain closed`);
  }
  assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, itemId, "OFF_HAND"), null,
    "the four Owner mappings are main-hand presentations only");
  const bytes = await readFile(resolve(rootPath, runtimeAsset.slice(1)));
  assert.equal(createHash("sha256").update(bytes).digest("hex"), runtimeSha256,
    itemId + " exact GLB bytes must match Owner-authorized SHA256");
  formalDescriptors.set(assetId, descriptor);
}

assert.equal(G009_OWNER_INTENTIONALLY_UNMAPPED_ITEM_IDS.length, 5);
for (const itemId of G009_OWNER_INTENTIONALLY_UNMAPPED_ITEM_IDS) {
  assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, itemId, "MAIN_HAND"), null,
    itemId + " must remain intentionally unmapped");
  const projection = projectServerEquippedHandItems([
    { item_id: itemId, slot: "weapon", equipped: true },
  ], (id, slot) => resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, id, slot));
  assert.equal(projection.slots[0].status, "failed_closed");
  assert.equal(projection.slots[0].reason, "equipped_item_unmapped");
}
assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, "unknown_weapon", "MAIN_HAND"), null);
assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, "adventure_sword", "MAIN_HAND"), null,
  "D007 candidate item aliases are not formal mapping authority");
for (const retiredId of G009_FORMAL9_RETIRED_ASSET_IDS) {
  for (const slot of ["MAIN_HAND", "OFF_HAND"]) {
    assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, retiredId, slot), null,
      retiredId + " is retired and must not resolve as an item or alias");
  }
}
for (const candidateAlias of ["katana", "hunting_knife", "army_sword", "adventure_sword"]) {
  assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, candidateAlias, "MAIN_HAND"), null,
    candidateAlias + " D007 candidate alias must not reach a retired visual");
}

const wooden = resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, "wooden_sword", "MAIN_HAND");
assert(wooden, "Wooden Sword existing exact mapping must remain resolvable");
assert.equal(wooden.asset_id, "WEAPON_628812E9B559");
assert.equal(wooden.runtime_asset, "/assets/3d_shop/formal_character_equipment_v1/weapons/01_wooden_sword.glb");
assert.equal(wooden.runtime_sha256, "628812e9b559b3282c5cac39aeee1f52be5f4134b44c81ae87a91c16f3d509ec");
assert.equal(wooden.item_mapping_status, "CURRENT_SERVER_ID");

const displayNameOnly = projectServerEquippedHandItems([{
  display_name: "Adventure Sword",
  filename: "21_adventure_sword.glb",
  asset_id: "WEAPON_A7C05D43F943",
  slot: "weapon",
  equipped: true,
}], (id, slot) => resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, id, slot));
assert.equal(displayNameOnly.slots[0].status, "failed_closed", "names, filenames, and client asset IDs are not authority");

const duplicateAssetSchema = structuredClone(schema);
duplicateAssetSchema.equipment_catalog.items[1].asset_id = duplicateAssetSchema.equipment_catalog.items[0].asset_id;
assert.throws(() => createG009RuntimeEquipmentIndex(duplicateAssetSchema), /duplicate equipment asset identity/,
  "duplicate asset IDs in the D007 catalog must fail closed");

// A retired D007 row that is still present in the historical catalog must not
// be served for its former item, and the replacement does not depend on it.
const withoutD007Formal9 = {
  byAssetId: new Map([...equipmentIndex.byAssetId]
    .filter(([assetId]) => !G009_FORMAL9_RETIRED_ASSET_IDS.includes(assetId))),
};
for (const [itemId, assetId] of expectedMapped) {
  assert.equal(resolveG009OwnerApprovedRuntimeEquipmentIdentity(withoutD007Formal9, itemId, "MAIN_HAND")?.asset_id, assetId,
    itemId + " replacement must not depend on retired D007 rows");
}
assert.throws(() => { G009_OWNER_APPROVED_FORMAL_EQUIPMENT_ROWS[0].asset_id = "WEAPON_A7C05D43F943"; }, TypeError,
  "replacement bindings are frozen; no alias can be written at runtime");

// Fixture scene/root/mesh nodes and loader are TEST ONLY. Mapping descriptors
// above come from the exact checked-in D007 catalog plus immutable Owner IDs.
// TEST ONLY: every Future30 Hero ships hand.R / hand.L joints; the fixture
// mirrors that so hand slots can resolve their bone-driven anchors.
function addTestOnlyHandBones(character) {
  const arm = new THREE.Bone();
  arm.name = "TEST_ONLY_upper_arm";
  arm.position.set(0, 1.4, 0);
  character.add(arm);
  for (const [name, x] of [["hand.R", -0.62], ["hand.L", 0.62]]) {
    const bone = new THREE.Bone();
    bone.name = name;
    bone.position.set(x, 0, 0.05);
    arm.add(bone);
  }
  return character;
}

const scene = new THREE.Group();
const characterRoot = new THREE.Group();
characterRoot.name = "TEST_ONLY_F_OWNED_CANONICAL_CHARACTER_A1";
const characterBody = new THREE.Mesh(
  new THREE.BoxGeometry(1, 2, 0.8),
  new THREE.MeshBasicMaterial(),
);
characterBody.position.y = 1;
characterRoot.add(characterBody);
addTestOnlyHandBones(characterRoot);
scene.add(characterRoot);
const host = createG009SharedHeroAttachmentHost(characterRoot, THREE);
formalDescriptors.set(wooden.presentation_id, wooden);
const fixtureDescriptors = new Map();
function testOnlyDescriptor(slot, id, extra = {}) {
  const descriptor = Object.freeze({
    presentation_id: id,
    slot,
    test_only: true,
    fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED",
    ...extra,
  });
  fixtureDescriptors.set(id, descriptor);
  return descriptor;
}
host.registerResolver("MAIN_HAND", (id) => formalDescriptors.get(id) || fixtureDescriptors.get(id) || null);
host.registerResolver("OFF_HAND", (id) => fixtureDescriptors.get(id) || null);
for (const slot of ["HEAD", "BACK", "AURA", "COMPANION"]) {
  host.registerResolver(slot, (id) => fixtureDescriptors.get(id) || null);
}

const SLOTS = ["MAIN_HAND", "OFF_HAND", "HEAD", "BACK", "AURA", "COMPANION"];
const nodeFor = (slot) => slot === "CHARACTER"
  ? characterRoot
  : characterRoot.children.find((child) => child.name === "G009_SHARED_HERO_SLOT_" + slot)?.children[0] || null;
const loaderPending = new Map();
const adapter = createHeroEquipmentAttachmentAdapter({ getHeroSharedAttachmentHost: () => host }, {
  allowTestOnlyDescriptors: true,
  loadPresentation: async (descriptor) => {
    if (descriptor.server_item_id === "riverstone_sabre") {
      return new Promise((resolveLoad) => loaderPending.set(descriptor.server_item_id, resolveLoad));
    }
    const node = new THREE.Group();
    node.name = "TEST_ONLY_LOADED_" + descriptor.presentation_id;
    return node;
  },
});
const appearance = {
  character_key: "A1",
  character_key_source: "player_appearance.character_key",
  character_key_authority: "player_appearance.character_key",
  character_entitled: true,
  character_runtime: { character_key: "A1" },
  fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED",
};

const testOnlyOffHand = testOnlyDescriptor("OFF_HAND", "TEST_ONLY_OFF_HAND_FIXTURE");
for (const slot of ["HEAD", "BACK", "AURA", "COMPANION"]) {
  const descriptor = testOnlyDescriptor(slot, "TEST_ONLY_" + slot + "_FIXTURE");
  await host.attach(slot, descriptor.presentation_id, async () => {
    const node = new THREE.Group();
    node.name = descriptor.presentation_id;
    return node;
  });
}
await adapter.setHand("MAIN_HAND", wooden, appearance);
await adapter.setHand("OFF_HAND", testOnlyOffHand, appearance);
for (const slot of ["CHARACTER", ...SLOTS]) assert(nodeFor(slot), slot + " must coexist in the shared host fixture");

let before = new Map(["CHARACTER", ...SLOTS].map((slot) => [slot, nodeFor(slot)]));
await adapter.setHand("MAIN_HAND", formalDescriptors.get("WEAPON_6F06505A7BED"), appearance);
for (const [slot, node] of before) {
  if (slot !== "MAIN_HAND") assert.equal(nodeFor(slot), node, "MAIN_HAND replacement must preserve " + slot);
}
assert.notEqual(nodeFor("MAIN_HAND"), before.get("MAIN_HAND"));

const stalePromise = adapter.setHand("MAIN_HAND", formalDescriptors.get("WEAPON_EC86CE30E759"), appearance);
before = new Map(["CHARACTER", ...SLOTS].map((slot) => [slot, nodeFor(slot)]));
await adapter.setHand("MAIN_HAND", formalDescriptors.get("WEAPON_C84A8635BED2"), appearance);
const staleNode = new THREE.Group();
loaderPending.get("riverstone_sabre")(staleNode);
assert.equal((await stalePromise).status, "stale");
assert.equal(staleNode.parent, null);
for (const [slot, node] of before) {
  if (slot !== "MAIN_HAND") assert.equal(nodeFor(slot), node, "stale MAIN_HAND load must preserve " + slot);
}
assert.equal(nodeFor("MAIN_HAND").name, "TEST_ONLY_LOADED_WEAPON_C84A8635BED2");

const beforeDetach = new Map(["CHARACTER", ...SLOTS].map((slot) => [slot, nodeFor(slot)]));
adapter.detach("OFF_HAND");
assert.equal(nodeFor("OFF_HAND"), null);
for (const [slot, node] of beforeDetach) {
  if (slot !== "OFF_HAND") assert.equal(nodeFor(slot), node, "OFF_HAND detach must preserve " + slot);
}
await adapter.setHand("OFF_HAND", testOnlyOffHand, appearance);
before = new Map(["CHARACTER", ...SLOTS].map((slot) => [slot, nodeFor(slot)]));
adapter.dispose();
assert.equal(nodeFor("MAIN_HAND"), null);
assert.equal(nodeFor("OFF_HAND"), null);
for (const slot of ["CHARACTER", "HEAD", "BACK", "AURA", "COMPANION"]) {
  assert.equal(nodeFor(slot), before.get(slot), "equipment adapter dispose must preserve " + slot);
}
assert.equal(host.diagnostics().disposed, false, "equipment adapter must not dispose the F-owned shared host");
host.destroy();

console.log("FORMAL9_MAPPED=4/4 Owner-selected rights-cleared replacement IDs, paths, and GLB SHA256 verified");
console.log("FORMAL9_INTENTIONALLY_UNMAPPED=5/5 fail-closed");
console.log("WOODEN_SWORD_UNCHANGED=PASS");
console.log("RETIRED_D007_FORMAL9_VISUALS=4/4 fail-closed (item, alias, asset ID)");
console.log("UNKNOWN_DUPLICATE_MISSING_NO_INFERENCE_WRONG_MODEL=PASS fail-closed");
console.log("RIGHTS_STATUS=RIGHTS_CLEARED; EQUIP_CAPABILITY=false; RELEASE_ELIGIBILITY=" + G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED);
console.log("FORMAL_MAIN_HAND_SHARED_HOST_FIXTURE=PASS; other slot descriptors TEST ONLY");
console.log("CROSS_SLOT_PRESERVATION=PASS");
console.log("STALE_ASYNC_PROTECTION=PASS");
console.log("DETACH_DISPOSE=PASS");
console.log("AUTHENTICATED_LIVE_COEXISTENCE=NOT_CLAIMED");
