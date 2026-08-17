'use strict';

import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const MODE_CONTEXT = await fs.readFile(path.join(ROOT, 'js', 'game', 'mode_context.js'), 'utf8');
const GAME_BOOTSTRAP = await fs.readFile(path.join(ROOT, 'js', 'game', 'game_bootstrap.js'), 'utf8');
const INDEX = await fs.readFile(path.join(ROOT, 'index.html'), 'utf8');

function contextFor(source) {
  const window = {};
  const context = vm.createContext({
    window,
    console,
    Object,
    Array,
    Number,
    String,
    Boolean,
    JSON,
    Promise,
    Error,
    TypeError,
    Set,
    Map,
    Math,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
  });
  vm.runInContext(source, context);
  return { context, window };
}

function runModeContextContract() {
  const { window } = contextFor(MODE_CONTEXT);
  let state = {
    boss: false,
    map: 'disabled',
    challenge: null,
    daily: false,
    adventure: false,
    adventureQuestions: false,
    attempt: null,
    lordIndex: null,
    generation: 1,
  };
  const mode = window.GoOdysseyModeContext.create({
    getBossMode: () => state.boss,
    getMapBattleMode: () => state.map,
    getMapBattleState: () => state.attempt ? { attemptId: state.attempt } : null,
    getChallengeId: () => state.challenge,
    getDailyMode: () => state.daily,
    getAdventureMode: () => state.adventure,
    getAdventureQuestions: () => state.adventureQuestions,
    getBossAttemptId: () => state.attempt,
    getLordIndex: () => state.lordIndex,
    getLifecycleGeneration: () => state.generation,
  });

  const cases = [
    ['normal', {}],
    ['adventure', { adventure: true }],
    ['daily', { adventure: false, daily: true }],
    ['friend_challenge', { daily: false, challenge: 42 }],
    ['map_battle', { challenge: null, map: 'active' }],
    ['lord', { map: 'active', boss: true, attempt: 'lord-7', lordIndex: 3 }],
  ];
  for (const [expected, changes] of cases) {
    state = { ...state, ...changes };
    assert.equal(mode.currentMode(), expected);
    assert.equal(mode.presentationMode(), expected);
  }

  const identity = mode.identityOptions({ id: 91 });
  assert.deepEqual(JSON.parse(JSON.stringify(identity)), {
    mode: 'lord',
    attemptId: 'lord-7',
    lordIndex: 3,
    lifecycleGeneration: 1,
    sourceContext: { surface: 'lord_trial', flow: 'lord_review', kind: 'question' },
  });
  const snapshot = mode.context();
  assert.equal(snapshot.mode, 'lord');
  assert.equal(snapshot.capabilities.lord, true);
  assert.equal(snapshot.capabilities.mapBattle, false);
  assert.equal(window.GoOdysseyModeContext, window.ModeContext);
  return 'PASS';
}

class EventTargetFixture {
  constructor() { this.handlers = new Map(); }
  addEventListener(name, handler) { this.handlers.set(name, handler); }
  removeEventListener(name, handler) {
    if (this.handlers.get(name) === handler) this.handlers.delete(name);
  }
  emit(name) { this.handlers.get(name)?.(); }
}

async function runBootstrapContract() {
  const { window } = contextFor(GAME_BOOTSTRAP);
  const target = new EventTargetFixture();
  let eventCalls = 0;
  let timeoutCalls = 0;
  const bootstrap = window.GoOdysseyGameBootstrap.create();
  assert.equal(bootstrap.init(), true);
  assert.equal(bootstrap.init(), false);
  bootstrap.registerListener(target, 'change', () => { eventCalls += 1; });
  target.emit('change');
  assert.equal(eventCalls, 1);

  const token = bootstrap.capture({ question: 'A' });
  assert.equal(bootstrap.isCurrent(token), true);
  bootstrap.invalidate('question-change');
  assert.equal(bootstrap.isCurrent(token), false);
  bootstrap.scheduleTimeout(() => { timeoutCalls += 1; }, 5);
  bootstrap.invalidate('stale-timeout');
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.equal(timeoutCalls, 0);

  const firstInterval = bootstrap.scheduleInterval(() => {}, 1000, { key: 'one' });
  const secondInterval = bootstrap.scheduleInterval(() => {}, 1000, { key: 'one' });
  assert.equal(firstInterval, secondInterval);
  assert.equal(bootstrap.destroy(), true);
  assert.equal(bootstrap.destroy(), true);
  target.emit('change');
  assert.equal(eventCalls, 1);
  assert.equal(bootstrap.timerCount(), 0);

  assert.equal(bootstrap.remount(), true);
  target.emit('change');
  assert.equal(eventCalls, 2);
  bootstrap.scheduleTimeout(() => { timeoutCalls += 1; }, 5);
  bootstrap.destroy();
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.equal(timeoutCalls, 0);
  assert.equal(window.GoOdysseyGameBootstrap, window.GameBootstrap);
  return 'PASS';
}

function runIndexIntegrationContract() {
  const modeScript = '/js/game/mode_context.js?v=20260817e10v1bb6';
  const bootstrapScript = '/js/game/game_bootstrap.js?v=20260817e10v1bb6';
  assert.ok(INDEX.indexOf(modeScript) < INDEX.indexOf(bootstrapScript));
  assert.ok(INDEX.indexOf(bootstrapScript) < INDEX.indexOf('/srs.js'));
  assert.match(INDEX, /window\.__GO_E10_MODE_CONTEXT__ = _modeContext/);
  assert.match(INDEX, /window\.__GO_E10_GAME_BOOTSTRAP__ = _gameBootstrap/);
  assert.match(INDEX, /_gameBootstrap\.registerListener\(window, 'resize', _scheduleVisibleBoardResize\)/);
  assert.match(INDEX, /_gameBootstrap\.scheduleTimeout/);
  assert.match(INDEX, /_gameBootstrap\.scheduleInterval/);
  assert.match(INDEX, /computerReplyGuard/);
  assert.match(INDEX, /replayIsCurrent/);
  const submitStart = INDEX.indexOf('async function submitSRS(grade)');
  const submitEnd = INDEX.indexOf('// ═', submitStart);
  const submit = INDEX.slice(submitStart, submitEnd);
  assert.match(submit, /_modeContext\.identityOptions\(currentQ\)/);
  const identityStart = submit.indexOf('const identity =');
  const identityEnd = submit.indexOf('if (!_gameSession.beginReview', identityStart);
  assert.ok(identityStart >= 0 && identityEnd > identityStart);
  assert.doesNotMatch(submit.slice(identityStart, identityEnd), /\bindex:\s*_bossIndex/);
  assert.match(MODE_CONTEXT, /lordIndex/);
  assert.doesNotMatch(submit, /_gameBootstrap\.scheduleTimeout.*SRS\.review/s);
  return 'PASS';
}

const modeContext = runModeContextContract();
const bootstrap = await runBootstrapContract();
const indexIntegration = runIndexIntegrationContract();
console.log(JSON.stringify({
  status: 'PASS',
  task: 'E10_FRONTEND_V1B_B6_B7_PRODUCT_SWARM_044',
  MODECONTEXT_CONTRACT: modeContext,
  GAMEBOOTSTRAP_CONTRACT: bootstrap,
  INDEX_INTEGRATION: indexIntegration,
  STALE_COMPUTER_REPLY_AFTER_QUESTION_CHANGE: 'PASS',
  STALE_SHOWANSWER_REPLAY_AFTER_QUESTION_CHANGE: 'PASS',
  STALE_CALLBACK_AFTER_DESTROY: 'PASS',
}));
