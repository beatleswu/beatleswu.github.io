"""Offline execution of lane B's presentation consumer; no backend or network."""

from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "js/g009_hero_hub_batch_a.js"

HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = {};
function element() {
  return {textContent: '', innerHTML: '', dataset: {},
    querySelectorAll() { return []; },
    appendChild(child) { elements[child.id] = child; }};
}
for (const id of ['g009-character-card-name', 'g009-character-display-name',
  'g009-player-display-name', 'g009-character-companion-summary',
  'g009-character-equipment-summary', 'g009-equipment-list',
  'g009-character-switch-grid']) elements[id] = element();
elements['g009-character-card-name'].parentElement = element();
const listeners = {};
let lang = 'en';
const context = {
  document: {readyState: 'loading', body: {dataset: {}},
    getElementById(id) { return elements[id] || null; },
    createElement() { return element(); },
    querySelectorAll() { return []; },
    addEventListener(name, fn) { listeners[name] = fn; }},
  window: {addEventListener() {}},
  I18n: {getLang() { return lang; }, t(key) { return key; }},
  fetch() { throw new Error('Network is forbidden in these tests'); },
};
let source = fs.readFileSync(process.argv[1], 'utf8');
// Expose the closure only in this VM, leaving the shipped runtime private.
source = source.replace(/\}\)\(\);\s*$/, `
  globalThis.testHub = {state, renderAll, installRuntimeSignals};
})();`);
vm.runInNewContext(source, context);
const hub = context.testHub;
hub.state.catalog = {applied_character_key: 'A1', entries: [
  {character_key: 'A1', owned: true}, {character_key: 'R1', owned: false}]};
function draw(inventory) { hub.state.inventory = inventory; hub.renderAll(); }
"""


@pytest.mark.parametrize("scenario", [
    r"""
draw([]);
const note = elements['g009-level-explanation'];
assert.match(note.textContent, /Player level \(LV\) follows XP/);
assert.match(note.textContent, /Go rank.*Go skill/);
assert.match(note.textContent, /does not provide a separate hero level/);
assert.equal(elements['g009-character-card-name'].textContent, 'Lorne Redscarf');
hub.renderAll();
assert.equal(elements['g009-level-explanation'], note, 'rerender reuses the note');
assert.match(elements['g009-character-switch-grid'].innerHTML, /Character appearance/);
assert.doesNotMatch(elements['g009-character-switch-grid'].innerHTML, /data-g009-character-key="R1"/);
""",
    r"""
const inventory = [{item_id: 'sword', name_en: 'Sword', slot: 'weapon',
  functional_equipment: true, equipped: true},
  {item_id: 'hidden', name_en: 'Unequipped', functional_equipment: true, equipped: false}];
const before = JSON.stringify(inventory);
draw(inventory);
assert.match(elements['g009-equipment-list'].innerHTML, /Main hand · Functional equipment/);
assert.match(elements['g009-character-equipment-summary'].textContent, /Sword · Functional equipment/);
assert.doesNotMatch(elements['g009-equipment-list'].innerHTML, /Unequipped/);
assert.equal(JSON.stringify(inventory), before, 'presentation must not mutate authority');
""",
    r"""
for (const value of [undefined, false, 'true', 1]) {
  draw([{name_en: 'Mystery', equipped: true, functional_equipment: value}]);
  assert.match(elements['g009-equipment-list'].innerHTML, /Equipment type unconfirmed/);
  assert.doesNotMatch(elements['g009-equipment-list'].innerHTML, /Functional equipment|Cosmetic/);
}
""",
    r"""
draw(null);
assert.match(elements['g009-equipment-list'].innerHTML, /temporarily unavailable/);
draw([]);
assert.match(elements['g009-equipment-list'].innerHTML, /No server-owned equipment is equipped/);
""",
    r"""
draw([{item_id: '<bad>', name_en: '<img src=x onerror=bad()>', equipped: true,
  functional_equipment: true, icon: 'https://invalid.example/icon.png'}]);
const html = elements['g009-equipment-list'].innerHTML;
assert.match(html, /&lt;img/);
assert.match(html, /data-equipment-item="&lt;bad&gt;"/);
assert.doesNotMatch(html, /<img|https:\/\//);
""",
    r"""
draw([{name: '木劍', name_en: 'Sword', equipped: true, functional_equipment: true}]);
hub.installRuntimeSignals();
lang = 'zh-TW';
listeners['e9:i18n-changed']();
assert.match(elements['g009-level-explanation'].textContent, /玩家等級.*經驗值.*圍棋棋力.*獨立英雄等級/);
assert.match(elements['g009-equipment-list'].innerHTML, /功能裝備/);
assert.match(elements['g009-character-switch-grid'].innerHTML, /角色外觀/);
lang = 'en';
listeners['e9:i18n-changed']();
assert.match(elements['g009-level-explanation'].textContent, /Player level/);
assert.doesNotMatch(elements['g009-equipment-list'].innerHTML, /功能裝備/);
""",
], ids=["level-meaning", "functional-equipped", "unknown-classification",
        "unavailable-empty", "escaped-output", "locale-change"])
def test_hero_presentation_runtime(scenario):
    result = subprocess.run(
        ["node", "-e", HARNESS + scenario, str(RUNTIME)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
