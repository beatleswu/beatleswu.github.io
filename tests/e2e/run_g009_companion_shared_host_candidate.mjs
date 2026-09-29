// Controlled module regression, NOT authenticated browser/WebGL acceptance.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const source = name => readFile(path.join(root, name), 'utf8');
const three = await import(pathToFileURL(path.join(root, 'assets/3d_shop/p048/vendor/three.module.js')));
const manifest = JSON.parse(await source('schemas/future30_c005_real_asset_runtime_mapping_manifest.json'));
const manifestHash = createHash('sha256').update(await readFile(path.join(root, 'schemas/future30_c005_real_asset_runtime_mapping_manifest.json'))).digest('hex');
assert.equal(manifest.roster.length, 30);
assert.equal(manifest.visual_models.length, 33);
assert.deepEqual(manifest.visual_models.filter(row => row.variant === 'BLUE').map(row => row.character_id), ['AR1', 'AR2', 'AR3']);
for (const row of manifest.visual_models) {
  assert(manifest.roster.some(logical => logical.character_id === row.character_id));
  assert.equal(createHash('sha256').update(await readFile(path.join(root, row.runtime_glb))).digest('hex'), row.runtime_sha256);
}

const stage = { isConnected: true, dataset: {}, clientWidth: 320, clientHeight: 400, children: [], replaceChildren(...nodes) { this.children = nodes; } };
const avatar = { dataset: {} };
const listeners = new Map();
globalThis.window = {
  devicePixelRatio: 1,
  addEventListener(name, callback) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(callback); },
  removeEventListener(name, callback) { listeners.get(name)?.delete(callback); },
};
globalThis.document = { getElementById: id => id === 'char-avatar' ? avatar : stage };
globalThis.location = { href: 'http://127.0.0.1/hero' };
globalThis.requestAnimationFrame = callback => setTimeout(callback, 0);
globalThis.cancelAnimationFrame = clearTimeout;
let liveRenderers = 0;
let maxRenderers = 0;
let framesEnabled = true;
class Renderer {
  constructor() {
    liveRenderers++;
    maxRenderers = Math.max(maxRenderers, liveRenderers);
    this.domElement = { width: 0, height: 0, remove() { stage.children = stage.children.filter(child => child !== this); } };
    this.info = { render: { calls: 1, triangles: 12 } };
    this.capabilities = { isWebGL2: true };
    this.renderLists = { dispose() {} };
  }
  setPixelRatio(value) { this.ratio = value; }
  getPixelRatio() { return this.ratio; }
  setSize(width, height) { this.domElement.width = width; this.domElement.height = height; }
  setAnimationLoop(callback) { if (callback && framesEnabled) { callback(); callback(); } }
  render() {}
  dispose() { assert(!this.disposed); this.disposed = true; liveRenderers--; }
}
const roots = [];
function mesh() {
  const model = new three.Mesh(new three.BoxGeometry(1, 2, 1), new three.MeshStandardMaterial());
  model.userData.disposed = 0;
  model.geometry.addEventListener('dispose', () => { model.userData.disposed++; });
  model.material.addEventListener('dispose', () => { model.userData.materialDisposed = true; });
  roots.push(model);
  return model;
}
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
let parseGate = null;
let parseStarted = null;
globalThis.__fThree = { ...three, WebGLRenderer: Renderer };
globalThis.__fLoader = class {
  async parseAsync() {
    const model = mesh();
    for (const name of ['hand.R', 'hand.L']) {
      const bone = new three.Bone();
      bone.name = name;
      model.add(bone);
    }
    const gate = parseGate; parseStarted?.resolve(); if (gate) await gate.promise;
    return { scene: model };
  }
};
let selectedKey = 'A1';
let changeProjection = () => {};
let readGate = null;
const requests = [];
function projection() {
  const entries = manifest.roster.map(row => {
    const visuals = manifest.visual_models.filter(model => model.character_id === row.character_id);
    const red = visuals.find(model => model.variant === 'RED');
    return { ...red, character_key: row.character_id, owned: true, is_applied: row.character_id === selectedKey,
      acquisition_source: 'ACCEPTANCE_TEST', visual_models: visuals };
  });
  const entry = entries.find(row => row.character_key === selectedKey) || entries[0];
  const catalog = { entries, logical_count: 30, visual_count: 33, c005_manifest_sha256: manifestHash, blue_optional: ['AR1', 'AR2', 'AR3'] };
  const appearance = { character_key: selectedKey, character_key_source: 'player_appearance.character_key',
    character_key_authority: 'player_appearance.character_key', character_entitled: true,
    character_runtime: { ...entry, character_key: selectedKey, default_variant: 'RED', c005_manifest_sha256: manifestHash } };
  changeProjection(catalog, appearance);
  return { catalog, appearance };
}
globalThis.fetch = async (url, options) => {
  requests.push({ url, options });
  if (url.startsWith('/api/')) {
    const payload = projection();
    if (readGate) await readGate.promise; // Deliberately ignores abort to test stale completion.
    return { ok: true, status: 200, json: async () => structuredClone(url.endsWith('appearance') ? payload.appearance : payload.catalog) };
  }
  const bytes = await readFile(path.join(root, url));
  return { ok: true, status: 200, arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) };
};
let heroSource = await source('js/g008_future30_hero_renderer.js');
const sharedHostSource = await source('js/g009_shared_hero_attachment_host.js');
const sharedHostUrl = `data:text/javascript;base64,${Buffer.from(sharedHostSource).toString('base64')}`;
heroSource = heroSource.replace(/^import \* as THREE[^\n]+/m, 'const THREE = globalThis.__fThree;')
  .replace(/^import \{ GLTFLoader \}[^\n]+/m, 'const GLTFLoader = globalThis.__fLoader;')
  .replace(/^import \{\s*createG009SharedHeroAttachmentHost,\s*G009_HERO_PRESENTATION_SLOTS,\s*\} from "\.\/g009_shared_hero_attachment_host\.js";$/m,
    `const { createG009SharedHeroAttachmentHost, G009_HERO_PRESENTATION_SLOTS } = await import("${sharedHostUrl}");`);
const hero = await import(`data:text/javascript;base64,${Buffer.from(heroSource).toString('base64')}`);

const { createCompanionChild } = await import(pathToFileURL(path.join(root, "js/g009_companion_child.mjs")));
let pet = {pet_key:"ink_drop_kelpie", level:9, stage:"III"};
let statusGate = null;
let statusStarted = null;
let childLoadGate = null;
let childStarted = null;
let lastLoaded = null;
let missing = false;
let badDescriptor = false;
let statusReads = 0;
const child = createCompanionChild({
  hero, eventTarget:window,
  fetchImpl: async (url, options) => {
    assert.equal(url, "/api/pet/status");
    assert.equal(options.credentials, "include");
    assert.equal(options.cache, "no-store");
    statusReads++;
    const snapshot = structuredClone({pet});
    const gate = statusGate;
    statusStarted?.resolve();
    if (gate) await gate.promise; // simulate a transport that ignores abort
    return {ok:true, json:async()=>snapshot};
  },
  resolvePresentation: async value => ({
    presentation_id: value.pet_key + ":" + (value.level >= 25 ? "III" : value.level >= 10 ? "II" : "I"),
    pet_key:value.pet_key, stage:badDescriptor ? "IV" : value.level >= 25 ? "III" : value.level >= 10 ? "II" : "I",
    slot:"COMPANION", asset_path:"/assets/TEST_ONLY.glb", asset_sha256:"a".repeat(64), asset_bytes:1,
  }),
  loadPresentation: async () => {
    if (missing) throw new Error("COMPANION_MODEL_HTTP_404");
    const node = mesh();
    lastLoaded = node;
    const gate = childLoadGate;
    childStarted?.resolve();
    if (gate) await gate.promise;
    return node; // actual shared host owns geometry/material disposal
  },
});
await hero.mountHeroAppearance();
function ready(key, stageName) {
  assert.equal(child.getState().status, "ready");
  assert.equal(child.getState().pet_key,key);
  assert.equal(child.getState().stage,stageName);
  const slot = hero.getHeroSharedAttachmentHost().diagnostics().slots.find(x=>x.slot==="COMPANION");
  assert.equal(slot.child_count,1);
  assert.equal(slot.presentation_id,key+":"+stageName);
  assert.equal(liveRenderers,1);
  assert.equal(stage.children.length,1);
}
ready("ink_drop_kelpie","I");
const originalRenderer = stage.children[0];
const sibling = mesh();
hero.registerHeroPresentationResolver("HEAD",id=>id==="TEST_ONLY_HEAD"?{presentation_id:id,slot:"HEAD"}:null);
await hero.attachHeroChildPresentation("HEAD","TEST_ONLY_HEAD",async()=>sibling);
const otherEquipment = new Map();
for (const slot of ['BACK', 'AURA', 'MAIN_HAND', 'OFF_HAND']) {
  const id = `TEST_ONLY_${slot}`;
  const node = mesh();
  hero.registerHeroPresentationResolver(slot, value => value === id ? { presentation_id:id, slot } : null);
  await hero.attachHeroChildPresentation(slot, id, async () => node);
  otherEquipment.set(slot, node);
}
for (const slot of ['HEAD', 'BACK', 'AURA', 'MAIN_HAND', 'OFF_HAND', 'COMPANION']) {
  assert.equal(hero.getHeroSharedAttachmentHost().diagnostics().slots.find(x => x.slot === slot).child_count, 1);
}
assert.equal(hero.getHeroSharedAttachmentHost().getSlotLayout('MAIN_HAND').anchor_position.length, 3);
assert.equal(hero.getHeroSharedAttachmentHost().getSlotLayout('OFF_HAND').anchor_position.length, 3);
const prior = lastLoaded;
pet={pet_key:"fatty",level:10}; await child.refresh();
ready("fatty","II");
assert.equal(prior.userData.disposed,1);
assert.equal(prior.parent,null);
assert.equal(sibling.userData.disposed,0);
for (const node of otherEquipment.values()) assert.equal(node.userData.disposed, 0);
assert.equal(stage.children[0],originalRenderer);
for (const [level,expected] of [[9,"I"],[10,"II"],[24,"II"],[25,"III"]]) {
  pet={pet_key:"fatty",level,stage:"I"}; await child.refresh(); ready("fatty",expected);
}
// Out-of-order model completion and rapid switch.
childLoadGate=deferred(); childStarted=deferred();
pet={pet_key:"ink_drop_kelpie",level:9};
const oldLoad=child.refresh(); await childStarted.promise;
const staleNode=lastLoaded; const gate=childLoadGate;
childLoadGate=null; childStarted=null;
pet={pet_key:"obsidian_bastion",level:25}; await child.refresh();
gate.resolve(); await oldLoad;
ready("obsidian_bastion","III");
assert.equal(staleNode.parent,null);
assert.equal(staleNode.userData.disposed,1);
// Out-of-order status cannot select a stale model.
statusGate=deferred(); statusStarted=deferred();
pet={pet_key:"fatty",level:1}; const oldStatus=child.refresh(); await statusStarted.promise;
const sg=statusGate; statusGate=null; statusStarted=null;
pet={pet_key:"whispering_void_kit",level:24}; await child.refresh();
sg.resolve(); await oldStatus; ready("whispering_void_kit","II");
for (const value of [{pet_key:"unknown",level:1},{pet_key:"Bunny",level:1},{pet_key:"fatty",level:null}]) {
  pet=value; await child.refresh();
  assert.equal(child.getState().status,"unavailable");
  assert.equal(hero.getHeroSharedAttachmentHost().diagnostics().slots.find(x=>x.slot==="COMPANION").child_count,0);
  assert.equal(sibling.userData.disposed,0); assert.equal(liveRenderers,1);
}
pet={pet_key:"fatty",level:1}; badDescriptor=true; await child.refresh();
assert.equal(child.getState().reason,"COMPANION_DESCRIPTOR_REJECTED"); badDescriptor=false;
missing=true; await child.refresh();
assert.equal(child.getState().reason,"COMPANION_MODEL_HTTP_404"); missing=false;
pet=null; await child.refresh(); assert.equal(child.getState().status,"none");
pet={pet_key:"star_shell_hatchling",level:25};
const readsBefore=statusReads;
await hero.refreshHeroAppearance(); ready("star_shell_hatchling","III"); assert(statusReads>readsBefore);
assert.equal(sibling.userData.disposed,1);
for (const node of otherEquipment.values()) assert.equal(node.userData.disposed, 1);
selectedKey="A3"; await hero.refreshHeroAppearance(); ready("star_shell_hatchling","III");
assert.equal(window.__G008_HERO_RENDER_STATE__.character_key,"A3");
// Destroy while parse/load is pending; old completion must never resurrect.
childLoadGate=deferred(); childStarted=deferred();
const late=child.refresh(); await childStarted.promise;
const destroyedNode=lastLoaded; const dg=childLoadGate;
hero.destroyHeroAppearance();
assert.equal(liveRenderers,0); assert.equal(stage.children.length,0);
assert.equal(listeners.get("g009:companion-status").size,0);
childLoadGate=null; childStarted=null;
pet={pet_key:"starpath_antlerling",level:10};
await hero.mountHeroAppearance();
dg.resolve(); await late; ready("starpath_antlerling","II");
assert.equal(destroyedNode.userData.disposed,1); assert.equal(destroyedNode.parent,null);
assert.equal(listeners.get("g009:companion-status").size,1);
child.dispose(); child.dispose();
assert.equal(listeners.get("g009:companion-status").size,0);
assert.equal(liveRenderers,1); // Companion cannot destroy Hero
// Wire the actual formal asset source to the actual child and actual shared host.
// GLB bytes/digests are real; GLTF parse/WebGL remain controlled boundaries.
const {createFormal18AssetSource} = await import(pathToFileURL(path.join(root,"js/g009_companion_formal18_assets.mjs")));
const formalSource = createFormal18AssetSource({
  THREE:three,
  parse:async()=>({scene:mesh()}),
  getLayout:()=>hero.getHeroSharedAttachmentHost().getSlotLayout("COMPANION"),
});
const formalChild = createCompanionChild({
  hero, eventTarget:window,
  fetchImpl:async()=>({ok:true,json:async()=>({pet:structuredClone(pet)})}),
  resolvePresentation:formalSource.resolve, loadPresentation:formalSource.load,
});
await hero.rehydrateHeroPresentations();
for (const key of ["ink_drop_kelpie","whispering_void_kit","star_shell_hatchling","starpath_antlerling","fatty","obsidian_bastion"]) {
  for (const [level,stageName] of [[9,"I"],[10,"II"],[24,"II"],[25,"III"]]) {
    pet={pet_key:key,level,stage:"III"};
    await formalChild.refresh();
    assert.equal(formalChild.getState().status,"ready");
    assert.equal(formalChild.getState().pet_key,key);
    assert.equal(formalChild.getState().stage,stageName);
    assert.equal(hero.getHeroSharedAttachmentHost().diagnostics().slots.find(x=>x.slot==="COMPANION").child_count,1);
    assert.equal(liveRenderers,1);
  }
}
await hero.refreshHeroAppearance();
assert.equal(formalChild.getState().pet_key,"obsidian_bastion");
assert.equal(formalChild.getState().stage,"III");
formalChild.dispose();
hero.destroyHeroAppearance(); hero.destroyHeroAppearance();
assert.equal(liveRenderers,0); assert.equal(maxRenderers,1);
console.log("COMPANION_FOUNDATION=PASS; STAGE_THRESHOLDS=PASS; PET_STAGE_SWITCH=PASS");
console.log("STATUS_AND_MODEL_RACES=PASS; DESTROY_REMOUNT=PASS; MAX_RENDERERS=1");
console.log("HERO_COMPANION_SHARED_SCENE=PASS_CONTROLLED; AUTHENTICATED_RELOG=NOT_RUN");
console.log("HEAD_BACK_AURA_MAIN_OFF_COMPANION_SIX_SLOT=PASS_CONTROLLED; FINAL_D_HAND_BONES=PASS");
console.log("FORMAL18_SHARED_HOST_PIPELINE=18/18 PASS_CONTROLLED_WITH_REAL_ASSET_BYTES");
