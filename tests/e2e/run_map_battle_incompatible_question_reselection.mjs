/*
 * P1-L3-22 browser-runtime contract harness.
 *
 * It evaluates the shipped SRS and MapBattle adapter sources, then evaluates
 * the real Adventure target-selection functions extracted from index.html.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const srsSource = fs.readFileSync(path.join(ROOT, 'srs.js'), 'utf8');
const adapterSource = fs.readFileSync(path.join(ROOT, 'js', 'map_battle_v1_adapter.js'), 'utf8');
const indexSource = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');

function extractFunction(source, name) {
  const marker = `function ${name}(`;
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, `missing ${name}`);
  const opening = source.indexOf('{', start);
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let index = opening; index < source.length; index += 1) {
    const char = source[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === quote) quote = null;
      continue;
    }
    if (char === "'" || char === '"' || char === '`') quote = char;
    else if (char === '{') depth += 1;
    else if (char === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

const sandbox = {
  console,
  setTimeout,
  clearTimeout,
  localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
  fetch: async () => ({ ok: true, json: async () => ({}) }),
  window: {},
};
sandbox.globalThis = sandbox;
sandbox.window.window = sandbox.window;
sandbox.window.fetch = sandbox.fetch;

vm.runInNewContext(`${srsSource}\nglobalThis.__SRS = SRS;`, sandbox, { filename: 'srs.js' });
vm.runInNewContext(adapterSource, sandbox, { filename: 'js/map_battle_v1_adapter.js' });
const SRS = sandbox.__SRS;
const adapter = sandbox.window.MapBattleV1.legacy;
assert.ok(SRS);
assert.ok(adapter);

const permanentPayload = {
  error: 'map_battle_question_incompatible',
  code: 'map_battle_question_incompatible',
  failure_class: 'MAP_BATTLE_QUESTION_INCOMPATIBLE',
  reason_code: 'ambiguous_authoritative_sgf_player_color',
  retryable: false,
  question_id: 31706,
  question_revision: 'rev-31706',
  session_question_fingerprint: 'fp-31706',
  quarantine_scope: 'session_question_revision',
};
let permanentError = null;
try {
  await adapter.prepare(
    { zoneKey: 'k16_20', questionId: permanentPayload.question_id },
    async () => ({ ok: false, status: 409, json: async () => permanentPayload }),
  );
} catch (error) {
  permanentError = error;
}
assert.ok(permanentError, 'typed permanent preparation failure must reject');
assert.equal(permanentError.code, permanentPayload.code);
assert.equal(permanentError.retryable, false);
assert.equal(permanentError.payload.failure_class, permanentPayload.failure_class);
assert.equal(permanentError.payload.reason_code, permanentPayload.reason_code);

const questions = [
  { id: 31706, question_revision: 'rev-31706' },
  { id: 31707, question_revision: 'rev-31707' },
  { id: 90003, question_revision: 'rev-90003' },
];
SRS.clearSessionQuarantine();
assert.equal(
  SRS.recordRejectedAnswer(31706, permanentError.payload, questions[0]),
  true,
);
assert.equal(SRS.isQuestionQuarantined(31706, 'rev-31706'), true);

const extracted = [
  extractFunction(indexSource, '_nextAdventureQuestionExcludingQuarantine'),
  extractFunction(indexSource, '_pickAdventureTarget'),
  extractFunction(indexSource, '_pickNextAdventureTarget'),
].join('\n');
const selectionSandbox = { ...sandbox, __SRS: SRS, __questions: questions };
selectionSandbox.globalThis = selectionSandbox;
vm.runInNewContext(`
const SRS = globalThis.__SRS;
function _isSessionQuestionQuarantined(question) {
  return !!question && SRS.isQuestionQuarantined(
    question.id,
    SRS.questionRevision(question),
  );
}
function _adventureQuestionSeen() { return false; }
function _adventureQuestionDefeated() { return false; }
${extracted}
globalThis.__selection = {
  initial: _pickAdventureTarget(globalThis.__questions),
  next: _pickNextAdventureTarget(globalThis.__questions, 31706),
  sequential: _nextAdventureQuestionExcludingQuarantine(globalThis.__questions, 31706, 1),
};
`, selectionSandbox, { filename: 'index.html:selection' });

const selection = selectionSandbox.__selection;
assert.equal(selection.initial.id, 31707, 'stage entry must skip the quarantined record');
assert.equal(selection.next.id, 31707, 'Next Question must skip the quarantined record');
assert.equal(selection.sequential.id, 31707, 'active traversal must skip the quarantined record');
assert.equal(selection.initial.id, 31707, 'same-session re-entry must not reselect the record');

const transientPayload = {
  code: 'map_battle_judge_unavailable',
  failure_class: 'TRANSIENT_SERVER_FAILURE',
  reason_code: 'map_battle_judge_unavailable',
  retryable: true,
  question_id: 90003,
  question_revision: 'rev-90003',
};
assert.equal(SRS.recordRejectedAnswer(90003, transientPayload, questions[2]), false);
assert.equal(SRS.isQuestionQuarantined(90003, 'rev-90003'), false);

console.log(JSON.stringify({
  permanentTransport: {
    code: permanentError.code,
    retryable: permanentError.retryable,
    failureClass: permanentError.payload.failure_class,
  },
  quarantinedQuestion: 31706,
  nextQuestion: selection.next.id,
  sameSessionReentry: selection.initial.id,
  transientQuarantined: false,
}));
