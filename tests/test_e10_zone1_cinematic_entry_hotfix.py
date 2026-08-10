"""Regression coverage for the E10 Zone 1 cinematic entry hotfix.

These tests execute the real routing/state helper source from the checkout.
They intentionally do not exercise Production or write player progression.
"""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
WORLD_STAGE = (ROOT / "js/e9/world_stage.js").read_text(encoding="utf-8")


def _block(source, start_marker, end_marker):
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_zone1_normal_progression_bridges_to_the_canonical_cinematic_host():
    body = _block(
        WORLD_STAGE,
        "function dispatchAdventureAction(contract) {",
        "\n  function configureAdventureButton(",
    )
    zone1 = body.index("contract.kind === 'normal_progression' && contract.targetZoneKey === 'k26_30'")
    ordinary = body.rindex("window.E9.startAdventureFromE9(contract.targetZoneKey);")
    branch = body[zone1:ordinary]
    assert "window.ensureLegacyAdventureMapReady({ reuseE9Adapter: true })" in branch
    assert "window.startAdventureStage(contract.targetZoneKey);" in branch
    assert "return;" in branch
    assert zone1 < ordinary


def test_canonical_zone1_host_preserves_existing_training_handoff():
    start = INDEX.index("async function startAdventureStage(zoneKey)")
    end = INDEX.index("\nfunction adventureIntroSeen(zone)", start)
    body = INDEX[start:end]
    assert "await showStageIntroCinematic(zone);" in body

    cinematic_start = INDEX.index("async function showStageIntroCinematic(zone)")
    cinematic_end = INDEX.index("\n\n window.startAdventureStage", cinematic_start)
    cinematic_body = INDEX[cinematic_start:cinematic_end]
    assert "enterAdventureZoneInPage(zone)" in cinematic_body


def test_intro_seen_state_is_account_nested_and_legacy_browser_shape_is_not_read():
    assert "ADVENTURE_INTRO_STORAGE_KEY = 'adventure_intro_seen_v2'" in INDEX
    seen = _block(INDEX, "function adventureIntroSeen(zone)", "\n\n// Account scope for Zone 1's POST_CLEAR")
    marked = _block(INDEX, "function markAdventureIntroSeen(zone)", "\n\n// Account scope for Zone 1's POST_CLEAR")
    assert "_postClearAccountId()" in seen
    assert "byUser[uid]?.[zone.key]" in seen
    assert "byUser[uid] = byUser[uid] || {}" in marked
    assert "seen[zone.key]" not in seen
    assert "seen[zone.key]" not in marked
    assert "adventure_intro_seen_v1" in INDEX  # documented legacy key only
    assert "localStorage.getItem('adventure_intro_seen_v1')" not in seen + marked


_INTRO_STATE_NODE_HARNESS = r"""
'use strict';
const fs = require('fs');
const assert = require('assert');
const vm = require('vm');

const source = fs.readFileSync(process.argv[1], 'utf8');

function extractFunction(name) {
  const start = source.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('function not found: ' + name);
  const open = source.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let i = open; i < source.length; i++) {
    const ch = source[i];
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth++;
    else if (ch === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error('unterminated function: ' + name);
}

const helper = extractFunction('_postClearAccountId');
const seen = extractFunction('adventureIntroSeen');
const mark = extractFunction('markAdventureIntroSeen');
const script = `
const ADVENTURE_INTRO_STORAGE_KEY = 'adventure_intro_seen_v2';
let _currentUserId = null;
const localStorage = {
  data: Object.create(null),
  getItem(key) { return Object.prototype.hasOwnProperty.call(this.data, key) ? this.data[key] : null; },
  setItem(key, value) { this.data[key] = String(value); },
};
${helper}
${seen}
${mark}
function setUser(uid) { _currentUserId = uid; }
function readIntro(zone) { return adventureIntroSeen(zone); }
function writeIntro(zone) { markAdventureIntroSeen(zone); }
function writeLegacyIntro(zone) { localStorage.setItem('adventure_intro_seen_v1', JSON.stringify({ [zone.key]: Date.now() })); }
`;
const sandbox = { console };
vm.createContext(sandbox);
new vm.Script(script).runInContext(sandbox);

const zone = { key: 'k26_30' };
sandbox.setUser(101);
assert.strictEqual(sandbox.readIntro(zone), false, 'fresh account should be unseen');
sandbox.writeIntro(zone);
assert.strictEqual(sandbox.readIntro(zone), true, 'same account should become seen');

sandbox.setUser(202);
assert.strictEqual(sandbox.readIntro(zone), false, 'second account must not inherit first account seen state');
sandbox.writeIntro(zone);
assert.strictEqual(sandbox.readIntro(zone), true, 'second account should keep its own seen state');

sandbox.setUser(101);
assert.strictEqual(sandbox.readIntro(zone), true, 'first account state remains isolated and durable');

// A legacy browser-wide v1 value must never suppress a newly resolved account.
sandbox.setUser(303);
    sandbox.writeLegacyIntro(zone);
assert.strictEqual(sandbox.readIntro(zone), false, 'legacy browser-wide state must not cross-suppress');

console.log('account-scoped intro state: 5 passed, 0 failed');
"""


def test_account_scoped_intro_state_real_helpers_cover_same_and_cross_account_browser_cases():
    result = subprocess.run(
        ["node", "-e", _INTRO_STATE_NODE_HARNESS, "--", str(ROOT / "index.html")],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f"account-scoped intro state failed:\n{result.stdout}\n{result.stderr}"
    assert "5 passed, 0 failed" in result.stdout


def test_later_cinematic_gates_and_progression_boundaries_are_unchanged():
    assert "if (!_adventureBossReady(zone)) return;" in INDEX
    assert "if (adventureBossReadyFilmSeen(zone)) return;" in INDEX
    assert "challenge_lord" in WORLD_STAGE
    assert "window.openAdventureBossFromQuestCard(contract.targetZoneKey)" in WORLD_STAGE
    assert "monster_defeated" in INDEX
    assert "_maybeTriggerZone1PostClearFilm" in INDEX

    dispatch = _block(
        WORLD_STAGE,
        "function dispatchAdventureAction(contract) {",
        "\n  function configureAdventureButton(",
    )
    assert "/api/" not in dispatch
    assert "submit" not in dispatch.lower()
    assert "fetch(" not in dispatch


def test_zone1_completed_account_keeps_replay_training_contract_instead_of_intro_route():
    # The existing E9 contract classifies a completed Zone 1 as replay_completed;
    # only normal_progression is sent to the cinematic host by this hotfix.
    assert "if (zone.status === 'completed')" in WORLD_STAGE
    assert "kind: 'replay_completed'" in WORLD_STAGE
    dispatch = _block(
        WORLD_STAGE,
        "function dispatchAdventureAction(contract) {",
        "\n  function configureAdventureButton(",
    )
    assert "contract.kind === 'normal_progression' && contract.targetZoneKey === 'k26_30'" in dispatch
    assert "contract.kind === 'replay_completed'" not in dispatch


def test_other_zone_normal_progression_still_uses_existing_ordinary_entry():
    dispatch = _block(
        WORLD_STAGE,
        "function dispatchAdventureAction(contract) {",
        "\n  function configureAdventureButton(",
    )
    zone1_branch = dispatch.index("contract.kind === 'normal_progression' && contract.targetZoneKey === 'k26_30'")
    ordinary = dispatch.rindex("window.E9.startAdventureFromE9(contract.targetZoneKey);")
    assert zone1_branch < ordinary
    assert "targetZoneKey === 'k26_30'" in dispatch[zone1_branch:ordinary]
