/**
 * LC004 — ReviewTransport attempt-payload contract runner.
 *
 * Proves js/game/review_transport.js forwards a FACTS-ONLY attempt block and
 * strips any client authority field. Exit non-zero on the first failure.
 * Loads the module via vm (Windows-safe; matches run_e10_review_transport_contract.mjs).
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(
  path.join(here, '..', '..', 'js', 'game', 'review_transport.js'),
  'utf8',
);
const sandbox = {};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
new vm.Script(src, { filename: 'review_transport.js' }).runInContext(sandbox);
const RT = sandbox.window.ReviewTransport;

let failures = 0;
function check(name, cond) {
  if (cond) { console.log('ok   -', name); }
  else { console.log('FAIL -', name); failures += 1; }
}

// 1. no attempt -> body is the legacy shape, no `attempt` key
{
  const body = RT.buildRequest({ question_id: 1, grade: 3 });
  check('no-attempt body has no attempt key', !('attempt' in body));
  check('no-attempt body keeps question_id/grade', body.question_id === 1 && body.grade === 3);
  check('no-attempt body has exactly the 8 legacy keys',
    Object.keys(body).sort().join(',') ===
    'grade,is_scaffolding,question_id,response_ms,source_context,training_set_id,unit_done,unit_name');
}

// 2. facts-only attempt -> forwarded verbatim (only the fact keys)
{
  const body = RT.buildRequest({
    question_id: 1, grade: 3,
    attempt: { moves: [{ x: 15, y: 3 }], player_color: 'B', transform: 'identity', board_size: 19 },
  });
  check('facts attempt forwarded', body.attempt && Array.isArray(body.attempt.moves));
  check('facts attempt keeps player_color', body.attempt.player_color === 'B');
  check('facts attempt keeps transform', body.attempt.transform === 'identity');
  check('facts attempt keeps board_size', body.attempt.board_size === 19);
  check('facts attempt has exactly the fact keys',
    Object.keys(body.attempt).sort().join(',') === 'board_size,moves,player_color,transform');
}

// 3. attempt carrying a client authority field -> whole attempt dropped
for (const bad of ['grade', 'correct', 'is_correct', 'result', 'verdict', 'judge_result', 'accepted', 'server_correct']) {
  const body = RT.buildRequest({
    question_id: 1, grade: 3,
    attempt: { moves: [{ x: 1, y: 1 }], [bad]: true },
  });
  check(`attempt with '${bad}' is dropped entirely`, !('attempt' in body));
}

// 4. attempt without a moves array -> dropped
{
  const body = RT.buildRequest({ question_id: 1, grade: 3, attempt: { player_color: 'B' } });
  check('attempt without moves array dropped', !('attempt' in body));
}

// 5. extra non-fact keys in a valid attempt -> pruned, attempt still sent
{
  const body = RT.buildRequest({
    question_id: 1, grade: 3,
    attempt: { moves: [{ x: 1, y: 1 }], player_color: 'B', ui_theme: 'dark', response_ms: 999 },
  });
  check('non-fact keys pruned from attempt',
    body.attempt && !('ui_theme' in body.attempt) && !('response_ms' in body.attempt));
}

// 6. legacyReview threads metadata.attempt through
{
  let captured = null;
  const fakeFetch = async (_url, opts) => {
    captured = JSON.parse(opts.body);
    return { ok: true, json: async () => ({
      ok: true, ease_factor: 2.5, interval: 1, due_date: 'x', new_badges: [], stats: {},
      xp_gain: 0, combo_mult: 1, pet_xp_added: 0, pet_xp_ratio: 0, pet_xp_gained: 0,
      combo_streak: 0, shield_used: false, xp_potion_active: false, ranked_up: false,
      new_rank_level: 0, pet: null, practice: {}, training: {}, new_appearance_items: [],
    }) };
  };
  await RT.legacyReview(7, 3, null, false,
    { attempt: { moves: [{ x: 2, y: 2 }], player_color: 'B', transform: 'identity' } }, fakeFetch);
  check('legacyReview forwards metadata.attempt', captured && captured.attempt && captured.attempt.moves[0].x === 2);
  check('legacyReview attempt is facts-only', captured && !('grade' in captured.attempt) && !('correct' in captured.attempt));
}

if (failures) { console.error(`\n${failures} LC004 transport check(s) failed`); process.exit(1); }
console.log('\nall LC004 transport checks passed');
