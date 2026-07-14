import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const viewports = [
  [1440, 900],
  [1366, 768],
  [1280, 800],
  [1024, 768],
  [768, 1024],
  [640, 960],
  [480, 854],
  [320, 568]
];
const legacySelectors = [
  '#welcome-state > .guild-hall-hero',
  '#welcome-state > .guild-entry-grid',
  '#skill-map',
  '#welcome-state > .home-left-col',
  '#welcome-state > .home-report'
];
const e9Url = '/index.html?E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';
const offUrl = '/index.html';

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fssync.existsSync(candidate)) return candidate;
  }
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN to run the E9 layout browser contract.');
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
    '.woff2': 'font/woff2'
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
  return {
    server,
    origin: `http://127.0.0.1:${address.port}`
  };
}

function buildMockResponse(pathname, method) {
  if (pathname === '/api/auth/me') {
    return {
      logged_in: true,
      user_id: 42,
      username: 'layout_tester',
      nickname: 'Layout Tester',
      display_name: 'Grandmaster of Very Long Display Names 測試者超長名字',
      is_admin: false,
      is_premium: false,
      needs_onboarding_choice: false,
      tour_done: true,
      elo_rating: 1450,
      newbie_quest_eligible: false
    };
  }
  if (pathname === '/api/skills/profile') {
    return {
      display_name: 'Grandmaster of Very Long Display Names 測試者超長名字',
      rank_level: 'LV12'
    };
  }
  if (pathname === '/api/user/coins') return { coins: 123456 };
  if (pathname === '/api/adventure/bootstrap') {
    return {
      zones: [
        { key: 'forest', label: '森林', name: 'Ancient Forest of Endless Training', icon: 'forest', status: 'available', locked: false, can_enter: true, cleared: true, stars: 3, bossAvailable: false },
        { key: 'cave', label: '洞窟', name: 'Crystal Cave', icon: 'cave', status: 'available', locked: false, can_enter: true, cleared: false, stars: 1, bossAvailable: true },
        { key: 'lake', label: '湖泊', name: 'Mirror Lake of Reflection', icon: 'lake', status: 'available', locked: false, can_enter: true, cleared: false, stars: 0, bossAvailable: false },
        { key: 'tower', label: '高塔', name: 'Tower of Tactical Reading', icon: 'tower', status: 'locked', locked: true, can_enter: false, cleared: false, stars: 0, bossAvailable: false },
        { key: 'ruins', label: '遺跡', name: 'Sunken Ruins', icon: 'ruins', status: 'available', locked: false, can_enter: true, cleared: true, stars: 2, bossAvailable: false },
        { key: 'summit', label: '峰頂', name: 'Storm Summit', icon: 'summit', status: 'available', locked: false, can_enter: true, cleared: false, stars: 0, bossAvailable: true }
      ]
    };
  }
  if (pathname === '/api/daily-challenge/today') return { submitted: false };
  if (pathname === '/api/srs/due') return { count: 17, due: [] };
  if (pathname === '/api/mistakes/stats') return { total: 28, corrected: 9, worst5: [] };
  if (pathname === '/api/questions') return [];
  if (pathname === '/api/subscription/status') return { daily_limit: 20, remaining: 10 };
  if (pathname === '/api/analytics/events') return null;
  if (method === 'POST') return { ok: true };
  return { ok: true };
}

async function collectMetrics(page, state, viewport, origin, requestLog, screenshotDir) {
  const [width, height] = viewport;
  await page.setViewportSize({ width, height });
  await page.goto(origin + (state === 'on' ? e9Url : offUrl), { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelector('main')?.scrollTo(0, 0);
    document.querySelector('.practice')?.scrollTo(0, 0);
  });
  await page.waitForTimeout(1000);
  const metrics = await page.evaluate(({ legacySelectors }) => {
    const rect = (selector) => {
      const el = document.querySelector(selector);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        top: r.top,
        left: r.left,
        width: r.width,
        height: r.height,
        bottom: r.bottom,
        right: r.right,
        display: cs.display,
        position: cs.position
      };
    };
    const countFocusable = (roots) => {
      const selectors = ['a[href]', 'button:not([disabled])', '[tabindex]'];
      let count = 0;
      roots.forEach((selector) => {
        const root = document.querySelector(selector);
        if (!root) return;
        selectors.forEach((focusable) => {
          root.querySelectorAll(focusable).forEach((el) => {
            const cs = getComputedStyle(el);
            if (el.hidden) return;
            if (el.closest('[hidden],[aria-hidden=\"true\"],[inert]')) return;
            if (cs.display === 'none' || cs.visibility === 'hidden') return;
            if (typeof el.tabIndex === 'number' && el.tabIndex < 0) return;
            count += 1;
          });
        });
      });
      return count;
    };
    const shellFocusables = countFocusable(['#e9-adventure-shell']);
    const legacyFocusables = countFocusable(legacySelectors);
    return {
      activeShell: document.body.getAttribute('data-adventure-shell-active'),
      body: {
        scrollWidth: document.body.scrollWidth,
        scrollHeight: document.body.scrollHeight,
        clientWidth: document.body.clientWidth,
        clientHeight: document.body.clientHeight
      },
      doc: {
        scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight,
        clientWidth: document.documentElement.clientWidth,
        clientHeight: document.documentElement.clientHeight
      },
      overflowX: document.documentElement.scrollWidth - window.innerWidth,
      shell: rect('#e9-adventure-shell'),
      welcome: rect('#welcome-state'),
      topHud: rect('#top-hud'),
      leftNav: rect('#left-nav'),
      stage: rect('#adventure-stage'),
      cards: rect('#right-cards'),
      dock: rect('#bottom-dock'),
      shellFocusables,
      legacyFocusables
    };
  }, { legacySelectors });
  const fileBase = `${state}-${width}x${height}`;
  await page.screenshot({ path: path.join(screenshotDir, `${fileBase}.png`), fullPage: true });
  return {
    viewport: `${width}x${height}`,
    state,
    metrics,
    requests: {
      components: requestLog.filter((item) => item.startsWith('/components/adventure/')).length
    }
  };
}

function assertContracts(results) {
  const failures = [];
  const byState = {
    off: results.filter((item) => item.state === 'off'),
    on: results.filter((item) => item.state === 'on')
  };

  byState.off.forEach((result) => {
    const { viewport, metrics } = result;
    if (metrics.activeShell !== 'legacy') failures.push(`${viewport} OFF: active shell expected legacy, got ${metrics.activeShell}`);
    if ((metrics.shell?.height || 0) !== 0) failures.push(`${viewport} OFF: E9 shell should stay hidden`);
    if (result.requests.components !== 0) failures.push(`${viewport} OFF: expected 0 E9 fragment requests, got ${result.requests.components}`);
    if (metrics.shellFocusables !== 0) failures.push(`${viewport} OFF: expected 0 E9 focusables, got ${metrics.shellFocusables}`);
  });

  byState.on.forEach((result) => {
    const { viewport, metrics } = result;
    if (metrics.activeShell !== 'e9') failures.push(`${viewport} ON: active shell expected e9, got ${metrics.activeShell}`);
    if (!metrics.shell || metrics.shell.height <= 0) failures.push(`${viewport} ON: shell missing or zero height`);
    if (!metrics.stage || metrics.stage.width <= 0 || metrics.stage.height <= 0) failures.push(`${viewport} ON: world stage collapsed`);
    if (metrics.shell && metrics.shell.top < 0) failures.push(`${viewport} ON: shell top ${metrics.shell.top} is clipped above viewport`);
    if (metrics.overflowX > 0) failures.push(`${viewport} ON: horizontal overflow ${metrics.overflowX}`);
    if (metrics.legacyFocusables !== 0) failures.push(`${viewport} ON: legacy focusables should be 0, got ${metrics.legacyFocusables}`);
    if (metrics.dock && metrics.cards && metrics.dock.top + 1 < metrics.cards.bottom) {
      failures.push(`${viewport} ON: bottom dock overlaps cards/stage flow`);
    }
    if (parseInt(viewport.split('x')[0], 10) >= 1280) {
      if (!metrics.leftNav || metrics.leftNav.width < 200 || metrics.leftNav.width > 270) {
        failures.push(`${viewport} ON: desktop left-nav width out of contract`);
      }
    }
    if (parseInt(viewport.split('x')[0], 10) <= 1024) {
      if (!metrics.stage || !metrics.shell || metrics.stage.width + 1 < metrics.shell.width) {
        failures.push(`${viewport} ON: stacked stage should occupy the shell width`);
      }
    }
  });

  if (failures.length) {
    throw new Error(failures.join('\n'));
  }
}

async function main() {
  const args = process.argv.slice(2);
  const outIndex = args.indexOf('--out');
  const screenshotIndex = args.indexOf('--screens');
  const outFile = outIndex >= 0 ? path.resolve(args[outIndex + 1]) : null;
  const screenshotDir = screenshotIndex >= 0
    ? path.resolve(args[screenshotIndex + 1])
    : path.resolve(repoRoot, 'docs', 'testing', 'e9_1d2', 'screenshots');

  await fs.mkdir(screenshotDir, { recursive: true });
  if (outFile) await fs.mkdir(path.dirname(outFile), { recursive: true });

  const { server, origin } = await startStaticServer(repoRoot);
  const browser = await chromium.launch({
    headless: true,
    executablePath: findChrome()
  });
  const page = await browser.newPage();
  try {
    const results = [];
    for (const state of ['off', 'on']) {
      for (const viewport of viewports) {
        const requestLog = [];
        await page.unrouteAll({ behavior: 'ignoreErrors' }).catch(() => {});
        await page.route('**/*', async (route) => {
          const req = route.request();
          const pathname = new URL(req.url()).pathname;
          requestLog.push(pathname);
          if (pathname.startsWith('/api/')) {
            const payload = buildMockResponse(pathname, req.method());
            if (payload === null) {
              await route.fulfill({ status: 204, body: '' });
              return;
            }
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(payload)
            });
            return;
          }
          await route.continue();
        });
        results.push(await collectMetrics(page, state, viewport, origin, requestLog, screenshotDir));
      }
    }
    assertContracts(results);
    if (outFile) {
      await fs.writeFile(outFile, JSON.stringify(results, null, 2));
    }
    process.stdout.write(JSON.stringify({ ok: true, result_count: results.length, screenshot_dir: screenshotDir, out_file: outFile }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((err) => {
  console.error(err.stack || String(err));
  process.exitCode = 1;
});
