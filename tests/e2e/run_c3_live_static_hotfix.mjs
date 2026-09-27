import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// Execute the actual index functions; adapters/DOM are deterministic local fixtures.
// No authenticated server, release, or Production acceptance is claimed.
const sourcePath = process.argv[2] || new URL('../../index.html', import.meta.url);
const baselinePath = process.argv[3];
const index = fs.readFileSync(sourcePath, 'utf8');
function between(text, start, end) {
  const a = text.indexOf(start);
  const b = text.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, `missing ${start}`);
  return text.slice(a, b);
}
function harness(text, { code = null, limit = '37', response = null } = {}) {
  const events = [];
  const box = { style: {} };
  const buttons = [{ style: {}, disabled: false }];
  const ctx = vm.createContext({
    window: { MapBattleV1: { legacy: {
      prepare: async () => { events.push('prepare'); if (code) throw { code, payload: { limit } }; return { active: true, attemptId: 'fixture', questionId: 7 }; },
      submit: async () => { events.push('submit'); if (code) throw { code, payload: { limit } }; return response; },
    } } },
    document: { getElementById: () => box, querySelectorAll: () => buttons },
    I18n: { t: key => key },
    setMsg: (text, kind) => events.push(['msg', text, kind]),
    notifyAdventureQuestionRuntimeError: reason => events.push(['blocked', reason]),
    _e10AcceptanceTrace: () => {},
    _publishMapBattleV1Lifecycle: () => {},
    _resetE10BattleRevealState: () => {},
    _setGoblinCavePostAnswerControls: () => {},
    _syncE10BattleActions: () => {},
    _isAdventureZonePractice: () => true,
    _mapBattleV1QuestionContext: () => ({ zoneKey: 'k26_30', questionId: 7 }),
    _isPermanentMapBattleQuestionFailure: () => false,
    _questionLoader: { adoptIdentity: () => events.push('adopt') },
    _persistMapBattleV1Resume: () => events.push('persist'),
    _clearMapBattleV1Resume: () => events.push('clearResume'),
    _clearMapBattleV1Transition: () => {},
    _rememberDailyLimitLock: () => events.push('rememberLimit'),
    _renderDailyLimitBlockedState: () => events.push(['wall', ctx._dailyLimitMax]),
    _mapBattleV1RenderAuthoritative: (_q, result) => events.push(['render', result]),
    _refreshMapBattleV1ServerProgress: async () => events.push('refreshProgress'),
    SRS: { markSeen: id => events.push(['seen', id]) },
    setTimeout: () => { events.push('timer'); return 1; },
    clearTimeout: () => {},
    _mapBattleV1LifecycleGeneration: 1, _mapBattleV1PrepareSerial: 0,
    _mapBattleV1State: { active: true, attemptId: 'fixture', zoneKey: 'k26_30' },
    _mapBattleV1Mode: 'active', _bossMode: false, _quizPet: null,
    _dailyLimitMax: 20, _dailyLimitReached: false, solved: false,
    currentQ: { id: 7 }, ADVENTURE_UNAVAILABLE_SOURCE_CONTEXT: 'adventure_unavailable',
  });
  ctx._mapBattleV1IsActive = () => ctx._mapBattleV1Mode === 'active' && ctx._mapBattleV1State?.active === true;
  const fragments = [
    between(text, 'function _blockAdventureProgression(', 'function _mapBattleV1QuestionContext('),
    between(text, 'async function _prepareMapBattleV1ForQuestion(', 'function _mapBattleV1IsStaleError('),
    between(text, 'function _mapBattleV1IsStaleError(', 'async function _submitMapBattleV1IfActive('),
    between(text, 'async function _submitMapBattleV1IfActive(', 'function isBeginnerVillageAdventureResult('),
    between(text, 'function _applyDailyLimit(', 'function hideExplanation('),
  ];
  vm.runInContext(fragments.join('\n'), ctx);
  return { ctx, events, box, buttons };
}
let checks = 0;
for (const method of ['prepare', 'submit']) {
  for (const limit of ['37', undefined]) {
    const h = harness(index, { code: 'daily_limit', limit: limit === undefined ? null : limit });
    const result = method === 'prepare' ? await h.ctx._prepareMapBattleV1ForQuestion({ id: 7 }) : await h.ctx._submitMapBattleV1IfActive([]);
    assert.equal(result, null);
    assert.equal(h.ctx._dailyLimitMax, limit === undefined ? 20 : 37);
    assert.equal(h.ctx._dailyLimitReached, true);
    assert.equal(h.ctx.solved, true);
    assert.equal(h.buttons[0].disabled, true);
    assert.match(h.box.innerHTML, /href="\/upgrade"/);
    assert.match(h.box.innerHTML, /index\.free_limit_wall\.cta/);
    assert.ok(h.events.some(e => Array.isArray(e) && e[0] === 'wall' && e[1] === h.ctx._dailyLimitMax));
    assert.equal(h.ctx._mapBattleV1Mode, 'blocked');
    await h.ctx._submitMapBattleV1IfActive([]);
    assert.equal(h.events.filter(e => e === 'submit').length, method === 'submit' ? 1 : 0, 'blocked retry must not resubmit');
    checks++;
  }
  const h = harness(index, { code: 'premium_required' });
  if (method === 'prepare') await h.ctx._prepareMapBattleV1ForQuestion({ id: 7 });
  else await h.ctx._submitMapBattleV1IfActive([]);
  assert.equal(h.ctx._mapBattleV1Mode, 'blocked');
  assert.ok(h.events.some(e => Array.isArray(e) && e[0] === 'msg' && e[1] === 'index.premium_req' && e[2] === 'err'));
  assert.equal(h.ctx._dailyLimitReached, false);
  await h.ctx._submitMapBattleV1IfActive([]);
  assert.equal(h.events.filter(e => e === 'submit').length, method === 'submit' ? 1 : 0);
  checks++;
}
const unchanged = [
  { method: 'prepare', options: {} },
  { method: 'prepare', options: { code: 'unknown_fixture_error' } },
  { method: 'submit', options: { code: 'unknown_fixture_error' } },
  { method: 'submit', options: { response: { accepted: true, result: 'CORRECT', next_action: 'continue' } } },
  { method: 'submit', options: { response: { accepted: true, result: 'INCORRECT', next_action: 'retry' } } },
  { method: 'submit', options: { response: { accepted: true, duplicate: true, result: 'CORRECT', next_action: 'continue' } } },
];
const baseline = baselinePath ? fs.readFileSync(baselinePath, 'utf8') : index;
for (const test of unchanged) {
  const observations = [];
  for (const text of [baseline, index]) {
    const h = harness(text, test.options);
    const result = test.method === 'prepare' ? await h.ctx._prepareMapBattleV1ForQuestion({ id: 7 }) : await h.ctx._submitMapBattleV1IfActive([]);
    if (test.options.response) assert.deepEqual(result, test.options.response);
    if (test.options.response?.duplicate) assert.ok(!h.events.includes('timer'));
    if (test.options.code && test.method === 'prepare') assert.ok(h.events.some(e => e[0] === 'blocked' && e[1] === 'map_battle_runtime_failure'));
    if (test.options.code && test.method === 'submit') assert.ok(h.events.some(e => e[0] === 'msg' && /retry the same answer without SRS fallback/.test(e[1])));
    observations.push(JSON.stringify({ result, events: h.events, mode: h.ctx._mapBattleV1Mode }));
  }
  assert.equal(observations[0], observations[1], `${test.method} path must remain unchanged`);
  checks++;
}
console.log(JSON.stringify({ status: 'PASS', checks, baselineCompared: Boolean(baselinePath), authenticatedRuntime: 'NOT_RUN' }));
