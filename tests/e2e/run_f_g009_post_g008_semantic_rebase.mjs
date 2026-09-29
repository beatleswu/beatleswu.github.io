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
// TEST ONLY: real Future30 Heroes ship hand.R / hand.L joints.
function withTestOnlyHandBones(model) {
  for (const [name, x] of [['hand.R', -0.6], ['hand.L', 0.6]]) {
    const bone = new three.Bone();
    bone.name = name;
    bone.position.set(x, 0.4, 0);
    model.add(bone);
  }
  return model;
}
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
let parseGate = null;
let parseStarted = null;
globalThis.__fThree = { ...three, WebGLRenderer: Renderer };
globalThis.__fLoader = class {
  async parseAsync() { const model = withTestOnlyHandBones(mesh()); const gate = parseGate; parseStarted?.resolve(); if (gate) await gate.promise; return { scene: model }; }
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
      acquisition_source: 'STARTER', visual_models: visuals };
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
const first = hero.mountHeroAppearance();
assert.equal(hero.mountHeroAppearance(), first);
const testOnlyCompanionResolver = id => id === 'TEST_ONLY_COMPANION'
  ? { presentation_id: id, slot: 'COMPANION', test_only: true } : null;
hero.registerHeroPresentationResolver('COMPANION', testOnlyCompanionResolver);
let rehydrationCount = 0;
hero.registerHeroPresentationRehydrator('TEST_ONLY_COMPANION_REHYDRATOR', async ({ character_key, host }) => {
  assert.equal(character_key, selectedKey);
  assert.equal(host.slots.length, 6);
  rehydrationCount++;
  return host.attach('COMPANION', 'TEST_ONLY_COMPANION', async descriptor => {
    assert.equal(descriptor.test_only, true);
    const child = mesh(); child.userData.testOnly = true;
    return child;
  });
});
await first;
assert.equal(window.__G008_HERO_RENDER_STATE__.state, 'ready');
assert.equal(window.__G008_HERO_RENDER_STATE__.character_key, 'A1');
assert.equal(stage.children.length, 1);
assert.equal(listeners.get('pagehide').size, 1);
const firstHost = hero.getHeroSharedAttachmentHost();
assert(firstHost);
assert.deepEqual(firstHost.slots, ['HEAD', 'BACK', 'AURA', 'MAIN_HAND', 'OFF_HAND', 'COMPANION']);
assert.equal(typeof firstHost.destroy, 'undefined');
const companionLayout = firstHost.getSlotLayout('COMPANION');
assert.equal(companionLayout.character_size.length, 3);
assert.equal(companionLayout.anchor_position.length, 3);
assert(companionLayout.character_size.every(Number.isFinite));
assert(companionLayout.anchor_position.every(Number.isFinite));
assert(Number.isFinite(companionLayout.ground_y));
assert(Object.isFrozen(companionLayout) && Object.isFrozen(companionLayout.anchor_position));
assert.throws(() => firstHost.getSlotLayout('UNKNOWN_SLOT'), /unknown_hero_presentation_slot/);
assert.equal(firstHost.diagnostics().slots.find(row => row.slot === 'COMPANION').presentation_id, 'TEST_ONLY_COMPANION');

// Six explicit TEST ONLY descriptors coexist under the single F-owned renderer.
const testOnlyIds = new Map(hero.HERO_PRESENTATION_SLOTS.map(slot => [slot, 'TEST_ONLY_' + slot]));
const firstChildren = new Map();
for (const slot of hero.HERO_PRESENTATION_SLOTS) {
  if (slot === 'COMPANION') continue;
  const id = testOnlyIds.get(slot);
  const resolver = requested => requested === id
    ? { presentation_id: id, slot, test_only: true } : null;
  hero.registerHeroPresentationResolver(slot, resolver);
  await hero.attachHeroChildPresentation(slot, id, async descriptor => {
    assert.equal(descriptor.test_only, true);
    const child = mesh(); child.userData.testOnly = true;
    firstChildren.set(slot, child);
    return child;
  });
}
assert(hero.HERO_PRESENTATION_SLOTS.every(slot =>
  firstHost.diagnostics().slots.find(row => row.slot === slot).child_count === 1));
const untouchedBack = firstChildren.get('BACK');
const replacedHead = firstChildren.get('HEAD');
const replacementHead = mesh();
await hero.attachHeroChildPresentation('HEAD', testOnlyIds.get('HEAD'), async () => replacementHead);
assert.equal(replacedHead.parent, null);
assert.equal(replacedHead.userData.disposed, 1);
assert.equal(replacementHead.parent.name, 'G009_SHARED_HERO_SLOT_HEAD');
assert(untouchedBack.parent);
await assert.rejects(
  hero.attachHeroChildPresentation('HEAD', 'UNKNOWN_TEST_ONLY_HEAD', async () => mesh()),
  /unknown_hero_presentation/,
);
assert.equal(replacementHead.parent.name, 'G009_SHARED_HERO_SLOT_HEAD');
assert.equal(replacementHead.userData.disposed, 0);
assert(untouchedBack.parent);
await assert.rejects(
  hero.attachHeroChildPresentation('HEAD', testOnlyIds.get('HEAD'), null),
  /hero_presentation_loader_required/,
);
await assert.rejects(
  hero.attachHeroChildPresentation('HEAD', testOnlyIds.get('HEAD'), async () => {
    throw new Error('TEST_ONLY_LOADER_REJECTED');
  }),
  /TEST_ONLY_LOADER_REJECTED/,
);
let invalidResultDisposals = 0;
await assert.rejects(
  hero.attachHeroChildPresentation('HEAD', testOnlyIds.get('HEAD'), async () => ({
    disposeOwnedResources() { invalidResultDisposals++; },
  })),
  /hero_presentation_object3d_required/,
);
assert.equal(invalidResultDisposals, 1);
const foreignParent = new three.Group();
const foreignNode = mesh();
foreignParent.add(foreignNode);
let foreignLoaderResourceDisposals = 0;
await assert.rejects(
  hero.attachHeroChildPresentation('HEAD', testOnlyIds.get('HEAD'), async () => ({
    node: foreignNode,
    disposeOwnedResources() { foreignLoaderResourceDisposals++; },
  })),
  /hero_presentation_node_already_parented/,
);
assert.equal(foreignLoaderResourceDisposals, 1);
assert.equal(foreignNode.parent, foreignParent);
assert.equal(foreignNode.userData.disposed, 0);
// The fixture's foreign owner, rather than the Hero host, releases this node.
foreignParent.remove(foreignNode);
foreignNode.geometry.dispose();
foreignNode.material.dispose();
assert.equal(replacementHead.parent.name, 'G009_SHARED_HERO_SLOT_HEAD');
assert.equal(replacementHead.userData.disposed, 0);
const validAfterRejection = mesh();
await hero.attachHeroChildPresentation('HEAD', testOnlyIds.get('HEAD'), async () => validAfterRejection);
assert.equal(replacementHead.parent, null);
assert.equal(replacementHead.userData.disposed, 1);
assert.equal(validAfterRejection.parent.name, 'G009_SHARED_HERO_SLOT_HEAD');
assert.throws(
  () => hero.attachHeroChildPresentation('UNKNOWN_SLOT', 'TEST_ONLY_X', async () => mesh()),
  /unknown_hero_presentation_slot/,
);
assert(untouchedBack.parent);
await hero.detachHeroChildPresentation('OFF_HAND');
assert.equal(firstChildren.get('OFF_HAND').parent, null);
assert.equal(firstChildren.get('OFF_HAND').userData.disposed, 1);
assert(untouchedBack.parent);

const lateLoad = deferred();
const lateLoadStarted = deferred();
let lateBackNode = null;
const staleAttach = hero.attachHeroChildPresentation('BACK', testOnlyIds.get('BACK'), async () => {
  lateLoadStarted.resolve();
  await lateLoad.promise;
  lateBackNode = mesh();
  return lateBackNode;
});
await lateLoadStarted.promise;
await hero.detachHeroChildPresentation('BACK');
lateLoad.resolve();
assert.equal((await staleAttach).status, 'stale');
assert.equal(lateBackNode.parent, null);
assert.equal(lateBackNode.userData.disposed, 1);
assert.equal(firstHost.diagnostics().slots.find(row => row.slot === 'BACK').child_count, 0);
const explicitRehydration = await hero.rehydrateHeroPresentations();
assert.equal(explicitRehydration.status, 'complete');
assert(rehydrationCount >= 2);
const requestCount = requests.length;
await hero.mountHeroAppearance();
assert.equal(requests.length, requestCount);
hero.destroyHeroAppearance();
hero.destroyHeroAppearance();
assert.equal(liveRenderers, 0);
assert.equal(hero.getHeroSharedAttachmentHost(), null);
assert.throws(() => firstHost.attach('COMPANION', 'TEST_ONLY_COMPANION', async () => mesh()), /stale_hero_attachment_host_handle/);
assert.throws(() => firstHost.getSlotLayout('COMPANION'), /stale_hero_attachment_host_handle/);
assert.equal(stage.children.length, 0);
assert.equal(listeners.get('pagehide').size, 0);
assert.equal(roots[0].userData.disposed, 1);
assert(roots[0].userData.materialDisposed);

// Every logical key traverses the same real validation/projection code; GLTF/WebGL are doubles.
for (const row of manifest.roster) {
  selectedKey = row.character_id;
  await hero.refreshHeroAppearance();
  assert.equal(window.__G008_HERO_RENDER_STATE__.state, 'ready', selectedKey);
  assert.equal(window.__G008_HERO_RENDER_STATE__.character_key, selectedKey);
}
selectedKey = 'A1';
const negatives = [
  (_c, a) => { a.character_key = 'A31'; },
  (_c, a) => { a.character_entitled = false; },
  (c) => { c.entries[0].owned = false; },
  (c) => { c.entries[0].is_applied = false; },
  (_c, a) => { a.character_key_source = 'client'; },
  (_c, a) => { a.character_runtime.visual_model_id = 'FUTURE30_MODEL_AR1_BLUE'; },
  (_c, a) => { a.character_runtime.default_variant = 'BLUE'; },
  (_c, a) => { a.character_runtime = null; },
  (c) => { c.entries[0].acquisition_source = 'CLIENT'; },
];
for (changeProjection of negatives) {
  await hero.refreshHeroAppearance();
  assert.equal(window.__G008_HERO_RENDER_STATE__.state, 'failed');
  assert.equal(stage.children.length, 0);
  assert.equal(liveRenderers, 0);
}
changeProjection = () => {};
// Destroy during parse, then remount a different server-selected key before old parse completes.
parseGate = deferred(); parseStarted = deferred();
const stale = hero.refreshHeroAppearance();
await parseStarted.promise;
const staleRoot = roots.at(-1);
const oldParseGate = parseGate;
hero.destroyHeroAppearance();
parseGate = null; parseStarted = null;
selectedKey = 'A3';
await hero.mountHeroAppearance();
oldParseGate.resolve(); await stale;
assert.equal(window.__G008_HERO_RENDER_STATE__.character_key, 'A3');
assert.equal(staleRoot.userData.disposed, 1);
assert.equal(staleRoot.parent, null);
assert.equal(stage.children.length, 1);

readGate = deferred();
const beforeRead = hero.refreshHeroAppearance();
hero.destroyHeroAppearance();
readGate.resolve(); readGate = null;
await beforeRead;
assert.equal(liveRenderers, 0);
assert.equal(window.__G008_HERO_RENDER_STATE__.state, 'inactive');
parseGate = deferred(); parseStarted = deferred();
const detached = hero.mountHeroAppearance();
await parseStarted.promise;
const detachedRoot = roots.at(-1);
stage.isConnected = false;
parseGate.resolve(); await detached;
assert.equal(detachedRoot.parent, null);
assert.equal(detachedRoot.userData.disposed, 1);
assert.equal(liveRenderers, 0);
stage.isConnected = true; parseGate = null; parseStarted = null;
framesEnabled = false;
parseStarted = deferred();
const duringFrames = hero.mountHeroAppearance();
await parseStarted.promise;
await new Promise(resolve => setTimeout(resolve, 5));
for (const callback of [...listeners.get('pagehide')]) callback();
await duringFrames;
assert.equal(stage.children.length, 0);
assert.equal(liveRenderers, 0);
framesEnabled = true; parseStarted = null;
await hero.mountHeroAppearance();
assert.notEqual(hero.getHeroSharedAttachmentHost(), firstHost);
assert.equal(hero.getHeroSharedAttachmentHost().diagnostics().slots.find(row => row.slot === 'COMPANION').presentation_id, 'TEST_ONLY_COMPANION');
hero.destroyHeroAppearance();
assert.equal(maxRenderers, 1);
assert(roots.every(model => model.userData.disposed === 1));

// P048 is tested as its existing preview runtime, never substituted for the Hero owner.
let previewSource = await source('js/3d_shop_p048_runtime.js');
previewSource = previewSource.replace(/^import \* as THREE[^\n]+/m, 'const THREE = globalThis.__fThree;')
  .replace(/^import \{ GLTFLoader \}[^\n]+/m, 'const GLTFLoader = globalThis.__fLoader;');
const { ThreeShopPresentationRuntime } = await import(`data:text/javascript;base64,${Buffer.from(previewSource).toString('base64')}`);
const preview = new ThreeShopPresentationRuntime({});
preview.heroGroup = new three.Group();
preview.heroRoot = mesh(); preview.heroGroup.add(preview.heroRoot);
preview.resolveEntry = id => ({ presentation_id: id, authority_domain: 'HEAD_PRESENTATION', runtime_asset: id,
  normalized_asset_scale: 1, presentation_scale: 1, local_position_offset: [0, 0, 0] });
const loads = new Map();
preview.loadGLTF = async (_url, id) => { const load = deferred(); loads.set(id, load); return load.promise; };
const headA = preview.setHead('HEAD_A');
const headB = preview.setHead('HEAD_B');
const headBRoot = mesh(); loads.get('HEAD_B').resolve({ scene: headBRoot }); await headB;
const headARoot = mesh(); loads.get('HEAD_A').resolve({ scene: headARoot }); await headA;
assert.equal(preview.currentHead, headBRoot);
assert.equal(headARoot.parent, null);
const back = preview.setBack(true);
await preview.setBack(false);
const staleBack = mesh(); loads.get('P045_B02_BACKPACK').resolve({ scene: staleBack }); await back;
assert.equal(staleBack.parent, null);
assert.equal(preview.currentHead, headBRoot);
const lateHead = preview.setHead('LATE');
preview.dispose();
const lateRoot = mesh(); loads.get('LATE').resolve({ scene: lateRoot }); await lateHead;
assert.equal(lateRoot.parent, null);
assert.equal(preview.currentHead, null);
await preview.setHead('AFTER_DISPOSE');
assert(!loads.has('AFTER_DISPOSE'));

// Execute actual inline functions, retaining full-page syntax validation separately.
const heroHtml = await source('hero.html');
const shopHtml = await source('shop.html');
function declaration(text, name) {
  const match = text.match(new RegExp(`(?:async )?function ${name}\\(`));
  assert(match, name);
  const start = match.index;
  const tail = text.slice(start);
  const end = tail.indexOf('\n}');
  assert(end > 0, name);
  return tail.slice(0, end + 2);
}
const context = vm.createContext({
  cosmeticCatalog: { products: [{ product_id: 'opaque-outfit', category: 'outfit' }] },
  premiumV1Offer: { cosmetic_pool: [] }, premiumV1SelectedCosmeticId: 'opaque-outfit',
  document: { getElementById: () => null },
  api: () => { throw new Error('retired Outfit must not reach API'); },
  _wardrobeItems: [{ id: 'old', type: 'outfit', owned: true, equipped: true }, { id: 'hat', type: 'hat', owned: true, equipped: true }],
});
for (const name of ['isOutfitV1Cosmetic', 'isOutfitV1ProductId', 'previewCosmetic', 'purchaseCosmetic', 'equipCosmetic', 'claimPremiumV1', 'updatePremiumV1Selection']) {
  vm.runInContext(declaration(shopHtml, name), context);
}
for (const name of ['isOutfitV1WardrobeItem', 'activeHeroWardrobeItems', 'handleInvClick', 'renderInvSlot']) {
  vm.runInContext(declaration(heroHtml, name), context);
}
for (const action of ['previewCosmetic', 'purchaseCosmetic', 'equipCosmetic', 'claimPremiumV1']) {
  await vm.runInContext(`${action}('opaque-outfit')`, context);
  await vm.runInContext(`${action}('cosmetic.outfit.legacy')`, context);
}
vm.runInContext("handleInvClick('outfit', 'old'); handleInvClick('hat', 'old'); renderInvSlot('outfit');", context);
assert.equal(vm.runInContext('activeHeroWardrobeItems(_wardrobeItems).length', context), 1);
assert.equal(vm.runInContext('_wardrobeItems.length', context), 2);
const claim = { setAttribute() {} };
context.document.getElementById = id => id === 'premium-v1-claim-selected' ? claim : null;
vm.runInContext("updatePremiumV1Selection({premium_entitled:true,cosmetic_pool:[{item_id:'opaque-outfit',owned:false}]})", context);
assert.equal(claim.disabled, true);
context.premiumV1SelectedCosmeticId = 'hat';
vm.runInContext("updatePremiumV1Selection({premium_entitled:true,cosmetic_pool:[{item_id:'hat',type:'hat',owned:false}]})", context);
assert.equal(claim.disabled, false);
vm.runInContext("updatePremiumV1Selection({premium_entitled:false,cosmetic_pool:[{item_id:'hat',type:'hat',owned:false}]})", context);
assert.equal(claim.disabled, true);
assert.match(heroHtml, /hidden style="display:none" aria-hidden="true" data-retired-outfit-v1/);
assert(!heroHtml.includes('const outfitItem = eq.outfit_id'));
let inlineBlocks = 0;
for (const html of [heroHtml, shopHtml]) {
  for (const match of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    if (/\bsrc\s*=|type=["'](?:module|importmap|application\/)/i.test(match[1])) continue;
    new vm.Script(match[2]); inlineBlocks++;
  }
}
console.log(JSON.stringify({ result: 'PASS', kind: 'controlled-module-not-browser', logicalProjectionCases: 30,
  visualMappingAndHashCases: 33, negativeProjectionCases: negatives.length, lifecycle: 'PASS',
  headBackRace: 'PASS', sharedHostSlots: 6, childRehydration: 'PASS', oneRendererMaximum: maxRenderers,
  outfitGuards: 'PASS', premiumSelectionPreserved: 'PASS', inlineBlocks }));
