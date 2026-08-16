'use strict';

/*
 * B1B is deliberately an independent contract runner.  It provides only a
 * deterministic browser-global fixture and never opens a network connection.
 * On the canonical pre-implementation base it reports a structured
 * missing_asset state; the Python wrapper classifies that as expected red.
 */

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const MODULE_PATH = path.join(ROOT, 'js', 'game', 'presentation_dispatcher.js');

const CASE_NAMES = [
  'missing_data',
  'data_not_ok',
  'all_effects_succeed',
  'badge_callback_throws',
  'badge_state_dependency_throws',
  'badge_seen_sync_throws',
  'badge_seen_promise_rejects',
  'monster_callback_throws',
  'quest_callback_throws',
  'on_error_throws',
  'deterministic_result',
  'never_calls_review_transport',
  'never_calls_progression',
];

function asError(error) {
  return {
    name: error?.name || 'Error',
    message: error?.message || String(error || ''),
  };
}

function createFixture() {
  const counters = {
    reviewFetches: [],
    srsReviewCalls: 0,
    progressionCalls: [],
    unhandledRejections: [],
  };
  const window = {};
  const forbidden = name => (...args) => {
    counters.progressionCalls.push({ name, args });
    return undefined;
  };
  const fetch = (url, options) => {
    const value = String(url);
    if (value === '/api/srs/review') {
      counters.reviewFetches.push({ url: value, options });
      return Promise.reject(new Error('review transport must not be called'));
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({}),
    });
  };
  const srs = {
    review: (...args) => {
      counters.srsReviewCalls += 1;
      throw new Error(`SRS.review must not be called: ${args.length}`);
    },
  };
  const localStorage = {
    values: new Map(),
    getItem(key) { return this.values.has(key) ? this.values.get(key) : null; },
    setItem(key, value) { this.values.set(key, String(value)); },
  };
  const consoleSink = {
    log() {},
    info() {},
    warn() {},
    error() {},
    debug() {},
  };
  const context = {
    window,
    console: consoleSink,
    fetch,
    SRS: srs,
    localStorage,
    performance: { now: () => 0 },
    Promise,
    Date,
    Math,
    JSON,
    URL,
    URLSearchParams,
    setTimeout,
    clearTimeout,
    setImmediate,
    clearImmediate,
    nextQuestion: forbidden('nextQuestion'),
    _handleBossAnswer: forbidden('_handleBossAnswer'),
    _loadBossQuestion: forbidden('_loadBossQuestion'),
    _finishBossBattle: forbidden('_finishBossBattle'),
    LordReviewController: { advance: forbidden('LordReviewController.advance') },
    GoOdysseyLordTrialController: { advance: forbidden('GoOdysseyLordTrialController.advance') },
    MapBattleV1: { settle: forbidden('MapBattleV1.settle') },
  };
  Object.assign(window, {
    window,
    fetch,
    SRS: srs,
    localStorage,
    performance: context.performance,
    nextQuestion: context.nextQuestion,
    _handleBossAnswer: context._handleBossAnswer,
    _loadBossQuestion: context._loadBossQuestion,
    _finishBossBattle: context._finishBossBattle,
    LordReviewController: context.LordReviewController,
    GoOdysseyLordTrialController: context.GoOdysseyLordTrialController,
    MapBattleV1: context.MapBattleV1,
  });
  context.globalThis = window;
  return { context, counters };
}

function loadDispatcher() {
  if (!fs.existsSync(MODULE_PATH)) {
    return {
      status: 'missing_asset',
      modulePath: path.relative(ROOT, MODULE_PATH).replaceAll(path.sep, '/'),
    };
  }

  const source = fs.readFileSync(MODULE_PATH, 'utf8');
  const { context, counters } = createFixture();
  vm.createContext(context);
  try {
    vm.runInContext(source, context, { filename: MODULE_PATH });
  } catch (error) {
    return { status: 'module_error', error: asError(error) };
  }

  const candidates = [
    context.window.GoOdysseyPresentationDispatcher,
    context.window.PresentationDispatcher,
  ];
  if (!candidates[0] || !candidates[1]
      || typeof candidates[0].dispatch !== 'function'
      || typeof candidates[1].dispatch !== 'function') {
    return {
      status: 'contract_error',
      reason: 'both required globals must expose dispatch(data, dependencies)',
      counters,
    };
  }
  return {
    status: 'ready',
    dispatcher: candidates[1],
    counters,
  };
}

function baseData() {
  return {
    ok: true,
    new_badges: ['badge-1'],
    monster: { id: 'monster-1', hp: 4 },
    quest_updates: [{ id: 'quest-1', progress: 1 }],
  };
}

function dependenciesFor(mode, events) {
  const failure = message => { throw new Error(message); };
  const badge = {
    state: () => {
      events.push('badge_state');
      if (mode === 'badge_state_dependency_throws') failure('badge state failed');
      return [{ id: 'badge-1', name: 'Contract Badge' }];
    },
    show: definition => {
      events.push(`badge:${definition?.id || 'unknown'}`);
      if (mode === 'badge_callback_throws') failure('badge callback failed');
      if (mode === 'on_error_throws') failure('source presentation failure');
    },
    seen: ids => {
      events.push(`badge_seen:${ids.join(',')}`);
      if (mode === 'badge_seen_sync_throws') failure('badge seen failed');
      if (mode === 'badge_seen_promise_rejects') {
        return Promise.reject(new Error('badge seen promise failed'));
      }
      return undefined;
    },
  };
  return {
    badge,
    monster: monster => {
      events.push(`monster:${monster?.id || 'unknown'}`);
      if (mode === 'monster_callback_throws') failure('monster callback failed');
    },
    quest: quests => {
      events.push(`quest:${Array.isArray(quests) ? quests.length : 'value'}`);
      if (mode === 'quest_callback_throws') failure('quest callback failed');
    },
    onError: report => {
      events.push(`error:${report?.stage || 'unknown'}`);
      if (mode === 'on_error_throws') failure('diagnostic callback failed');
    },
  };
}

async function executeCase(name) {
  const loaded = loadDispatcher();
  if (loaded.status !== 'ready') return { name, ...loaded };

  const events = [];
  let data = baseData();
  if (name === 'missing_data') data = undefined;
  if (name === 'data_not_ok') data = { ok: false, new_badges: ['badge-1'] };
  const dependencies = dependenciesFor(name, events);
  let result = null;
  let thrown = null;
  const rejectionHandler = reason => loaded.counters.unhandledRejections.push(asError(reason));
  process.on('unhandledRejection', rejectionHandler);
  try {
    result = await loaded.dispatcher.dispatch(data, dependencies);
    // A rejected badge-seen Promise must be observed by the dispatcher rather
    // than becoming an unhandled rejection after dispatch returns.
    await new Promise(resolve => setImmediate(resolve));
  } catch (error) {
    thrown = asError(error);
  } finally {
    process.off('unhandledRejection', rejectionHandler);
  }
  return {
    name,
    status: 'ready',
    result,
    events,
    thrown,
    counters: loaded.counters,
  };
}

function resultSummary(result) {
  if (!result || typeof result !== 'object') return result;
  return {
    ok: result.ok,
    skipped: result.skipped,
    failures: Array.isArray(result.failures)
      ? result.failures.map(failure => ({
          stage: failure?.stage,
          errorType: failure?.errorType,
          message: failure?.message,
        }))
      : result.failures,
  };
}

function hasStage(report, stage) {
  return Array.isArray(report.result?.failures)
    && report.result.failures.some(failure => failure?.stage === stage);
}

function expect(condition, message, failures) {
  if (!condition) failures.push(message);
}

async function validateReadyContract() {
  const failures = [];
  const reports = {};
  for (const name of CASE_NAMES) {
    reports[name] = await executeCase(name);
  }

  for (const name of CASE_NAMES) {
    const report = reports[name];
    expect(report.status === 'ready', `${name}: dispatcher not ready`, failures);
    if (report.status !== 'ready') continue;
    expect(report.thrown === null, `${name}: dispatch rejected`, failures);
    expect(report.counters.reviewFetches.length === 0,
      `${name}: review fetch was attempted`, failures);
    expect(report.counters.srsReviewCalls === 0,
      `${name}: SRS.review was called`, failures);
    expect(report.counters.progressionCalls.length === 0,
      `${name}: progression authority was called`, failures);
  }

  for (const name of ['missing_data', 'data_not_ok']) {
    const report = reports[name];
    expect(report.result?.ok === false && report.result?.skipped === true,
      `${name}: must return skipped result`, failures);
    expect(Array.isArray(report.result?.failures)
      && report.result.failures.length === 0,
    `${name}: skipped result must have no failures`, failures);
    expect(report.events.length === 0, `${name}: effects must be skipped`, failures);
  }

  const success = reports.all_effects_succeed;
  expect(success.result?.ok === true && success.result?.skipped === false,
    'all_effects_succeed: must return ok result', failures);
  expect(Array.isArray(success.result?.failures)
    && success.result.failures.length === 0,
  'all_effects_succeed: unexpected failures', failures);
  for (const effect of ['badge_state', 'badge:badge-1', 'badge_seen:badge-1', 'monster:monster-1', 'quest:1']) {
    expect(success.events.includes(effect), `all_effects_succeed: missing ${effect}`, failures);
  }

  for (const [name, stage] of [
    ['badge_callback_throws', 'badge'],
    ['badge_state_dependency_throws', 'badge_state'],
    ['badge_seen_sync_throws', 'badge_seen'],
    ['badge_seen_promise_rejects', 'badge_seen'],
    ['monster_callback_throws', 'monster'],
    ['quest_callback_throws', 'quest'],
  ]) {
    const report = reports[name];
    expect(hasStage(report, stage), `${name}: missing ${stage} failure`, failures);
    expect(report.thrown === null, `${name}: failure escaped dispatcher`, failures);
    expect(report.counters.unhandledRejections.length === 0,
      `${name}: unhandled rejection escaped dispatcher`, failures);
  }
  for (const name of ['badge_callback_throws', 'badge_state_dependency_throws', 'badge_seen_sync_throws']) {
    expect(reports[name].events.some(event => event.startsWith('monster:')),
      `${name}: monster effect did not remain independent`, failures);
    expect(reports[name].events.some(event => event.startsWith('quest:')),
      `${name}: quest effect did not remain independent`, failures);
  }
  expect(reports.monster_callback_throws.events.some(event => event.startsWith('quest:')),
    'monster_callback_throws: quest effect did not remain independent', failures);

  const onError = reports.on_error_throws;
  expect(hasStage(onError, 'badge'), 'on_error_throws: source failure missing', failures);
  expect(onError.thrown === null, 'on_error_throws: diagnostic throw escaped', failures);

  const deterministic = await executeCase('all_effects_succeed');
  expect(JSON.stringify(resultSummary(success.result)) === JSON.stringify(resultSummary(deterministic.result)),
    'deterministic_result: result is not deterministic', failures);

  return { status: 'ready', cases: reports, failures };
}

async function main() {
  const initial = loadDispatcher();
  if (initial.status === 'missing_asset') {
    console.log(JSON.stringify({
      contract: 'E10_FRONTEND_V1B_PRESENTATION_DISPATCHER_B1B',
      status: 'missing_asset',
      modulePath: initial.modulePath,
      cases: Object.fromEntries(CASE_NAMES.map(name => [name, { status: 'skipped' }])),
    }));
    return;
  }
  if (initial.status !== 'ready') {
    console.log(JSON.stringify({
      contract: 'E10_FRONTEND_V1B_PRESENTATION_DISPATCHER_B1B',
      ...initial,
    }));
    process.exitCode = 2;
    return;
  }

  const result = await validateReadyContract();
  console.log(JSON.stringify({
    contract: 'E10_FRONTEND_V1B_PRESENTATION_DISPATCHER_B1B',
    ...result,
  }));
  if (result.failures.length) process.exitCode = 2;
}

main().catch(error => {
  console.log(JSON.stringify({
    contract: 'E10_FRONTEND_V1B_PRESENTATION_DISPATCHER_B1B',
    status: 'harness_error',
    error: asError(error),
  }));
  process.exitCode = 1;
});
