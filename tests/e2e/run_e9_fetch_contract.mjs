import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const outArgIndex = process.argv.indexOf('--out');
const outFile = outArgIndex >= 0 ? path.resolve(process.argv[outArgIndex + 1]) : null;
const e9Url = '/index.html?E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';
const targetEndpoints = [
  '/api/skills/profile',
  '/api/user/coins',
  '/api/adventure/bootstrap',
  '/api/daily-challenge/today',
  '/api/srs/due',
  '/api/mistakes/stats',
];

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fssync.existsSync(candidate)) return candidate;
  }
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN to run the E9 fetch contract.');
}

function contentTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[ext] || 'application/octet-stream';
}

async function startStaticServer(rootDir) {
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, 'http://127.0.0.1');
      let rel = decodeURIComponent(url.pathname);
      if (rel === '/') rel = '/index.html';
      const abs = path.resolve(rootDir, '.' + rel);
      if (!abs.startsWith(rootDir)) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      const stat = await fs.stat(abs).catch(() => null);
      if (!stat || !stat.isFile()) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      res.writeHead(200, { 'Content-Type': contentTypeFor(abs) });
      fssync.createReadStream(abs).pipe(res);
    } catch (err) {
      res.writeHead(500);
      res.end(String(err));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  return { server, origin: `http://127.0.0.1:${address.port}` };
}

function buildMockResponse(pathname) {
  if (pathname === '/api/auth/me') {
    return {
      logged_in: true,
      user_id: 42,
      username: 'fetch_tester',
      nickname: 'Fetch Tester',
      display_name: 'Fetch Tester',
      is_admin: false,
      is_premium: false,
      needs_onboarding_choice: false,
      tour_done: true,
      elo_rating: 1450,
      newbie_quest_eligible: false,
    };
  }
  if (pathname === '/api/questions') return [];
  if (pathname === '/api/subscription/status') return { daily_limit: 20, remaining: 10 };
  if (pathname === '/api/srs/all') return [];
  if (pathname === '/api/skills/profile') return { display_name: 'Fetch Tester', rank_level: 'LV12' };
  if (pathname === '/api/user/coins') return { coins: 123456 };
  if (pathname === '/api/adventure/bootstrap') {
    return {
      zones: [
        { key: 'forest', name: 'Forest', status: 'completed', stars: 3, boss: { available: false } },
        { key: 'cave', name: 'Cave', status: 'unlocked', stars: 1, boss: { available: true } },
        { key: 'lake', name: 'Lake', status: 'locked', stars: 0, boss: { available: false } },
      ],
    };
  }
  if (pathname === '/api/daily-challenge/today') return { user_submitted: false, user_correct: null };
  if (pathname === '/api/srs/due') return { count: 17, due: [] };
  if (pathname === '/api/mistakes/stats') return { total: 28, corrected: 9, worst5: [] };
  if (pathname === '/api/analytics/events') return null;
  return { ok: true };
}

function defaultBossFinishResponse() {
  return {
    ok: true,
    passed: true,
    cooldown_left: 30,
    zones: [
      {
        key: 'forest',
        name: 'Forest',
        status: 'completed',
        stars: 3,
        boss: { available: false },
      },
      {
        key: 'cave',
        name: 'Cave',
        status: 'completed',
        stars: 2,
        boss: { available: false },
      },
      {
        key: 'lake',
        name: 'Lake',
        status: 'unlocked',
        stars: 0,
        boss: { available: false },
      },
    ],
  };
}

async function installFetchTrace(page) {
  await page.addInitScript(() => {
    window.__E9_FETCH_TRACE__ = [];
    window.__E9_FETCH_SEQ__ = 0;
    const origFetch = window.fetch.bind(window);
    window.fetch = function tracedFetch(input, init) {
      const url = typeof input === 'string' ? input : input.url;
      const pathname = new URL(url, window.location.origin).pathname;
      const stack = new Error().stack || '';
      const lower = stack.toLowerCase();
      let initiator = 'unknown';
      if (lower.includes('top_hud')) initiator = 'top_hud';
      else if (lower.includes('right_cards')) initiator = 'right_cards';
      else if (lower.includes('world_stage')) initiator = 'world_stage';
      else if (lower.includes('player_state')) initiator = 'player_state';
      else if (lower.includes('activity_state')) initiator = 'activity_state';
      else if (lower.includes('adventure_state')) initiator = 'adventure_state';
      else if (lower.includes('srs.js')) initiator = 'legacy_srs';
      else if (lower.includes('index.html')) initiator = 'legacy_index';
      window.__E9_FETCH_TRACE__.push({
        order: ++window.__E9_FETCH_SEQ__,
        t: Number(performance.now().toFixed(3)),
        pathname,
        initiator,
        stack,
      });
      return origFetch(input, init);
    };
  });
}

async function createPage(browser, origin, scenario = {}) {
  const page = await browser.newPage();
  await installFetchTrace(page);
  const counters = new Map();
  await page.route('**/*', async (route) => {
    const req = route.request();
    const pathname = new URL(req.url()).pathname;
    const count = (counters.get(pathname) || 0) + 1;
    counters.set(pathname, count);

    if (pathname.startsWith('/api/')) {
      if (scenario.bossFinish && pathname === '/api/adventure/boss/finish') {
        await route.fulfill({
          status: scenario.bossFinish.status || 200,
          contentType: 'application/json',
          body: JSON.stringify(scenario.bossFinish.body || defaultBossFinishResponse()),
        });
        return;
      }
      if (scenario.apiFailure && pathname === scenario.apiFailure.path) {
        const limit = scenario.apiFailure.times || 1;
        if (count <= limit) {
          await route.fulfill({
            status: scenario.apiFailure.status || 500,
            contentType: 'application/json',
            body: JSON.stringify({ error: 'forced failure' }),
          });
          return;
        }
      }
      const payload = buildMockResponse(pathname);
      if (payload === null) {
        await route.fulfill({ status: 204, body: '' });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      });
      return;
    }
    await route.continue();
  });
  await page.goto(origin + e9Url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  return page;
}

async function resetTrace(page) {
  await page.evaluate(() => {
    window.__E9_FETCH_TRACE__ = [];
    window.__E9_FETCH_SEQ__ = 0;
  });
}

async function readTrace(page) {
  return page.evaluate(() => window.__E9_FETCH_TRACE__);
}

function summarize(trace) {
  const filtered = trace.filter((entry) => targetEndpoints.includes(entry.pathname));
  const byEndpoint = {};
  for (const endpoint of targetEndpoints) {
    const rows = filtered.filter((entry) => entry.pathname === endpoint);
    byEndpoint[endpoint] = {
      count: rows.length,
      initiators: rows.map((row) => row.initiator),
      order: rows.map((row) => row.order),
    };
  }
  return { filtered, byEndpoint };
}

function assertCounts(caseName, actual, expected) {
  const failures = [];
  for (const endpoint of targetEndpoints) {
    const got = actual[endpoint].count;
    const want = expected[endpoint];
    if (got !== want) failures.push(`${caseName}: ${endpoint} expected ${want}, got ${got}`);
  }
  if (failures.length) throw new Error(failures.join('\n'));
}

async function runCase(browser, origin, name, scenario, action, expected) {
  const page = await createPage(browser, origin, scenario);
  try {
    if (action !== 'after-load') {
      await resetTrace(page);
      await action(page);
      await page.waitForTimeout(700);
    }
    const trace = await readTrace(page);
    const summary = summarize(trace);
    assertCounts(name, summary.byEndpoint, expected);
    if (typeof scenario.verify === 'function') {
      await scenario.verify(page, summary, trace);
    }
    return { name, expected, actual: summary.byEndpoint, trace: summary.filtered };
  } finally {
    await page.close();
  }
}

async function main() {
  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  try {
    const report = { ok: true, cases: [] };

    report.cases.push(await runCase(browser, origin, 'single_activation_request_counts', {}, 'after-load', {
      '/api/skills/profile': 1,
      '/api/user/coins': 1,
      '/api/adventure/bootstrap': 1,
      '/api/daily-challenge/today': 1,
      '/api/srs/due': 1,
      '/api/mistakes/stats': 1,
    }));

    report.cases.push(await runCase(browser, origin, 'repeated_init_not_refetch', {}, async (page) => {
      await page.evaluate(() => { window.E9.initShell(); window.E9.initShell(); });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 0,
      '/api/mistakes/stats': 0,
    }));

    report.cases.push(await runCase(browser, origin, 'critical_fallback_restores_legacy_ambient', {
      verify: async (page) => {
        const shellState = await page.evaluate(() => ({
          activeShell: window.E9.getActiveShell(),
          shellAttr: document.body.getAttribute('data-adventure-shell-active'),
          legacySkillMapHidden: document.querySelector('#skill-map')?.hidden,
          e9ShellHidden: document.querySelector('#e9-adventure-shell')?.hidden,
        }));
        if (shellState.activeShell !== 'legacy' || shellState.shellAttr !== 'legacy') {
          throw new Error('critical_fallback_restores_legacy_ambient: legacy shell did not retake ownership');
        }
        if (shellState.legacySkillMapHidden !== false || shellState.e9ShellHidden !== true) {
          throw new Error('critical_fallback_restores_legacy_ambient: shell visibility did not switch to legacy');
        }
      },
    }, async (page) => {
      await page.evaluate(() => { window.E9.recoverToLegacy(new Error('synthetic fallback')); });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 1,
      '/api/mistakes/stats': 1,
    }));

    report.cases.push(await runCase(browser, origin, 'repeated_fallback_is_idempotent', {}, async (page) => {
      await page.evaluate(() => { window.E9.recoverToLegacy(new Error('synthetic fallback 1')); });
      await page.waitForTimeout(2500);
      await page.evaluate(() => { window.E9.recoverToLegacy(new Error('synthetic fallback 2')); });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 1,
      '/api/mistakes/stats': 1,
    }));

    report.cases.push(await runCase(browser, origin, 'language_switch_not_refetch', {}, async (page) => {
      await page.evaluate(() => { window.I18n.setLang(window.I18n.getLang() === 'en' ? 'zh' : 'en'); });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 0,
      '/api/mistakes/stats': 0,
    }));

    report.cases.push(await runCase(browser, origin, 'non_critical_failure_does_not_refetch_others', {
      apiFailure: { path: '/api/mistakes/stats', status: 500, times: 1 },
      verify: async (page) => {
        const activeShell = await page.evaluate(() => window.E9.getActiveShell());
        if (activeShell !== 'e9') {
          throw new Error('non_critical_failure_does_not_refetch_others: non-critical failure switched ownership away from E9');
        }
      },
    }, 'after-load', {
      '/api/skills/profile': 1,
      '/api/user/coins': 1,
      '/api/adventure/bootstrap': 1,
      '/api/daily-challenge/today': 1,
      '/api/srs/due': 1,
      '/api/mistakes/stats': 1,
    }));

    report.cases.push(await runCase(browser, origin, 'critical_world_stage_failure_retry_contract', {
      apiFailure: { path: '/api/adventure/bootstrap', status: 500, times: 2 },
    }, 'after-load', {
      '/api/skills/profile': 1,
      '/api/user/coins': 1,
      '/api/adventure/bootstrap': 2,
      '/api/daily-challenge/today': 1,
      '/api/srs/due': 2,
      '/api/mistakes/stats': 2,
    }));

    report.cases.push(await runCase(browser, origin, 'boss_finish_success_invalidates_cache_and_rededupes', {
      bossFinish: { status: 200, body: defaultBossFinishResponse() },
    }, async (page) => {
      await page.evaluate(async () => {
        await window.eval(`(async () => {
          _bossMode = true;
          _bossZone = { key: 'cave', name: 'Cave', nameEn: 'Cave' };
          _bossQueue = [101, 102];
          _bossCorrect = 2;
          await _finishBossBattle();
          await Promise.all([
            window.E9.Adapters.AdventureState.fetchAdventureState(),
            window.E9.Adapters.AdventureState.fetchAdventureState(),
          ]);
        })()`);
      });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 1,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 0,
      '/api/mistakes/stats': 0,
    }));

    report.cases.push(await runCase(browser, origin, 'boss_finish_failure_keeps_cached_adventure_state', {
      bossFinish: {
        status: 500,
        body: { ok: false, error: 'forced boss finish failure' },
      },
    }, async (page) => {
      await page.evaluate(async () => {
        await window.eval(`(async () => {
          _bossMode = true;
          _bossZone = { key: 'cave', name: 'Cave', nameEn: 'Cave' };
          _bossQueue = [201, 202];
          _bossCorrect = 1;
          await _finishBossBattle();
          await window.E9.Adapters.AdventureState.fetchAdventureState();
        })()`);
      });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 0,
      '/api/mistakes/stats': 0,
    }));

    report.cases.push(await runCase(browser, origin, 'resize_not_refetch', {}, async (page) => {
      await page.setViewportSize({ width: 768, height: 1024 });
      await page.setViewportSize({ width: 1440, height: 900 });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 0,
      '/api/mistakes/stats': 0,
    }));

    report.cases.push(await runCase(browser, origin, 'history_back_not_refetch', {}, async (page) => {
      await page.evaluate(() => {
        history.pushState({ test: 1 }, '', location.pathname + location.search + '&trace_nav=1');
        history.back();
      });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 0,
      '/api/mistakes/stats': 0,
    }));

    report.cases.push(await runCase(browser, origin, 'repeated_component_loaded_event_not_refetch', {}, async (page) => {
      await page.evaluate(() => {
        [
          ['top_hud', '#e9-top-hud-slot'],
          ['right_cards', '#e9-right-cards-slot'],
          ['world_stage', '#e9-world-stage-slot'],
        ].forEach(([component, selector]) => {
          const root = document.querySelector(selector);
          if (root) {
            root.dispatchEvent(new CustomEvent('e9:component-loaded', { bubbles: true, detail: { component, root } }));
          }
        });
      });
    }, {
      '/api/skills/profile': 0,
      '/api/user/coins': 0,
      '/api/adventure/bootstrap': 0,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 0,
      '/api/mistakes/stats': 0,
    }));

    report.cases.push(await runCase(browser, origin, 'legacy_off_state_zero_e9_requests', {}, async (page) => {
      await page.goto(origin + '/index.html', { waitUntil: 'networkidle' });
      await page.waitForTimeout(700);
    }, {
      '/api/skills/profile': 1,
      '/api/user/coins': 1,
      '/api/adventure/bootstrap': 1,
      '/api/daily-challenge/today': 0,
      '/api/srs/due': 1,
      '/api/mistakes/stats': 1,
    }));

    const legacyOff = report.cases[report.cases.length - 1];
    const legacyOffE9Owned = legacyOff.trace.filter((row) => (
      row.initiator === 'top_hud' ||
      row.initiator === 'right_cards' ||
      row.initiator === 'world_stage' ||
      row.initiator === 'player_state' ||
      row.initiator === 'activity_state' ||
      row.initiator === 'adventure_state'
    ));
    if (legacyOffE9Owned.length) {
      throw new Error('legacy_off_state_zero_e9_requests: expected 0 E9-owned requests, got ' + legacyOffE9Owned.length);
    }

    if (outFile) {
      await fs.mkdir(path.dirname(outFile), { recursive: true });
      await fs.writeFile(outFile, JSON.stringify(report, null, 2));
    }
    process.stdout.write(JSON.stringify({ ok: true, case_count: report.cases.length, out_file: outFile }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((err) => {
  console.error(err.stack || String(err));
  process.exit(1);
});
