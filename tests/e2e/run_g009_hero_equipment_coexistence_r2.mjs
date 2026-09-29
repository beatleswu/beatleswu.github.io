import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import * as THREE from "../../assets/3d_shop/p048/vendor/three.module.js";
import { createG009SharedHeroAttachmentHost } from "../../js/g009_shared_hero_attachment_host.js";
import { createG009RuntimeEquipmentIndex, resolveG009RuntimeEquipmentIdentity } from "../../js/g009_d007_runtime_identity_resolver.mjs";
import { resolveG009OwnerApprovedRuntimeEquipmentIdentity } from "../../js/g009_owner_approved_formal_equipment_mapping.js";
import { projectServerEquippedHandItems } from "../../js/g009_equipment_inventory_projection.js";
import { createHeroEquipmentAttachmentAdapter } from "../../js/hero_equipment_attachment_adapter.js";
import { G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED } from "../../js/g009_formal9_rights_cleared_replacement_catalog.js";

const g008 = JSON.parse(await readFile(
  new URL("../../schemas/future30_c005_real_asset_runtime_mapping_manifest.json", import.meta.url),
  "utf8",
));
const d007Schema = JSON.parse(await readFile(
  new URL("../../schemas/g009_d007_runtime_prerequisite_v1.json", import.meta.url),
  "utf8",
));
const eHtml = await readFile(new URL("../../hero.html", import.meta.url), "utf8");
const equipmentBootstrap = await readFile(new URL("../../js/g009_d_r2_shared_host_bootstrap.js", import.meta.url), "utf8");
const canonicalKeys = new Set(g008.roster.map((row) => row.character_id));
assert(canonicalKeys.has("A1") && canonicalKeys.has("A3"), "known canonical keys must come from the G008 manifest");
assert(eHtml.includes("/js/g009_d_r2_shared_host_bootstrap.js"));
assert(equipmentBootstrap.includes("/api/player/inventory"));
assert(!equipmentBootstrap.includes("new THREE.WebGLRenderer"));
assert(!equipmentBootstrap.includes("method: \"POST\""));

const equipmentIndex = createG009RuntimeEquipmentIndex(d007Schema);
const resolveCurrentServerItem = (itemId, slot) => {
  const row = resolveG009OwnerApprovedRuntimeEquipmentIdentity(equipmentIndex, itemId, slot);
  if (!row || row.server_item_id !== itemId || row.slot !== slot
    || row.equip_capability !== false
    || !["NOT_CLEARED", G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED].includes(row.release_eligibility)) return null;
  return { ...row, presentation_id: row.asset_id, slot: row.slot };
};
const wooden = projectServerEquippedHandItems([
  { item_id: "wooden_sword", slot: "weapon", equipped: true },
], resolveCurrentServerItem);
assert.equal(wooden.slots[0].status, "resolved");
assert.equal(wooden.slots[0].descriptor.asset_id, "WEAPON_628812E9B559");
const iron = projectServerEquippedHandItems([
  { item_id: "iron_sword", slot: "weapon", equipped: true },
], resolveCurrentServerItem);
assert.equal(iron.slots[0].status, "resolved");
assert.equal(iron.slots[0].descriptor.asset_id, "WEAPON_C43E15596CA6");
assert.equal(iron.slots[0].descriptor.rights.RIGHTS_STATUS, "RIGHTS_CLEARED");
assert.equal(iron.slots[0].descriptor.release_eligibility, G009_RIGHTS_CLEARED_RELEASE_NOT_ADMITTED);
assert.equal(wooden.slots[1].status, "empty");
assert.equal(projectServerEquippedHandItems([
  { item_id: "dragon_claw", slot: "weapon", equipped: true },
], resolveCurrentServerItem).slots[0].status, "failed_closed");
assert.equal(projectServerEquippedHandItems([
  { display_name: "Wooden Sword", slot: "weapon", equipped: true },
], resolveCurrentServerItem).slots[0].status, "failed_closed");
assert.equal(projectServerEquippedHandItems([
  { item_id: "wooden_sword", slot: "weapon", equipped: true },
  { item_id: "wooden_sword", slot: "weapon", equipped: true },
], resolveCurrentServerItem).slots[0].status, "failed_closed");

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

const SLOTS = ["MAIN_HAND", "OFF_HAND", "HEAD", "BACK", "AURA", "COMPANION"];
const ALL = ["CHARACTER", ...SLOTS];
const scene = new THREE.Group();
scene.name = "TEST_ONLY_SCENE_WITH_F_OWNED_CHARACTER";
const characterRoot = new THREE.Group();
characterRoot.name = "F_OWNED_CHARACTER_A1_TEST_FIXTURE";
const body = new THREE.Mesh(new THREE.BoxGeometry(1, 2, 0.8), new THREE.MeshBasicMaterial());
body.position.y = 1;
characterRoot.add(body);
addTestOnlyHandBones(characterRoot);
scene.add(characterRoot);

const host = createG009SharedHeroAttachmentHost(characterRoot, THREE);
const fixtureDescriptors = new Map();
const pending = new Map();
const loaderCalls = [];

function addTestOnlyDescriptor(slot, id, { defer = false } = {}) {
  const descriptor = Object.freeze({
    presentation_id: id,
    slot,
    test_only: true,
    fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED",
    ...(defer ? { defer: true } : {}),
  });
  fixtureDescriptors.set(id, descriptor);
  return descriptor;
}

for (const slot of SLOTS) {
  host.registerResolver(slot, (id) => fixtureDescriptors.get(id) || null);
}

function makeHostNode(name) {
  const node = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.2, 0.2), new THREE.MeshBasicMaterial());
  node.name = name;
  node.userData.test_only = true;
  return node;
}

async function loadPresentation(descriptor, context) {
  loaderCalls.push({ descriptor, ...context });
  assert.equal(descriptor.test_only, true, "all equipment/item descriptors in this fixture must stay TEST ONLY");
  if (descriptor.defer) {
    const promise = new Promise((resolve) => pending.set(descriptor.presentation_id, resolve));
    return promise;
  }
  return makeHostNode(descriptor.presentation_id);
}

const runtime = { getHeroSharedAttachmentHost: () => host };
const adapter = createHeroEquipmentAttachmentAdapter(runtime, {
  loadPresentation,
  allowTestOnlyDescriptors: true,
});
const appearance = (key) => ({
  character_key: key,
  character_key_source: "player_appearance.character_key",
  character_key_authority: "player_appearance.character_key",
  character_entitled: true,
  character_runtime: { character_key: key },
  fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED",
});

function nodeFor(slot) {
  if (slot === "CHARACTER") return characterRoot;
  const anchor = characterRoot.children.find((child) => child.name === "G009_SHARED_HERO_SLOT_" + slot);
  return anchor?.children[0] || null;
}

function assertSlotPresent(slot) {
  const node = nodeFor(slot);
  assert(node, slot + " fixture must be attached");
  assert.equal(node.parent, slot === "CHARACTER"
    ? scene
    : characterRoot.children.find((child) => child.name === "G009_SHARED_HERO_SLOT_" + slot));
}

function capture() {
  return new Map(ALL.map((slot) => [slot, nodeFor(slot)]));
}

function assertOthersPreserved(changed, before) {
  for (const [slot, node] of before) {
    if (slot === changed) continue;
    assert.equal(nodeFor(slot), node, changed + " operation replaced " + slot);
    if (node) assertSlotPresent(slot);
  }
}

async function attachFixtureSlot(slot, id) {
  addTestOnlyDescriptor(slot, id);
  return host.attach(slot, id, async (resolved) => makeHostNode(resolved.presentation_id));
}

addTestOnlyDescriptor("MAIN_HAND", "TEST_ONLY_MAIN_HAND_A");
addTestOnlyDescriptor("OFF_HAND", "TEST_ONLY_OFF_HAND_A");
for (const slot of ["HEAD", "BACK", "AURA", "COMPANION"]) {
  await attachFixtureSlot(slot, "TEST_ONLY_" + slot + "_A");
}
await adapter.setHand("MAIN_HAND", fixtureDescriptors.get("TEST_ONLY_MAIN_HAND_A"), appearance("A1"));
await adapter.setHand("OFF_HAND", fixtureDescriptors.get("TEST_ONLY_OFF_HAND_A"), appearance("A1"));
for (const slot of ALL) assertSlotPresent(slot);
assert(loaderCalls.every((call) => call.character_key === "A1"), "hand loader must receive the F-validated character key");

// Replacing either hand changes only that one shared-host child slot.
let before = capture();
addTestOnlyDescriptor("MAIN_HAND", "TEST_ONLY_MAIN_HAND_B");
await adapter.setHand("MAIN_HAND", fixtureDescriptors.get("TEST_ONLY_MAIN_HAND_B"), appearance("A1"));
assertOthersPreserved("MAIN_HAND", before);
before = capture();
addTestOnlyDescriptor("OFF_HAND", "TEST_ONLY_OFF_HAND_B");
await adapter.setHand("OFF_HAND", fixtureDescriptors.get("TEST_ONLY_OFF_HAND_B"), appearance("A1"));
assertOthersPreserved("OFF_HAND", before);
for (const slot of ALL) assertSlotPresent(slot);

// A missing/untrusted character context or unknown exact presentation ID
// fails closed without destroying other slots. F owns canonical-key lookup.
const callsBeforeInvalid = loaderCalls.length;
await assert.rejects(
  () => adapter.setHand("MAIN_HAND", fixtureDescriptors.get("TEST_ONLY_MAIN_HAND_B"), { character_key: "A1" }),
  (error) => error?.code === "CHARACTER_AUTHORITY_REQUIRED",
);
assert.equal(loaderCalls.length, callsBeforeInvalid);
before = capture();
await assert.rejects(
  () => adapter.setHand("MAIN_HAND", {
    presentation_id: "UNKNOWN_TEST_ONLY_MAIN_HAND",
    slot: "MAIN_HAND",
    test_only: true,
    fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED",
  }, appearance("A1")),
  /unknown_hero_presentation/,
);
assertOthersPreserved("MAIN_HAND", before);

// Latest MAIN_HAND request wins after older async completion.
const oldMain = addTestOnlyDescriptor("MAIN_HAND", "TEST_ONLY_MAIN_HAND_OLD_ASYNC", { defer: true });
const pendingMain = adapter.setHand("MAIN_HAND", oldMain, appearance("A1"));
const currentMain = addTestOnlyDescriptor("MAIN_HAND", "TEST_ONLY_MAIN_HAND_CURRENT");
await adapter.setHand("MAIN_HAND", currentMain, appearance("A1"));
const staleMain = makeHostNode("TEST_ONLY_MAIN_HAND_STALE_ROOT");
pending.get(oldMain.presentation_id)(staleMain);
assert.equal((await pendingMain).status, "stale");
assert.equal(nodeFor("MAIN_HAND").name, "TEST_ONLY_MAIN_HAND_CURRENT");
assert.equal(staleMain.parent, null);

// OFF_HAND detach and adapter dispose invalidate pending loads but preserve
// the shared host, F-owned character, and the other four child slots.
const oldOff = addTestOnlyDescriptor("OFF_HAND", "TEST_ONLY_OFF_HAND_BEFORE_DETACH", { defer: true });
const pendingOff = adapter.setHand("OFF_HAND", oldOff, appearance("A1"));
const beforeOffDetach = capture();
adapter.detach("OFF_HAND");
const staleOff = makeHostNode("TEST_ONLY_OFF_HAND_STALE_AFTER_DETACH");
pending.get(oldOff.presentation_id)(staleOff);
assert.equal((await pendingOff).status, "stale");
assert.equal(nodeFor("OFF_HAND"), null);
assert.equal(staleOff.parent, null);
assertOthersPreserved("OFF_HAND", beforeOffDetach);

addTestOnlyDescriptor("OFF_HAND", "TEST_ONLY_OFF_HAND_BEFORE_DISPOSE", { defer: true });
const pendingDispose = adapter.setHand(
  "OFF_HAND", fixtureDescriptors.get("TEST_ONLY_OFF_HAND_BEFORE_DISPOSE"), appearance("A1"),
);
const beforeDispose = capture();
adapter.dispose();
const staleDispose = makeHostNode("TEST_ONLY_OFF_HAND_STALE_AFTER_DISPOSE");
pending.get("TEST_ONLY_OFF_HAND_BEFORE_DISPOSE")(staleDispose);
assert.equal((await pendingDispose).status, "stale");
assert.equal(staleDispose.parent, null);
assert.equal(nodeFor("MAIN_HAND"), null);
assert.equal(nodeFor("OFF_HAND"), null);
for (const slot of ["CHARACTER", "HEAD", "BACK", "AURA", "COMPANION"]) {
  assert.equal(nodeFor(slot), beforeDispose.get(slot), slot + " preserved on adapter dispose");
  assertSlotPresent(slot);
}
assert.equal(host.diagnostics().disposed, false, "D adapter must not destroy F-owned host");

host.destroy();
assert.equal(host.diagnostics().disposed, true);
console.log("CHARACTER_KEY_AUTHORITY=PASS (F-owned A1 from G008 manifest)");
console.log("UNKNOWN_CHARACTER_CONTEXT_FAIL_CLOSED=PASS");
console.log("LEGACY_FALLBACK_FOR_UNKNOWN=ABSENT");
console.log("MAIN_HAND_ADAPTER=PASS");
console.log("OFF_HAND_ADAPTER=PASS");
console.log("ALL_SLOT_FIXTURE_COEXISTENCE=PASS (equipment descriptors TEST ONLY)");
console.log("CROSS_SLOT_PRESERVATION=PASS");
console.log("DETACH_DISPOSE=PASS");
console.log("STALE_ASYNC_PROTECTION=PASS");
console.log("FORMAL_MAPPING_CONSUMED=PASS; SERVER_MAPPING_MUTATION=NO");
