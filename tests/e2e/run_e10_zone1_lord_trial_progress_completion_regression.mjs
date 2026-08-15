/*
 * Zone 1 Lord Trial progress/completion regression.
 *
 * This is a browser-state test, not a static "1/20 exists" assertion.  It
 * drives the same submitSRS -> _handleBossAnswer -> _finishBossBattle path,
 * records every rendered position, and verifies one authoritative finish
 * settlement plus the existing Zone 1 success card.  It also proves that a
 * transient answer/save message cannot remove the dedicated progress node.
 */
'use strict';

import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const chromeCandidates = [
  process.env.CHROME_BIN,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);
const chromePath = chromeCandidates.find((candidate) => fssync.existsSync(candidate));
if (!chromePath) throw new Error('No Chrome/Edge executable found');

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      let rel = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
      if (rel === '/') rel = '/index.html';
      const abs = path.resolve(rootDir, `.${rel}`);
      if (!abs.startsWith(rootDir)) { res.writeHead(404); res.end(); return; }
      const stat = await fs.stat(abs).catch(() => null);
      if (!stat?.isFile()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': contentTypeFor(abs) });
      fssync.createReadStream(abs).pipe(res);
    } catch (error) {
      res.writeHead(500); res.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const FAKE_INIT_SCRIPT = `
(() => {
  class FakeAudio { constructor() {} play() { return Promise.resolve(); } pause() {} }
  window.Audio = FakeAudio;
  window.speechSynthesis = { getVoices: () => [], speak: () => {}, cancel: () => {} };
  window.SpeechSynthesisUtterance = function () {};
})();
`;

async function newPage(browser, origin) {
  const page = await browser.newPage();
  await page.addInitScript(FAKE_INIT_SCRIPT);
  await page.route('**/api/**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: '{}',
  }));
  await page.route('**/api/auth/me', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      logged_in: true,
      user_id: 1,
      username: 'zone1_trial_fixture',
      display_name: 'Zone 1 Trial Fixture',
      is_admin: false,
      is_premium: true,
      needs_onboarding_choice: false,
      tour_done: true,
    }),
  }));
  // The app's own startup fetches /api/questions asynchronously and
  // assigns the result to allQuestions; the generic '{}' catch-all above
  // is not an array, so whenever that in-flight fetch resolves it silently
  // clobbers the array each test scenario sets up by hand.  Previously this
  // never had a real window to land in because a Boss transition completed
  // in a handful of milliseconds; it stays a live race with any slower
  // (bounded-wait, settle-then-verify) transition.  A superset covering
  // every question id any scenario below references means the race is
  // harmless regardless of which assignment lands last.
  await page.route('**/api/questions*', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(Array.from({ length: 20 }, (_, index) => ({
      id: index + 1, topic: 'Zone 1 fixture', content: '(;GM[1]SZ[9])', accepted_moves: [],
    }))),
  }));
  await page.goto(`${origin}/index.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(80);
  return page;
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: chromePath });
  const results = [];
  try {
    const page = await newPage(browser, origin);
    try {
      const trace = await page.evaluate(async () => {
        allQuestions = Array.from({ length: 20 }, (_, index) => ({
          id: index + 1,
          topic: 'Zone 1 fixture',
          content: '(;GM[1]SZ[9])',
          accepted_moves: [],
        }));
        SRS.review = async () => ({ ok: true });
        SRS.markSeen = () => {};
        // A bare `currentQ = question` stub used to be enough to isolate
        // Boss progress/finish logic from real board rendering.  The new
        // visible-board contract now requires currentProblem/currentNode/
        // board and a genuinely visible, correctly-stamped canvas before it
        // will consider a transition settled -- so the stub does the same
        // minimal real work loadQuestion() itself does (unhide the wrapper,
        // build a real board via the production initBoard()) instead of
        // faking success.
        window.loadQuestion = async (question) => {
          currentQ = question;
          document.getElementById('welcome-state')?.classList.add('hidden');
          document.getElementById('board-canvas-wrap')?.classList.remove('hidden');
          currentProblem = { size: 9, tree: { move: null, color: null, children: [] }, black: [], white: [], pl: 'B' };
          currentNode = currentProblem.tree;
          initBoard(9, { section: { top: -.5, left: -.5, right: -.5, bottom: -.5 }, displayLines: 9, startX: 0, startY: 0 });
          return true;
        };
        _adventureProgress = [
          { key: 'k26_30', cleared: false, unlocked: true, index: 0 },
          { key: 'k21_25', unlocked: false, index: 1 },
        ];
        const finishCalls = [];
        window.fetch = async (url) => {
          if (String(url).includes('/api/adventure/boss/finish')) {
            finishCalls.push(String(url));
            return {
              ok: true,
              json: async () => ({
                ok: true,
                passed: true,
                // Deliberately use server values different from the local
                // tally to prove the result card reads authoritative data.
                correct: 19,
                total: 20,
                pass_score: 16,
                cooldown_left: 0,
                zones: [
                  { key: 'k26_30', cleared: true, unlocked: true, index: 0 },
                  { key: 'k21_25', unlocked: true, index: 1 },
                ],
              }),
            };
          }
          return { ok: true, json: async () => ({}) };
        };
        _bossMode = true;
        _bossZone = _adventureProgress[0];
        _bossQueue = allQuestions.map((question) => question.id);
        _bossIndex = 0;
        _bossCorrect = 0;
        _bossFinishInFlight = false;
        await _loadBossQuestion();
        const positions = [{
          question: 1,
          progress: document.getElementById('boss-trial-progress')?.textContent || '',
          visible: getComputedStyle(document.getElementById('boss-trial-progress')).display !== 'none',
          index: _bossIndex,
        }];
        for (let answer = 0; answer < 20; answer += 1) {
          await submitSRS(3);
          const progress = document.getElementById('boss-trial-progress');
          // Simulate the transient answer/save copy that previously replaced
          // the only progress surface.
          if (answer < 19) setMsg('answer saved', 'ok');
          positions.push({
            question: Math.min(answer + 2, 20),
            progress: progress?.textContent || '',
            visible: !!progress && getComputedStyle(progress).display !== 'none',
            index: _bossIndex,
          });
        }
        return {
          positions,
          finishCallCount: finishCalls.length,
          bossMode: _bossMode,
          bossIndex: _bossIndex,
          bossCorrect: _bossCorrect,
          resultClass: document.getElementById('boss-cinematic')?.className || '',
          resultTitle: document.getElementById('boss-cinematic-title')?.textContent || '',
          resultLine: document.getElementById('boss-cinematic-line')?.textContent || '',
        };
      });
      results.push({ name: '20-question browser state progression and one finish', ok: true, trace });
      const expected = [1, 2, 3, 19, 20].map((position) => `${position}/20`);
      for (const position of [1, 2, 3, 19, 20]) {
        const row = trace.positions[position - 1];
        if (!row?.visible || !row.progress.includes(`${position}/20`)) {
          throw new Error(`progress missing at ${position}/20: ${JSON.stringify(row)}`);
        }
      }
      if (trace.finishCallCount !== 1) throw new Error(`expected one finish request, got ${trace.finishCallCount}`);
      if (trace.bossMode !== false || trace.bossIndex !== 20) throw new Error(`trial did not settle cleanly: ${JSON.stringify(trace)}`);
      if (!trace.resultClass.includes('result-zone1-win')) throw new Error(`success card not rendered: ${trace.resultClass}`);
      if (!trace.resultLine.includes('19') || !trace.resultLine.includes('20')) {
        throw new Error(`success card did not use server score: ${trace.resultLine}`);
      }
      if (!trace.resultTitle) throw new Error('success card title missing');
      void expected;
    } finally {
      await page.close();
    }

    const failurePage = await newPage(browser, origin);
    try {
      const failure = await failurePage.evaluate(async () => {
        allQuestions = [{ id: 1, topic: 'Zone 1 fixture', content: '(;GM[1]SZ[9])', accepted_moves: [] }];
        SRS.review = async () => ({ ok: true });
        SRS.markSeen = () => {};
        // A bare `currentQ = question` stub used to be enough to isolate
        // Boss progress/finish logic from real board rendering.  The new
        // visible-board contract now requires currentProblem/currentNode/
        // board and a genuinely visible, correctly-stamped canvas before it
        // will consider a transition settled -- so the stub does the same
        // minimal real work loadQuestion() itself does (unhide the wrapper,
        // build a real board via the production initBoard()) instead of
        // faking success.
        window.loadQuestion = async (question) => {
          currentQ = question;
          document.getElementById('welcome-state')?.classList.add('hidden');
          document.getElementById('board-canvas-wrap')?.classList.remove('hidden');
          currentProblem = { size: 9, tree: { move: null, color: null, children: [] }, black: [], white: [], pl: 'B' };
          currentNode = currentProblem.tree;
          initBoard(9, { section: { top: -.5, left: -.5, right: -.5, bottom: -.5 }, displayLines: 9, startX: 0, startY: 0 });
          return true;
        };
        _adventureProgress = [
          { key: 'k26_30', cleared: false, unlocked: true, index: 0 },
          { key: 'k21_25', cleared: false, unlocked: false, index: 1 },
        ];
        const finishCalls = [];
        window.fetch = async (url) => {
          if (String(url).includes('/api/adventure/boss/finish')) {
            finishCalls.push(String(url));
            return {
              ok: true,
              json: async () => ({
                ok: true,
                passed: false,
                correct: 0,
                total: 1,
                pass_score: 1,
                cooldown_left: 30,
                zones: _adventureProgress,
              }),
            };
          }
          return { ok: true, json: async () => ({}) };
        };
        _bossMode = true; _bossZone = _adventureProgress[0]; _bossQueue = [1];
        _bossIndex = 0; _bossCorrect = 0; _bossFinishInFlight = false;
        await _loadBossQuestion();
        await submitSRS(1);
        return {
          finishCallCount: finishCalls.length,
          resultClass: document.getElementById('boss-cinematic')?.className || '',
          zoneCleared: Boolean(_adventureProgress[0]?.cleared),
          nextZoneUnlocked: Boolean(_adventureProgress[1]?.unlocked),
        };
      });
      results.push({ name: 'failure retains uncleared Zone 1 state', ok: true, failure });
      if (failure.finishCallCount !== 1 || !failure.resultClass.includes('result-zone1-fail')) {
        throw new Error(`failure result not rendered: ${JSON.stringify(failure)}`);
      }
      if (failure.zoneCleared || failure.nextZoneUnlocked) {
        throw new Error(`failure mutated clear/unlock state: ${JSON.stringify(failure)}`);
      }
    } finally {
      await failurePage.close();
    }

    const duplicatePage = await newPage(browser, origin);
    try {
      const duplicate = await duplicatePage.evaluate(async () => {
        allQuestions = [{ id: 1, topic: 'Zone 1 fixture', content: '(;GM[1]SZ[9])', accepted_moves: [] }];
        SRS.review = async () => ({ ok: true });
        SRS.markSeen = () => {};
        // A bare `currentQ = question` stub used to be enough to isolate
        // Boss progress/finish logic from real board rendering.  The new
        // visible-board contract now requires currentProblem/currentNode/
        // board and a genuinely visible, correctly-stamped canvas before it
        // will consider a transition settled -- so the stub does the same
        // minimal real work loadQuestion() itself does (unhide the wrapper,
        // build a real board via the production initBoard()) instead of
        // faking success.
        window.loadQuestion = async (question) => {
          currentQ = question;
          document.getElementById('welcome-state')?.classList.add('hidden');
          document.getElementById('board-canvas-wrap')?.classList.remove('hidden');
          currentProblem = { size: 9, tree: { move: null, color: null, children: [] }, black: [], white: [], pl: 'B' };
          currentNode = currentProblem.tree;
          initBoard(9, { section: { top: -.5, left: -.5, right: -.5, bottom: -.5 }, displayLines: 9, startX: 0, startY: 0 });
          return true;
        };
        _adventureProgress = [
          { key: 'k26_30', cleared: false, unlocked: true, index: 0 },
          { key: 'k21_25', cleared: false, unlocked: false, index: 1 },
        ];
        const finishCalls = [];
        window.fetch = async (url) => {
          if (String(url).includes('/api/adventure/boss/finish')) {
            finishCalls.push(String(url));
            await new Promise((resolve) => setTimeout(resolve, 25));
            return {
              ok: true,
              json: async () => ({
                ok: true,
                passed: true,
                correct: 1,
                total: 1,
                pass_score: 1,
                cooldown_left: 0,
                zones: [
                  { key: 'k26_30', cleared: true, unlocked: true, index: 0 },
                  { key: 'k21_25', cleared: false, unlocked: true, index: 1 },
                ],
              }),
            };
          }
          return { ok: true, json: async () => ({}) };
        };
        _bossMode = true; _bossZone = _adventureProgress[0]; _bossQueue = [1];
        _bossIndex = 0; _bossCorrect = 0; _bossFinishInFlight = false;
        await _loadBossQuestion();
        await Promise.all([_handleBossAnswer(3), _handleBossAnswer(3)]);
        return {
          finishCallCount: finishCalls.length,
          bossIndex: _bossIndex,
          bossCorrect: _bossCorrect,
          bossMode: _bossMode,
        };
      });
      results.push({ name: 'duplicate answer cannot double-submit finish', ok: true, duplicate });
      if (duplicate.finishCallCount !== 1 || duplicate.bossIndex !== 1 || duplicate.bossCorrect !== 1) {
        throw new Error(`duplicate completion guard failed: ${JSON.stringify(duplicate)}`);
      }
    } finally {
      await duplicatePage.close();
    }

    for (const viewport of [
      { name: 'desktop', width: 1440, height: 900 },
      { name: 'ipad-landscape', width: 1180, height: 820 },
      { name: 'ipad-portrait', width: 820, height: 1180 },
      { name: 'iphone', width: 430, height: 932 },
    ]) {
      const responsivePage = await newPage(browser, origin);
      try {
        await responsivePage.setViewportSize({ width: viewport.width, height: viewport.height });
        const state = await responsivePage.evaluate(async () => {
          allQuestions = [{ id: 1, topic: 'Zone 1 fixture', content: '(;GM[1]SZ[9])', accepted_moves: [] }];
          window.loadQuestion = async (question) => {
            currentQ = question;
            document.getElementById('welcome-state')?.classList.add('hidden');
            document.getElementById('board-canvas-wrap')?.classList.remove('hidden');
            currentProblem = { size: 9, tree: { move: null, color: null, children: [] }, black: [], white: [], pl: 'B' };
            currentNode = currentProblem.tree;
            initBoard(9, { section: { top: -.5, left: -.5, right: -.5, bottom: -.5 }, displayLines: 9, startX: 0, startY: 0 });
            return true;
          };
          _bossMode = true; _bossZone = { key: 'k26_30' }; _bossQueue = [1]; _bossIndex = 0; _bossCorrect = 0;
          await _loadBossQuestion();
          const el = document.getElementById('boss-trial-progress');
          const rect = el.getBoundingClientRect();
          return { text: el.textContent, display: getComputedStyle(el).display, width: rect.width, viewport: window.innerWidth };
        });
        if (state.display === 'none' || !state.text.includes('1/1') || state.width <= 0 || state.width > viewport.width) {
          throw new Error(`${viewport.name} progress layout invalid: ${JSON.stringify(state)}`);
        }
        results.push({ name: `responsive ${viewport.name}`, ok: true, state });
      } finally {
        await responsivePage.close();
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  console.log(JSON.stringify({ ok: results.every((result) => result.ok), results }, null, 2));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
