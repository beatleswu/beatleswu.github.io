/* E042 cleared-zone Lord replay contract.
 *
 * This browser fixture supplies the same server-shaped bootstrap to the E9
 * adapter and the legacy Lord entry bridge.  It exercises the shipped DOM
 * CTA, the existing /api/adventure/boss/start and /finish contracts, and
 * reloads from the authoritative snapshot.  It never calls app.py or writes
 * application data.
 */
'use strict';

import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');

const chromeCandidates = [
  process.env.CHROME_BIN,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);
const chromePath = chromeCandidates.find((candidate) => fssync.existsSync(candidate));
if (!chromePath) throw new Error('No Chrome/Edge executable found');

function contentType(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.webp': 'image/webp',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer() {
  const server = http.createServer(async (request, response) => {
    try {
      let relative = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
      if (relative === '/') relative = '/index.html';
      const absolute = path.resolve(ROOT, `.${relative}`);
      if (!absolute.startsWith(ROOT)) { response.writeHead(404); response.end(); return; }
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) { response.writeHead(404); response.end(); return; }
      response.writeHead(200, { 'Content-Type': contentType(absolute) });
      fssync.createReadStream(absolute).pipe(response);
    } catch (error) {
      response.writeHead(500); response.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const AUTH = {
  logged_in: true,
  user_id: 42042,
  username: 'e042_fixture',
  display_name: 'E042 Fixture Player',
  nickname: 'E042 Fixture Player',
  is_admin: false,
  is_premium: true,
  needs_onboarding_choice: false,
  tour_done: true,
  elo_rating: 1400,
  newbie_quest_eligible: false,
};

function zone(key, fields = {}) {
  const cleared = key === 'k26_30';
  return {
    key,
    name: key === 'k26_30' ? '新手村' : '史萊姆平原',
    name_en: key === 'k26_30' ? 'Beginner Village' : 'Slime Plains',
    status: cleared ? 'completed' : 'unlocked',
    unlocked: true,
    can_enter: true,
    cleared,
    completed: cleared,
    stars: cleared ? 1 : 0,
    seen: cleared ? 30 : 18,
    total: cleared ? 30 : 25,
    boss: { available: key === 'k21_25' },
    boss_exam_size: 1,
    boss_pass_score: 1,
    cooldown_required: 30,
    ...fields,
  };
}

function bootstrap() {
  return {
    zones: [zone('k26_30'), zone('k21_25')],
    current_zone_key: 'k21_25',
    selected: { zone_key: 'k26_30' },
    recommended: { zone_key: 'k21_25' },
    primary_action: { kind: 'challenge_lord', zone_key: 'k21_25', boss_key: 'swarm_lord' },
    secondary_action: { kind: 'replenish_stars', zone_key: 'k26_30' },
    cinematics: { e10_zone1_intro_v1: { seen: true, seen_at: '2026-08-01T00:00:00Z' } },
  };
}

function question() {
  return {
    id: 4201,
    topic: 'E042 replay fixture',
    content: '(;GM[1]SZ[9]PL[B];B[dd])',
    accepted_moves: [{ x: 3, y: 3 }],
  };
}

function committedReviewPayload({ outcome, attemptId }) {
  return {
    ok: true,
    ease_factor: 2.5,
    interval: 1,
    due_date: '2026-08-28',
    new_badges: [],
    stats: {},
    xp_gain: 0,
    combo_mult: 1,
    pet_xp_added: 0,
    pet_xp_ratio: 0,
    pet_xp_gained: 0,
    combo_streak: 0,
    shield_used: false,
    xp_potion_active: false,
    ranked_up: false,
    new_rank_level: 'LV1',
    pet: null,
    practice: null,
    training: null,
    new_appearance_items: [],
    boss_verdict: {
      schema: 'lord_trial_verdict_v1',
      attempt_id: attemptId,
      question_id: 4201,
      verdict: outcome === 'pass' ? 'AUTHORITATIVE_PASS' : 'AUTHORITATIVE_FAIL',
      authoritative_grade: outcome === 'pass' ? 5 : 0,
      judge_version: 'lord-trial-map-battle-judge-v1',
      reason_code: 'answer_tree_leaf',
    },
  };
}

function bodyJson(body) {
  return JSON.stringify(body);
}

async function runScenario(browser, origin, {
  name,
  viewport,
  hasTouch = false,
  lang,
  outcome,
}) {
  const page = await browser.newPage({ viewport, hasTouch });
  const requests = [];
  const consoleErrors = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/')) {
      requests.push({ method: request.method(), pathname: url.pathname, body: request.postData() || '' });
    }
  });
  page.on('console', (message) => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  page.on('pageerror', (error) => consoleErrors.push(String(error && error.message || error)));
  await page.addInitScript(() => {
    class FakeAudio { play() { return Promise.resolve(); } pause() {} }
    window.Audio = FakeAudio;
    window.speechSynthesis = { getVoices: () => [], speak: () => {}, cancel: () => {} };
    window.SpeechSynthesisUtterance = function () {};
    localStorage.setItem('last_session_uid_v1', '42042');
    localStorage.setItem('adventure_bossready_seen_v1', JSON.stringify({ 1: { k21_25: Date.now(), k26_30: Date.now() } }));
  });
  await page.route('**/api/**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '{}',
  }));
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: bodyJson(AUTH),
  }));
  await page.route('**/api/questions**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: bodyJson([question()]),
  }));
  await page.route('**/api/srs/due**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: bodyJson({ due: [], count: 0 }),
  }));
  await page.route('**/api/srs/all**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '[]',
  }));
  await page.route('**/api/badges/definitions**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '[]',
  }));
  await page.route('**/api/badges/earned**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: '[]',
  }));
  await page.route('**/api/unit-progress**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: bodyJson({ unit_complete: false }),
  }));
  await page.route('**/api/srs/review**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: bodyJson(committedReviewPayload({ outcome, attemptId: `e042-${name}` })),
  }));
  await page.route('**/api/adventure/bootstrap**', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: bodyJson(bootstrap()),
  }));
  let startCalls = 0;
  let finishCalls = 0;
  let finishReward = null;
  await page.route('**/api/adventure/boss/start**', (route) => {
    startCalls += 1;
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: bodyJson({
        ok: true,
        replay: true,
        attempt_mode: 'replay',
        attempt_id: `e042-${name}`,
        question_ids: [4201],
        zone: zone('k26_30'),
      }),
    });
  });
  await page.route('**/api/adventure/boss/finish**', (route) => {
    finishCalls += 1;
    finishReward = { coins: 0, first_clear: false };
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: bodyJson({
        ok: true,
        passed: outcome === 'pass',
        correct: outcome === 'pass' ? 1 : 0,
        total: 1,
        replay: true,
        attempt_mode: 'replay',
        reward: finishReward,
        zones: [zone('k26_30'), zone('k21_25')],
      }),
    });
  });

  const shell = 'E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';
  await page.goto(`${origin}/index.html?lang=${lang}&${shell}&go-odyssey-static-contract=e10-vs1f-integrated-world-map&staticContract=e10-vs1f-integrated-world-map`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#e9-world-stage-zones [data-zone]').length >= 2, { timeout: 15000 });
  await page.evaluate(() => document.querySelector('[data-zone="k26_30"]')?.click());
  await page.waitForFunction(() => {
    const buttons = [
      document.getElementById('e9-world-stage-details-cta'),
      document.getElementById('e9-world-stage-primary-cta'),
      document.querySelector('.e9-zone__inline-cta'),
    ];
    return buttons.some((button) => button && !button.hidden && button.getBoundingClientRect().width > 0);
  }, { timeout: 10000 });

  const cta = await page.evaluate(() => {
    const buttons = [
      document.getElementById('e9-world-stage-details-cta'),
      document.getElementById('e9-world-stage-primary-cta'),
      document.querySelector('.e9-zone__inline-cta'),
    ].filter((button) => button && !button.hidden && button.getBoundingClientRect().width > 0);
    const button = buttons[0];
    const rect = button.getBoundingClientRect();
    const state = document.getElementById('e9-world-stage-slot')?.__e9WorldStageState;
    return {
      id: button.id || null,
      text: button.textContent || '',
      disabled: button.disabled,
      rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height },
      selectedZoneKey: state?.selectedZoneKey || null,
      currentPlayerZoneKey: state?.currentPlayerZoneKey || null,
      detail: window.E9?.latestZoneSelection || null,
    };
  });
  const expectedReplayText = lang === 'zh' ? '再次挑戰領主' : 'Challenge this boss again';
  const expectedLordCardText = lang === 'zh' ? '再次挑戰領主' : 'Challenge Again';
  if (cta.disabled || !cta.text.includes(expectedReplayText)) {
    throw new Error(`${name}: cleared primary CTA was not replay: ${JSON.stringify(cta)}`);
  }
  if (cta.selectedZoneKey !== 'k26_30' || cta.currentPlayerZoneKey !== 'k21_25'
    || cta.detail?.ctaKind !== 'replay_completed' || cta.detail?.currentPlayerZoneKey !== 'k21_25') {
    throw new Error(`${name}: selection changed authoritative player location: ${JSON.stringify(cta)}`);
  }
  if (lang === 'en' && /[\u4e00-\u9fff]/.test(cta.text)) throw new Error(`${name}: Chinese leaked into English CTA`);
  if (cta.rect.width <= 0 || cta.rect.height <= 0) throw new Error(`${name}: CTA has no hit target`);

  const ctaLocator = cta.id
    ? page.locator(`#${cta.id}`)
    : page.locator('.e9-zone__inline-cta:not(.e9-zone__inline-cta--secondary)');
  await ctaLocator.click();
  await page.locator('#boss-cinematic[aria-hidden="false"]').waitFor({ state: 'visible', timeout: 15000 });
  const lordCardText = await page.locator('#boss-cinematic').textContent();
  if (!lordCardText.includes(expectedLordCardText)) throw new Error(`${name}: Lord card replay copy missing: ${lordCardText}`);
  await page.locator('#boss-cinematic-btn').click();
  await page.locator('#boss-trial-progress').waitFor({ state: 'visible', timeout: 15000 });
  const board = page.locator('#board-canvas-wrap canvas').first();
  await board.waitFor({ state: 'visible', timeout: 15000 });
  const box = await board.boundingBox();
  if (!box) throw new Error(`${name}: replay board has no hit-test box`);
  await page.mouse.click(box.x + box.width * (3.5 / 9), box.y + box.height * (3.5 / 9));
  await page.locator(`#boss-cinematic.result-zone1-${outcome === 'pass' ? 'win' : 'fail'}`).waitFor({ state: 'visible', timeout: 15000 });
  if (startCalls !== 1 || finishCalls !== 1) throw new Error(`${name}: expected exactly one server replay start/finish, got ${startCalls}/${finishCalls}`);

  const result = await page.evaluate(() => ({
    title: document.getElementById('boss-cinematic-title')?.textContent || '',
    line: document.getElementById('boss-cinematic-line')?.textContent || '',
    zone: (_adventureProgress || []).find((item) => item.key === 'k26_30') || null,
  }));
  if (outcome === 'pass') {
    if (!result.title.includes(lang === 'zh' ? '再次挑戰完成' : 'Replay Complete')) throw new Error(`${name}: replay pass result missing: ${JSON.stringify(result)}`);
    if (!result.line.includes(lang === 'zh' ? '清關狀態' : 'clear state')) throw new Error(`${name}: replay pass did not preserve-clear message`);
  } else {
    if (!result.title.includes(lang === 'zh' ? '再次挑戰未通過' : 'Replay Not Passed')) throw new Error(`${name}: replay fail result missing: ${JSON.stringify(result)}`);
    if (!result.line.includes(lang === 'zh' ? '清關狀態' : 'clear state')) throw new Error(`${name}: replay fail did not preserve-clear message`);
  }
  if (!result.zone || result.zone.cleared !== true || Number(result.zone.stars) !== 1) {
    throw new Error(`${name}: replay changed existing clear/stars: ${JSON.stringify(result.zone)}`);
  }
  if (!finishReward || finishReward.coins !== 0 || finishReward.first_clear !== false) {
    throw new Error(`${name}: replay returned a first-clear reward: ${JSON.stringify(finishReward)}`);
  }
  const forbiddenWrites = requests.filter((request) => request.method !== 'GET'
    && /reward|coins|inventory|wardrobe|spirit|unlock|mapping|postclear/i.test(request.pathname));
  const spiritCalls = requests.filter((request) => /spirit/i.test(request.pathname));
  if (forbiddenWrites.length || spiritCalls.length) throw new Error(`${name}: replay crossed reward/Spirit boundary: ${JSON.stringify({ forbiddenWrites, spiritCalls })}`);

  await page.locator('#boss-cinematic-btn').click();
  await page.waitForTimeout(outcome === 'pass' ? 650 : 100);
  await page.evaluate(() => {
    const overlay = document.getElementById('boss-cinematic');
    const control = overlay?.querySelector('.intro-skip-btn:not([hidden]), .boss-cinematic-close-x:not([hidden])');
    if (control && getComputedStyle(control).display !== 'none') control.click();
  });
  await page.waitForTimeout(100);
  if (await page.locator('#boss-cinematic[aria-hidden="false"]').count()) {
    throw new Error(`${name}: Continue left a dead-end modal`);
  }
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#e9-world-stage-zones [data-zone]').length >= 2, { timeout: 15000 });
  await page.evaluate(() => document.querySelector('[data-zone="k26_30"]')?.click());
  await page.waitForFunction(() => {
    const button = document.getElementById('e9-world-stage-details-cta');
    const primary = document.getElementById('e9-world-stage-primary-cta');
    const inline = document.querySelector('.e9-zone__inline-cta');
    return [button, primary, inline].some((item) => item && !item.hidden && item.getBoundingClientRect().width > 0);
  }, { timeout: 10000 });
  const afterReload = await page.evaluate(() => {
    const button = [
      document.getElementById('e9-world-stage-details-cta'),
      document.getElementById('e9-world-stage-primary-cta'),
      document.querySelector('.e9-zone__inline-cta'),
    ].find((item) => item && !item.hidden && item.getBoundingClientRect().width > 0);
    const state = document.getElementById('e9-world-stage-slot')?.__e9WorldStageState;
    return {
      text: button?.textContent || '',
      disabled: button?.disabled,
      current: state?.currentPlayerZoneKey || null,
      selected: state?.selectedZoneKey || null,
      nextZoneUnlocked: !!state?.zones?.find((item) => item.key === 'k21_25' && item.canEnter === true && !item.locked),
      detail: window.E9?.latestZoneSelection || null,
    };
  });
  if (afterReload.disabled || !afterReload.text.includes(expectedReplayText)
    || afterReload.current !== 'k21_25' || afterReload.selected !== 'k26_30'
    || afterReload.nextZoneUnlocked !== true
    || afterReload.detail?.ctaKind !== 'replay_completed') {
    throw new Error(`${name}: reload did not restore replay/selection state: ${JSON.stringify(afterReload)}`);
  }
  await page.close();
  return {
    name, viewport, lang, outcome, cta, result, afterReload,
    startCalls, finishCalls, finishReward, consoleErrors,
    rewardWrites: forbiddenWrites.length,
    spiritCalls: spiritCalls.length,
  };
}

async function main() {
  const { server, origin } = await startStaticServer();
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const specs = [
    { name: 'desktop-en-pass', viewport: { width: 1440, height: 900 }, lang: 'en', outcome: 'pass' },
    { name: 'ipad-landscape-en-fail', viewport: { width: 1024, height: 768 }, hasTouch: true, lang: 'en', outcome: 'fail' },
    { name: 'ipad-portrait-zh-pass', viewport: { width: 768, height: 1024 }, hasTouch: true, lang: 'zh', outcome: 'pass' },
    { name: 'mobile-zh-fail', viewport: { width: 430, height: 932 }, hasTouch: true, lang: 'zh', outcome: 'fail' },
  ];
  try {
    const results = [];
    for (const spec of specs) {
      process.stdout.write(`run ${spec.name}\n`);
      results.push(await runScenario(browser, origin, spec));
    }
    if (results.some((result) => result.consoleErrors.length)) {
      throw new Error(`browser errors: ${JSON.stringify(results.map((result) => ({ name: result.name, errors: result.consoleErrors })))}`);
    }
    console.log(JSON.stringify({ ok: true, contract: 'e042-cleared-zone-replay-cta', results }, null, 2));
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
