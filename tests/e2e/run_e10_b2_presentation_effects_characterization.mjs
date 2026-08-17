import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const INDEX = await fs.readFile(path.join(REPO_ROOT, 'index.html'), 'utf8');
const PRESENTATION_DISPATCHER = await fs.readFile(
  path.join(REPO_ROOT, 'js/game/presentation_dispatcher.js'),
  'utf8',
);
const PRESENTATION_EFFECTS_B2 = await fs.readFile(
  path.join(REPO_ROOT, 'js/game/presentation_effects_b2.js'),
  'utf8',
);
const REVIEW_TRANSPORT = await fs.readFile(
  path.join(REPO_ROOT, 'js/game/review_transport.js'),
  'utf8',
);
const SRS = await fs.readFile(path.join(REPO_ROOT, 'srs.js'), 'utf8');

function extractFunction(source, name) {
  let start = source.indexOf(`function ${name}`);
  assert.notEqual(start, -1, `missing function ${name}`);
  if (source.slice(Math.max(0, start - 6), start) === 'async ') start -= 6;

  let open = -1;
  let parenDepth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === '(') parenDepth += 1;
    else if (source[i] === ')') parenDepth -= 1;
    else if (source[i] === '{' && parenDepth === 0) {
      open = i;
      break;
    }
  }
  assert.notEqual(open, -1, `missing body for ${name}`);

  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let i = open; i < source.length; i += 1) {
    const ch = source[i];
    const next = source[i + 1];
    if (lineComment) {
      if (ch === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (ch === '*' && next === '/') {
        blockComment = false;
        i += 1;
      }
      continue;
    }
    if (quote) {
      if (escaped) {
        escaped = false;
        continue;
      }
      if (ch === '\\') {
        escaped = true;
        continue;
      }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '/' && next === '/') {
      lineComment = true;
      i += 1;
      continue;
    }
    if (ch === '/' && next === '*') {
      blockComment = true;
      i += 1;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      quote = ch;
      continue;
    }
    if (ch === '{') depth += 1;
    if (ch === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`unterminated function ${name}`);
}

class FakeElement {
  constructor(id = null, tagName = 'div') {
    this.id = id;
    this.tagName = tagName.toUpperCase();
    this.style = {};
    this.dataset = {};
    this.textContent = '';
    this.innerHTML = '';
    this.className = '';
    this.children = [];
    this.parentNode = null;
    this.src = '';
    this.alt = '';
    this.loading = '';
    this.decoding = '';
    this.title = '';
    this.offsetWidth = 160;
    this.offsetHeight = 36;
    this.offsetLeft = 0;
    this.offsetTop = 0;
    this._classes = new Set();
    this.classList = {
      add: (...names) => names.forEach((name) => this._classes.add(name)),
      remove: (...names) => names.forEach((name) => this._classes.delete(name)),
      contains: (name) => this._classes.has(name),
    };
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this.children = [];
    children.forEach((child) => this.appendChild(child));
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    this.parentNode = null;
  }

  addEventListener() {}

  getBoundingClientRect() {
    return { left: 20, right: 120, top: 80, bottom: 120, width: 100, height: 40 };
  }
}

class FakeDocument {
  constructor() {
    this.elements = new Map();
    this.body = this.getElementById('body');
  }

  getElementById(id) {
    if (!this.elements.has(id)) this.elements.set(id, new FakeElement(id));
    return this.elements.get(id);
  }

  createElement(tagName) {
    return new FakeElement(null, tagName);
  }

  querySelector() {
    return null;
  }
}

function makeTimers() {
  let nextId = 1;
  const timers = new Map();
  return {
    timers,
    setTimeout(callback, delay = 0) {
      const timer = { id: nextId++, callback, delay, cleared: false };
      timers.set(timer.id, timer);
      return timer.id;
    },
    clearTimeout(id) {
      const timer = timers.get(id);
      if (timer) timer.cleared = true;
      timers.delete(id);
    },
  };
}

function makeResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body };
}

async function characterizeToastTimers() {
  const document = new FakeDocument();
  const timers = makeTimers();
  const parent = { _appearState: { appearanceLoaded: true } };
  const context = vm.createContext({
    document,
    window: { parent },
    APPEAR_RARITY_LABELS_IDX: (rarity) => (rarity === 'rare' ? 'Rare label' : ''),
    setTimeout: timers.setTimeout,
    clearTimeout: timers.clearTimeout,
  });
  vm.runInContext(`
    let _toastTimer = null;
    ${extractFunction(INDEX, 'showItemToast')}
    ${extractFunction(INDEX, 'showLootToast')}
    ${extractFunction(INDEX, 'showAppearToast')}
    ${extractFunction(INDEX, 'showPetRewardToast')}
    ${extractFunction(INDEX, 'showQuestPetRewardToasts')}
    this.api = { showItemToast, showLootToast, showAppearToast, showPetRewardToast,
      showQuestPetRewardToasts };
  `, context);
  const api = context.api;

  api.showItemToast('loot-toast', '🪙', 'First', 'rare');
  const staleTimer = [...timers.timers.values()].at(-1);
  assert.equal(document.getElementById('loot-toast').style.display, 'flex');
  assert.equal(document.getElementById('loot-toast-name').textContent, 'First');
  assert.equal(staleTimer.delay, 4500, 'loot toast uses the legacy 4.5 second timer');

  api.showItemToast('loot-toast', '💎', 'Second', 'common');
  assert.equal(staleTimer.cleared, true, 'replacing a toast clears _toastTimer');
  assert.equal(document.getElementById('loot-toast-name').textContent, 'Second');
  // The old callback has no generation guard.  This is an intentional
  // characterization of the current stale-callback behavior.
  staleTimer.callback();
  assert.equal(document.getElementById('loot-toast').style.display, 'none');

  api.showAppearToast({ emoji: '🧢', name: 'Hat', rarity: 'rare' });
  assert.equal(document.getElementById('loot-toast').style.display, 'none');
  assert.equal(document.getElementById('appear-toast').style.display, 'flex');
  assert.equal(parent._appearState.appearanceLoaded, false);
  assert.equal(document.getElementById('appear-toast-rarity').textContent, 'Rare label');

  api.showPetRewardToast({ name: 'Candy', qty: 2 }, 900);
  const delayedPet = [...timers.timers.values()].at(-1);
  assert.equal(delayedPet.delay, 900, 'pet reward toast preserves its requested delay');
  delayedPet.callback();
  assert.equal(document.getElementById('pet-toast').style.display, 'flex');
  assert.equal(document.getElementById('pet-toast-name').textContent, 'Candy × 2');

  const before = timers.timers.size;
  api.showQuestPetRewardToasts([
    { pet_reward: { name: 'Candy', qty: 1 } },
    { pet_reward: { name: 'Fruit', qty: 3 } },
  ], 1800);
  const questTimers = [...timers.timers.values()].slice(-2);
  assert.equal(timers.timers.size, before + 2);
  assert.deepEqual(questTimers.map((timer) => timer.delay), [1800, 2700]);
}

async function characterizeShopStatus() {
  const document = new FakeDocument();
  const calls = [];
  let mode = 'success';
  const status = {
    inventory: { hint_ticket: 2 },
    shield_active: true,
    xp_potion_until: '2099-01-01T00:00:00Z',
  };
  const context = vm.createContext({
    document,
    window: {},
    I18n: { t: (key) => key },
    Date,
    fetch: (url, options) => {
      calls.push({ url, options });
      return mode === 'failure'
        ? Promise.reject(new Error('shop unavailable'))
        : Promise.resolve(makeResponse(status));
    },
  });
  vm.runInContext(`
    let _shopStatus = null;
    let _shopStatusFetchedAt = 0;
    const _SHOP_STATUS_TTL = 60000;
    ${extractFunction(INDEX, '_renderShopStatus')}
    ${extractFunction(INDEX, '_refreshShopStatus')}
    ${extractFunction(INDEX, '_ensureShopStatus')}
    this.api = { refresh: _refreshShopStatus, ensure: _ensureShopStatus,
      state: () => ({ status: _shopStatus, fetchedAt: _shopStatusFetchedAt }),
      set: (value, fetchedAt) => { _shopStatus = value; _shopStatusFetchedAt = fetchedAt; } };
  `, context);
  const api = context.api;

  await api.refresh();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/shop/status');
  assert.equal(calls[0].options.credentials, 'include');
  assert.equal(Object.prototype.hasOwnProperty.call(calls[0].options, 'method'), false);
  assert.equal(document.getElementById('btn-hint').style.display, 'inline-block');
  assert.equal(document.getElementById('hint-count').textContent, '×2');
  assert.match(document.getElementById('shop-fx-bar').textContent, /shop\.fxShield/);

  mode = 'failure';
  await api.refresh();
  assert.equal(api.state().status, null, 'failure clears cached shop status');
  assert.equal(document.getElementById('btn-hint').style.display, 'none');
  assert.equal(document.getElementById('shop-fx-bar').style.display, 'none');

  // This is an isolated _ensureShopStatus contract, not a page-wide
  // zero-network assertion: a fresh cache only skips this helper's request.
  mode = 'success';
  calls.length = 0;
  api.set(status, Date.now());
  api.ensure();
  await Promise.resolve();
  assert.equal(calls.length, 0, 'fresh cache redraws without another shop-status request');
  api.set(status, Date.now() - 60001);
  api.ensure();
  await Promise.resolve();
  assert.equal(calls.length, 1, 'expired cache continues through GET /api/shop/status');
}

async function characterizeDispatcherEffects() {
  const document = new FakeDocument();
  const timers = makeTimers();
  const events = [];
  const fetchCalls = [];
  const context = vm.createContext({
    document,
    window: {
      SFX: { play: (name) => events.push(['streak_sound', name]) },
      _nqMapActive: false,
    },
    SFX: { play: (name) => events.push(['streak_sound', name]) },
    I18n: {
      getLang: () => 'en',
      t: (key) => key,
    },
    isEn: () => true,
    setTimeout: timers.setTimeout,
    clearTimeout: timers.clearTimeout,
    fetch: (url, options) => {
      fetchCalls.push({ url, options });
      return Promise.resolve(makeResponse({ xp: 42, rank_level: 'LV4', rank_pct: 12 }));
    },
    _quizPet: { key: 'ink_drop_kelpie' },
    _lastMonsterType: 'goblin',
    _isAdventureZonePractice: () => false,
    _e10AcceptanceTrace: (name, details) => events.push(['trace', name, details]),
    _refreshShopStatus: () => events.push(['shield_status']),
    setMsg: (...args) => events.push(['message', ...args]),
    spawnXpFloat: (...args) => events.push(['xp_float', ...args]),
    updateXpHud: (...args) => events.push(['xp_hud', ...args]),
    popRankBadge: () => events.push(['rank_badge']),
    showRankUpPopup: (...args) => events.push(['rank_up', ...args]),
    updateMonsterUI: (...args) => events.push(['monster_presentation', ...args]),
    monsterSpeakDie: (...args) => events.push(['monster_die', ...args]),
    monsterSpeakHurt: (...args) => events.push(['monster_hurt', ...args]),
    petReact: (...args) => events.push(['pet_reaction', ...args]),
    showQuizPetMarker: (...args) => events.push(['pet_xp_marker', ...args]),
    updateQuizPetStatusBadge: (...args) => events.push(['pet_status', ...args]),
    updatePlayerHPUI: (...args) => events.push(['player_hp_presentation', ...args]),
    updateSPUI: (...args) => events.push(['sp_presentation', ...args]),
    showLootToast: (...args) => events.push(['loot_toast', ...args]),
    showAppearToast: (...args) => events.push(['appearance_toast', ...args]),
    updateQuestPanel: (...args) => events.push(['quest_panel', ...args]),
    showQuestPetRewardToasts: (...args) => events.push(['quest_pet_reward_toast', ...args]),
    SRS: {
      dispatchReviewPresentation: (...args) => events.push(['srs_presentation_dispatch', ...args]),
    },
  });
  vm.runInContext(`
    ${extractFunction(INDEX, '_dispatchCommittedReviewPresentation')}
    this.api = { dispatch: _dispatchCommittedReviewPresentation };
  `, context);

  const data = {
    ok: true,
    shield_used: true,
    xp_gain: 42,
    combo_mult: 1.5,
    pet_xp_added: 2,
    combo_streak: 5,
    ranked_up: false,
    pet_xp_gained: 1,
    monster: { type: 'goblin', hp: 30, max_hp: 100, dmg: 6, defeated: false },
    pet: { fullness: 0 },
    practice: { active: true, ready: false },
    player: { hp: 80, max_hp: 100, hp_change: -5 },
    sp: { current: 7 },
    loot: { icon: '🪙', name: 'Coin', rarity: 'common' },
    appearance_loot: { emoji: '🧢', name: 'Hat', rarity: 'rare' },
    new_appearance_items: [
      { emoji: '🧣', name: 'Scarf', rarity: 'uncommon' },
      { emoji: '🧤', name: 'Gloves', rarity: 'common' },
    ],
    quest_updates: [{ key: 'daily', pet_reward: { name: 'Candy', qty: 1 } }],
  };
  context.api.dispatch(data, 3);
  await Promise.resolve();
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));

  assert.ok(events.some(([name]) => name === 'shield_status'), 'B2A shield_status');
  assert.deepEqual(events.find(([name]) => name === 'xp_float'), ['xp_float', 42, 1.5]);
  assert.equal(document.getElementById('xp-last-gain').textContent, '+42 XP · Combo ×1.5 · 🐾+2');
  assert.ok(events.some(([name]) => name === 'xp_hud'), 'B2A xp_gain_and_hud refresh');
  assert.ok(events.some(([name, value]) => name === 'streak_sound' && value === 'streak5'), 'B2A streak5 sound');
  assert.deepEqual(events.find(([name]) => name === 'monster_presentation')[1], data.monster);
  assert.ok(events.some(([name]) => name === 'monster_hurt'), 'B2B monster presentation speech');
  assert.deepEqual(events.find(([name]) => name === 'pet_reaction'), ['pet_reaction', 'combo']);
  assert.ok(events.some(([name]) => name === 'pet_status'), 'B2B pet status');
  assert.ok(events.some(([name]) => name === 'pet_xp_marker' && name !== undefined), 'B2B pet XP marker');
  assert.deepEqual(events.find(([name]) => name === 'player_hp_presentation')[1], data.player);
  assert.deepEqual(events.find(([name]) => name === 'sp_presentation')[1], data.sp.current);
  assert.deepEqual(events.find(([name]) => name === 'loot_toast')[1], data.loot);
  assert.ok(events.some(([name]) => name === 'quest_panel'), 'B2C quest panel');
  assert.deepEqual(events.find(([name]) => name === 'quest_pet_reward_toast')[1], data.quest_updates);

  const scheduledDelays = [...timers.timers.values()].map((timer) => timer.delay);
  assert.ok(scheduledDelays.includes(1800), 'appearance loot waits behind the loot toast');
  assert.ok(scheduledDelays.includes(3600), 'first new appearance waits behind loot and appearance');
  assert.ok(scheduledDelays.includes(5400), 'second new appearance preserves 1.8 second order');
  assert.ok(scheduledDelays.includes(1800), 'quest pet reward toast follows the shared loot offset');

  context.api.dispatch({ ok: true, xp_gain: 1, ranked_up: true, new_rank_level: 'LV5' }, 3);
  assert.ok(events.some(([name, rank]) => name === 'rank_up' && rank === 'LV5'), 'B2A rank-up presentation');
  context.api.dispatch({ ok: true, xp_gain: 1, combo_streak: 7 }, 3);
  assert.ok(events.some(([name, value]) => name === 'streak_sound' && value === 'streak7'), 'B2A streak7 sound');
  context.api.dispatch({ ok: true }, 0);
  assert.ok(events.some(([name, value]) => name === 'pet_reaction' && value === 'wrong'), 'B2B wrong-answer pet reaction');
}

async function characterizeHpSpAndMapBattleSharedHelpers() {
  const document = new FakeDocument();
  const timers = makeTimers();
  const floatCalls = [];
  const context = vm.createContext({
    document,
    setTimeout: timers.setTimeout,
    spawnDmgFloat: (...args) => floatCalls.push(args),
    showScreenFlash: (...args) => floatCalls.push(['flash', ...args]),
    showKOEffect: () => floatCalls.push(['ko']),
  });
  vm.runInContext(`
    let _playerHp = 100;
    let _playerMaxHp = 100;
    let _currentSp = 0;
    let _maxSp = 100;
    ${extractFunction(INDEX, 'updatePlayerHPUI')}
    ${extractFunction(INDEX, 'updateSPUI')}
    this.api = { updatePlayerHPUI, updateSPUI,
      state: () => ({ hp: _playerHp, maxHp: _playerMaxHp, sp: _currentSp, maxSp: _maxSp }) };
  `, context);
  context.api.updatePlayerHPUI({ hp: 35, max_hp: 100, hp_change: -5, ko: true });
  assert.equal(document.getElementById('ba-player-hp-bar').style.width, '35%');
  assert.equal(document.getElementById('ba-player-hp-bar').style.background, '#d97706');
  assert.equal(document.getElementById('ba-player-hp-text').textContent, '❤️ 35/100');
  assert.deepEqual(floatCalls[0], ['💢 -5', '#d97706']);
  assert.deepEqual(floatCalls[1], ['flash', 'rgba(220,38,38,.5)']);
  assert.equal(timers.timers.size, 1, 'KO presentation is delayed by 120ms');
  context.api.updateSPUI(40, 80);
  assert.equal(document.getElementById('sp-bar-fill').style.width, '50%');
  assert.equal(document.getElementById('sp-text').textContent, '40/80');
  context.api.updateSPUI(100);
  assert.equal(document.getElementById('sp-bar-fill').style.width, '100%');
  assert.equal(document.getElementById('sp-text').textContent, '100/80');

  const renderSource = extractFunction(INDEX, '_mapBattleV1RenderAuthoritative');
  const renderCalls = [];
  const state = {
    playerHp: 61,
    playerHpMax: 100,
    monsterHp: 44,
    monsterHpMax: 100,
    monsterDefeated: false,
    playerDefeated: false,
  };
  const renderContext = vm.createContext({
    _mapBattleV1State: state,
    _recordE10BattleAnswerResult: () => renderCalls.push(['record']),
    updateMonsterUI: (monster) => renderCalls.push(['monster', monster]),
    updatePlayerHPUI: (player) => renderCalls.push(['player', player]),
    _syncE10BattleActions: () => renderCalls.push(['actions']),
  });
  vm.runInContext(`
    ${renderSource}
    this.api = { render: _mapBattleV1RenderAuthoritative };
  `, renderContext);
  const before = JSON.stringify(state);
  renderContext.api.render(
    { id: 7, monster_type: 'goblin', monster_name: 'Goblin' },
    { duplicate: false, damage_to_monster: 12, damage_to_player: 7, player_heal_applied: 2 },
  );
  const playerRender = renderCalls.find(([name]) => name === 'player')[1];
  const monsterRender = renderCalls.find(([name]) => name === 'monster')[1];
  assert.equal(playerRender.hp_change, -5, 'Map Battle renders authoritative damage/heal delta');
  assert.equal(monsterRender.dmg, 12, 'Map Battle renders authoritative monster delta');
  assert.equal(JSON.stringify(state), before, 'shared UI helpers do not settle or mutate Map Battle state');
  renderCalls.length = 0;
  renderContext.api.render(
    { id: 7, monster_type: 'goblin', monster_name: 'Goblin' },
    { duplicate: true, damage_to_monster: 12, damage_to_player: 7, player_heal_applied: 2 },
  );
  assert.equal(renderCalls.find(([name]) => name === 'player')[1].hp_change, 0, 'duplicate Map Battle result does not replay HP');
  assert.equal(renderCalls.find(([name]) => name === 'monster')[1].dmg, 0, 'duplicate Map Battle result does not replay monster damage');
}

async function characterizeQuestPanel() {
  const document = new FakeDocument();
  const timers = makeTimers();
  const quest = (key, completed, progress, target, extra = {}) => ({
    key,
    name: key,
    name_en: key,
    desc: `${key} desc`,
    color: 'amber',
    icon: '🎯',
    completed,
    progress,
    target,
    xp: 10,
    xp_awarded: completed,
    ...extra,
  });
  const loaded = quest('loaded', true, 1, 1);
  const context = vm.createContext({
    document,
    window: {},
    I18n: {
      localized: (q, field) => q[field] || q.name,
      t: (key) => key === 'index.quest.toast' ? 'Quest {name} +{xp}' : key,
    },
    setTimeout: timers.setTimeout,
    fetch: () => Promise.resolve(makeResponse({ quests: [loaded] })),
  });
  vm.runInContext(`
    const QUEST_COLORS = { amber: { bg:'#fffbeb', fill:'#d97706', text:'#92400e' } };
    const _questCompleted = new Set();
    let _lastQuests = null;
    ${extractFunction(INDEX, 'questItemHtml')}
    ${extractFunction(INDEX, 'renderQuestList')}
    ${extractFunction(INDEX, 'showQuestCompleteToast')}
    ${extractFunction(INDEX, 'updateQuestPanel')}
    ${extractFunction(INDEX, 'loadQuestsPanel')}
    this.api = { questItemHtml, renderQuestList, updateQuestPanel, loadQuestsPanel,
      state: () => ({ last: _lastQuests, completed: [..._questCompleted] }) };
  `, context);
  const api = context.api;

  await api.loadQuestsPanel();
  assert.equal(api.state().last[0].key, 'loaded');
  assert.deepEqual(Array.from(api.state().completed), ['loaded'], 'initial load seeds _questCompleted without a toast');
  assert.equal(document.body.children.length, 0);
  assert.equal(document.getElementById('quest-list').innerHTML.includes('loaded'), true);

  const active = quest('active', false, 0, 3, { bonus: true });
  api.updateQuestPanel([loaded, active]);
  const html = document.getElementById('quest-list').innerHTML;
  assert.match(html, /quest-item-loaded/);
  assert.match(html, /quest-item-active/);
  assert.match(html, /0 \/ 3/);
  assert.match(html, /locked/);
  assert.equal(api.state().last[1].key, 'active');

  const newlyDone = quest('newly-done', true, 2, 2);
  api.updateQuestPanel([newlyDone]);
  assert.deepEqual(Array.from(api.state().completed).sort(), ['loaded', 'newly-done']);
  assert.equal(document.body.children.length, 1, 'new completion uses the quest toast path');
  assert.match(document.body.children[0].textContent, /newly-done/);
  api.updateQuestPanel([newlyDone]);
  assert.equal(document.body.children.length, 1, '_questCompleted suppresses duplicate completion toasts');
}

async function characterizeSrsPresentationFailureBoundary() {
  const calls = [];
  let reviewCalls = 0;
  const storage = new Map();
  const context = vm.createContext({
    window: {},
    localStorage: {
      getItem: (key) => storage.get(key) || null,
      setItem: (key, value) => storage.set(key, value),
    },
    fetch: (url, options) => {
      calls.push({ url, options });
      if (url === '/api/srs/review') {
        reviewCalls += 1;
        return Promise.resolve(makeResponse({
          ok: true,
          ease_factor: 2.5,
          interval: 3,
          due_date: '2026-08-17',
          new_badges: [],
          stats: { xp: 10, total_correct: 1 },
          xp_gain: 0,
          combo_mult: 1.0,
          pet_xp_added: 0,
          pet_xp_ratio: 0.0,
          pet_xp_gained: 0,
          combo_streak: 0,
          shield_used: false,
          xp_potion_active: false,
          ranked_up: false,
          new_rank_level: null,
          pet: null,
          practice: { level: 1 },
          training: { level: 1 },
          new_appearance_items: [],
          monster: { type: 'goblin', hp: 80, max_hp: 100 },
          player: null,
          quest_updates: [],
          sp: null,
          loot: null,
          appearance_loot: null,
        }));
      }
      if (url === '/api/srs/due') return Promise.resolve(makeResponse({ due: [] }));
      if (url === '/api/srs/all') return Promise.resolve(makeResponse([]));
      if (url === '/api/badges/definitions') return Promise.resolve(makeResponse([]));
      if (url === '/api/badges/earned') return Promise.resolve(makeResponse([]));
      return Promise.resolve(makeResponse({}));
    },
  });
  vm.runInContext(
    `${PRESENTATION_DISPATCHER}\n${PRESENTATION_EFFECTS_B2}\n${REVIEW_TRANSPORT}\n${SRS}\nthis.api = SRS;`,
    context,
  );
  const api = context.api;
  await api.init(null, () => { throw new Error('monster renderer failed'); }, null);
  const committed = await api.review(7, 3, null, false, {});
  const failures = [];
  const result = api.dispatchReviewPresentation(committed, {
    onError: (failure) => {
      failures.push(failure);
      throw new Error('diagnostic observer must not become authority');
    },
  });
  assert.equal(result.ok, false);
  assert.deepEqual(Array.from(result.failures, (failure) => failure.stage), ['monster']);
  assert.equal(failures.length, 1);
  assert.equal(reviewCalls, 1, 'presentation failure never retries /api/srs/review');
  assert.equal(calls.filter(({ url }) => url === '/api/srs/review').length, 1);
  const skipped = api.dispatchReviewPresentation({ ok: false });
  assert.equal(skipped.ok, false);
  assert.equal(skipped.skipped, true);
  assert.equal(skipped.failures.length, 0);
}

async function characterizeReviewCommitAndMapBattleAuthority() {
  const submitSource = extractFunction(INDEX, 'submitSRS');
  assert.ok(
    submitSource.indexOf('_submitMapBattleV1IfActive') < submitSource.indexOf('SRS.review'),
    'Map Battle active branch precedes legacy SRS review transport',
  );

  const mapEvents = [];
  const mapContext = vm.createContext({
    console,
    currentQ: { id: 101 },
    _bossMode: false,
    _mapBattleV1Mode: 'active',
    _mapBattleV1State: { attemptId: 'a1' },
    _mapBattleV1Moves: [{ x: 1, y: 2 }],
    _dailyLimitBlocksCurrentFlow: () => false,
    _submitMapBattleV1IfActive: async (moves) => mapEvents.push(['map_submit', moves]),
    SRS: { review: async () => { throw new Error('legacy SRS review must not run'); } },
  });
  vm.runInContext(`${submitSource}\nthis.run = () => submitSRS(3);`, mapContext);
  await mapContext.run();
  assert.equal(mapEvents.length, 1, 'active Map Battle owns answer submission');
  assert.equal(mapEvents[0][0], 'map_submit');

  const events = [];
  let activeReviewIdentity = null;
  let reviewInFlight = false;
  const _gameSession = {
    adoptQuestion: (question, options = {}) => {
      activeReviewIdentity = Object.freeze({
        questionId: Number(question.id),
        mode: options.mode ?? null,
        attemptId: options.attemptId ?? null,
        lordIndex: options.lordIndex ?? null,
        lifecycleGeneration: options.lifecycleGeneration ?? null,
        sourceContext: options.sourceContext ?? null,
      });
      return activeReviewIdentity;
    },
    beginReview: (identity) => {
      if (identity !== activeReviewIdentity || reviewInFlight) return false;
      reviewInFlight = true;
      return true;
    },
    presentationContext: (identity) => {
      if (identity !== activeReviewIdentity) return null;
      return Object.freeze({
        questionId: identity.questionId,
        mode: identity.mode,
        attemptId: identity.attemptId,
        lordIndex: identity.lordIndex,
        lifecycleGeneration: identity.lifecycleGeneration,
        sourceContext: identity.sourceContext,
      });
    },
    endReview: (identity) => {
      if (identity !== activeReviewIdentity || !reviewInFlight) return false;
      reviewInFlight = false;
      return true;
    },
  };
  const commitContext = vm.createContext({
    console,
    window: { _nqMapActive: false },
    I18n: { t: (key) => key },
    currentQ: { id: 102 },
    _bossMode: false,
    _mapBattleV1Mode: 'disabled',
    _mapBattleV1State: null,
    _mapBattleV1Moves: [],
    _mapBattleV1LifecycleGeneration: 0,
    _dailyLimitBlocksCurrentFlow: () => false,
    _reviewRequestInFlightKey: null,
    _activeBossZone: null,
    _newbieQuestActive: false,
    _todayTotal: 0,
    _todayCorrect: 0,
    _zoneWrongStreak: 0,
    srsDoneCount: 0,
    _premiumWeeklyMode: null,
    _guildQuestMode: null,
    currentUnitName: () => null,
    _currentReviewMetadata: () => ({}),
    _gameSession,
    _e10AcceptanceTrace: (name) => events.push(name),
    updateTodayMini: () => events.push('today'),
    _dispatchCommittedReviewPresentation: () => {
      events.push('presentation_failure');
      throw new Error('presentation failed');
    },
    loadMapProgressStatus: () => events.push('map_progress'),
    isBeginnerVillageAdventureResult: () => false,
    updateSRSProgress: () => events.push('progress'),
    nextQuestion: () => events.push('next_question'),
    resetProblem: () => events.push('reset'),
    setMsg: () => events.push('message'),
    _applyDailyLimit: () => events.push('daily_limit'),
    SRS: {
      review: async () => {
        events.push('review');
        return { ok: true };
      },
      markSeen: () => events.push('mark_seen'),
    },
  });
  vm.runInContext(`${submitSource}\nthis.run = async () => {
    try { await submitSRS(3); return { rejected: false }; }
    catch (error) { return { rejected: true, message: error.message }; }
  };`, commitContext);
  const result = await commitContext.run();
  assert.equal(result.rejected, true, 'current direct dispatcher exception is observable to its caller');
  assert.deepEqual(events.slice(0, 5), [
    'REVIEW_REQUESTED', 'review', 'mark_seen', 'REVIEW_COMMITTED', 'today',
  ]);
  assert.equal(events.filter((event) => event === 'review').length, 1);
  assert.equal(events.filter((event) => event === 'presentation_failure').length, 1);
  assert.equal(events.filter((event) => event === 'next_question').length, 1);
  assert.equal(events.filter((event) => event === 'progress').length, 1);
  assert.equal(events.includes('map_progress'), false, 'a throwing dispatcher interrupts post-dispatch work');
}

await characterizeToastTimers();
await characterizeShopStatus();
await characterizeDispatcherEffects();
await characterizeHpSpAndMapBattleSharedHelpers();
await characterizeQuestPanel();
await characterizeSrsPresentationFailureBoundary();
await characterizeReviewCommitAndMapBattleAuthority();

console.log('E10_B2_PRESENTATION_EFFECTS_CHARACTERIZATION: PASS (14 effects; legacy baseline)');
