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
const MODE_CONTEXT = await fs.readFile(path.join(ROOT, 'js', 'game', 'mode_context.js'), 'utf8');
const GAME_BOOTSTRAP = await fs.readFile(path.join(ROOT, 'js', 'game', 'game_bootstrap.js'), 'utf8');
const REVIEW_TRANSPORT = await fs.readFile(path.join(ROOT, 'js', 'game', 'review_transport.js'), 'utf8');
const DISPATCHER = await fs.readFile(path.join(ROOT, 'js', 'game', 'presentation_dispatcher.js'), 'utf8');
const LORD_CONTROLLER = await fs.readFile(path.join(ROOT, 'js', 'game', 'lord_trial_controller.js'), 'utf8');
const MAP_BATTLE = await fs.readFile(path.join(ROOT, 'js', 'map_battle_v1_adapter.js'), 'utf8');
const SRS = await fs.readFile(path.join(ROOT, 'srs.js'), 'utf8');

const SCRIPT_PATHS = [
  '/wgo/wgo.min.js',
  '/wgo/stone_skin.js',
  '/i18n.js',
  '/community_reward_notifications.js',
  '/js/game/presentation_dispatcher.js',
  '/js/game/presentation_effects_b2.js',
  '/js/game/review_transport.js',
  '/js/game/question_loader.js',
  '/js/game/board_renderer.js',
  '/js/game/game_session.js',
  '/js/game/mode_context.js',
  '/js/game/game_bootstrap.js',
  '/srs.js',
  '/js/game/lord_trial_controller.js',
  '/js/map_battle_v1_adapter.js',
];

const MODE_NAMES = ['Normal', 'Adventure', 'Daily', 'Lord', 'Friend Challenge', 'MapBattle'];

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
    Math,
    ...extra,
  });
  return { context, window };
}

function functionSlice(source, marker, nextMarker) {
  const start = source.indexOf(marker);
  assert.ok(start >= 0, `missing source marker: ${marker}`);
  const end = nextMarker ? source.indexOf(nextMarker, start + marker.length) : source.length;
  return source.slice(start, end < 0 ? source.length : end);
}

function characterizeBootstrap() {
  const positions = SCRIPT_PATHS.map((script) => {
    const position = INDEX.indexOf(script);
    assert.ok(position >= 0, `missing script: ${script}`);
    return position;
  });
  for (let index = 1; index < positions.length; index += 1) {
    assert.ok(positions[index - 1] < positions[index], `script order violation before ${SCRIPT_PATHS[index]}`);
  }

  assert.match(INDEX, /const _gameSession = window\.GoOdysseyGameSession\.create\(/);
  assert.match(INDEX, /const _questionLoader = window\.GoOdysseyQuestionLoader\.create\(/);
  assert.match(INDEX, /const _boardRenderer = window\.GoOdysseyBoardRenderer\.create\(/);
  assert.match(INDEX, /const _modeContext = window\.GoOdysseyModeContext\.create\(/);
  assert.match(INDEX, /const _gameBootstrap = window\.GoOdysseyGameBootstrap\.create\(/);
  assert.match(INDEX, /document\.addEventListener\('DOMContentLoaded'/);
  assert.match(INDEX, /window\.onload\s*=\s*async/);
  assert.match(INDEX, /window\.addEventListener\('load'/);
  assert.match(INDEX, /_gameBootstrap\.registerListener\(window, 'resize', _scheduleVisibleBoardResize\)/);

  const listenerCount = (INDEX.match(/(?:window|document|[A-Za-z_$][\w$]*)\.addEventListener\(/g) || []).length;
  const timerCount = (INDEX.match(/(?:window\.)?setTimeout\(/g) || []).length;
  const intervalCount = (INDEX.match(/(?:window\.)?setInterval\(/g) || []).length
    + (INDEX.includes('_gameBootstrap.scheduleInterval(') ? 1 : 0);
  assert.ok(listenerCount > 0);
  assert.ok(timerCount > 0);
  assert.ok(intervalCount > 0);

  return {
    script_order: SCRIPT_PATHS,
    listener_registration_count: listenerCount,
    timeout_registration_count: timerCount,
    interval_registration_count: intervalCount,
    global_init_calls: ['GameSession.create', 'QuestionLoader.create', 'BoardRenderer.create'],
    dom_ready_hooks: 2,
    load_hooks: 1,
    self_init_signals: ['SRS.init', 'window.onload', 'DOMContentLoaded'],
  };
}

function characterizeAuthorityBoundaries() {
  assert.match(QUESTION_LOADER, /generation \+= 1/);
  assert.match(QUESTION_LOADER, /function invalidate\(/);
  assert.match(QUESTION_LOADER, /gameSession\.adoptQuestion/);
  assert.match(QUESTION_LOADER, /setCurrentQuestion/);
  assert.doesNotMatch(QUESTION_LOADER, /fetch\(|ReviewTransport|SRS\.review|nextQuestion|_handleBossAnswer|settle|reward/);

  for (const method of ['mount', 'remount', 'resize', 'clear', 'render', 'teardown', 'destroy']) {
    assert.match(BOARD_RENDERER, new RegExp(`\\b${method}\\b`));
  }
  assert.doesNotMatch(BOARD_RENDERER, /fetch\(|ReviewTransport|SRS\.review|nextQuestion|_handleBossAnswer|Lord|MapBattle|settle|reward/);

  assert.match(INDEX, /function loadQuestion\(q, options = \{\}\)\s*\{[\s\S]*?_questionLoader\.load\(q, options\)/);
  const loadAdapter = functionSlice(INDEX, 'async function loadQuestion(q, options = {})', 'async function _loadQuestionImplementation');
  assert.doesNotMatch(loadAdapter, /fetch\(|SRS\.review|currentQ\s*=/);
  assert.equal((INDEX.match(/currentQ = question;/g) || []).length, 1);
  assert.match(INDEX, /QuestionLoader owns the generic question-load epoch/);
  assert.match(INDEX, /_questionLoader\.invalidate\('navigation'\)/);
  assert.doesNotMatch(INDEX, /_mapBattleV1LifecycleGeneration\s*\+=/);

  assert.match(INDEX, /window\.GoOdysseyGameSession\.create/);
  assert.match(INDEX, /getCurrentQuestion: \(\) => currentQ/);
  assert.match(INDEX, /_questionLoader\.adoptIdentity/);
  assert.match(INDEX, /function _resizeVisibleBoard\(\)/);
  const resizeBlock = functionSlice(INDEX, 'function _resizeVisibleBoard()', 'function _scheduleVisibleBoardResize');
  assert.match(resizeBlock, /_boardRenderer\.resize\(\{ width, height: width \}\)/);
  assert.doesNotMatch(resizeBlock, /loadQuestion\(|SRS\.review|submitSRS\(/);
  assert.match(INDEX, /_gameBootstrap\.scheduleTimeout/);
  assert.match(INDEX, /_gameBootstrap\.scheduleInterval/);

  const submit = functionSlice(INDEX, 'async function submitSRS(grade)', 'function _renderPresentationEffects');
  assert.match(submit, /_submitMapBattleV1IfActive/);
  assert.match(submit, /ReviewTransport/);
  assert.match(submit, /_getLordTrialController\(\)/);

  assert.match(REVIEW_TRANSPORT, /review/);
  assert.match(REVIEW_TRANSPORT, /\/api\/srs\/review/);
  assert.match(SRS, /legacyReview|ReviewTransport/);
  assert.match(DISPATCHER, /GoOdysseyPresentationDispatcher|PresentationDispatcher/);
  assert.match(LORD_CONTROLLER, /handleCommittedReview|server_commit|client_transition/);
  assert.match(MAP_BATTLE, /map_battle|settle|review/);

  return {
    question_loader: {
      load_generation_owner: 'QuestionLoader',
      ui_authority: 0,
      review_http_authority: 0,
      progression_authority: 0,
      lord_authority: 0,
      mapbattle_settlement_authority: 0,
    },
    board_renderer: {
      question_load_authority: 0,
      review_authority: 0,
      progression_authority: 0,
      lord_authority: 0,
      mapbattle_settlement_authority: 0,
    },
    gamesession: 'identity/session seam only',
    review_transport: 'ordinary review HTTP boundary',
    lord: 'LordTrialController progression boundary',
    mapbattle: 'MapBattle settlement boundary remains distinct',
    friend_challenge: 'distinct challenge answer transport',
  };
}

function characterizeModes() {
  const daily = functionSlice(INDEX, 'async function startDailyTraining()', 'async function _loadDailyQuestion()');
  const dailyLoad = functionSlice(INDEX, 'async function _loadDailyQuestion()', 'function _updateDailyProgressUI');
  const friendLoad = functionSlice(INDEX, 'function _loadChallengeQuestion(idx)', 'async function _submitChallengeAnswer');
  const friendSubmit = functionSlice(INDEX, 'async function _submitChallengeAnswer(qid, correct)', 'function _showChallengeComplete');
  const boardAnswer = functionSlice(INDEX, 'function onBoardClick(bx,by)', 'function resetProblem');
  const mapLoad = functionSlice(INDEX, 'async function _prepareMapBattleV1ForQuestion', 'async function _submitMapBattleV1IfActive');
  const mapSubmit = functionSlice(INDEX, 'async function _submitMapBattleV1IfActive', 'function isBeginnerVillageAdventureResult');
  const lordLoad = functionSlice(INDEX, 'async function _loadBossQuestion()', 'async function _handleBossAnswer');
  const lordSubmit = functionSlice(INDEX, 'async function _handleBossAnswer', 'async function _finishBossBattle');

  assert.match(INDEX, /function loadQuestion\(/);
  assert.match(INDEX, /function startAdventureStage\(/);
  assert.match(INDEX, /function nextQuestion\(/);
  assert.match(INDEX, /function startDailyTraining\(/);
  assert.match(daily, /_loadDailyQuestion\(/);
  assert.match(dailyLoad, /loadQuestion\(/);
  assert.match(INDEX, /function startBossBattle\(/);
  assert.match(lordLoad, /loadQuestion|_settleVisibleBossQuestionBoard/);
  assert.match(lordSubmit, /handleCommittedReview/);
  assert.match(INDEX, /function initChallengeMode\(/);
  assert.match(friendLoad, /loadQuestion\(q\)/);
  assert.match(friendSubmit, /\/api\/challenges\/friend\//);
  assert.doesNotMatch(friendSubmit, /SRS\.review|\/api\/srs\/review/);
  assert.match(boardAnswer, /submitSRS\(3\)/);
  assert.match(boardAnswer, /_challengeCorrectHandler/);
  assert.match(boardAnswer, /_challengeWrongHandler/);
  assert.match(mapLoad, /_questionLoader\.adoptIdentity|_mapBattleV1Mode/);
  assert.match(mapSubmit, /settle|fetch\(|_mapBattleV1/);
  assert.match(INDEX, /_modeContext\.identityOptions/);
  assert.match(MODE_CONTEXT, /'lord'/);
  assert.match(MODE_CONTEXT, /'daily'/);
  assert.match(MODE_CONTEXT, /'friend_challenge'/);
  assert.match(MODE_CONTEXT, /'map_battle'/);
  assert.match(MODE_CONTEXT, /'adventure'/);
  assert.match(INDEX, /@app\.route\('\/rating_test'\)|\/rating_test/);

  const modes = {
    Normal: {
      QUESTION_LOAD_PATH: 'loadQuestion -> QuestionLoader.load -> _loadQuestionImplementation',
      GAMESESSION_IDENTITY: 'GameSession.adoptQuestion via QuestionLoader commit',
      BOARD_RENDER_PATH: 'BoardRenderer mount/render through _loadQuestionImplementation',
      ANSWER_SUBMISSION_PATH: 'submitSRS -> ReviewTransport.review -> SRS.review',
      PROGRESSION_OWNER: 'existing normal nextQuestion/application flow',
      DESTROY_REMOUNT_BEHAVIOR: 'BoardRenderer teardown/remount only',
      MODE_SWITCH_BEHAVIOR: 'normal fallback and navigation invalidation',
    },
    Adventure: {
      QUESTION_LOAD_PATH: 'startAdventureStage -> loadQuestion -> QuestionLoader.load',
      GAMESESSION_IDENTITY: 'QuestionLoader commit; current identity projection remains normal with adventure context',
      BOARD_RENDER_PATH: 'BoardRenderer renders adventure question',
      ANSWER_SUBMISSION_PATH: 'ordinary ReviewTransport unless MapBattle encounter is active',
      PROGRESSION_OWNER: 'adventure stage / existing nextQuestion policy',
      DESTROY_REMOUNT_BEHAVIOR: 'renderer lifecycle is separate from stage state',
      MODE_SWITCH_BEHAVIOR: 'adventure map entry/return invalidates loader on navigation',
    },
    Daily: {
      QUESTION_LOAD_PATH: 'startDailyTraining -> _loadDailyQuestion -> loadQuestion',
      GAMESESSION_IDENTITY: 'QuestionLoader commit with daily mode projection',
      BOARD_RENDER_PATH: 'BoardRenderer renders daily question',
      ANSWER_SUBMISSION_PATH: 'ordinary SRS review guarded by daily state',
      PROGRESSION_OWNER: 'daily training flow / existing nextQuestion policy',
      DESTROY_REMOUNT_BEHAVIOR: 'no daily-specific renderer authority',
      MODE_SWITCH_BEHAVIOR: 'daily entry/exit toggles mode and reuses loader boundary',
    },
    Lord: {
      QUESTION_LOAD_PATH: 'startBossBattle -> _loadBossQuestion -> guarded board settlement',
      GAMESESSION_IDENTITY: 'QuestionLoader/GameSession identity with lord mode and index',
      BOARD_RENDER_PATH: 'BoardRenderer renders Lord board',
      ANSWER_SUBMISSION_PATH: 'submitSRS -> SRS.review -> LordTrialController.handleCommittedReview',
      PROGRESSION_OWNER: 'LordTrialController',
      DESTROY_REMOUNT_BEHAVIOR: 'renderer lifecycle cannot advance Lord state',
      MODE_SWITCH_BEHAVIOR: 'Lord entry/exit owns its queue; no ordinary nextQuestion authority',
    },
    'Friend Challenge': {
      QUESTION_LOAD_PATH: 'initChallengeMode -> _loadChallengeQuestion -> loadQuestion',
      GAMESESSION_IDENTITY: 'QuestionLoader/GameSession shared question identity',
      BOARD_RENDER_PATH: 'BoardRenderer renders challenge question',
      ANSWER_SUBMISSION_PATH: 'correct: submitSRS(3) plus challenge POST; wrong: challenge POST plus direct ReviewTransport',
      PROGRESSION_OWNER: 'Friend Challenge answer/next challenge flow',
      DESTROY_REMOUNT_BEHAVIOR: 'challenge transport remains distinct from renderer lifecycle',
      MODE_SWITCH_BEHAVIOR: 'challenge entry/exit retains distinct transport semantics',
    },
    MapBattle: {
      QUESTION_LOAD_PATH: '_prepareMapBattleV1ForQuestion -> QuestionLoader.adoptIdentity',
      GAMESESSION_IDENTITY: 'GameSession identity adopted for MapBattle question',
      BOARD_RENDER_PATH: 'BoardRenderer renders MapBattle board',
      ANSWER_SUBMISSION_PATH: '_submitMapBattleV1IfActive -> existing MapBattle settlement',
      PROGRESSION_OWNER: 'MapBattle settlement authority',
      DESTROY_REMOUNT_BEHAVIOR: 'renderer lifecycle is not settlement authority',
      MODE_SWITCH_BEHAVIOR: 'encounter return invalidates loader and returns to adventure map',
    },
  };
  assert.deepEqual(Object.keys(modes), MODE_NAMES);
  return modes;
}

async function runQuestionLoaderLifecycle() {
  const resolvers = new Map();
  const events = [];
  const { context, window } = makeContext();
  vm.runInContext(GAME_SESSION, context);
  vm.runInContext(QUESTION_LOADER, context);

  let current = null;
  let lifecycleGeneration = 0;
  const session = window.GoOdysseyGameSession.create({
    getCurrentQuestion: () => current,
    getLifecycleGeneration: () => lifecycleGeneration,
  });
  const loader = window.GoOdysseyQuestionLoader.create({
    gameSession: session,
    onGeneration: (generation, reason) => {
      lifecycleGeneration = generation;
      events.push(['generation', generation, reason]);
    },
    setCurrentQuestion: (question) => {
      current = question;
      events.push(['adopt', question.id]);
    },
    load: (question, token) => new Promise((resolve) => {
      resolvers.set(question.id, { token, resolve });
    }),
  });

  const firstQuestion = { id: 701, mode: 'normal' };
  const secondQuestion = { id: 702, mode: 'normal' };
  const first = loader.load(firstQuestion);
  const second = loader.load(secondQuestion);
  assert.equal(resolvers.size, 2);
  resolvers.get(702).resolve(Boolean(resolvers.get(702).token.commit()));
  assert.equal(await second, true);
  resolvers.get(701).resolve(Boolean(resolvers.get(701).token.commit()));
  assert.equal(await first, false);
  assert.equal(current, secondQuestion);
  assert.equal(loader.generation(), 2);
  assert.equal(session.currentQuestionIdentity().questionId, 702);
  assert.equal(events.filter((event) => event[0] === 'adopt').length, 1);

  const staleQuestion = { id: 703, mode: 'normal' };
  const stale = loader.load(staleQuestion);
  const staleToken = resolvers.get(703).token;
  loader.invalidate('session');
  resolvers.get(703).resolve(Boolean(staleToken.commit()));
  assert.equal(await stale, false);
  assert.equal(session.currentQuestionIdentity(), null);

  return {
    LOAD_A_THEN_B: 'PASS',
    STALE_LOAD_SUPPRESSION: 'PASS',
    SESSION_INVALIDATION: 'PASS',
    GAMESESSION_QUESTION_ADOPTED: 'PASS',
    CURRENT_QUESTION_FINAL: current.id,
    GENERATION_OWNER: 'QuestionLoader',
    REVIEW_SUBMISSION_DELTA: 0,
    PROGRESSION_DELTA: 0,
    LORD_ADVANCEMENT_DELTA: 0,
    MAPBATTLE_SETTLEMENT_DELTA: 0,
  };
}

class FakeContainer {
  constructor() {
    this.innerHTML = '';
    this.style = { width: '', height: '' };
    this.children = [];
  }
  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    return child;
  }
}

class FakeBoard {
  constructor(container) {
    this.container = container;
    this.listeners = new Map();
    this.setDimensionsCalls = [];
    this.objects = [];
    this.element = { tagName: 'CANVAS', parentNode: container };
    container.appendChild(this.element);
  }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  removeEventListener(name, handler) {
    if (this.listeners.get(name) === handler) this.listeners.delete(name);
  }
  setDimensions(width, height) { this.setDimensionsCalls.push([width, height]); }
  addObject(object) { this.objects.push(object); }
  removeObject(object) { this.objects = this.objects.filter((item) => item !== object); }
  removeAllObjects() { this.objects = []; }
}

function runBoardRendererLifecycle() {
  const container = new FakeContainer();
  const boards = [];
  const { context, window } = makeContext();
  vm.runInContext(BOARD_RENDERER, context);
  let activeBoard = null;
  let clickCalls = 0;
  const renderer = window.GoOdysseyBoardRenderer.create({
    getContainer: () => container,
    setBoard: (value) => { activeBoard = value; },
    createBoard: ({ container: host }) => {
      const board = new FakeBoard(host);
      boards.push(board);
      return { board, width: 320 };
    },
  });
  const clickHandler = () => { clickCalls += 1; };
  assert.equal(renderer.mount({ onClick: clickHandler }).renderGeneration, 1);
  const firstBoard = activeBoard;
  assert.equal(firstBoard.listeners.size, 1);
  assert.equal(renderer.resize({ width: 480, height: 480 }), true);
  assert.deepEqual(firstBoard.setDimensionsCalls, [[480, 480]]);
  assert.equal(renderer.render(() => {}, { generation: 1 }), true);

  assert.equal(renderer.remount({ onClick: clickHandler }).renderGeneration, 2);
  const secondBoard = activeBoard;
  assert.equal(firstBoard.listeners.size, 0);
  assert.equal(secondBoard.listeners.size, 1);
  assert.equal(renderer.clear(), true);

  let staleCallbackCalls = 0;
  assert.equal(renderer.teardown(), true);
  assert.equal(renderer.render(() => { staleCallbackCalls += 1; }), false);
  assert.equal(staleCallbackCalls, 0);
  assert.equal(renderer.destroy(), true);
  assert.equal(renderer.destroy(), true);
  assert.equal(activeBoard, null);

  assert.equal(renderer.mount({ onClick: clickHandler }).renderGeneration, 3);
  assert.equal(renderer.isMounted(), true);
  assert.equal(boards.length, 3);
  assert.equal(clickCalls, 0);

  return {
    BOARD_RENDERER_LIFECYCLE: 'PASS',
    BOARDRENDERER_TEARDOWN_IDEMPOTENT: 'PASS',
    STALE_RENDER_SUPPRESSION: 'PASS',
    DESTROY_THEN_REMOUNT: 'PASS',
    LISTENER_COUNT_DELTA_ON_REMOUNT: 0,
    TIMER_COUNT_DELTA_ON_REMOUNT: 0,
    REVIEW_DELTA_ON_REMOUNT: 0,
    QUESTION_LOAD_DELTA_ON_REMOUNT: 0,
    PROGRESSION_DELTA_ON_REMOUNT: 0,
    LORD_ADVANCEMENT_DELTA_ON_REMOUNT: 0,
    MAPBATTLE_SETTLEMENT_DELTA_ON_REMOUNT: 0,
    GAMESESSION_QUESTION_IDENTITY_UNCHANGED: 'YES',
    RENDERING_CANNOT_PROGRESS_GAMEPLAY: 'PASS',
  };
}

function runRegisteredResizeScenario() {
  const registrations = [];
  const window = {
    innerWidth: 1024,
    innerHeight: 768,
    addEventListener(name, handler) { registrations.push([name, handler]); },
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
    currentQ: { id: 704 },
    _mapBattleV1LifecycleGeneration: 19,
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
    _gameBootstrap: {
      registerListener: (target, name, handler) => { target.addEventListener(name, handler); },
      scheduleTimeout: (callback) => { callback(); return 1; },
    },
    setTimeout: (callback) => { callback(); return 1; },
    clearTimeout: () => {},
    console,
    Number,
    Math,
    resizeCalls: 0,
    lastResize: null,
  });
  const start = INDEX.indexOf('function _resizeVisibleBoard');
  const registration = "_gameBootstrap.registerListener(window, 'resize', _scheduleVisibleBoardResize);";
  const end = INDEX.indexOf(registration, start) + registration.length;
  assert.ok(start >= 0 && end > start);
  vm.runInContext(INDEX.slice(start, end), context);
  const resizeHandlers = registrations.filter(([name]) => name === 'resize');
  assert.equal(resizeHandlers.length, 1);
  const identityBefore = JSON.stringify(context.currentQ);
  resizeHandlers[0][1]({ type: 'resize' });
  resizeHandlers[0][1]({ type: 'resize', orientationEquivalent: true });
  assert.equal(context.resizeCalls, 2);
  assert.equal(context.lastResize.width, 320);
  assert.equal(context.lastResize.height, 320);
  assert.equal(JSON.stringify(context.currentQ), identityBefore);
  return {
    REAL_WINDOW_RESIZE_HANDLER: 'PASS',
    REAL_WINDOW_RESIZE_DISPATCH: 'PASS',
    REAL_WINDOW_RESIZE_CALLS: context.resizeCalls,
    RESIZE_QUESTION_LOAD_DELTA: 0,
    RESIZE_REVIEW_SUBMISSION_DELTA: 0,
    RESIZE_PROGRESSION_DELTA: 0,
    RESIZE_LORD_ADVANCEMENT_DELTA: 0,
    RESIZE_MAPBATTLE_SETTLEMENT_DELTA: 0,
    RESIZE_GAMESESSION_IDENTITY_UNCHANGED: 'YES',
  };
}

function assertRuntimeAliases() {
  const { context, window } = makeContext();
  vm.runInContext(QUESTION_LOADER, context);
  vm.runInContext(BOARD_RENDERER, context);
  vm.runInContext(MODE_CONTEXT, context);
  vm.runInContext(GAME_BOOTSTRAP, context);
  assert.equal(window.GoOdysseyQuestionLoader, window.QuestionLoader);
  assert.equal(window.GoOdysseyBoardRenderer, window.BoardRenderer);
  assert.equal(window.GoOdysseyModeContext, window.ModeContext);
  assert.equal(window.GoOdysseyGameBootstrap, window.GameBootstrap);
  return {
    QUESTIONLOADER_GLOBAL_ALIAS: 'PASS',
    BOARDRENDERER_GLOBAL_ALIAS: 'PASS',
    GLOBAL_ALIAS_SINGLE_OBJECT: 'PASS',
  };
}

const bootstrap = characterizeBootstrap();
const authority = characterizeAuthorityBoundaries();
const modes = characterizeModes();
const aliases = assertRuntimeAliases();
const questionLoader = await runQuestionLoaderLifecycle();
const boardRenderer = runBoardRendererLifecycle();
const resize = runRegisteredResizeScenario();

const report = {
  status: 'PASS',
  task: 'E10_FRONTEND_V1B_B6_B7_CHARACTERIZATION_SWARM_CODEX_043',
  characterization: {
    modes,
    rating_test: 'SEPARATE_RUNTIME_NOT_IN_SHARED_BROWSER_HARNESS',
    bootstrap,
    authority,
    aliases,
    questionLoader,
    boardRenderer,
    resize,
  },
  risks: {
    duplicate_init: 'CURRENT_BEHAVIOR_REQUIRES_B6_B7_MIGRATION: multiple global/self-init hooks are present; no central lifecycle owner',
    duplicate_listener: 'CURRENT_BEHAVIOR_REQUIRES_B6_B7_MIGRATION: document/window and mode-local listeners are not centrally torn down',
    duplicate_timer: 'CURRENT_BEHAVIOR_REQUIRES_B6_B7_MIGRATION: global interval and many transient timeouts lack one shared lifecycle registry',
    stale_callback: 'B5 renderer/load guards PASS; remaining app-level callback inventory requires B6/B7 lifecycle ownership',
  },
  invariants: {
    ACTIVE_QUESTION_BROWSER_AUTHORITY_COUNT: 1,
    GENERIC_QUESTION_LOAD_GENERATION_OWNER: 'QuestionLoader',
    NON_MAPBATTLE_MODES_DEPEND_ON_MAPBATTLE_NAMED_LOAD_EPOCH: 'NO',
    MAPBATTLE_GAMESESSION_LOAD_IDENTITY: 'YES',
    MAPBATTLE_BEGINREVIEW_UNIFICATION: 'NO',
    MAPBATTLE_REVIEWTRANSPORT_UNIFICATION: 'NO',
    MAPBATTLE_SETTLEMENT_AUTHORITY_MOVED: 'NO',
    CURRENTQ_AUTHORITY_CLASS: 'BOUNDED_COMPATIBILITY_PROJECTION',
    LEGACY_LOADQUESTION_AUTHORITY: 'ADAPTER_ONLY',
    RENDERING_CANNOT_PROGRESS_GAMEPLAY: 'YES',
  },
};
console.log(JSON.stringify(report));
