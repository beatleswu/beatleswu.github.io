import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as THREE from "../../assets/3d_shop/p048/vendor/three.module.js";
import { createG009SharedHeroAttachmentHost } from "../../js/g009_shared_hero_attachment_host.js";
import { createG009RuntimeEquipmentIndex } from "../../js/g009_d007_runtime_identity_resolver.mjs";
import {
  createG009D007PresentationIndex,
  createG009D007SharedHostAdapter,
} from "../../js/g009_d007_shared_host_adapter.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const heroHtml = await readFile(path.join(root, "hero.html"), "utf8");
const bootstrapSource = await readFile(path.join(root, "js/g009_d007_shared_host_bootstrap.js"), "utf8");
assert(heroHtml.includes("/js/g009_d007_shared_host_bootstrap.js"));
assert(!heroHtml.includes("formal_3d_character_equipment_runtime.js"));
assert(!bootstrapSource.includes("formal_3d_character_equipment_runtime.js"));
assert(!bootstrapSource.includes("new THREE.WebGLRenderer"));
const schema = JSON.parse(await readFile(path.join(root, "schemas/g009_d007_runtime_prerequisite_v1.json"), "utf8"));
const p048 = JSON.parse(await readFile(path.join(root, "assets/3d_shop/p048/runtime_manifest.json"), "utf8"));
const index = createG009D007PresentationIndex(schema, p048);
const equipmentIndex = createG009RuntimeEquipmentIndex(schema);
assert.equal(equipmentIndex.items.length, 12);
assert.equal(index.resolve("HEAD", "P045_H06_TOP_HAT").presentation_id, "P045_H06_TOP_HAT");
assert.equal(index.resolve("BACK", "P045_B02_BACKPACK").presentation_id, "P045_B02_BACKPACK");
assert.equal(index.resolve("AURA", "AURA_PRESENTATION_RING").kind, "procedural_presentation_only");
assert.equal(index.resolve("HEAD", "UNKNOWN_TEST_ONLY_HEAD"), null);

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

function makeRoot() {
  const character = new THREE.Group();
  character.name = "TEST_ONLY_authoritative_character_fixture";
  const body = new THREE.Mesh(new THREE.BoxGeometry(1, 2, 0.8), new THREE.MeshBasicMaterial());
  body.position.y = 1;
  character.add(body);
  return addTestOnlyHandBones(character);
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function snapshot(characterKey, head, back, aura) {
  const wardrobe = [];
  const equipped = {};
  for (const [slot, id, presentationId, color] of [
    ["hat", "test-head-owned", head, "#45d6c0"],
    ["back", "test-back-owned", back, "#45d6c0"],
    ["aura", "test-aura-owned", aura, "#45d6c0"],
  ]) {
    const field = slot === "hat" ? "hat_id" : slot + "_id";
    equipped[field] = presentationId ? id : null;
    if (presentationId) wardrobe.push({
      id,
      slot,
      is_equipped: true,
      color,
      presentation_mapping: { presentation_id: presentationId },
      fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED",
    });
  }
  return {
    character_key: characterKey,
    character_key_source: "player_appearance.character_key",
    character_key_authority: "player_appearance.character_key",
    character_entitled: true,
    character_runtime: { character_key: characterKey },
    equipped,
    wardrobe,
    fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED",
  };
}

let assetGate = deferred();
let delayedAssetPath = null;
let delayedStarted = null;
const requestedPaths = [];
async function fetchImpl(url) {
  const normalized = String(url).replace(/^\//, "");
  requestedPaths.push(normalized);
  if (normalized === delayedAssetPath) {
    delayedStarted?.resolve();
    await assetGate.promise;
  }
  const bytes = await readFile(path.join(root, normalized));
  return { ok: true, arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) };
}

// Parser is intentionally TEST ONLY: the fixture exercises resolver, exact
// byte verification and host lifecycle, not authenticated visual acceptance.
class TestOnlyGLTFLoader {
  async parseAsync(_bytes, url) {
    const node = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.2, 0.2), new THREE.MeshBasicMaterial());
    node.name = "TEST_ONLY_PARSED_" + path.basename(new URL(url).pathname);
    node.userData.test_only_parser = true;
    return { scene: node };
  }
}

const characterRoot = makeRoot();
const host = createG009SharedHeroAttachmentHost(characterRoot, THREE);
for (const slot of ["HEAD", "BACK", "AURA"]) {
  host.registerResolver(slot, (id) => index.resolve(slot, id));
}
const testOnlyIds = new Map([
  ["MAIN_HAND", "TEST_ONLY_MAIN_HAND"],
  ["OFF_HAND", "TEST_ONLY_OFF_HAND"],
  ["COMPANION", "TEST_ONLY_COMPANION"],
]);
for (const [slot, id] of testOnlyIds) {
  host.registerResolver(slot, (candidate) => candidate === id
    ? { presentation_id: id, slot, fixture_authority: "TEST_ONLY_NOT_AUTHENTICATED" }
    : null);
}

const adapter = createG009D007SharedHostAdapter({
  THREE,
  GLTFLoader: TestOnlyGLTFLoader,
  host,
  presentationIndex: index,
  fetchImpl,
  baseUrl: "http://localhost/hero.html",
});
const mainChild = new THREE.Object3D();
const offChild = new THREE.Object3D();
const companionChild = new THREE.Object3D();
for (const [slot, id, node] of [
  ["MAIN_HAND", testOnlyIds.get("MAIN_HAND"), mainChild],
  ["OFF_HAND", testOnlyIds.get("OFF_HAND"), offChild],
  ["COMPANION", testOnlyIds.get("COMPANION"), companionChild],
]) {
  await host.attach(slot, id, async () => node);
}

const initial = await adapter.renderServerSnapshot(snapshot(
  "A1", "P045_H06_TOP_HAT", "P045_B02_BACKPACK", "AURA_PRESENTATION_RING",
));
assert.equal(initial.authority, "player_appearance.character_key");
assert.equal(initial.formal_item_mapping_created, false);
assert.equal(initial.equip_capability, false);
assert.deepEqual(initial.slots.map((row) => row.status), ["attached", "attached", "attached"]);
assert.deepEqual(host.diagnostics().slots.map((row) => row.child_count), [1, 1, 1, 1, 1, 1]);
assert(requestedPaths.includes("assets/3d_shop/p048/head/H06_Top_Hat.glb"));
assert(requestedPaths.includes("assets/3d_shop/p048/back/B02_Backpack.glb"));

const originalHead = host.diagnostics().slots.find((row) => row.slot === "HEAD").presentation_id;
assert.equal(originalHead, "P045_H06_TOP_HAT");
const replaced = await adapter.renderServerSnapshot(snapshot(
  "A1", "P045_H06_FROG_HAT", "P045_B02_BACKPACK", "AURA_PRESENTATION_RING",
));
assert.equal(replaced.slots[0].status, "attached");
assert.equal(host.diagnostics().slots.find((row) => row.slot === "HEAD").presentation_id, "P045_H06_FROG_HAT");
for (const slot of ["BACK", "AURA", "MAIN_HAND", "OFF_HAND", "COMPANION"]) {
  assert.equal(host.diagnostics().slots.find((row) => row.slot === slot).child_count, 1, slot + " preserved on Head replacement");
}

// A newer Head request wins even if the earlier GLB completes last.
assetGate = deferred();
delayedAssetPath = "assets/3d_shop/p048/head/H06_Beanie.glb";
delayedStarted = deferred();
const olderHead = adapter.renderServerSnapshot(snapshot("A1", "P045_H06_BEANIE", null, null));
await delayedStarted.promise;
delayedAssetPath = null;
const newerHead = await adapter.renderServerSnapshot(snapshot("A1", "P045_H06_SANTA_HAT", null, null));
assert.equal(newerHead.slots[0].status, "attached");
assetGate.resolve();
assert.equal((await olderHead).slots[0].status, "stale");
assert.equal(host.diagnostics().slots.find((row) => row.slot === "HEAD").presentation_id, "P045_H06_SANTA_HAT");
for (const slot of ["BACK", "AURA"]) {
  assert.equal(host.diagnostics().slots.find((row) => row.slot === slot).child_count, 0, slot + " follows server detach");
}
for (const slot of ["MAIN_HAND", "OFF_HAND", "COMPANION"]) {
  assert.equal(host.diagnostics().slots.find((row) => row.slot === slot).child_count, 1, slot + " preserved by D007 snapshot");
}

const unknown = await adapter.renderServerSnapshot(snapshot(
  "A1", "UNKNOWN_TEST_ONLY_HEAD", "P045_B02_BACKPACK", "AURA_PRESENTATION_RING",
));
assert.equal(unknown.slots[0].status, "failed_closed");
assert.equal(host.diagnostics().slots.find((row) => row.slot === "HEAD").child_count, 0);
for (const slot of ["BACK", "AURA", "MAIN_HAND", "OFF_HAND", "COMPANION"]) {
  assert.equal(host.diagnostics().slots.find((row) => row.slot === slot).child_count, 1, slot + " preserved on unknown Head");
}

// Pending Back load detached before completion cannot resurrect or affect peers.
assetGate = deferred();
delayedAssetPath = "assets/3d_shop/p048/back/B02_Backpack.glb";
delayedStarted = deferred();
const lateBack = adapter.renderServerSnapshot(snapshot(
  "A1", null, "P045_B02_BACKPACK", "AURA_PRESENTATION_RING",
));
await delayedStarted.promise;
await host.detach("BACK");
assetGate.resolve();
const lateResult = await lateBack;
assert.equal(lateResult.slots[1].status, "stale");
assert.equal(host.diagnostics().slots.find((row) => row.slot === "BACK").child_count, 0);
for (const slot of ["AURA", "MAIN_HAND", "OFF_HAND", "COMPANION"]) {
  assert.equal(host.diagnostics().slots.find((row) => row.slot === slot).child_count, 1, slot + " preserved after Back detach");
}
host.destroy();
assert.equal(host.diagnostics().disposed, true);
assert.equal(characterRoot.children.some((node) => node.name.startsWith("G009_SHARED_HERO_SLOT_")), false);

// A new character receives a distinct host; stale work from the old host is disposed.
const switchedRoot = makeRoot();
const switchedHost = createG009SharedHeroAttachmentHost(switchedRoot, THREE);
for (const slot of ["HEAD", "BACK", "AURA"]) {
  switchedHost.registerResolver(slot, (id) => index.resolve(slot, id));
}
const disposeGate = deferred();
const staleAfterDispose = switchedHost.attach("BACK", "P045_B02_BACKPACK", async () => {
  await disposeGate.promise;
  return new THREE.Object3D();
});
await Promise.resolve();
switchedHost.destroy();
disposeGate.resolve();
assert.equal((await staleAfterDispose).status, "stale");
assert.equal(switchedHost.diagnostics().disposed, true);

await assert.rejects(() => adapter.renderServerSnapshot({ character_key: "UNKNOWN_TEST_ONLY" }),
  /d007_character_authority_fail_closed/);
// Hand slots follow the skeleton hand bone; they never use bounding-box layout.
const poseRoot = makeRoot();
const poseHost = createG009SharedHeroAttachmentHost(poseRoot, THREE);
const rightHand = poseRoot.getObjectByName("hand.R");
const leftHand = poseRoot.getObjectByName("hand.L");
const mainAnchor = poseRoot.children.find((node) => node.name === "G009_SHARED_HERO_SLOT_MAIN_HAND");
const offAnchor = poseRoot.children.find((node) => node.name === "G009_SHARED_HERO_SLOT_OFF_HAND");
assert.equal(mainAnchor.userData.anchor_source, "HAND_BONE:hand.R");
assert.equal(offAnchor.userData.anchor_source, "HAND_BONE:hand.L");
const handCases = [[mainAnchor, rightHand], [offAnchor, leftHand]];
const closeTo = (a, b) => a.elements.every((value, i) => Math.abs(value - b.elements[i]) < 1e-9);
poseRoot.updateMatrixWorld(true);
for (const [anchor, bone] of handCases) assert(closeTo(anchor.matrixWorld, bone.matrixWorld), "anchor starts at hand bone");
poseRoot.getObjectByName("TEST_ONLY_upper_arm").rotation.set(0.4, -0.7, 1.1);
poseRoot.position.set(2, 0.5, -1);
poseRoot.scale.setScalar(1.7);
poseRoot.updateMatrixWorld(true);
for (const [anchor, bone] of handCases) assert(closeTo(anchor.matrixWorld, bone.matrixWorld), "anchor follows posed hand bone");
const posedBox = new THREE.Box3().setFromObject(poseRoot);
assert(!posedBox.isEmpty());
assert.deepEqual(poseHost.getSlotLayout("MAIN_HAND").anchor_position, mainAnchor.position.toArray());
poseHost.destroy();

// A character without resolvable hand bones fails closed for hand slots only.
const bonelessRoot = new THREE.Group();
bonelessRoot.add(new THREE.Mesh(new THREE.BoxGeometry(1, 2, 0.8), new THREE.MeshBasicMaterial()));
const bonelessHost = createG009SharedHeroAttachmentHost(bonelessRoot, THREE);
bonelessHost.registerResolver("MAIN_HAND", (id) => ({ presentation_id: id, slot: "MAIN_HAND" }));
bonelessHost.registerResolver("OFF_HAND", (id) => ({ presentation_id: id, slot: "OFF_HAND" }));
bonelessHost.registerResolver("BACK", (id) => index.resolve("BACK", id));
let loaderCalls = 0;
for (const slot of ["MAIN_HAND", "OFF_HAND"]) {
  await assert.rejects(() => bonelessHost.attach(slot, "TEST_ONLY_" + slot, async () => { loaderCalls += 1; return new THREE.Object3D(); }),
    new RegExp("hero_hand_bone_unresolved:" + slot));
  assert.throws(() => bonelessHost.getSlotLayout(slot), /hero_hand_bone_unresolved/);
  const anchor = bonelessRoot.children.find((node) => node.name === "G009_SHARED_HERO_SLOT_" + slot);
  assert.equal(anchor.userData.anchor_source, "UNRESOLVED_HAND_BONE");
  assert.equal(anchor.children.length, 0, slot + " is never placed beside the character");
}
assert.equal(loaderCalls, 0, "no hand-held asset is loaded without a hand bone");
assert.equal((await bonelessHost.attach("BACK", "P045_B02_BACKPACK", async () => new THREE.Object3D())).status, "attached",
  "non-hand slots keep working without hand bones");
const duplicateRoot = makeRoot();
const extra = new THREE.Bone(); extra.name = "hand_R"; duplicateRoot.add(extra);
const duplicateHost = createG009SharedHeroAttachmentHost(duplicateRoot, THREE);
assert.throws(() => duplicateHost.getSlotLayout("MAIN_HAND"), /hero_hand_bone_unresolved:MAIN_HAND/,
  "ambiguous hand bones fail closed");
assert.deepEqual(duplicateHost.getSlotLayout("OFF_HAND").anchor_position.length, 3);
bonelessHost.destroy();
duplicateHost.destroy();

console.log("HAND_SLOTS_FOLLOW_HAND_BONES=PASS (MAIN_HAND=hand.R, OFF_HAND=hand.L, posed and moved root)");
console.log("MISSING_OR_AMBIGUOUS_HAND_BONE_FAIL_CLOSED=PASS (no bounding-box fallback)");
console.log("D007_R1_HEAD_BACK_AURA_SHARED_HOST=PASS");
console.log("ALL_SLOT_CLASSES_COEXIST_TEST_ONLY=PASS");
console.log("CROSS_SLOT_PRESERVATION=PASS");
console.log("REPLACE_DETACH_DISPOSE=PASS");
console.log("STALE_ASYNC_PROTECTION=PASS");
console.log("UNKNOWN_CHARACTER_FAIL_CLOSED=PASS");
console.log("FORMAL_MAPPING_CREATED=NO");
