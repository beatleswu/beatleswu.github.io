/**
 * E10 Frontend V1B B3 ReviewTransport contract runner.
 *
 * This runner is intentionally future-facing.  The pinned base does not yet
 * contain js/game/review_transport.js, so it reports one explicit expected-red
 * marker instead of hiding the missing seam with skip/xfail behavior.  Once
 * B3 supplies the seam, the same runner executes all checks below.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const MODULE_PATH = path.join(REPO_ROOT, 'js', 'game', 'review_transport.js');
const ENDPOINT = '/api/srs/review';

const CORE20 = [
  'ok',
  'ease_factor',
  'interval',
  'due_date',
  'new_badges',
  'stats',
  'xp_gain',
  'combo_mult',
  'pet_xp_added',
  'pet_xp_ratio',
  'pet_xp_gained',
  'combo_streak',
  'shield_used',
  'xp_potion_active',
  'ranked_up',
  'new_rank_level',
  'pet',
  'practice',
  'training',
  'new_appearance_items',
];

const T2_OPTIONAL_FIELDS = [
  'monster',
  'player',
  'quest_updates',
  'sp',
  'loot',
  'appearance_loot',
];

const FULL26 = [...CORE20, ...T2_OPTIONAL_FIELDS];
const DUP4 = [
  'ok',
  'progression_applied',
  'progression_duplicate',
  'question_id',
];
const REQUEST_FIELDS = [
  'question_id',
  'grade',
  'unit_name',
  'unit_done',
  'response_ms',
  'source_context',
  'training_set_id',
  'is_scaffolding',
];

function fullPayload() {
  const core = {
    ok: true,
    ease_factor: 2.5,
    interval: 3,
    due_date: '2026-08-17',
    new_badges: [],
    stats: { xp: 10, total_correct: 1 },
    xp_gain: 10,
    combo_mult: 1.0,
    pet_xp_added: 0,
    pet_xp_ratio: 0.0,
    pet_xp_gained: 1,
    combo_streak: 1,
    shield_used: false,
    xp_potion_active: false,
    ranked_up: false,
    new_rank_level: null,
    pet: null,
    practice: { level: 1 },
    training: { level: 1 },
    new_appearance_items: [],
  };
  return {
    ...core,
    monster: { defeated: false },
    player: { hp: 30 },
    quest_updates: [],
    sp: null,
    loot: null,
    appearance_loot: null,
  };
}

function corePayload() {
  const full = fullPayload();
  return Object.fromEntries(CORE20.map((field) => [field, full[field]]));
}

function duplicatePayload() {
  return {
    ok: true,
    progression_applied: false,
    progression_duplicate: true,
    question_id: 7001,
  };
}

function response(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    async json() { return body; },
  };
}

function fetcherFor(result) {
  const calls = [];
  const fetcher = async (url, options) => {
    calls.push({ url, options });
    return result;
  };
  fetcher.calls = calls;
  return fetcher;
}

function loadTransport() {
  const source = fs.readFileSync(MODULE_PATH, 'utf8');
  const window = {};
  window.window = window;
  const sandbox = {
    window,
    globalThis: window,
    console,
    Promise,
    Error,
    TypeError,
    Object,
    Array,
    JSON,
    Number,
    String,
    Boolean,
    RegExp,
    Symbol,
  };
  vm.runInNewContext(source, sandbox, { filename: MODULE_PATH });
  return { transport: window.ReviewTransport, source };
}

function command() {
  return {
    question_id: 7001,
    grade: 5,
    unit_name: 'Whole Board',
    unit_done: true,
    response_ms: 4200,
    source_context: 'boss_trial:attempt-001',
    training_set_id: null,
    is_scaffolding: false,
  };
}

function assertRequestCall(fetcher, expectedBody) {
  assert.equal(fetcher.calls.length, 1, 'one answer must issue one Review request');
  const [{ url, options }] = fetcher.calls;
  assert.equal(url, ENDPOINT);
  assert.equal(options.credentials, 'include');
  assert.equal(options.method, 'POST');
  assert.deepEqual(options.headers, { 'Content-Type': 'application/json' });
  assert.deepEqual(JSON.parse(options.body), expectedBody);
}

function assertTransportError(error, code) {
  assert.equal(error.kind, 'TRANSPORT_ERROR');
  assert.equal(error.code, code);
  return true;
}

async function runContract() {
  const { transport, source } = loadTransport();
  assert.ok(transport && typeof transport === 'object');
  assert.equal(transport.endpoint, ENDPOINT);
  for (const method of ['buildRequest', 'mapOutcome', 'review', 'legacyReview']) {
    assert.equal(typeof transport[method], 'function', `${method} must be public`);
  }
  assert.equal(transport.retry, undefined, 'ReviewTransport must not expose retry');
  assert.equal(transport.dispatch, undefined, 'ReviewTransport must not own presentation');
  assert.equal(transport.present, undefined, 'ReviewTransport must not own presentation');

  const forbiddenDependencies = [
    /\bdocument\b/,
    /\bnextQuestion\b/,
    /\bLordReviewController\b/,
    /\bMapBattleV1\b/,
    /\bSRS\b/,
    /localStorage/,
    /sessionStorage/,
    /\/api\/badges\/seen/,
    /\/api\/unit-progress/,
    /\/api\/xp\/status/,
  ];
  for (const pattern of forbiddenDependencies) {
    assert.equal(pattern.test(source), false, `forbidden ReviewTransport dependency: ${pattern}`);
  }

  const privateStateNames = [
    '_allCards',
    '_dueSet',
    '_seenSet',
    '_earned',
    '_onBadge',
    '_onMonster',
    '_onQuest',
  ];
  for (const name of privateStateNames) {
    assert.equal(Object.prototype.hasOwnProperty.call(transport, name), false);
    assert.equal(source.includes(name), false, `private SRS state leaked: ${name}`);
  }

  const privateCommand = {
    ...command(),
    internal: true,
    submission_id: 'internal-only-value',
    attempt_id: 'must-not-leak',
    mode: 'lord',
  };
  const built = transport.buildRequest(privateCommand);
  assert.deepEqual(Object.keys(built), REQUEST_FIELDS);
  assert.deepEqual(built, {
    question_id: 7001,
    grade: 5,
    unit_name: 'Whole Board',
    unit_done: true,
    response_ms: 4200,
    source_context: 'boss_trial:attempt-001',
    training_set_id: null,
    is_scaffolding: false,
  });

  const defaults = transport.buildRequest({ question_id: 7001, grade: 0 });
  assert.deepEqual(defaults, {
    question_id: 7001,
    grade: 0,
    unit_name: null,
    unit_done: false,
    response_ms: null,
    source_context: 'practice',
    training_set_id: null,
    is_scaffolding: false,
  });

  const full = fullPayload();
  const fullFetcher = fetcherFor(response(full));
  const fullOutcome = await transport.review(command(), fullFetcher);
  assert.equal(fullOutcome.kind, 'PUBLIC_FULL');
  assert.deepEqual(fullOutcome.payload, full);
  assert.deepEqual(Object.keys(fullOutcome.payload), FULL26);
  assertRequestCall(fullFetcher, built);

  const core = corePayload();
  const coreOutcome = transport.mapOutcome(core);
  assert.equal(coreOutcome.kind, 'PUBLIC_CORE');
  assert.deepEqual(Object.keys(coreOutcome.payload), CORE20);
  assert.equal(Object.prototype.hasOwnProperty.call(coreOutcome.payload, 'loot'), false);
  core.xp_gain = 999;
  assert.equal(coreOutcome.payload.xp_gain, 10, 'outcome is a top-level snapshot');

  // Incident 017 response matrix: a review response gets an approved
  // presentation extension appended by the server (review_compatibility.py,
  // APPROVED_PRESENTATION_EXTENSION_FIELDS) whenever it ranks the player up
  // (level_up_rewards) and/or the battlefield/equipment path runs
  // (combat_stats). CORE20-only and FULL26-only are already covered above;
  // this exercises the remaining approved combinations. Every case must
  // preserve the extension value(s) on the returned payload -- the shape
  // check strips them only for the exact-key comparison, not from the
  // result callers actually receive.
  const levelUpReward = { rewards: ['skill:atk1'] };
  const combatStats = { attack_bonus: 0.08 };

  const coreWithCombatStats = { ...corePayload(), combat_stats: combatStats };
  const coreWithCombatStatsOutcome = transport.mapOutcome(coreWithCombatStats);
  assert.equal(coreWithCombatStatsOutcome.kind, 'PUBLIC_CORE');
  assert.deepEqual(coreWithCombatStatsOutcome.payload, coreWithCombatStats);

  const coreWithLevelUp = { ...corePayload(), level_up_rewards: levelUpReward };
  const coreWithLevelUpOutcome = transport.mapOutcome(coreWithLevelUp);
  assert.equal(coreWithLevelUpOutcome.kind, 'PUBLIC_CORE');
  assert.deepEqual(coreWithLevelUpOutcome.payload, coreWithLevelUp);

  const coreWithBothExtensions = {
    ...corePayload(),
    combat_stats: combatStats,
    level_up_rewards: levelUpReward,
  };
  const coreWithBothOutcome = transport.mapOutcome(coreWithBothExtensions);
  assert.equal(coreWithBothOutcome.kind, 'PUBLIC_CORE');
  assert.deepEqual(coreWithBothOutcome.payload, coreWithBothExtensions);

  const fullWithCombatStats = { ...fullPayload(), combat_stats: combatStats };
  const fullWithCombatStatsOutcome = transport.mapOutcome(fullWithCombatStats);
  assert.equal(fullWithCombatStatsOutcome.kind, 'PUBLIC_FULL');
  assert.deepEqual(fullWithCombatStatsOutcome.payload, fullWithCombatStats);

  const fullWithLevelUp = { ...fullPayload(), level_up_rewards: levelUpReward };
  const fullWithLevelUpOutcome = transport.mapOutcome(fullWithLevelUp);
  assert.equal(fullWithLevelUpOutcome.kind, 'PUBLIC_FULL');
  assert.deepEqual(fullWithLevelUpOutcome.payload, fullWithLevelUp);

  const fullWithBothExtensions = {
    ...fullPayload(),
    combat_stats: combatStats,
    level_up_rewards: levelUpReward,
  };
  const fullWithBothOutcome = transport.mapOutcome(fullWithBothExtensions);
  assert.equal(fullWithBothOutcome.kind, 'PUBLIC_FULL');
  assert.deepEqual(fullWithBothOutcome.payload, fullWithBothExtensions);

  // The allowlist is exact, not a general "ignore anything extra" relaxation:
  // a genuinely unrecognized key must still be rejected even alongside an
  // approved one.
  assert.throws(
    () => transport.mapOutcome({ ...corePayload(), level_up_rewards: {}, unexpected: true }),
    (error) => error.code === 'invalid_review_response',
  );

  const coreFetcher = fetcherFor(response(corePayload()));
  const legacyCore = await transport.legacyReview(
    7001,
    3,
    null,
    false,
    { source_context: 'practice' },
    coreFetcher,
  );
  assert.deepEqual(legacyCore, corePayload());
  assert.deepEqual(Object.keys(legacyCore), CORE20);
  assertRequestCall(coreFetcher, {
    question_id: 7001,
    grade: 3,
    unit_name: null,
    unit_done: false,
    response_ms: null,
    source_context: 'practice',
    training_set_id: null,
    is_scaffolding: false,
  });

  const duplicate = duplicatePayload();
  const duplicateInternal = transport.mapOutcome(duplicate, { internal: true });
  assert.equal(duplicateInternal.kind, 'INTERNAL_DUPLICATE');
  assert.deepEqual(Object.keys(duplicateInternal.payload), DUP4);
  assert.throws(
    () => transport.mapOutcome(duplicate),
    (error) => error.code === 'invalid_review_response',
  );

  for (const malformed of [
    null,
    [],
    { ok: true },
    { ...corePayload(), unexpected: true },
  ]) {
    assert.throws(
      () => transport.mapOutcome(malformed),
      (error) => error.code === 'invalid_review_response',
    );
  }

  const dailyLimit = {
    error: 'daily_limit',
    message: 'free daily limit reached',
    today_count: 20,
    limit: 20,
    upgrade_url: '/upgrade',
  };
  const rejectedFetcher = fetcherFor(response(dailyLimit, { ok: false, status: 429 }));
  await assert.rejects(
    () => transport.review(command(), rejectedFetcher),
    (error) => {
      assert.equal(error.kind, 'REJECTED');
      assert.equal(error.code, 'daily_limit');
      assert.equal(error.status, 429);
      assert.deepEqual(error.payload, dailyLimit);
      return true;
    },
  );
  assertRequestCall(rejectedFetcher, built);

  const legacyRejectedFetcher = fetcherFor(
    response(dailyLimit, { ok: false, status: 429 }),
  );
  const legacyRejected = await transport.legacyReview(
    7001,
    5,
    null,
    false,
    {},
    legacyRejectedFetcher,
  );
  assert.deepEqual(legacyRejected, dailyLimit);
  assertRequestCall(legacyRejectedFetcher, {
    question_id: 7001,
    grade: 5,
    unit_name: null,
    unit_done: false,
    response_ms: null,
    source_context: 'practice',
    training_set_id: null,
    is_scaffolding: false,
  });

  const businessRejected = { error: 'invalid_source_context' };
  await assert.rejects(
    () => transport.review(command(), fetcherFor(
      response(businessRejected, { ok: false, status: 400 }),
    )),
    (error) => error.kind === 'REJECTED' && error.code === 'invalid_source_context',
  );

  const networkFetcher = fetcherFor(null);
  networkFetcher.calls.length = 0;
  const failingNetworkFetcher = async (url, options) => {
    networkFetcher.calls.push({ url, options });
    throw new Error('offline');
  };
  await assert.rejects(
    () => transport.review(command(), failingNetworkFetcher),
    (error) => assertTransportError(error, 'review_transport_error'),
  );
  assert.equal(networkFetcher.calls.length, 1);

  const parseFailureFetcher = fetcherFor({
    ok: true,
    status: 200,
    async json() { throw new Error('not-json'); },
  });
  await assert.rejects(
    () => transport.review(command(), parseFailureFetcher),
    (error) => assertTransportError(error, 'review_response_parse_error'),
  );
  assert.equal(parseFailureFetcher.calls.length, 1);

  const httpFailureFetcher = fetcherFor(
    response({ message: 'server unavailable' }, { ok: false, status: 503 }),
  );
  await assert.rejects(
    () => transport.review(command(), httpFailureFetcher),
    (error) => assertTransportError(error, 'review_http_error'),
  );
  assert.equal(httpFailureFetcher.calls.length, 1);

  const presentationFetcher = fetcherFor(response(fullPayload()));
  const committed = await transport.review(command(), presentationFetcher);
  assert.equal(committed.kind, 'PUBLIC_FULL');
  try {
    throw new Error('presentation-only failure');
  } catch {
    // A display failure is outside this module and cannot cause another Review.
  }
  assert.equal(presentationFetcher.calls.length, 1);

  return {
    status: 'PASS',
    checks: [
      'command_serialization',
      'identity_and_defaults',
      'public_full_and_core_mapping',
      'approved_presentation_extension_fields_survive_exact_shape_check',
      'internal_duplicate_boundary',
      'legacy_passthrough',
      'rejected_review',
      'transport_and_validation_errors',
      'one_request_and_no_presentation_retry',
      'no_dom_lord_mapbattle_or_private_srs_dependency',
    ],
  };
}

async function main() {
  if (!fs.existsSync(MODULE_PATH)) {
    console.error(JSON.stringify({
      status: 'EXPECTED_RED',
      reason: 'MISSING_FUTURE_REVIEW_TRANSPORT_SEAM',
      path: 'js/game/review_transport.js',
    }));
    process.exitCode = 2;
    return;
  }
  const report = await runContract();
  console.log(JSON.stringify(report));
}

main().catch((error) => {
  console.error(JSON.stringify({
    status: 'FAIL',
    reason: error?.code || error?.name || 'REVIEW_TRANSPORT_CONTRACT_FAILURE',
    message: error?.message || String(error),
    stack: error?.stack || null,
  }));
  process.exitCode = 1;
});
