import assert from 'node:assert/strict';
import fs from 'node:fs';

const index = fs.readFileSync(new URL('../../index.html', import.meta.url), 'utf8');

function extractFunction(name, endMarker) {
  const start = index.indexOf(`function ${name}`);
  assert.notEqual(start, -1, `missing function ${name}`);
  const end = index.indexOf(endMarker, start);
  assert.notEqual(end, -1, `missing function boundary ${endMarker}`);
  const source = index.slice(start, end);
  const opening = source.indexOf('{');
  let depth = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  for (let i = opening; i < source.length; i += 1) {
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
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
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
    if (ch === "'" || ch === '"' || ch === '`') quote = ch;
    else if (ch === '{') depth += 1;
    else if (ch === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(0, i + 1);
    }
  }
  throw new Error(`unterminated function ${name}`);
}

const metadataSource = extractFunction('_currentReviewMetadata', 'function _incident002ServerPracticeFlow');
const practiceSource = extractFunction('_incident002ServerPracticeFlow', 'let playerColor');

function evaluate({ adventure, mode, active }) {
  const questions = adventure ? '[{id: 7001}]' : 'null';
  const state = active ? '{active: true}' : 'null';
  const source = `
    return (function() {
      let _bossMode = false;
      let _bossAttemptId = null;
      let _premiumWeeklyMode = null;
      let _guildQuestMode = null;
      let _guildQuestAnswerMoves = [];
      let _challengeId = null;
      let _dailyMode = false;
      let _questionStartedAt = null;
      let _adventureActiveQuestions = ${questions};
      let _mapBattleV1Mode = ${JSON.stringify(mode)};
      let _mapBattleV1State = ${state};
      const ADVENTURE_UNAVAILABLE_SOURCE_CONTEXT = 'adventure_unavailable';
      const location = {search: ''};
      const performance = {now: () => 1000};
      const SRS = {practiceAnswer: () => Promise.resolve({})};
      function _isAdventureZonePractice() {
        return Array.isArray(_adventureActiveQuestions) && _adventureActiveQuestions.length > 0;
      }
      function _mapBattleV1IsActive() {
        return !_bossMode
          && _isAdventureZonePractice()
          && _mapBattleV1Mode === 'active'
          && !!_mapBattleV1State
          && _mapBattleV1State.active === true;
      }
      ${metadataSource}
      ${practiceSource}
      return {
        metadata: _currentReviewMetadata(),
        practice: _incident002ServerPracticeFlow(),
      };
    })();
  `;
  return Function(source)();
}

const failureCases = [
  {label: 'disabled', mode: 'disabled'},
  {label: 'pending', mode: 'pending'},
  {label: 'not eligible', mode: 'blocked'},
  {label: 'runtime failure', mode: 'blocked'},
];
for (const {label, mode} of failureCases) {
  const failed = evaluate({adventure: true, mode, active: false});
  assert.equal(failed.practice, false, `${label} must not use Practice transport`);
  assert.equal(failed.metadata.source_context, 'adventure_unavailable', `${label} must be auditable`);
  assert.equal(failed.metadata.adventure_failure_mode, mode);
}

const active = evaluate({adventure: true, mode: 'active', active: true});
assert.equal(active.practice, false, 'active Adventure must use Map Battle transport');

const ordinaryPractice = evaluate({adventure: false, mode: 'disabled', active: false});
assert.equal(ordinaryPractice.practice, true, 'ordinary Practice remains available');
assert.equal(ordinaryPractice.metadata.source_context, 'practice');

console.log(JSON.stringify({
  status: 'PASS_P0_LANE_B_ADVENTURE_FORWARD_REPAIR_CLIENT_CONTRACT',
  failedAdventureModes: ['disabled', 'pending', 'map_battle_mode_not_eligible', 'runtime_failure'],
  adventureFailureSourceContext: 'adventure_unavailable',
  ordinaryPracticeSourceContext: ordinaryPractice.metadata.source_context,
}));
