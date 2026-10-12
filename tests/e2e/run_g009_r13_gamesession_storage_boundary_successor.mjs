/* R13 successor to the E10 B4 GameSession boundary.
 *
 * The frozen B4 runner forbids any browser storage in GameSession. N07/N08's
 * exactly-once recovery needs ONE narrow exception: ordinary public (practice)
 * answers persist their pending submission identity in sessionStorage. This
 * successor keeps every other B4 prohibition and proves the exception is bounded.
 * The frozen B4 file is not edited.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const MODULE_PATH = path.join(ROOT, 'js', 'game', 'game_session.js');
const SOURCE = fs.readFileSync(MODULE_PATH, 'utf8');

// Every original B4 source prohibition EXCEPT sessionStorage (scoped below), plus other storage/network channels.
const STILL_FORBIDDEN = [
  /\bdocument\b/, /\bfetch\b/, /\/api\/srs\/review/, /\bReviewTransport\b/, /\bSRS\b/,
  /\bprogress(?:ion)?\b/i, /\bLord(?:Review|Trial)?\b/, /\bMapBattle\b/, /\bretry\b/i, /localStorage/,
  /\bindexedDB\b/, /\bcookie\b/i, /\bBroadcastChannel\b/, /\bXMLHttpRequest\b/,
];

function boundary() {
  for (const pattern of STILL_FORBIDDEN) {
    assert.equal(pattern.test(SOURCE), false, `GameSession has forbidden dependency: ${pattern}`);
  }
  assert.equal(/sourceIdentity/.test(SOURCE), true);
  assert.equal(/\bcurrentQ\b/.test(SOURCE), false);
  const lines = SOURCE.split('\n');
  const hits = lines.map((line, i) => [i + 1, line]).filter(([, line]) => /sessionStorage/.test(line));
  assert.equal(hits.length, 2, 'sessionStorage may appear exactly twice (one read, one write)');
  const owner = (n) => {
    for (let i = n - 1; i >= 0; i--) {
      const m = /^\s{8}([A-Za-z_]+)\(.*\)\s*\{\s*$/.exec(lines[i]);
      if (m) return m[1];
    }
    return null;
  };
  assert.equal(owner(hits[0][0]), '_publicReviewStore');
  assert.equal(owner(hits[1][0]), '_savePublicReview');
  assert.ok(/global\.sessionStorage\.getItem\(storageKey\)/.test(hits[0][1]));
  assert.ok(/global\.sessionStorage\.setItem\(store\.storageKey, JSON\.stringify\(store\.entries\)\)/.test(hits[1][1]));
  assert.ok(/go:public-review:v1:\$\{owner\}/.test(SOURCE), 'storage key must be scoped to the authenticated owner');
}

class FakeStorage {
  constructor() { this.map = new Map(); this.failWrites = false; }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { if (this.failWrites) throw new Error('quota'); this.map.set(k, String(v)); }
}

let uuidCounter = 0;
function load(storage) {
  const window = { sessionStorage: storage, crypto: { randomUUID: () => `uuid-${++uuidCounter}` } };
  window.window = window;
  vm.runInNewContext(SOURCE, {
    window, globalThis: window, console: { log() {}, info() {}, warn() {}, error() {} },
    Object, Array, Number, String, Boolean, JSON, Math, Error, TypeError, RangeError, Promise, Map, Set,
  }, { filename: MODULE_PATH });
  return window.GoOdysseyGameSession.create({});
}

const cmd = (over = {}) => ({
  question_id: 7101, grade: 5, unit_name: 'u1', source_context: 'practice', training_set_id: null,
  is_scaffolding: false, ...over,
});
const keyOf = (s) => `go:public-review:v1:${s}`;
const ENTRY_KEY = JSON.stringify(['normal', 7101, 'u1']);

function scope() {
  const s = load(new FakeStorage());
  for (const bad of [
    cmd({ source_context: 'boss_trial' }), cmd({ source_context: 'guild_quest' }), cmd({ internal: true }),
    cmd({ boss_answer: { moves: [] } }), cmd({ guild_answer: { moves: [] } }), cmd({ training_set_id: 3 }),
  ]) {
    assert.throws(() => s.beginPublicReview(1, bad), /public_review_recovery_scope_mismatch/);
  }
  for (const owner of [0, -1, 'x', null, 1.5]) {
    assert.throws(() => s.beginPublicReview(owner, cmd()), /public_review_authenticated_owner_required/);
  }
}

function storedShape() {
  const st = new FakeStorage();
  const s = load(st);
  const a = s.beginPublicReview(1, cmd());
  s.publicReviewCommand(a, true);
  s.recordPublicReviewOutcome(a, 'UNKNOWN_UNCONFIRMED');
  const raw = JSON.parse(st.getItem(keyOf(1)));
  for (const entry of Object.values(raw)) {
    assert.deepEqual(Object.keys(entry).sort(), ['command', 'sent', 'state', 'uiSettled']);
    for (const k of Object.keys(entry.command)) {
      assert.ok(['question_id', 'grade', 'unit_name', 'source_context', 'training_set_id', 'is_scaffolding',
        'submission_id', 'unit_done'].includes(k), `unexpected stored field ${k}`);
    }
  }
  assert.ok(!/xp|reward|coin|loot|rank|verdict|boss|guild/i.test(st.getItem(keyOf(1))), 'no reward/authority data persisted');
  assert.deepEqual([...st.map.keys()], [keyOf(1)], 'only the owner-scoped key is written');
}

function reloadReusesIdentity() {
  const st = new FakeStorage();
  const first = load(st);
  const a = first.beginPublicReview(1, cmd());
  const sent = first.publicReviewCommand(a, true);
  first.recordPublicReviewOutcome(a, 'UNKNOWN_UNCONFIRMED');
  first.endPublicReview(a);
  const second = load(st); // simulated reload: fresh module instance, same sessionStorage
  const b = second.beginPublicReview(1, cmd());
  assert.equal(b.command.submission_id, sent.submission_id, 'same submission id after reload');
  assert.equal(b.firstRequest, false);
  assert.equal(b.settled, false);
  second.endPublicReview(b);
  assert.throws(() => second.beginPublicReview(1, cmd({ grade: 3 })), /public_review_pending_payload_changed/);
}

function otherPlayersAndModesIsolated() {
  const st = new FakeStorage();
  const s = load(st);
  const a = s.beginPublicReview(1, cmd());
  s.endPublicReview(a);
  const other = s.beginPublicReview(2, cmd());
  assert.notEqual(other.command.submission_id, a.command.submission_id);
  assert.ok(st.getItem(keyOf(1)) && st.getItem(keyOf(2)));
  s.endPublicReview(other);
  const practice = s.beginPublicReview(1, cmd(), 'practice-mode');
  assert.notEqual(practice.command.submission_id, a.command.submission_id, 'mode is part of the key');
}

function tamperFailsClosed() {
  for (const corrupt of ['{not json', '[]', '"x"']) {
    const st = new FakeStorage();
    st.setItem(keyOf(1), corrupt);
    const s = load(st);
    assert.throws(() => s.beginPublicReview(1, cmd()), /public_review_recovery_state_invalid|SyntaxError|JSON/,
      `corrupt state must fail closed: ${corrupt}`);
  }
  // entry without a submission id
  let st = new FakeStorage();
  st.setItem(keyOf(1), JSON.stringify({ [ENTRY_KEY]: { command: { question_id: 7101 }, state: 'CREATED', sent: false, uiSettled: false } }));
  assert.throws(() => load(st).beginPublicReview(1, cmd()), /public_review_recovery_state_invalid/);
  // lost storage: a brand-new, unsent identity -- never a fabricated committed state
  st = new FakeStorage();
  const lost = load(st).beginPublicReview(1, cmd());
  assert.equal(lost.settled, false);
  assert.equal(lost.firstRequest, true);
  // a local record cannot be settled without a server-confirmed outcome
  const s = load(new FakeStorage());
  const a = s.beginPublicReview(1, cmd());
  assert.throws(() => s.settlePublicReview(a), /public_review_commit_not_confirmed/);
  s.publicReviewCommand(a, false);
  assert.throws(() => s.settlePublicReview(a), /public_review_commit_not_confirmed/);
  assert.throws(() => s.recordPublicReviewOutcome(a, 'GRANTED_XP'), /public_review_outcome_invalid/);
  // a forged local NEW_COMMITTED state cannot settle without a server outcome observed by this page
  const stF = new FakeStorage();
  const sF = load(stF);
  const aF = sF.beginPublicReview(1, cmd());
  const rawF = JSON.parse(stF.getItem(keyOf(1)));
  rawF[ENTRY_KEY].state = 'NEW_COMMITTED';
  stF.setItem(keyOf(1), JSON.stringify(rawF));
  const sF2 = load(stF);
  const aF2 = sF2.beginPublicReview(1, cmd());
  assert.throws(() => sF2.settlePublicReview(aF2), /public_review_commit_not_confirmed/);
  sF2.publicReviewCommand(aF2, false);
  sF2.recordPublicReviewOutcome(aF2, 'NEW_COMMITTED'); // as index.html does from the server response
  assert.equal(sF2.settlePublicReview(aF2), true);
  // a forged "settled" flag cannot skip server verification; the API grants nothing
  const forged = new FakeStorage();
  forged.setItem(keyOf(1), JSON.stringify({ [ENTRY_KEY]: { command: { question_id: 7101, grade: 5, unit_name: 'u1',
    source_context: 'practice', training_set_id: null, is_scaffolding: false, submission_id: 'forged' },
  state: 'NEW_COMMITTED', sent: true, uiSettled: true } }));
  const fS = load(forged);
  const f = fS.beginPublicReview(1, cmd());
  assert.equal(f.settled, false, 'a persisted settled flag is not trusted on a fresh page');
  assert.equal(f.firstRequest, false, 'the stored submission id is reused for verification');
  assert.equal(f.command.submission_id, 'forged');
  fS.publicReviewCommand(f, false);
  fS.recordPublicReviewOutcome(f, 'DUPLICATE_COMMITTED_RECOVERED');
  assert.equal(fS.settlePublicReview(f), true);
  fS.endPublicReview(f);
  assert.equal(fS.beginPublicReview(1, cmd()).settled, true, 'settled once confirmed by this page');
  const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(load(new FakeStorage())));
  assert.ok(!methods.some((n) => /xp|reward|coin|grant|loot|rank/i.test(n)), 'GameSession exposes no reward/progression API');
}

function persistenceFailureBlocksSend() {
  const st = new FakeStorage();
  st.failWrites = true;
  const s = load(st);
  assert.throws(() => s.beginPublicReview(1, cmd()), /quota/, 'must fail before POST when persistence is unavailable');
  const noStorage = load(undefined);
  assert.throws(() => noStorage.beginPublicReview(1, cmd()), /getItem/, 'missing storage must fail before POST');
}

function newAttemptOnlyAfterSettleOrRejection() {
  const s = load(new FakeStorage());
  const a = s.beginPublicReview(1, cmd());
  s.endPublicReview(a);
  assert.equal(s.newPublicReviewAttempt(a), false, 'uncertain submission cannot be discarded');
  s.publicReviewCommand(a, false);
  s.recordPublicReviewOutcome(a, 'SERVER_REJECTED');
  assert.equal(s.newPublicReviewAttempt(a), true);
  const b = s.beginPublicReview(1, cmd());
  assert.notEqual(b.command.submission_id, a.command.submission_id);
}

try {
  boundary();
  scope();
  storedShape();
  reloadReusesIdentity();
  otherPlayersAndModesIsolated();
  tamperFailsClosed();
  persistenceFailureBlocksSend();
  newAttemptOnlyAfterSettleOrRejection();
  console.log(JSON.stringify({ status: 'PASS', checks: [
    'original_b4_prohibitions_kept_except_scoped_sessionStorage', 'two_exact_storage_sites_owner_scoped_key',
    'practice_only_scope', 'stored_shape_has_no_reward_or_authority_data', 'reload_reuses_submission_identity',
    'owner_and_mode_isolation', 'tamper_fails_closed_no_forged_commit', 'persistence_failure_blocks_send',
    'uncertain_submission_not_discardable'] }));
} catch (error) {
  console.error(JSON.stringify({ status: 'FAIL', message: error?.message || String(error), stack: error?.stack || null }));
  process.exitCode = 1;
}
