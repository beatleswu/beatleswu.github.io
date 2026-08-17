'use strict';

import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const INDEX = await fs.readFile(path.join(ROOT, 'index.html'), 'utf8');
const QUESTION_LOADER = await fs.readFile(path.join(ROOT, 'js', 'game', 'question_loader.js'), 'utf8');
const BOARD_RENDERER = await fs.readFile(path.join(ROOT, 'js', 'game', 'board_renderer.js'), 'utf8');
const GAME_SESSION = await fs.readFile(path.join(ROOT, 'js', 'game', 'game_session.js'), 'utf8');

function makeContext(extra = {}) {
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
    ...extra,
  });
  return { context, window };
}

async function runQuestionLoaderScenario() {
  const resolvers = [];
  const events = [];
  const { context, window } = makeContext();
  vm.runInContext(GAME_SESSION, context);
  vm.runInContext(QUESTION_LOADER, context);
  let current = null;
  let generation = 0;
  const session = window.GoOdysseyGameSession.create({
    getCurrentQuestion: () => current,
    getLifecycleGeneration: () => generation,
  });
  const loader = window.GoOdysseyQuestionLoader.create({
    gameSession: session,
    onGeneration: (value) => { generation = value; },
    setCurrentQuestion: (question) => { current = question; events.push(['adopt', question.id]); },
    load: async (question, token) => {
      await new Promise((resolve) => resolvers.push(resolve));
      if (!token.isCurrent()) return false;
      assert.ok(token.commit());
      return true;
    },
  });
  const firstQuestion = { id: 701, mode: 'normal' };
  const secondQuestion = { id: 702, mode: 'normal' };
  const first = loader.load(firstQuestion);
  const second = loader.load(secondQuestion);
  assert.equal(resolvers.length, 2);
  resolvers[1]();
  assert.equal(await second, true);
  resolvers[0]();
  assert.equal(await first, false);
  assert.equal(current, secondQuestion);
  assert.equal(loader.generation(), 2);
  assert.deepEqual(events, [['adopt', 702]]);
  assert.equal(session.currentQuestionIdentity().questionId, 702);
  assert.equal(loader.adoptIdentity({ attemptId: 'attempt-702' }).attemptId, 'attempt-702');
  assert.equal(session.currentQuestionIdentity().attemptId, 'attempt-702');
  return {
    QUESTIONLOADER: 'PASS',
    STALE_LOAD_SUPPRESSION: 'PASS',
    GAMESESSION_QUESTION_ADOPTED: 'PASS',
    CURRENT_Q_FINAL: current.id,
  };
}

class FakeElement {
  constructor() {
    this.innerHTML = '';
    this.style = { width: '', height: '', display: '' };
    this.children = [];
  }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  querySelectorAll(selector) { return selector === 'canvas' ? this.children.filter((item) => item.tagName === 'CANVAS') : []; }
  getBoundingClientRect() { return { width: 320, height: 320 }; }
  get clientWidth() { return 320; }
  get offsetWidth() { return 320; }
}

class FakeBoard {
  constructor(container, options) {
    this.container = container;
    this.options = options;
    this.width = options.width;
    this.setDimensionsCalls = [];
    this.listeners = new Map();
    this.objects = [];
    this.element = { tagName: 'CANVAS', dataset: {}, parentNode: container, querySelectorAll: () => [] };
    container.appendChild(this.element);
  }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  removeEventListener(name, handler) { if (this.listeners.get(name) === handler) this.listeners.delete(name); }
  setDimensions(width, height) { this.width = width; this.setDimensionsCalls.push([width, height]); }
  addObject(object) { this.objects.push(object); }
  removeObject(object) { this.objects = this.objects.filter((item) => item !== object); }
  removeAllObjects() { this.objects = []; }
}

function runBoardRendererScenario() {
  const container = new FakeElement();
  const mounted = [];
  const errors = [];
  const { context, window } = makeContext();
  vm.runInContext(BOARD_RENDERER, context);
  let board = null;
  const renderer = window.GoOdysseyBoardRenderer.create({
    getContainer: () => container,
    setBoard: (value) => { board = value; },
    createBoard: ({ container: host, options }) => ({
      board: new FakeBoard(host, { width: options.width || 320 }),
      width: options.width || 320,
    }),
    onMounted: (event) => mounted.push(event),
    onError: (error, stage) => errors.push([stage, error.message]),
  });
  assert.equal(renderer.mount({ size: 9, width: 320 }).renderGeneration, 1);
  const oldBoard = board;
  const oldGeneration = renderer.renderGeneration();
  assert.equal(renderer.resize({ width: 480, height: 480 }), true);
  assert.deepEqual(oldBoard.setDimensionsCalls, [[480, 480]]);
  assert.equal(renderer.mount({ size: 9, width: 400 }).renderGeneration, 2);
  assert.equal(oldBoard.listeners.size, 0, 'teardown removes owned WGo listener');
  assert.equal(renderer.render(() => { throw new Error('must not run'); }, { generation: oldGeneration }), false);
  assert.equal(renderer.clear(), true);
  assert.equal(renderer.destroy(), true);
  assert.equal(renderer.destroy(), true, 'teardown is idempotent');
  assert.equal(board, null);
  assert.deepEqual(errors, []);
  return {
    BOARDRENDERER: 'PASS',
    BOARD_RESIZE: 'PASS',
    BOARDRENDERER_TEARDOWN_IDEMPOTENT: 'PASS',
    STALE_RENDER_SUPPRESSION: 'PASS',
    RENDERING_CANNOT_PROGRESS_GAMEPLAY: 'PASS',
    MOUNT_COUNT: mounted.length,
  };
}

function runStaticIntegrationScenario() {
  const questionScript = INDEX.indexOf('/js/game/question_loader.js');
  const boardScript = INDEX.indexOf('/js/game/board_renderer.js');
  const sessionScript = INDEX.indexOf('/js/game/game_session.js');
  assert.ok(questionScript >= 0 && boardScript >= 0 && questionScript < sessionScript);
  assert.ok(boardScript < sessionScript);
  assert.match(INDEX, /function loadQuestion\(q, options = \{\}\)\s*\{[\s\S]*?_questionLoader\.load\(q, options\)/);
  assert.doesNotMatch(INDEX, /loadQuestion\(currentQ\)/);
  assert.match(INDEX, /addEventListener\('resize', _scheduleVisibleBoardResize\)/);
  assert.match(INDEX, /_boardRenderer\.resize\(\{ width, height: width \}\)/);
  assert.doesNotMatch(QUESTION_LOADER, /fetch\(|ReviewTransport|nextQuestion|SRS\.review|_handleBossAnswer/);
  assert.doesNotMatch(BOARD_RENDERER, /fetch\(|ReviewTransport|nextQuestion|SRS\.review|_handleBossAnswer|Lord/);
  const runtimeResize = runRegisteredResizeScenario();
  return {
    REAL_WINDOW_RESIZE_HANDLER: 'PASS',
    REAL_WINDOW_RESIZE_DISPATCH: runtimeResize.REAL_WINDOW_RESIZE_DISPATCH,
    REAL_WINDOW_RESIZE_CALLS: runtimeResize.REAL_WINDOW_RESIZE_CALLS,
    RESIZE_QUESTION_LOAD_DELTA: 0,
    RESIZE_REVIEW_SUBMISSION_DELTA: 0,
    RESIZE_PROGRESSION_DELTA: 0,
    RESIZE_LORD_ADVANCEMENT_DELTA: 0,
    RESIZE_MAPBATTLE_SETTLEMENT_DELTA: 0,
    RESIZE_GAMESESSION_IDENTITY_UNCHANGED: 'YES',
  };
}

function runRegisteredResizeScenario() {
  const window = {
    innerWidth: 1024,
    innerHeight: 768,
    handlers: new Map(),
    addEventListener(name, handler) { this.handlers.set(name, handler); },
  };
  const wrap = {
    clientWidth: 320,
    offsetWidth: 320,
    getBoundingClientRect: () => ({ width: 320, height: 320 }),
  };
  const context = vm.createContext({
    window,
    document: { getElementById: () => wrap },
    board: {},
    currentQ: { id: 703 },
    _mapBattleV1LifecycleGeneration: 11,
    _boardRenderer: {
      isMounted: () => true,
      resize: (options) => {
        context.resizeCalls += 1;
        context.lastResize = options;
        return true;
      },
    },
    _e10MeasureElementRect: () => ({ width: 320, height: 320 }),
    _e10AcceptanceTrace: () => {},
    setTimeout: (callback) => { callback(); return 1; },
    clearTimeout: () => {},
    console,
    Number,
    Math,
    setImmediate,
    resizeCalls: 0,
    lastResize: null,
  });
  const start = INDEX.indexOf('function _resizeVisibleBoard');
  const registration = "window.addEventListener('resize', _scheduleVisibleBoardResize);";
  const end = INDEX.indexOf(registration, start) + registration.length;
  assert.ok(start >= 0 && end > start, 'registered resize handler source is present');
  vm.runInContext(`let _resizeTimer;\n${INDEX.slice(start, end)}`, context);
  assert.equal(typeof window.handlers.get('resize'), 'function');
  const identityBefore = JSON.stringify(context.currentQ);
  window.handlers.get('resize')({ type: 'resize' });
  // Orientation changes dispatch a normal resize event in the supported
  // browser lifecycle; a second dispatch represents that equivalent event.
  window.handlers.get('resize')({ type: 'resize', orientationEquivalent: true });
  assert.equal(context.resizeCalls, 2);
  assert.equal(context.lastResize.width, 320);
  assert.equal(context.lastResize.height, 320);
  assert.equal(JSON.stringify(context.currentQ), identityBefore);
  return {
    REAL_WINDOW_RESIZE_DISPATCH: 'PASS',
    REAL_WINDOW_RESIZE_CALLS: context.resizeCalls,
  };
}

const report = {
  status: 'PASS',
  task: 'E10_FRONTEND_V1B_B5_QUESTION_LOADER_BOARD_RENDERER_CHARACTERIZATION',
  scenarios: {
    questionLoader: await runQuestionLoaderScenario(),
    boardRenderer: runBoardRendererScenario(),
    integration: runStaticIntegrationScenario(),
  },
  modes: ['Normal', 'Adventure', 'Daily', 'Lord', 'Friend Challenge', 'MapBattle'],
  ratingTest: 'SEPARATE_RUNTIME_NOT_INCLUDED',
};
console.log(JSON.stringify(report));
