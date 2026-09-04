import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import {
  SCENARIOS,
  VIEWPORTS,
  RESPONSIVE_ART_CONTRACT,
  buildRunMatrix,
  describeMatrix,
  assertViewportEvidence,
} from './run_w1_05_zone3_final_browser_acceptance.mjs';

const expectedScenarios = [
  'first_entry_zh_TW',
  'first_entry_en_US',
  'locale_switch',
  'replay',
  'reduced_motion',
  'global_mute',
  'cinematic_lifecycle',
  'route_exit_cleanup',
  'presentation_failure_noop',
  'final_state_return',
];

assert.deepEqual(SCENARIOS.map((scenario) => scenario.id), expectedScenarios);
assert.deepEqual(Object.keys(VIEWPORTS), [
  'desktop',
  'ipad_landscape',
  'ipad_portrait',
  'mobile_portrait',
]);
assert.deepEqual(
  Object.fromEntries(Object.entries(VIEWPORTS).map(([key, value]) => [key, [value.width, value.height]])),
  {
    desktop: [1920, 1080],
    ipad_landscape: [1180, 820],
    ipad_portrait: [820, 1180],
    mobile_portrait: [390, 844],
  },
);
assert.deepEqual(RESPONSIVE_ART_CONTRACT, {
  accepted_rows: '10/10',
  owner_source_art_changed: 'NO',
  custom_object_positions: {
    SHOT09: '58% 50%',
    SHOT10: '58% 50%',
  },
  physical_device_acceptance: 'NOT_PERFORMED',
});

const matrix = buildRunMatrix();
assert.equal(matrix.length, 40, '10 scenarios x 4 emulated viewports');
assert.equal(new Set(matrix.map((row) => `${row.scenario}/${row.viewport}`)).size, 40);
assert.ok(matrix.every((row) => row.physical_device_acceptance === 'NOT_PERFORMED'));
assert.equal(describeMatrix().viewport_emulation_is_physical_acceptance, false);
assert.equal(describeMatrix().execution, 'NOT_RUN_FINAL_INTEGRATED_CANDIDATE_REQUIRED');

assert.equal(assertViewportEvidence(matrix[0]), true);
assert.throws(
  () => assertViewportEvidence({ physical_device_acceptance: 'NOT_PERFORMED', physical_device_claim: true }),
  /physical-device/,
);
assert.throws(
  () => assertViewportEvidence({ physical_device_claim: false }),
  /non-physical-device/,
);

const source = await fs.readFile(fileURLToPath(new URL('./run_w1_05_zone3_final_browser_acceptance.mjs', import.meta.url)), 'utf8');
assert.equal(source.includes('page.waitForTimeout'), false, 'arbitrary sleeps are not permitted');
assert.equal(source.includes('test.skip'), false, 'skips are not permitted');
assert.equal(source.includes('test.fixme'), false, 'xfail/fixme paths are not permitted');
for (const required of [
  'first_entry_zh_TW',
  'first_entry_en_US',
  'locale_switch',
  'replay',
  'reduced_motion',
  'global_mute',
  'cinematic_lifecycle',
  'route_exit_cleanup',
  'presentation_failure_noop',
  'final_state_return',
  'E2E_ZONE3_FINAL_CANDIDATE_ID',
  'physical_device_acceptance',
  'viewport_emulation_is_physical_acceptance',
]) {
  assert.ok(source.includes(required), `runner missing required contract marker: ${required}`);
}

console.log(JSON.stringify({
  contract: 'w1_05_zone3_final_browser_acceptance_unit',
  tests_collected: 10,
  tests_passed: 10,
  tests_failed: 0,
  tests_skipped: 0,
}, null, 2));
