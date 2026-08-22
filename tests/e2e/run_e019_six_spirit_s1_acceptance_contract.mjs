import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const contractPath = path.join(here, '..', 'fixtures', 'e019_six_spirit_s1_contract.json');
const contract = JSON.parse(fs.readFileSync(contractPath, 'utf8'));

assert.deepEqual(contract.canonical_existing_spirit_ids, [
  'ink_drop_kelpie',
  'whispering_void_kit',
  'star_shell_hatchling',
  'starpath_antlerling',
  'fatty',
  'obsidian_bastion',
]);
assert.equal(contract.six_slots.length, 6);
assert.deepEqual(contract.six_slots.slice(3).map((slot) => slot.role), [
  'EXPLORATION',
  'PRECISION',
  'SUPPORT',
]);
assert.deepEqual(contract.six_slots.map((slot) => slot.spirit_id), contract.canonical_existing_spirit_ids);
assert(contract.six_slots.every((slot) => slot.identity_source === 'canonical_catalog'));

const expectedDevices = new Map([
  ['desktop', [3, 2]],
  ['ipad_landscape', [3, 2]],
  ['ipad_portrait', [2, 3]],
  ['mobile_portrait', [2, 3]],
  ['narrow_portrait', [2, 3]],
]);
for (const entry of contract.responsive_acceptance_matrix) {
  const expected = expectedDevices.get(entry.device);
  assert(expected, `missing device contract: ${entry.device}`);
  assert.deepEqual([entry.grid.columns, entry.grid.rows], expected);
  assert.equal(entry.grid.columns * entry.grid.rows, 6);
  assert(entry.viewport.width > 0 && entry.viewport.height > 0);
}
assert.equal(expectedDevices.size, contract.responsive_acceptance_matrix.length);

assert.equal(contract.hero_companion_ui.runtime_status, 'PENDING_RUNTIME');
assert.equal(contract.world_map_follower_interface.runtime_status, 'PENDING_RUNTIME');
assert.equal(contract.owner_visual_evidence.screenshots_required_now, false);
assert.equal(contract.owner_visual_evidence.runtime_status, 'PENDING_RUNTIME');

console.log('E019 Six-Spirit S1 acceptance matrix: PASS_FIXTURE_CONTRACT');
console.log('E019 browser/runtime visual execution: PENDING_RUNTIME');
