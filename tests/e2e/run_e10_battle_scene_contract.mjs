import assert from 'node:assert/strict';
import fsSync from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const INDEX = await fs.readFile(path.resolve(HERE, '../../index.html'), 'utf8');

function extractFunction(name, endName) {
  let start = INDEX.indexOf(`function ${name}`);
  assert.notEqual(start, -1, `missing ${name}`);
  if (INDEX.slice(Math.max(0, start - 6), start) === 'async ') start -= 6;
  const end = endName ? INDEX.indexOf(`function ${endName}`, start) : INDEX.length;
  assert.notEqual(end, -1, `missing ${endName}`);
  let open = -1;
  let parenDepth = 0;
  for (let i = start; i < INDEX.length; i += 1) {
    if (INDEX[i] === '(') parenDepth += 1;
    else if (INDEX[i] === ')') parenDepth -= 1;
    else if (INDEX[i] === '{' && parenDepth === 0) { open = i; break; }
  }
  assert.notEqual(open, -1, `missing body for ${name}`);
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let i = open; i < INDEX.length; i += 1) {
    const ch = INDEX[i];
    const next = INDEX[i + 1];
    if (lineComment) {
      if (ch === '\n') lineComment = false;
      continue;
    }
    if (blockComment) {
      if (ch === '*' && next === '/') { blockComment = false; i += 1; }
      continue;
    }
    if (quote) {
      if (escaped) { escaped = false; continue; }
      if (ch === '\\') { escaped = true; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '/' && next === '/') { lineComment = true; i += 1; continue; }
    if (ch === '/' && next === '*') { blockComment = true; i += 1; continue; }
    if (ch === "'" || ch === '"' || ch === '`') { quote = ch; continue; }
    if (ch === '{') depth += 1;
    if (ch === '}') {
      depth -= 1;
      if (depth === 0) return INDEX.slice(start, i + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

const isE10BattleShell = extractFunction('_isE10BattleShell', '_hydrateE10BattlePresentation');
const hydratePresentation = extractFunction('_hydrateE10BattlePresentation', 'updateQuizPetStatusBadge');
const renderAuthoritative = extractFunction('_mapBattleV1RenderAuthoritative', '_prepareMapBattleV1ForQuestion');
const submitV1 = extractFunction('_submitMapBattleV1IfActive', 'isBeginnerVillageAdventureResult');

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  ].filter(Boolean);
  return candidates.find((candidate) => {
    try { return fsSync.existsSync(candidate); } catch { return false; }
  });
}

const executablePath = findChrome();
assert.ok(executablePath, 'Chrome executable is required for this browser contract');
const browser = await chromium.launch({ headless: true, executablePath });
const page = await browser.newPage();
page.on('pageerror', (error) => console.error(`BROWSER_ERROR: ${error.message}`));
await page.setContent('<!doctype html><html><body></body></html>');

const contractScript = `
  window.__runE10HydrationContract = async function () {
    let calls = [];
    let _adventureActiveQuestions = [{ id: 1 }];
    let _e10BattlePresentationPromise = null;
    function _isAdventureZonePractice() { return _adventureActiveQuestions.length > 0; }
    async function loadPlayerAvatar() { calls.push('avatar'); }
    async function loadQuizPet() { calls.push('pet'); }
    ${isE10BattleShell}
    ${hydratePresentation}
    window.__GO_E9_ACTIVE_SHELL__ = 'e9';
    document.body.dataset.adventureShellActive = 'e9';
    await _hydrateE10BattlePresentation();
    calls.push('battle-render');
    await _hydrateE10BattlePresentation();
    return calls;
  };

  window.__runE10AutoNextContract = async function (kind) {
    let nextCalls = 0;
    let progressCalls = 0;
    let completionCalls = 0;
    let markedSeen = 0;
    let playerRenders = [];
    let srsDoneCount = 0;
    let _mapBattleV1State = {
      active: true, monsterHp: 90, monsterHpMax: 100,
      playerHp: 100, playerHpMax: 100,
      monsterDefeated: kind === 'defeat', playerDefeated: false,
    };
    let _mapBattleV1Mode = 'active';
    let _mapBattleV1LifecycleGeneration = 0;
    let _mapBattleV1TransitionPending = false;
    let _mapBattleV1Transition = null;
    let _mapBattleV1TransitionTimer = null;
    let _mapBattleV1CompletionCallbackCount = 0;
    let _mapBattleV1TransitionCount = 0;
    let _mapBattleV1NextQuestionCount = 0;
    let currentQ = { id: 1, monster_type: 'goblin', monster_name: 'Goblin' };
    let _quizPet = null;
    const response = kind === 'wrong'
      ? { accepted: true, duplicate: false, result: 'INCORRECT', next_action: 'continue', damage_to_monster: 0, damage_to_player: 5 }
      : kind === 'invalid'
        ? { accepted: false, duplicate: false, result: 'INVALID', next_action: 'continue', damage_to_monster: 0, damage_to_player: 0 }
        : { accepted: true, duplicate: kind === 'duplicate', result: 'CORRECT', next_action: kind === 'defeat' ? 'monster_defeated' : 'continue', damage_to_monster: 10, damage_to_player: 0, heal_to_player: 1, player_heal_applied: 1 };
    function _mapBattleV1IsActive() { return _mapBattleV1Mode === 'active' && _mapBattleV1State.active === true; }
    function _syncE10BattleActions() {}
    function _resetE10BattleRevealState() {}
    function _recordE10BattleAnswerResult() {}
    function _clearMapBattleV1Transition() {
      if (_mapBattleV1TransitionTimer !== null) clearTimeout(_mapBattleV1TransitionTimer);
      _mapBattleV1TransitionTimer = null;
      _mapBattleV1Transition = null;
      _mapBattleV1TransitionPending = false;
    }
    function _mapBattleV1IsStaleError() { return false; }
    async function _prepareMapBattleV1ForQuestion() { return null; }
    function _clearMapBattleV1Resume() {}
    function _persistMapBattleV1Resume() {}
    function _publishMapBattleV1Lifecycle() {}
    async function _refreshMapBattleV1ServerProgress() { return true; }
    function updateMonsterUI(_monster, { onAnimationComplete = null } = {}) { if (onAnimationComplete) onAnimationComplete(); }
    function updatePlayerHPUI(player) { playerRenders.push(player); }
    function setMsg() {}
    function showBeginnerVillageEncounterContinuation() { return false; }
    function returnToAdventureMapAfterEncounter() { completionCalls += 1; }
    function updateSRSProgress() { progressCalls += 1; }
    function nextQuestion() { nextCalls += 1; }
    function petReact() {}
    const SRS = { markSeen() { markedSeen += 1; } };
    window.MapBattleV1 = { legacy: { submit: async () => response } };
    ${renderAuthoritative}
    ${submitV1}
    await _submitMapBattleV1IfActive([]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    return { nextCalls, progressCalls, completionCalls, markedSeen, srsDoneCount,
      playerHpChange: playerRenders.length ? playerRenders[playerRenders.length - 1].hp_change : null };
  };
`;
new Function(contractScript);
await page.addScriptTag({ content: contractScript });

const hydration = await page.evaluate(() => window.__runE10HydrationContract());
assert.deepEqual(hydration, ['avatar', 'pet', 'battle-render']);

for (const [kind, expected] of [
  ['correct', { nextCalls: 1, progressCalls: 1, completionCalls: 0 }],
  ['duplicate', { nextCalls: 0, progressCalls: 0, completionCalls: 0 }],
  ['wrong', { nextCalls: 0, progressCalls: 0, completionCalls: 0 }],
  ['invalid', { nextCalls: 0, progressCalls: 0, completionCalls: 0 }],
  ['defeat', { nextCalls: 0, progressCalls: 0, completionCalls: 1 }],
]) {
  const result = await page.evaluate((value) => window.__runE10AutoNextContract(value), kind);
  assert.deepEqual(
    { nextCalls: result.nextCalls, progressCalls: result.progressCalls, completionCalls: result.completionCalls },
    expected,
    `${kind} transition contract`,
  );
  if (kind === 'correct') assert.equal(result.playerHpChange, 1, 'correct renders authoritative heal');
  if (kind === 'duplicate') assert.equal(result.playerHpChange, 0, 'duplicate does not replay HP animation');
  if (kind === 'wrong') assert.equal(result.playerHpChange, -5, 'wrong renders authoritative damage only');
}

await browser.close();
console.log('E10_BATTLE_SCENE_CONTRACT: PASS');
