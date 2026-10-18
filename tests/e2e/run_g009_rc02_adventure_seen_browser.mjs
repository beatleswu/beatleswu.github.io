// RC02: real Chrome + the real index.html + real authenticated Flask + disposable PostgreSQL.
// Nothing on the page or the server is mocked; only requests to other origins are blocked.
// This exercises the Adventure seen/target predicates with real /api/srs/due and /api/srs/all data and real
// public-review answers. It is NOT an Adventure-screen click-through, nor Safari / iPad.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('C:/Users/beatl/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const event = (phase, details = {}) => console.log('RC02_EVENT ' + JSON.stringify({ phase, ...details }));

async function newContext(profileSuffix) {
  const context = await chromium.launchPersistentContext(config.profile + profileSuffix, {
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true, chromiumSandbox: true, serviceWorkers: 'block', viewport: { width: 1440, height: 1000 },
  });
  context.setDefaultTimeout(25000);
  await context.addCookies([{ name: 'session', value: config.cookie, url: config.baseURL, httpOnly: true, sameSite: 'Lax' }]);
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return url.origin === config.baseURL ? route.continue() : route.abort('blockedbyclient');
  });
  return context;
}

async function openReady(context) {
  const page = context.pages()[0] || await context.newPage();
  page.on('pageerror', error => console.log('RC02_PAGE_ERROR ' + String(error)));
  await page.goto(config.baseURL + '/', { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.waitForFunction(uid => typeof _currentUserId !== 'undefined' && Number(_currentUserId) === uid
    && typeof allQuestions !== 'undefined' && allQuestions.length >= 30, config.userId, { timeout: 45000 });
  await initProgress(page);
  return page;
}

async function initProgress(page) {
  // The page's own idle ownership pass calls SRS.init(onNewBadge); the server-progress map is what Adventure resume hydrates.
  await page.evaluate(async () => { await SRS.init(onNewBadge); await _refreshMapBattleV1ServerProgress(); });
}

const enterDaily = async page => {
  await page.evaluate(async () => { await startDailyTraining(); });
  await page.waitForFunction(() => !!currentQ && !!currentProblem && !!board && _dailyMode === true && _incident002ServerPracticeFlow() === false);
};
const answerWrong = async (page, id) => {
  await enterDaily(page);
  await page.evaluate(async q => { await loadQuestion(allQuestions.find(x => x.id === q)); }, id);
  await page.waitForFunction(q => Number(currentQ && currentQ.id) === q, id);
  await page.evaluate(async () => { await submitSRS(0); });   // real public review POST, wrong answer
  await page.waitForFunction(q => SRS.isSeen(q), id);
};

const probe = (page, ids) => page.evaluate(wanted => {
  const qs = allQuestions.filter(q => wanted.includes(q.id)).sort((a, b) => wanted.indexOf(a.id) - wanted.indexOf(b.id));
  const out = {};
  for (const id of wanted) {
    const card = SRS.getCard(id);
    out[id] = {
      getCardExists: !!card, getCardInterval: card ? card.interval : null, getCardDue: card ? card.due_date : null,
      srsIsSeen: SRS.isSeen(id), serverProgress: _mapBattleV1ServerProgress.has(String(id)),
      adventureSeen: _adventureQuestionSeen(id), defeated: _adventureQuestionDefeated(id),
    };
  }
  const pick = _pickAdventureTarget(qs);
  return { cards: out, firstTarget: pick ? pick.id : null };
}, ids);

const IDS = config.ids;
let context = await newContext('_a');
try {
  const page = await openReady(context);
  const before = await probe(page, IDS);
  event('probe_before', before);

  if (config.case === 'R1') {
    // mixed: IDS[0] answered wrong earlier (persisted card), IDS[1], IDS[2] never answered
    assert.equal(before.cards[IDS[0]].adventureSeen, true, 'persisted wrong question is seen');
    for (const id of IDS.slice(1)) assert.equal(before.cards[id].adventureSeen, false, `virgin ${id} must be unseen even when a synthetic default card exists`);
    assert.equal(before.firstTarget, IDS[1], 'a true unseen puzzle comes before an already-wrong one');
    event('r1_done', { syntheticDefaultCardsForVirgin: IDS.slice(1).map(id => before.cards[id].getCardExists) });
  } else if (config.case === 'R2') {
    // a real accepted answer (wrong) keeps the question seen; repeated init and a reload never regress it
    const target = IDS[0];
    assert.equal(before.cards[target].adventureSeen, false);
    assert.equal(before.firstTarget, target);
    await answerWrong(page, target);
    const afterAnswer = await probe(page, IDS);
    assert.equal(afterAnswer.cards[target].adventureSeen, true, 'accepted wrong answer marks the puzzle seen immediately');
    await page.evaluate(async () => { await SRS.init(onNewBadge); await SRS.init(onNewBadge); });   // repeated init
    const afterInit = await probe(page, IDS);
    assert.equal(afterInit.cards[target].adventureSeen, true, 'repeated init keeps it seen (server card)');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(uid => typeof _currentUserId !== 'undefined' && Number(_currentUserId) === uid && typeof allQuestions !== 'undefined' && allQuestions.length >= 30, config.userId);
    await initProgress(page);
    const afterReload = await probe(page, IDS);
    assert.equal(afterReload.cards[target].adventureSeen, true, 'after reload the server card keeps it seen');
    assert.equal(afterReload.firstTarget, IDS[1], 'the next true-unseen puzzle is selected');
    event('r2_done', { afterAnswer: afterAnswer.cards[target], afterReload: afterReload.cards[target] });
  } else if (config.case === 'R3') {
    // all seen and wrong -> reinforcement is still offered; all defeated -> stop
    assert.equal(before.firstTarget, IDS[0], 'all seen but wrong: reinforce the first not-defeated puzzle');
    const defeatedAll = await page.evaluate(ids => {
      const qs = allQuestions.filter(q => ids.includes(q.id));
      const saved = new Map(_mapBattleV1ServerProgress);
      for (const id of ids) _mapBattleV1ServerProgress.set(String(id), { question_id: id, last_grade: 5 });
      const pick = _pickAdventureTarget(qs);
      _mapBattleV1ServerProgress = saved;
      return pick ? pick.id : null;
    }, IDS);
    assert.equal(defeatedAll, null, 'every puzzle server-defeated: nothing left to pick');
    const next = await page.evaluate(ids => {
      const qs = allQuestions.filter(q => ids.includes(q.id));
      const n = _pickNextAdventureTarget(qs, ids[0]);
      const manual = SRS.findNextAvailableQuestion(qs, qs[0], 1);
      return { next: n ? n.id : null, manualNext: manual ? manual.id : null };
    }, IDS);
    assert.notEqual(next.manualNext, null, 'manual Next still wraps / replays seen puzzles');
    event('r3_done', { defeatedAll, ...next });
  } else if (config.case === 'R5') {
    // two real clients: A answers -> B (fresh load) agrees; a client opened earlier keeps its old snapshot until it refreshes
    const target = IDS[0];
    const stale = await context.newPage();
    await stale.goto(config.baseURL + '/', { waitUntil: 'domcontentloaded' });
    await stale.waitForFunction(uid => typeof _currentUserId !== 'undefined' && Number(_currentUserId) === uid && typeof allQuestions !== 'undefined' && allQuestions.length >= 30, config.userId);
    await initProgress(stale);
    const staleBefore = await probe(stale, IDS);
    assert.equal(staleBefore.cards[target].adventureSeen, false);
    await answerWrong(page, target);
    const ctxB = await newContext('_b');
    const pageB = await openReady(ctxB);
    const fresh = await probe(pageB, IDS);
    const staleAfter = await probe(stale, IDS);
    await initProgress(stale);
    const staleRefreshed = await probe(stale, IDS);
    assert.equal(fresh.cards[target].adventureSeen, true, 'a fresh client agrees with the server');
    assert.equal(staleRefreshed.cards[target].adventureSeen, true, 'the older client agrees after its own refresh');
    event('r5_done', { staleBeforeRefresh: staleAfter.cards[target].adventureSeen, staleAfterRefresh: staleRefreshed.cards[target].adventureSeen,
      freshSeen: fresh.cards[target].adventureSeen,
      note: 'real-time cross-client refresh (RC06) is out of scope; the pre-refresh value is recorded, not asserted' });
    await ctxB.close();
  } else throw new Error('unknown case');
  console.log('RC02_BROWSER_PASS ' + config.case);
} finally {
  await context.close();
}
