import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const INDEX = await fs.readFile(path.join(ROOT, 'index.html'), 'utf8');

function extractFunction(name, endName) {
  let start = INDEX.indexOf(`function ${name}`);
  assert.notEqual(start, -1, `missing ${name}`);
  // Include a leading `async ` keyword in the extraction if present --
  // otherwise an async function's body (e.g. enterAdventureZoneInPage,
  // which awaits _resolveMapBattleV1Resume()) gets pasted into the test
  // harness script as a non-async declaration, a syntax error at parse time.
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

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find((candidate) => fssync.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found.');
  return executable;
}

function contentType(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.webp': 'image/webp',
    '.png': 'image/png',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startServer() {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      if (url.pathname === '/inventory.html') {
        response.writeHead(404);
        response.end('noncanonical inventory source filename');
        return;
      }
      const routeFiles = new Map([
        ['/inventory', 'inventory.html'],
        ['/index.html', 'index.html'],
        ['/', 'index.html'],
      ]);
      const relative = routeFiles.get(url.pathname) || decodeURIComponent(url.pathname).replace(/^\/+/, '');
      const absolute = path.resolve(ROOT, relative);
      if (absolute !== ROOT && !absolute.startsWith(`${ROOT}${path.sep}`)) {
        response.writeHead(403);
        response.end('forbidden');
        return;
      }
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      response.writeHead(200, { 'Content-Type': contentType(absolute) });
      fssync.createReadStream(absolute).pipe(response);
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

const isE10BattleShell = extractFunction('_isE10BattleShell', '_hydrateE10BattlePresentation');
const actionState = extractFunction('_isE10BattleActionState', '_syncE10BattleActions');
const syncActions = extractFunction('_syncE10BattleActions', 'showE10BattleExplanation');
const publishShellOwner = extractFunction('publishAdventureShellOwner', 'isE10AdventureShellOwner');
const enterAdventure = extractFunction('enterAdventureZoneInPage', 'adventureActiveZone');

async function runBattleEntryOwnershipContract(browser) {
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><html><body>
    <button id="btn-e10-battle-explain" style="display:none"></button>
    <button id="btn-adventure-return" style="display:none"></button>
  </body></html>`);
  await page.addScriptTag({ content: `
    const E10_MAP_SHELL_OWNER = 'e10-map';
    const E10_BATTLE_SHELL_OWNER = 'e10-battle';
    let _mapBattleV1LifecycleGeneration = 0;
    let _mapBattleV1Mode = 'pending';
    let currentQ = null;
    let allQuestions = [{ id: 7, topic: 'zone-book', locked: false }];
    let _adventureActiveQuestions = [];
    let loadBehavior = 'success';
    let loadCalls = 0;
    const ADVENTURE_ZONES = [{ key: 'zone-1', books: [] }];
    function _pickAdventureTarget(questions) { return questions[0] || null; }
    // No stored resume in this synthetic harness -- exercises the same
    // "fall through to the deterministic selector" path a genuinely fresh
    // zone entry takes in production.
    async function _resolveMapBattleV1Resume() { return null; }
    function renderList() {}
    function firstQuestionHref() { return '/?adventure=1&zone=zone-1'; }
    function _isAdventureZonePractice() { return true; }
    function isBeginnerVillageAdventureResult() { return false; }
    ${publishShellOwner}
    ${isE10BattleShell}
    ${actionState}
    ${syncActions}
    function loadQuestion(question) {
      loadCalls += 1;
      _mapBattleV1LifecycleGeneration += 1;
      currentQ = question;
      _mapBattleV1Mode = 'active';
      _syncE10BattleActions(true);
      return Promise.resolve(loadBehavior === 'success');
    }
    ${enterAdventure}
    window.__runBattleEntryOwnershipContract = async function () {
      publishAdventureShellOwner(E10_MAP_SHELL_OWNER);
      const started = await enterAdventureZoneInPage(ADVENTURE_ZONES[0]);
      const immediate = {
        started,
        owner: window.__GO_ADVENTURE_SHELL_OWNER__,
        bodyOwner: document.body.getAttribute('data-adventure-shell-owner'),
        explanation: document.getElementById('btn-e10-battle-explain').style.display,
        returnToMap: document.getElementById('btn-adventure-return').style.display,
      };
      await new Promise((resolve) => setTimeout(resolve, 0));
      const settled = {
        owner: window.__GO_ADVENTURE_SHELL_OWNER__,
        bodyOwner: document.body.getAttribute('data-adventure-shell-owner'),
      };
      loadBehavior = 'fail';
      publishAdventureShellOwner(E10_MAP_SHELL_OWNER);
      const failedStarted = await enterAdventureZoneInPage(ADVENTURE_ZONES[0]);
      await new Promise((resolve) => setTimeout(resolve, 0));
      const failed = {
        started: failedStarted,
        owner: window.__GO_ADVENTURE_SHELL_OWNER__,
        bodyOwner: document.body.getAttribute('data-adventure-shell-owner'),
      };
      return { immediate, settled, failed, loadCalls };
    };
  ` });
  const result = await page.evaluate(() => window.__runBattleEntryOwnershipContract());
  await page.close();
  assert.equal(result.immediate.started, true);
  assert.equal(result.immediate.owner, 'e10-battle');
  assert.equal(result.immediate.bodyOwner, 'e10-battle');
  assert.equal(result.immediate.explanation, 'inline-flex');
  assert.equal(result.immediate.returnToMap, 'inline-flex');
  assert.deepEqual(result.settled, { owner: 'e10-battle', bodyOwner: 'e10-battle' });
  assert.deepEqual(result.failed, { started: true, owner: 'e10-map', bodyOwner: 'e10-map' });
  assert.equal(result.loadCalls, 2);
  return result;
}

async function runCanonicalInventoryRouteContract(origin) {
  const canonical = await fetch(`${origin}/inventory`);
  const canonicalBytes = Buffer.from(await canonical.arrayBuffer());
  const sourceBytes = await fs.readFile(path.join(ROOT, 'inventory.html'));
  assert.equal(canonical.status, 200);
  assert.ok(canonicalBytes.equals(sourceBytes), 'canonical /inventory body must match inventory.html bytes');
  const sourceFilename = await fetch(`${origin}/inventory.html`);
  assert.equal(sourceFilename.status, 404, 'inventory.html is a package filename, not a public route');
  return {
    canonicalRoute: '/inventory',
    canonicalStatus: canonical.status,
    canonicalBodyMatchesSource: canonicalBytes.equals(sourceBytes),
    noncanonicalRoute: '/inventory.html',
    noncanonicalStatus: sourceFilename.status,
  };
}

async function runBattleReloadContract(browser) {
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><html><body>
    <button id="btn-e10-battle-explain" style="display:none"></button>
    <button id="btn-adventure-return" style="display:none"></button>
  </body></html>`);
  await page.addScriptTag({ content: `
    let _mapBattleV1Mode = 'active';
    let currentQ = { id: 7, monster_type: 'goblin', monster_name: 'Goblin' };
    function _isAdventureZonePractice() { return true; }
    function isBeginnerVillageAdventureResult() { return false; }
    ${isE10BattleShell}
    ${actionState}
    ${syncActions}
    window.__runShellOwnerContract = function () {
      window.__GO_E9_ACTIVE_SHELL__ = 'legacy';
      document.body.dataset.adventureShellActive = 'legacy';
      window.__GO_ADVENTURE_SHELL_OWNER__ = 'e10-battle';
      document.body.dataset.adventureShellOwner = 'e10-battle';
      _syncE10BattleActions(true);
      const e10 = {
        owner: window.__GO_ADVENTURE_SHELL_OWNER__,
        renderer: window.__GO_E9_ACTIVE_SHELL__,
        battleOwned: _isE10BattleShell(),
        explanation: document.getElementById('btn-e10-battle-explain').style.display,
        returnToMap: document.getElementById('btn-adventure-return').style.display,
      };
      window.__GO_ADVENTURE_SHELL_OWNER__ = null;
      document.body.removeAttribute('data-adventure-shell-owner');
      _syncE10BattleActions(true);
      return {
        e10,
        legacy: {
          battleOwned: _isE10BattleShell(),
          explanation: document.getElementById('btn-e10-battle-explain').style.display,
          returnToMap: document.getElementById('btn-adventure-return').style.display,
        },
      };
    };
  ` });
  const result = await page.evaluate(() => window.__runShellOwnerContract());
  await page.close();
  assert.deepEqual(result, {
    e10: {
      owner: 'e10-battle',
      renderer: 'legacy',
      battleOwned: true,
      explanation: 'inline-flex',
      returnToMap: 'inline-flex',
    },
    legacy: {
      battleOwned: false,
      explanation: 'none',
      returnToMap: 'none',
    },
  });
  return result;
}

async function runBackpackReloadContract(browser, origin) {
  const page = await browser.newPage({ viewport: { width: 820, height: 1180 } });
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    const bodies = {
      '/api/auth/me': { logged_in: true, user_id: 42, username: 'shell_fixture' },
      '/api/shop/catalog': { inventory: {}, items: [], daily_items: [], weekly_items: [], monthly_items: [] },
      '/api/pet/status': { inventory: [], pet: null },
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(bodies[pathname] || { ok: true }),
    });
  });
  await page.goto(`${origin}/inventory?e10=1`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const initial = await page.evaluate(() => ({
    ownerBody: document.body.getAttribute('data-adventure-shell-owner'),
    ownerDocument: document.documentElement.getAttribute('data-adventure-shell-owner'),
    globalNav: document.querySelectorAll('.cg-nav-links').length,
    e10HeaderVisible: document.querySelectorAll('[data-e10-backpack-only]:not([hidden])').length,
    legacyHeaderVisible: document.querySelectorAll('[data-legacy-backpack-header]:not([hidden])').length,
    shellCount: document.querySelectorAll('#inventory-page-header').length,
  }));
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const reloaded = await page.evaluate(() => ({
    ownerBody: document.body.getAttribute('data-adventure-shell-owner'),
    ownerDocument: document.documentElement.getAttribute('data-adventure-shell-owner'),
    globalNav: document.querySelectorAll('.cg-nav-links').length,
    e10HeaderVisible: document.querySelectorAll('[data-e10-backpack-only]:not([hidden])').length,
    legacyHeaderVisible: document.querySelectorAll('[data-legacy-backpack-header]:not([hidden])').length,
    shellCount: document.querySelectorAll('#inventory-page-header').length,
  }));
  await page.goto(`${origin}/inventory`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('#backpack-status')?.dataset.state === 'ready');
  const generic = await page.evaluate(() => ({
    ownerBody: document.body.getAttribute('data-adventure-shell-owner'),
    ownerDocument: document.documentElement.getAttribute('data-adventure-shell-owner'),
    globalNav: document.querySelectorAll('.cg-nav-links').length,
    e10HeaderVisible: document.querySelectorAll('[data-e10-backpack-only]:not([hidden])').length,
  }));
  await page.close();
  for (const state of [initial, reloaded]) {
    assert.equal(state.ownerBody, 'e10-backpack');
    assert.equal(state.ownerDocument, 'e10-backpack');
    assert.equal(state.globalNav, 0);
    assert.equal(state.e10HeaderVisible, 1);
    assert.equal(state.legacyHeaderVisible, 0);
    assert.equal(state.shellCount, 1);
  }
  assert.deepEqual(generic, {
    ownerBody: null,
    ownerDocument: null,
    globalNav: 1,
    e10HeaderVisible: 0,
  });
  return { initial, reloaded, generic };
}

const { server, origin } = await startServer();
const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
try {
  const battleEntry = await runBattleEntryOwnershipContract(browser);
  const inventoryRoute = await runCanonicalInventoryRouteContract(origin);
  const battle = await runBattleReloadContract(browser);
  const backpack = await runBackpackReloadContract(browser, origin);
  process.stdout.write(JSON.stringify({
    contract: 'e10-production-shell-context-recovery-v1',
    ok: true,
    battleEntry,
    inventoryRoute,
    battle,
    backpack,
  }, null, 2));
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
