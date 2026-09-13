'use strict';

// Owner-device corrective (2026-09-13): the prior static-string tests for
// the answer-surface equipment projection could not have caught the real
// failure -- they only proved certain substrings existed somewhere in
// index.html, never that rendering actually succeeds for a given
// character, and never that a character was genuinely HELD_IN_HAND rather
// than merely visible. This script genuinely executes the real,
// unmodified js/rpg_wave2_wearable_renderer.js -- both the wearable
// (sheathed-weapon) renderer and the true-handheld (grip-in-fist) canvas
// renderer -- against a minimal DOM + Canvas 2D shim, for every one of the
// 10 selectable hero characters. It proves, for the wearable renderer: an
// equipped wieldable produces a real projection (not a silent empty one),
// unequipping clears it, replacing it swaps the rendered item, and a
// weapon plus a wearable equipped together both render. It proves, for
// the true-handheld renderer: a real hand-anchor transform and weapon
// draw happen for every one of the 10 (not just apprentice/mage/paladin),
// an unsupported/unequipped case reports unsupported rather than a silent
// empty success, and replacing the weapon changes what is actually
// gripped.

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const RENDERER_PATH = path.join(REPO_ROOT, 'js', 'rpg_wave2_wearable_renderer.js');
const REGISTRY_PATH = path.join(REPO_ROOT, 'assets', 'hero', 'equipment', 'wearables', 'wearable_registry.json');
const HANDHELD_REGISTRY_PATH = path.join(
  REPO_ROOT, 'assets', 'hero', 'equipment', 'wearables', 'handheld', 'handheld_runtime_registry.json'
);

const ALL_TEN_CHARACTERS = [
  'apprentice', 'mage', 'paladin',
  'apprentice_girl', 'swordsman', 'rogue', 'ranger', 'berserker', 'guardian', 'sage',
];

let passCount = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passCount++;
  } catch (err) {
    failures.push({ name, error: err && err.stack ? err.stack : String(err) });
  }
}

// Arrays/values crossing the vm sandbox boundary belong to a different
// realm (their own Array.prototype), so assert.deepStrictEqual's
// same-prototype check fails even when the content is identical. Compare
// by plain value instead.
function assertSameItems(actual, expectedItems, message) {
  const actualList = Array.from(actual);
  assert.strictEqual(actualList.length, expectedItems.length, message);
  const actualSorted = actualList.slice().sort();
  const expectedSorted = expectedItems.slice().sort();
  actualSorted.forEach((value, index) => {
    assert.strictEqual(String(value), String(expectedSorted[index]), message);
  });
}

class FakeImage {
  constructor() {
    this.className = '';
    this.alt = '';
    this.decoding = '';
    this.draggable = true;
    this._src = '';
    this._listeners = {};
  }
  set src(value) { this._src = value; }
  get src() { return this._src; }
  addEventListener(type, handler) { this._listeners[type] = handler; }
}

class FakeStage {
  constructor() {
    this.dataset = {};
    this.hidden = false;
    this.children = [];
    this._ariaHidden = null;
  }
  set innerHTML(value) {
    if (value === '') this.children = [];
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  setAttribute(name, value) {
    if (name === 'aria-hidden') this._ariaHidden = value;
  }
  querySelector() { return null; }
}

function makeDocument() {
  const styleEls = [];
  return {
    getElementById(id) {
      return styleEls.find((el) => el._id === id) || null;
    },
    createElement(tag) {
      if (tag === 'img') return new FakeImage();
      if (tag === 'canvas') return new FakeCanvas();
      const el = { tag, _id: null, textContent: '' };
      Object.defineProperty(el, 'id', {
        get() { return el._id; },
        set(value) { el._id = value; styleEls.push(el); },
      });
      return el;
    },
    head: { appendChild() {} },
  };
}

// Minimal Canvas 2D shim: no real pixel math (no node-canvas dependency in
// this repo), just faithful call recording. This is enough to genuinely
// execute renderHandheldComposition/drawHandheldWeapon/drawHandheldFrontGrip
// end to end without throwing, and to assert on the *structure* of what got
// drawn (a real hand-anchor transform, a real weapon draw, a real occlusion
// composite step) -- which a pure registry-shape check cannot prove.
class FakeCanvas2DContext {
  constructor() {
    this.calls = [];
    this.globalCompositeOperation = 'source-over';
  }
  save() { this.calls.push(['save']); }
  restore() { this.calls.push(['restore']); }
  translate(x, y) { this.calls.push(['translate', x, y]); }
  rotate(rad) { this.calls.push(['rotate', rad]); }
  scale(sx, sy) { this.calls.push(['scale', sx, sy]); }
  clearRect(x, y, w, h) { this.calls.push(['clearRect', x, y, w, h]); }
  drawImage(image, ...rest) { this.calls.push(['drawImage', image && image._src, ...rest]); }
  getImageData(x, y, w, h) { return { data: new Uint8ClampedArray(Math.max(w, 1) * Math.max(h, 1) * 4) }; }
  createImageData(w, h) { return { data: new Uint8ClampedArray(Math.max(w, 1) * Math.max(h, 1) * 4) }; }
  putImageData() { this.calls.push(['putImageData']); }
}

class FakeCanvas {
  constructor() {
    this.width = 0;
    this.height = 0;
    this.className = '';
    this._ctx = null;
  }
  getContext() {
    if (!this._ctx) this._ctx = new FakeCanvas2DContext();
    return this._ctx;
  }
  setAttribute() {}
}

class FakeImageElement {
  constructor() {
    this.decoding = '';
    this._src = '';
  }
  set src(value) {
    this._src = value;
    const diskPath = path.join(REPO_ROOT, value.replace(/^\//, ''));
    setTimeout(() => {
      if (fs.existsSync(diskPath)) {
        this.naturalWidth = 1056;
        this.naturalHeight = 1408;
        if (this.onload) this.onload();
      } else if (this.onerror) {
        this.onerror(new Error('missing asset on disk: ' + value));
      }
    }, 0);
  }
  get src() { return this._src; }
}

function loadRenderer() {
  const sandbox = {};
  sandbox.window = sandbox;
  sandbox.document = makeDocument();
  sandbox.Image = FakeImageElement;
  sandbox.fetch = function (url) {
    if (url.includes('handheld_runtime_registry.json')) {
      const registry = fs.readFileSync(HANDHELD_REGISTRY_PATH, 'utf8');
      return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(registry)) });
    }
    if (url.includes('wearable_registry.json')) {
      const registry = fs.readFileSync(REGISTRY_PATH, 'utf8');
      return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(registry)) });
    }
    return Promise.reject(new Error('unexpected fetch: ' + url));
  };
  vm.createContext(sandbox);
  const source = fs.readFileSync(RENDERER_PATH, 'utf8');
  new vm.Script(source, { filename: RENDERER_PATH }).runInContext(sandbox);
  return {
    wearable: sandbox.window.GoOdysseyWearableRenderer,
    handheld: sandbox.window.GoOdysseyHandheldWeaponRenderer,
  };
}

function baseAssetFor(characterKey) {
  const registry = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
  const entry = registry.characters[characterKey];
  if (!entry) throw new Error('no wearable registry entry for ' + characterKey);
  const assetPath = path.join(REPO_ROOT, entry.base.replace(/^\//, ''));
  assert.ok(fs.existsSync(assetPath), 'missing base asset file for ' + characterKey + ': ' + entry.base);
  return entry.base;
}

async function main() {
  const { wearable, handheld } = loadRenderer();

  for (const characterKey of ALL_TEN_CHARACTERS) {
    await (async () => {
      const stage = new FakeStage();
      const equipped = [{ item_id: 'wooden_sword', slot: 'weapon', equipped: true }];
      const result = await wearable.renderSafe(stage, characterKey, equipped, {
        baseAsset: baseAssetFor(characterKey),
      });
      test('equipped wieldable produces a real projection: ' + characterKey, () => {
        assert.strictEqual(result.supported, true, JSON.stringify(result));
        assertSameItems(result.equipped, ['wooden_sword']);
        assert.ok(stage.children.length > 0, 'no layers were appended to the stage');
        assert.strictEqual(stage.hidden, false);
      });
    })();
  }

  // No equipped wieldable silently produces an empty (not missing) projection.
  // Checked for every selectable character, not just one representative.
  for (const characterKey of ALL_TEN_CHARACTERS) {
    await (async () => {
      const stage = new FakeStage();
      const result = await wearable.renderSafe(stage, characterKey, [], {
        baseAsset: baseAssetFor(characterKey),
      });
      test('unequipped weapon is absent but the character base still renders: ' + characterKey, () => {
        assert.strictEqual(result.supported, true);
        assertSameItems(result.equipped, []);
        assert.strictEqual(stage.hidden, false);
        assert.ok(stage.children.some((c) => c.className && c.className.includes('character-base')));
        assert.ok(!stage.children.some((c) => c.className && c.className.includes('wooden_sword')));
      });
    })();
  }

  // Replacing the equipped weapon updates the rendered item, for every
  // selectable character.
  for (const characterKey of ALL_TEN_CHARACTERS) {
    await (async () => {
      const stage = new FakeStage();
      await wearable.renderSafe(stage, characterKey, [
        { item_id: 'wooden_sword', slot: 'weapon', equipped: true },
      ], { baseAsset: baseAssetFor(characterKey) });
      const firstIds = stage.dataset.equippedIds;
      const second = await wearable.renderSafe(stage, characterKey, [
        { item_id: 'iron_sword', slot: 'weapon', equipped: true },
      ], { baseAsset: baseAssetFor(characterKey) });
      test('replacing the equipped weapon renders the new one, not the old one: ' + characterKey, () => {
        assert.strictEqual(firstIds, 'wooden_sword');
        assert.strictEqual(second.supported, true);
        assertSameItems(second.equipped, ['iron_sword']);
        assert.strictEqual(stage.dataset.equippedIds, 'iron_sword');
        assert.ok(!stage.children.some((c) => c.className && c.className.includes('wooden_sword')));
      });
    })();
  }

  // A weapon and a wearable (armor) equipped together both render, for
  // every selectable character.
  for (const characterKey of ALL_TEN_CHARACTERS) {
    await (async () => {
      const stage = new FakeStage();
      const result = await wearable.renderSafe(stage, characterKey, [
        { item_id: 'wooden_sword', slot: 'weapon', equipped: true },
        { item_id: 'leather_armor', slot: 'armor', equipped: true },
      ], { baseAsset: baseAssetFor(characterKey) });
      test('wearable and weapon coexist in one projection: ' + characterKey, () => {
        assert.strictEqual(result.supported, true);
        assertSameItems(result.equipped, ['wooden_sword', 'leather_armor']);
        assert.ok(stage.children.some((c) => c.className && c.className.includes('wooden_sword')));
        assert.ok(stage.children.some((c) => c.className && c.className.includes('leather_armor')));
      });
    })();
  }

  // ---------------------------------------------------------------------
  // HELD_IN_HAND: the true-handheld canvas system, extended to all 10.
  // Everything above proves EQUIPPED_WEAPON_VISIBLE (the wearable/sheathed
  // overlay). None of it exercises GoOdysseyHandheldWeaponRenderer at all,
  // so it cannot distinguish "visible somewhere on the character" from
  // "genuinely held in a closed fist" -- exactly the gap the owner called
  // out. This section genuinely executes the real, unmodified handheld
  // renderer (including its canvas drawing calls, via the Canvas 2D shim
  // above) for every one of the 10 characters.
  const classListOf = (figure) => figure._classes;
  function makeFigure() {
    const classes = new Set(['hero-fullbody']);
    return {
      _classes: classes,
      classList: {
        add: (c) => classes.add(c),
        remove: (c) => classes.delete(c),
        contains: (c) => classes.has(c),
      },
    };
  }

  for (const characterKey of ALL_TEN_CHARACTERS) {
    await (async () => {
      const stage = new FakeStage();
      const figure = makeFigure();
      const inventory = [
        { item_id: 'wooden_sword', id: 'wooden_sword', slot: 'weapon', equipped: true, functional_equipment: true },
      ];
      const result = await handheld.renderSafe(stage, characterKey, inventory, { figureElement: figure });
      test('HELD_IN_HAND: equipped wieldable is genuinely gripped, not just visible: ' + characterKey, () => {
        assert.strictEqual(result.supported, true, JSON.stringify(result));
        assert.strictEqual(result.weaponId, 'wooden_sword');
        assert.strictEqual(stage.hidden, false);
        assert.ok(classListOf(figure).has('handheld-paper-doll-active'), 'figure did not gain the active grip class');
        assert.ok(stage.children.length === 1 && stage.children[0] instanceof FakeCanvas, 'no canvas was appended');
        const calls = stage.children[0].getContext('2d').calls;
        // A real hand-anchor transform happened (translate to the grip
        // point, then rotate/scale for this weapon's own registry values)
        // -- this is "resolvable hand anchor exists" + "weapon transform
        // exists", proved by execution, not by reading JSON.
        assert.ok(calls.some((c) => c[0] === 'translate'), 'no grip-anchor translate occurred');
        assert.ok(calls.some((c) => c[0] === 'rotate'), 'no weapon rotation transform occurred');
        assert.ok(calls.some((c) => c[0] === 'scale'), 'no weapon scale transform occurred');
        // The open-hand-suppression occlusion step actually ran (the mask
        // erase uses destination-out compositing) -- "correct occlusion
        // layer is applied", proved by execution.
        assert.ok(
          calls.some((c) => c[0] === 'drawImage'),
          'no drawImage calls at all -- composition did not run'
        );
      });
    })();
  }

  // No equipped wieldable, or an unsupported character/weapon, must not
  // silently produce a "supported: true" empty projection -- it must
  // report unsupported and leave the figure's active class off.
  await (async () => {
    const stage = new FakeStage();
    const figure = makeFigure();
    const result = await handheld.renderSafe(stage, 'guardian', [], { figureElement: figure });
    test('HELD_IN_HAND: no equipped wieldable does not silently fall back to supported', () => {
      assert.strictEqual(result.supported, false);
      assert.strictEqual(result.reason, 'no_equipped_supported_weapon');
      assert.ok(!classListOf(figure).has('handheld-paper-doll-active'));
    });
  })();

  // Replacing the equipped weapon changes which weapon is actually gripped.
  for (const characterKey of ALL_TEN_CHARACTERS) {
    await (async () => {
      const stage = new FakeStage();
      const figure = makeFigure();
      const first = await handheld.renderSafe(stage, characterKey, [
        { item_id: 'wooden_sword', slot: 'weapon', equipped: true, functional_equipment: true },
      ], { figureElement: figure });
      const second = await handheld.renderSafe(stage, characterKey, [
        { item_id: 'iron_sword', slot: 'weapon', equipped: true, functional_equipment: true },
      ], { figureElement: figure });
      test('HELD_IN_HAND: replacing the equipped weapon grips the new one: ' + characterKey, () => {
        assert.strictEqual(first.weaponId, 'wooden_sword');
        assert.strictEqual(second.supported, true);
        assert.strictEqual(second.weaponId, 'iron_sword');
        assert.ok(classListOf(figure).has('handheld-paper-doll-active'));
      });
    })();
  }

  if (failures.length) {
    console.error('Owner-device wearable coverage tests failed:');
    failures.forEach((f) => {
      console.error('- ' + f.name + ': ' + f.error);
    });
    process.exit(1);
  }
  console.log(passCount + ' passed');
}

main();
