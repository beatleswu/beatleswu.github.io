/* D037 source contract checks for active-Spirit selection projection. */

const fs = require('fs');
const path = require('path');
const assert = require('assert');

const root = path.resolve(__dirname, '..', '..');
const hero = fs.readFileSync(path.join(root, 'hero.html'), 'utf8');
const index = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const app = fs.readFileSync(path.join(root, 'app.py'), 'utf8');
const runtime = fs.readFileSync(path.join(root, 'spirit_runtime.py'), 'utf8');

const heroMarkers = [
  "fetch('/api/pet/switch'",
  'ACTIVE_SPIRIT_SYNC_EVENT',
  'ACTIVE_SPIRIT_SYNC_CHANNEL',
  '_petSwitchInFlight',
  'newCompanionOperationId',
  'operation_id: operationId',
  'expected_active_spirit_id: expectedActive',
  'A network-level retry deliberately reuses the B023 operation identity',
  "!response.ok || data.ok !== true || !data.pet || data.pet.pet_key !== requestedKey",
  'data-spirit-id=',
  'aria-pressed=',
  'notifyActiveSpiritSelection();',
];
heroMarkers.forEach(marker => assert(hero.includes(marker), `hero missing ${marker}`));

const indexMarkers = [
  "function refreshActiveSpiritPresentation()",
  "active-spirit-selection-complete",
  'refreshActiveSpiritPresentation().catch(() => {});',
  "cache:'no-store'",
  'BroadcastChannel',
];
indexMarkers.forEach(marker => assert(index.includes(marker), `index missing ${marker}`));

const appMarkers = [
  "@app.route('/api/pet/switch', methods=['POST'])",
  'SPIRIT_NOT_OWNED',
  'STALE_ACTIVE_SPIRIT',
  'operation_type=\'SPIRIT_SWITCH\'',
];
appMarkers.forEach(marker => assert(app.includes(marker), `app missing ${marker}`));
assert(runtime.includes('single_active_spirit'));
assert(runtime.includes('pet_collection_with_user_pets_active_projection'));
assert(!hero.includes('localStorage.setItem(\'active_spirit'));

console.log('D037 active Spirit selection tests: 10 passed');
