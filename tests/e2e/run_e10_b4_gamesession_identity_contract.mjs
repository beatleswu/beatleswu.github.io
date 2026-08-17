import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const MODULE_PATH = path.join(ROOT, 'js', 'game', 'game_session.js');
const INDEX_PATH = path.join(ROOT, 'index.html');
const SRS_PATH = path.join(ROOT, 'srs.js');

const IDENTITY_FIELDS = [
  'questionId',
  'mode',
  'attemptId',
  'lordIndex',
  'lifecycleGeneration',
  'sourceContext',
];

const FORBIDDEN_FIELDS = [
  'dom',
  'document',
  'sgf',
  'board',
  'reward',
  'rewards',
  'presentation',
  'presentationContext',
  'transport',
  'reviewTransport',
  'fetch',
  'progression',
  'lord',
  'mapBattle',
  'retry',
  'storage',
  'sourceIdentity',
];

const FORBIDDEN_SOURCE = [
  /\bdocument\b/,
  /\bfetch\b/,
  /\/api\/srs\/review/,
  /\bReviewTransport\b/,
  /\bSRS\b/,
  /\bprogress(?:ion)?\b/i,
  /\bLord(?:Review|Trial)?\b/,
  /\bMapBattle\b/,
  /\bretry\b/i,
  /localStorage/,
  /sessionStorage/,
];

function readSource(filePath) {
  assert.equal(fs.existsSync(filePath), true, `required B4 module is missing: ${filePath}`);
  return fs.readFileSync(filePath, 'utf8');
}

function loadModule() {
  const source = readSource(MODULE_PATH);
  const window = {};
  window.window = window;
  const context = {
    window,
    globalThis: window,
    console: { log() {}, info() {}, warn() {}, error() {} },
    Object,
    Array,
    Number,
    String,
    Boolean,
    JSON,
    Math,
    Error,
    TypeError,
    RangeError,
    Promise,
  };
  vm.runInNewContext(source, context, { filename: MODULE_PATH });
  assert.ok(window.GoOdysseyGameSession, 'window.GoOdysseyGameSession must be present');
  return { api: window.GoOdysseyGameSession, source };
}

function identityInput(overrides = {}) {
  return {
    questionId: '42',
    mode: 'lord',
    attemptId: 'attempt-7',
    lordIndex: '3',
    lifecycleGeneration: 9,
    sourceContext: 'boss_trial',
    ...overrides,
  };
}

function assertIdentityShape(identity) {
  assert.deepEqual(Object.keys(identity), IDENTITY_FIELDS);
  assert.equal(identity.questionId, 42);
  assert.equal(identity.mode, 'lord');
  assert.equal(identity.attemptId, 'attempt-7');
  assert.equal(identity.lordIndex, 3);
  assert.equal(identity.lifecycleGeneration, 9);
  assert.equal(identity.sourceContext, 'boss_trial');
  for (const field of FORBIDDEN_FIELDS) {
    assert.equal(Object.prototype.hasOwnProperty.call(identity, field), false,
      `identity must not own ${field}`);
  }
}

function duplicateError(error) {
  return error?.code === 'duplicate_review' || error?.code === 'REVIEW_ALREADY_ACTIVE';
}

function runIdentityContracts(api) {
  assert.ok(api.QuestionIdentity && typeof api.QuestionIdentity === 'object');
  for (const method of ['normalize', 'equals', 'key']) {
    assert.equal(typeof api.QuestionIdentity[method], 'function',
      `QuestionIdentity.${method} must be public`);
  }
  assert.equal(typeof api.create, 'function', 'GameSession.create must be public');

  const normalized = api.QuestionIdentity.normalize(identityInput());
  assertIdentityShape(normalized);

  for (const questionId of [null, undefined, '', 'not-a-number', NaN, Infinity, -Infinity]) {
    assert.throws(
      () => api.QuestionIdentity.normalize(identityInput({ questionId })),
      /questionId|identity|finite|invalid/i,
      `non-finite questionId must be rejected: ${String(questionId)}`,
    );
  }

  const sameA = api.QuestionIdentity.normalize(identityInput({ sourceIdentity: 'ignored-a' }));
  const sameB = api.QuestionIdentity.normalize(identityInput({ sourceIdentity: 'ignored-b' }));
  const equal = api.QuestionIdentity.equals(sameA, sameB);
  assert.equal(equal, true, 'reserved sourceIdentity must not affect identity equality');
  assert.equal(api.QuestionIdentity.key(sameA), api.QuestionIdentity.key(sameB));
  assert.equal(api.QuestionIdentity.key(sameA), api.QuestionIdentity.key(identityInput()));
  assert.equal(typeof api.QuestionIdentity.key(sameA), 'string');
  assert.equal(api.QuestionIdentity.equals(sameA, identityInput({ questionId: '43' })), false);
  assert.notEqual(api.QuestionIdentity.key(sameA), api.QuestionIdentity.key(identityInput({ questionId: '43' })));

  for (const field of IDENTITY_FIELDS) {
    const changed = { ...identityInput(), [field]: field === 'questionId' ? '43' : `other-${field}` };
    assert.equal(api.QuestionIdentity.equals(sameA, changed), false,
      `identity equality must include ${field}`);
  }
}

function runSessionContracts(api) {
  const session = api.create();
  assert.ok(session && typeof session === 'object');
  for (const method of [
    'adopt',
    'current',
    'isCurrent',
    'invalidate',
    'beginReview',
    'endReview',
    'presentationContext',
  ]) {
    assert.equal(typeof session[method], 'function', `session.${method} must be public`);
  }
  for (const field of FORBIDDEN_FIELDS) {
    assert.equal(Object.prototype.hasOwnProperty.call(session, field), false,
      `session must not own ${field}`);
  }

  const first = identityInput();
  const second = identityInput({ questionId: '43', lifecycleGeneration: 10 });
  const adopted = session.adopt(first);
  assertIdentityShape(adopted);
  assert.deepEqual(session.current(), adopted);
  assert.equal(session.isCurrent(first), true);
  assert.equal(session.isCurrent(second), false);

  const context = session.presentationContext();
  assert.deepEqual(Object.keys(context), IDENTITY_FIELDS);
  assert.deepEqual(context, adopted);

  session.beginReview(first);
  assert.throws(() => session.beginReview(first), duplicateError,
    'same identity must not begin two reviews concurrently');
  session.beginReview(second);
  assert.throws(() => session.beginReview(second), duplicateError,
    'distinct identity may only have one active review of its own');
  session.endReview(first);
  session.beginReview(first);
  session.endReview(first);
  session.endReview(second);

  session.adopt(first);
  assert.equal(session.isCurrent(first), true);
  session.adopt(second);
  assert.equal(session.isCurrent(first), false, 'old identity must become stale after adopt');
  assert.equal(session.isCurrent(second), true);
  assert.deepEqual(session.current(), api.QuestionIdentity.normalize(second));
  session.invalidate();
  assert.equal(session.current(), null, 'invalidate must clear current identity');
  assert.equal(session.isCurrent(second), false, 'invalidated identity must be stale');
  assert.equal(session.presentationContext(), null, 'invalidated session has no context');
}

function runBoundaryContracts(source) {
  for (const pattern of FORBIDDEN_SOURCE) {
    assert.equal(pattern.test(source), false, `GameSession has forbidden dependency: ${pattern}`);
  }
  assert.equal(/sourceIdentity/.test(source), true,
    'sourceIdentity must remain an explicitly reserved/inert boundary');
  assert.equal(/ReviewTransport/.test(source), false,
    'ReviewTransport remains outside GameSession authority');
  assert.equal(/currentQ/.test(source), false,
    'GameSession must not migrate currentQ ownership');
}

function runIntegrationContracts() {
  const index = fs.readFileSync(INDEX_PATH, 'utf8');
  const srs = fs.readFileSync(SRS_PATH, 'utf8');
  const gameSessionScript = /<script\b[^>]*src=["']([^"']*game_session\.js[^"']*)["'][^>]*><\/script>/i.exec(index);
  const srsScript = /<script\b[^>]*src=["']([^"']*srs\.js[^"']*)["'][^>]*><\/script>/i.exec(index);
  assert.ok(gameSessionScript, 'index.html must load game_session.js');
  assert.ok(srsScript, 'index.html must load srs.js');
  assert.ok(gameSessionScript.index < srsScript.index,
    'GameSession script must load before srs.js');
  assert.match(index, /GoOdysseyGameSession/,
    'index.html must use the GameSession API');
  assert.match(index, /\.adopt\s*\(/,
    'index.html must adopt identity through GameSession');
  assert.match(index, /\.current\s*\(/,
    'index.html must read current identity through GameSession');
  assert.equal(/GoOdysseyGameSession[\s\S]{0,500}currentQ\s*=/.test(index), false,
    'GameSession integration must not assign currentQ');
  assert.equal(/GoOdysseyGameSession[\s\S]{0,1200}\/api\/srs\/review/.test(index), false,
    'GameSession must not own review HTTP');
  assert.equal(/GoOdysseyGameSession[\s\S]{0,1200}\bfetch\s*\(/.test(index), false,
    'GameSession integration must not fetch');
  assert.equal(/fetch\s*\(\s*["']\/api\/srs\/review/.test(srs), false,
    'SRS must not regain direct review HTTP');
}

function main() {
  const { api, source } = loadModule();
  runIdentityContracts(api);
  runSessionContracts(api);
  runBoundaryContracts(source);
  runIntegrationContracts();
  console.log(JSON.stringify({
    status: 'PASS',
    checks: [
      'module_and_public_api',
      'identity_normalization_and_finite_question_id',
      'identity_only_and_reserved_source_identity',
      'stable_equality_and_key',
      'session_adopt_current_stale_guard_and_invalidation',
      'review_deduplication_and_release',
      'presentation_context_shape',
      'transport_and_authority_boundaries',
      'index_load_order_and_non_migration',
    ],
  }));
}

try {
  main();
} catch (error) {
  console.error(JSON.stringify({
    status: 'FAIL',
    reason: error?.code || error?.name || 'B4_GAME_SESSION_CONTRACT_FAILURE',
    message: error?.message || String(error),
    stack: error?.stack || null,
  }));
  process.exitCode = 1;
}
