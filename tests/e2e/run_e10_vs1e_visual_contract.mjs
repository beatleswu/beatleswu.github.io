import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const shellFlags = 'E9_DEBUG=1&e9Shell=1&e9TopHud=1&e9LeftNav=1&e9RightCards=1&e9BottomDock=1&e9WorldStage=1';

const zones = [
  ['k26_30', '圍棋新手村', 'Beginner Village', 'completed', false, true, 3, 30, 30],
  ['k21_25', '史萊姆平原', 'Slime Plains', 'unlocked', false, false, 1, 18, 25],
  ['k16_20', '哥布林洞穴', 'Goblin Cave', 'unlocked', false, false, 0, 12, 20],
  ['k11_15', '迷霧森林', 'Misty Forest', 'locked', true, false, 0, 0, 20],
  ['k6_10', '獸人部落', 'Orc Tribe', 'locked', true, false, 0, 0, 20],
  ['k1_5', '龍之谷', 'Dragon Valley', 'unlocked', false, false, 0, 8, 20],
  ['d1_2', '賢者之塔', 'Sage Tower', 'locked', true, false, 0, 0, 20],
  ['d3_4', '魔王城前線', 'Demon Castle Front', 'locked', true, false, 0, 0, 20],
  ['d5_6', '諸神黃昏', 'Ragnarök', 'locked', true, false, 0, 0, 20],
  ['d7_plus', '上古終焉神殿', 'Ancient Doom Temple', 'locked', true, false, 0, 0, 20],
].map(([key, name, name_en, status, locked, cleared, stars, seen, total]) => ({
  key,
  label: name,
  name,
  name_en,
  icon: 'zone',
  status,
  locked,
  can_enter: !locked,
  cleared,
  completed: cleared,
  stars,
  seen,
  total,
  boss: { available: !locked && !cleared },
  skipped_by_placement: status === 'skipped_by_placement',
}));

function fixtureZones(mode = 'default') {
  if (mode !== 'placement-high') return zones;
  return zones.map((zone, index) => ({
    ...zone,
    status: index < 5 ? 'skipped_by_placement' : (index === 5 ? 'unlocked' : 'locked'),
    locked: index > 5,
    can_enter: index <= 5,
    cleared: false,
    completed: false,
    skipped_by_placement: index < 5,
    stars: 0,
    boss: { available: index === 5 },
  }));
}

function findChrome() {
  const candidates = [
    process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  ].filter(Boolean);
  const executable = candidates.find((candidate) => fssync.existsSync(candidate));
  if (!executable) throw new Error('No Chrome/Edge executable found.');
  return executable;
}

function contentTypeFor(filePath) {
  return ({
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

const staticContractMarker = '<meta name="go-odyssey-static-contract" content="e10-vs1f-integrated-world-map">';

const runnerInstrumentation = {
  nextPageId: 1,
  pages: [],
  servers: [],
};

function observedAt() {
  return new Date().toISOString();
}

function safeFrameUrl(value) {
  try {
    const frame = typeof value.frame === 'function' ? value.frame() : null;
    return frame ? frame.url() : null;
  } catch {
    return null;
  }
}

function safePageUrl(page) {
  try {
    return page.url();
  } catch {
    return null;
  }
}

function safeFromServiceWorker(response) {
  try {
    return typeof response.fromServiceWorker === 'function'
      ? response.fromServiceWorker()
      : null;
  } catch {
    return null;
  }
}

function recordEvent(collection, kind, payload = {}) {
  collection.push({ kind, timestamp: observedAt(), ...payload });
}

function labelPageDiagnostics(page, label) {
  if (page.__e10RunnerDiagnostics) page.__e10RunnerDiagnostics.label = label;
}

async function installPageDiagnostics(page, browserErrors) {
  const diagnostics = {
    page_id: `page-${runnerInstrumentation.nextPageId}`,
    label: null,
    created_at: observedAt(),
    initial_url: page.url(),
    viewport: typeof page.viewportSize === 'function' ? page.viewportSize() : null,
    events: [],
    cdp_events: [],
    browser_events: [],
    instrumentation_errors: [],
  };
  runnerInstrumentation.nextPageId += 1;
  runnerInstrumentation.pages.push(diagnostics);
  page.__e10RunnerDiagnostics = diagnostics;

  page.on('request', (request) => recordEvent(diagnostics.events, 'request', {
    url: request.url(),
    method: request.method(),
    resource_type: request.resourceType(),
    frame: safeFrameUrl(request),
  }));
  page.on('response', (response) => recordEvent(diagnostics.events, 'response', {
    url: response.url(),
    method: response.request().method(),
    resource_type: response.request().resourceType(),
    status: response.status(),
    status_text: response.statusText(),
    frame: safeFrameUrl(response),
    from_service_worker: safeFromServiceWorker(response),
  }));
  page.on('requestfinished', (request) => recordEvent(diagnostics.events, 'requestfinished', {
    url: request.url(),
    method: request.method(),
    resource_type: request.resourceType(),
    frame: safeFrameUrl(request),
  }));
  page.on('requestfailed', (request) => {
    const failure = request.failure();
    recordEvent(diagnostics.events, 'requestfailed', {
      url: request.url(),
      method: request.method(),
      resource_type: request.resourceType(),
      failure_text: failure?.errorText || null,
      frame: safeFrameUrl(request),
      page_url: safePageUrl(page),
      viewport: diagnostics.viewport,
    });
    browserErrors.push({ kind: 'requestfailed', text: `${request.method()} ${request.url()}` });
  });
  page.on('console', (message) => {
    const location = typeof message.location === 'function' ? message.location() : null;
    recordEvent(diagnostics.browser_events, 'console', {
      type: message.type(),
      text: message.text(),
      location,
    });
    if (message.type() === 'error') browserErrors.push({ kind: 'console', text: message.text() });
  });
  page.on('pageerror', (error) => {
    const text = error && error.stack ? error.stack : String(error);
    recordEvent(diagnostics.browser_events, 'pageerror', { text });
    browserErrors.push({ kind: 'pageerror', text });
  });
  page.on('crash', () => recordEvent(diagnostics.browser_events, 'crash'));
  page.on('close', () => recordEvent(diagnostics.browser_events, 'close', { url: page.url() }));

  try {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send('Network.enable');
    diagnostics.cdp_network_enabled = true;
    cdp.on('Network.requestWillBeSent', (event) => recordEvent(diagnostics.cdp_events, 'Network.requestWillBeSent', {
      request_id: event.requestId,
      url: event.request?.url,
      method: event.request?.method,
      type: event.type,
      cdp_timestamp: event.timestamp,
    }));
    cdp.on('Network.responseReceived', (event) => recordEvent(diagnostics.cdp_events, 'Network.responseReceived', {
      request_id: event.requestId,
      url: event.response?.url,
      status: event.response?.status,
      mime_type: event.response?.mimeType,
      from_service_worker: event.response?.fromServiceWorker,
      type: event.type,
      cdp_timestamp: event.timestamp,
    }));
    cdp.on('Network.loadingFinished', (event) => recordEvent(diagnostics.cdp_events, 'Network.loadingFinished', {
      request_id: event.requestId,
      encoded_data_length: event.encodedDataLength,
      cdp_timestamp: event.timestamp,
    }));
    cdp.on('Network.loadingFailed', (event) => recordEvent(diagnostics.cdp_events, 'Network.loadingFailed', {
      request_id: event.requestId,
      error_text: event.errorText,
      blocked_reason: event.blockedReason || null,
      canceled: Boolean(event.canceled),
      type: event.type,
      cdp_timestamp: event.timestamp,
      page_url: safePageUrl(page),
      viewport: diagnostics.viewport,
    }));
  } catch (error) {
    diagnostics.instrumentation_errors.push({
      kind: 'cdp_setup',
      timestamp: observedAt(),
      text: error.stack || String(error),
    });
  }

  return diagnostics;
}

async function startStaticServer({ contractCase = 'target' } = {}) {
  const serverDiagnostics = {
    server_id: `server-${runnerInstrumentation.servers.length + 1}`,
    contract_case: contractCase,
    created_at: observedAt(),
    events: [],
  };
  runnerInstrumentation.servers.push(serverDiagnostics);
  const server = http.createServer(async (request, response) => {
    const requestId = `${serverDiagnostics.server_id}-request-${serverDiagnostics.events.filter((event) => event.kind === 'request').length + 1}`;
    recordEvent(serverDiagnostics.events, 'request', {
      request_id: requestId,
      method: request.method,
      url: request.url,
    });
    response.on('finish', () => recordEvent(serverDiagnostics.events, 'response_finished', {
      request_id: requestId,
      status: response.statusCode,
    }));
    response.on('close', () => recordEvent(serverDiagnostics.events, 'response_closed', {
      request_id: requestId,
      status: response.statusCode,
    }));
    response.on('error', (error) => recordEvent(serverDiagnostics.events, 'response_error', {
      request_id: requestId,
      text: error.stack || String(error),
    }));
    const recordResponseCreated = (status, headers = {}, relativePath = null) => {
      recordEvent(serverDiagnostics.events, 'response_created', {
        request_id: requestId,
        status,
        relative_path: relativePath,
        content_type: headers['Content-Type'] || headers['content-type'] || null,
      });
    };
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      const relative = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
      const absolute = path.resolve(repoRoot, `.${relative}`);
      if (!absolute.startsWith(repoRoot)) throw new Error('path outside repository');
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) {
        response.writeHead(404);
        recordResponseCreated(404, {}, relative);
        response.end('not found');
        return;
      }
      if (relative === '/index.html' && contractCase !== 'target') {
        let html = await fs.readFile(absolute, 'utf8');
        if (contractCase === 'missing') {
          html = html.replace(staticContractMarker, '');
        } else if (contractCase === 'wrong') {
          html = html.replace(
            staticContractMarker,
            '<meta name="go-odyssey-static-contract" content="unexpected-static-contract">'
          );
        } else if (contractCase === 'current-v209') {
          html = html.replace(
            staticContractMarker,
            '<meta name="go-odyssey-static-contract" content="v209-e10-world-stage-v1d1-i18n-a11y">'
          );
        } else {
          throw new Error(`unknown contract case: ${contractCase}`);
        }
        const headers = { 'Content-Type': 'text/html; charset=utf-8' };
        response.writeHead(200, headers);
        recordResponseCreated(200, headers, relative);
        response.end(html);
        return;
      }
      const headers = { 'Content-Type': contentTypeFor(absolute) };
      response.writeHead(200, headers);
      recordResponseCreated(200, headers, relative);
      fssync.createReadStream(absolute).pipe(response);
    } catch (error) {
      response.writeHead(500);
      recordResponseCreated(500, {}, null);
      response.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  serverDiagnostics.listening_at = observedAt();
  serverDiagnostics.origin = `http://127.0.0.1:${server.address().port}`;
  return { server, origin: serverDiagnostics.origin };
}

async function runCompatibilityFallbackCase(browser, origin, contractCase, outputDir) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  labelPageDiagnostics(page, `compatibility-${contractCase}`);
  await page.addInitScript((contract) => {
    localStorage.setItem('go-odyssey-static-contract', contract);
    localStorage.setItem('e10-vs1e', 'immersive-rpg');
  }, 'e10-vs1f-integrated-world-map');
  await page.goto(
    `${origin}/index.html?lang=en&${shellFlags}`
      + '&go-odyssey-static-contract=e10-vs1f-integrated-world-map'
      + '&staticContract=e10-vs1f-integrated-world-map'
      + '&host=godokoro.com',
    { waitUntil: 'networkidle' }
  );
  await page.locator('#e9-world-stage-zones [data-zone="k26_30"]').waitFor({ state: 'visible' });
  const snapshot = await page.evaluate(() => ({
    activeShell: document.body.getAttribute('data-adventure-shell-active'),
    bodySkin: document.body.getAttribute('data-e10-visual-skin'),
    bodyArtKit: document.body.getAttribute('data-e10-art-kit'),
    shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
    shellArtKit: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-art-kit'),
    nodeCount: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
    plaqueCount: document.querySelectorAll('#e9-world-stage-zones .e9-zone__plaque').length,
    selectedCount: document.querySelectorAll('#e9-world-stage-zones .is-selected').length,
    primaryCtaHidden: document.querySelector('#e9-world-stage-primary-cta')?.hidden,
    statusParent: document.querySelector('#e9-world-stage-status')?.parentElement?.id,
    stateCopyHidden: document.querySelector('#e9-world-stage-details-state')?.hidden,
    progressCopyHidden: document.querySelector('#e9-world-stage-details-progress')?.hidden,
    routePathCount: document.querySelectorAll('.e9-map-stage__route path').length,
    routeMaterialCount: document.querySelectorAll('.e9-route__material, [data-e10-vs1f-route-layer]').length,
    routeFilledCount: [...document.querySelectorAll('.e9-map-stage__route path')]
      .filter((path) => getComputedStyle(path).fill !== 'none').length,
    landmarkCount: document.querySelectorAll('.e10-zone-landmark').length,
    v2CleanMapCount: performance.getEntriesByType('resource')
      .filter((entry) => entry.name.includes('/assets/maps/e10_world_stage_v2_clean.webp')).length,
    vs1fPlayerCount: document.querySelectorAll('[data-player-location], .e10-current-hero').length,
    vs1fIconCount: document.querySelectorAll('[data-e10-vs1f-icon], .e9-dock__icon').length,
    vs1fAvatarCount: document.querySelectorAll('#top-hud-avatar-image').length,
    artAssetNodeCount: document.querySelectorAll('[data-e10-art-asset], img[src*="/assets/e10/ui/"]').length,
    artAssetRequestCount: performance.getEntriesByType('resource')
      .filter((entry) => entry.name.includes('/assets/e10/ui/')).length,
    nav32Count: document.querySelectorAll('.e9-nav__icon[viewBox="0 0 32 32"]').length,
    oversizedBlackSvgCount: [...document.querySelectorAll('svg path, svg polygon')]
      .filter((shape) => {
        const style = getComputedStyle(shape);
        const box = shape.getBoundingClientRect();
        return style.fill === 'rgb(0, 0, 0)' && box.width * box.height > 4096;
       }).length,
    legacyNavCount: document.querySelectorAll('.cg-nav-link[data-nav-key]').length,
    sessionControls: {
      presence: !!document.querySelector('#cg-presence-chip'),
      language: !!document.querySelector('.cg-nav-lang'),
      logout: !!document.querySelector('.cg-nav-logout'),
    },
  }));
  const screenshot = await saveViewportScreenshot(
    page,
    outputDir,
    `compatibility-${contractCase}-vs1d-fallback-1440x900-en.png`
  );
  await page.close();
  const failures = [];
  if (snapshot.activeShell !== 'e9') failures.push(`${contractCase}: E9 shell did not mount`);
  if (
    snapshot.bodySkin !== null || snapshot.shellSkin !== null
    || snapshot.bodyArtKit !== null || snapshot.shellArtKit !== null
  ) {
    failures.push(`${contractCase}: VS1E skin was enabled without the exact static marker`);
  }
  if (snapshot.nodeCount !== 10) failures.push(`${contractCase}: VS1D node rendering is incomplete`);
  // Authority hydration may preserve one generic Legacy selected tile.  The
  // fallback contract is about preventing E10-owned surfaces from leaking,
  // while duplicate selection remains invalid.
  if (snapshot.plaqueCount !== 0 || snapshot.selectedCount > 1 || !snapshot.primaryCtaHidden) {
    failures.push(`${contractCase}: VS1E on-map UI leaked into the VS1D fallback`);
  }
  if (
    snapshot.statusParent !== 'adventure-stage'
    || !snapshot.stateCopyHidden
    || !snapshot.progressCopyHidden
  ) failures.push(`${contractCase}: VS1D DOM contract was not restored`);
  if (
    snapshot.routePathCount !== 4
    || snapshot.routeMaterialCount !== 0
    || snapshot.routeFilledCount !== 0
    || snapshot.landmarkCount !== 0
    || snapshot.v2CleanMapCount !== 0
    || snapshot.vs1fPlayerCount !== 0
    || snapshot.vs1fIconCount !== 0
    || snapshot.vs1fAvatarCount !== 0
    || snapshot.artAssetNodeCount !== 0
    || snapshot.artAssetRequestCount !== 0
    || snapshot.nav32Count !== 0
    || snapshot.oversizedBlackSvgCount !== 0
  ) failures.push(`${contractCase}: VS1F SVG/mask/landmark DOM leaked into fallback`);
  if (snapshot.legacyNavCount !== 10) failures.push(`${contractCase}: Legacy header navigation was not preserved`);
  if (!Object.values(snapshot.sessionControls).every(Boolean)) failures.push(`${contractCase}: session controls are incomplete`);
  if (browserErrors.length) failures.push(`${contractCase}: browser errors ${JSON.stringify(browserErrors)}`);
  return { contractCase, screenshot, snapshot, browserErrors, failures };
}

function apiResponse(pathname, method, avatarKey = 'mage', fixtureMode = 'default', playerName = '晨星騎士') {
  if (pathname === '/api/auth/me') {
    return {
      logged_in: true,
      user_id: 42,
      username: 'visual_fixture',
      nickname: playerName,
      display_name: playerName,
      is_admin: false,
      is_premium: false,
      needs_onboarding_choice: false,
      tour_done: true,
      elo_rating: 1450,
      newbie_quest_eligible: false,
    };
  }
  if (pathname === '/api/skills/profile') return { display_name: playerName, rank_level: 'LV12' };
  if (pathname === '/api/user/coins') return { coins: 123456 };
  if (pathname === '/api/player/appearance') return { character_key: avatarKey };
  if (pathname === '/api/adventure/bootstrap') {
    const responseZones = fixtureZones(fixtureMode);
    const current = responseZones.find((zone) => zone.status === 'unlocked');
    return {
      zones: responseZones,
      placement: fixtureMode === 'placement-high' ? { effective_start_zone_key: 'k1_5' } : null,
      recommended: current ? { zone_key: current.key } : null,
      selected: current ? { zone_key: current.key } : null,
      // Mirror the server-owned progression authority: this is the first
      // canonical playable incomplete node for the fixture, not a selected
      // display zone.
      current_zone_key: current ? current.key : null,
      primary_action: current
        ? {
          kind: 'challenge_lord',
          zone_key: current.key,
          boss_key: {
            k21_25: 'swarm_lord',
            k1_5: 'grand_temple_knight',
          }[current.key] || null,
        }
        : null,
    };
  }
  if (pathname === '/api/daily-challenge/today') return { submitted: false };
  if (pathname === '/api/srs/due') return { count: 17, due: [] };
  if (pathname === '/api/srs/all') return [];
  if (pathname === '/api/badges/definitions' || pathname === '/api/badges/earned') return [];
  if (pathname === '/api/mistakes/stats') return { total: 28, corrected: 9, worst5: [] };
  if (pathname === '/api/questions') return [];
  if (pathname === '/api/subscription/status') return { daily_limit: 20, remaining: 10 };
  if (pathname === '/api/analytics/events' || method === 'POST') return null;
  return { ok: true };
}

async function installApiFixture(
  page,
  browserErrors,
  avatarKey = 'mage',
  fixtureMode = 'default',
  playerName = '晨星騎士'
) {
  await installPageDiagnostics(page, browserErrors);
  page.on('response', (response) => {
    if (response.status() >= 500) {
      browserErrors.push({ kind: 'http5xx', text: `${response.status()} ${response.url()}` });
    }
  });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const payload = apiResponse(
      new URL(request.url()).pathname,
      request.method(),
      avatarKey,
      fixtureMode,
      playerName
    );
    await route.fulfill(payload === null
      ? { status: 204, body: '' }
      : { status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
}

async function waitForShell(page) {
  await page.locator('#e9-adventure-shell[data-e10-visual-skin="immersive-rpg"]').waitFor({ state: 'visible' });
  await page.locator('#e9-world-stage-zones [data-zone="k26_30"]').waitFor({ state: 'visible' });
  const count = await page.locator('#e9-world-stage-zones [data-zone]').count();
  if (count !== 10) throw new Error(`expected 10 World Stage nodes, got ${count}`);
}

async function runtimeSnapshot(page) {
  return page.evaluate(() => {
    const isVisible = (element) => {
      if (!element || element.hidden) return false;
      const style = getComputedStyle(element);
      const box = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden'
        && box.width > 0 && box.height > 0;
    };
    const roundRect = (value) => value && Object.fromEntries(
      ['x', 'y', 'width', 'height', 'top', 'right', 'bottom', 'left']
        .map((key) => [key, Math.round(value[key] * 100) / 100])
    );
    const rect = (selector) => {
      const element = document.querySelector(selector);
      return element ? element.getBoundingClientRect().toJSON() : null;
    };
    const allTargets = Array.from(document.querySelectorAll(
      '#e9-adventure-shell a[href], #e9-adventure-shell button:not([disabled])'
    )).filter((element) => {
      const style = getComputedStyle(element);
      const target = element.getBoundingClientRect();
      return !element.hidden && style.display !== 'none' && style.visibility !== 'hidden'
        && target.width > 0 && target.height > 0;
    });
    const duplicateIds = Array.from(document.querySelectorAll('[id]'))
      .map((element) => element.id)
      .filter((id, index, ids) => ids.indexOf(id) !== index);
    const navItems = Array.from(document.querySelectorAll('.e9-nav__item'))
      .filter((element) => {
        const box = element.getBoundingClientRect();
        return box.width > 0 && box.height > 0;
      });
    const visibleNavigationControls = Array.from(document.querySelectorAll(
      '#e9-adventure-shell [data-e10-nav-key], #e9-adventure-shell [data-e10-vs1f-nav="more"]'
    )).filter(isVisible);
    const navItemRects = navItems.map((element) => element.getBoundingClientRect());
    const zoneRects = Array.from(document.querySelectorAll('#e9-world-stage-zones [data-zone]'))
      .map((element) => element.getBoundingClientRect());
    const overlapCount = (rects) => rects.reduce((count, current, index) => (
      count + rects.slice(index + 1).filter((other) => (
        current.left < other.right
        && current.right > other.left
        && current.top < other.bottom
        && current.bottom > other.top
      )).length
    ), 0);
    const labelWrapCount = navItems.filter((item) => {
      const label = item.querySelector('span');
      if (!label) return false;
      const style = getComputedStyle(label);
      const lineHeight = Number.parseFloat(style.lineHeight);
      return style.whiteSpace !== 'nowrap'
        || (Number.isFinite(lineHeight) && label.getBoundingClientRect().height > lineHeight * 1.25);
    }).length;
    const labelOverTwoLineCount = navItems.filter((item) => {
      const label = item.querySelector('span');
      if (!label) return false;
      const lineHeight = Number.parseFloat(getComputedStyle(label).lineHeight);
      return Number.isFinite(lineHeight) && label.getBoundingClientRect().height > lineHeight * 2.25;
    }).length;
    const map = document.querySelector('#e9-map-stage')?.getBoundingClientRect();
    const lastZone = zoneRects.at(-1);
    const nav = document.querySelector('#left-nav')?.getBoundingClientRect();
    const intersects = (a, b) => !!(a && b && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top);
    const rectFromEdges = (left, top, right, bottom) => ({
      x: left, y: top, width: right - left, height: bottom - top,
      left, top, right, bottom,
    });
    const routeSegments = Array.from(document.querySelectorAll('[data-e10-route-from][data-e10-route-to]'));
    const worldState = window.E9?.latestZoneSelection || {};
    const playerIdentity = document.querySelector('.e9-hud__player');
    const playerAvatar = document.querySelector('.e9-hud__avatar');
    const playerName = document.querySelector('.e9-hud__name');
    const playerLevel = document.querySelector('.e9-hud__level');
    const playerDropdown = document.querySelector('.e10-player-menu-arrow');
    const playerNameBox = playerName?.getBoundingClientRect();
    const playerLevelBox = playerLevel?.getBoundingClientRect();
    const playerContentBox = playerNameBox && playerLevelBox
      ? rectFromEdges(
        Math.min(playerNameBox.left, playerLevelBox.left),
        Math.min(playerNameBox.top, playerLevelBox.top),
        Math.max(playerNameBox.right, playerLevelBox.right),
        Math.max(playerNameBox.bottom, playerLevelBox.bottom)
      )
      : null;
    const dock = document.querySelector('.e9-dock');
    const dockParent = dock?.parentElement;
    const dockStyle = dock ? getComputedStyle(dock) : null;
    const dockBefore = dock ? getComputedStyle(dock, '::before') : null;
    const dockAfter = dock ? getComputedStyle(dock, '::after') : null;
    const dockBox = dock?.getBoundingClientRect() || null;
    const dockItems = dock ? Array.from(dock.querySelectorAll('.e9-dock__item')) : [];
    const dockSlotCenterFractions = [260, 450, 640, 830, 1020].map((value) => value / 1280);
    const dockGeometryItems = dockBox ? dockItems.map((item, index) => {
      const badge = item.querySelector('.e9-dock__icon')?.getBoundingClientRect();
      const label = item.querySelector(':scope > span')?.getBoundingClientRect();
      const badgeCenterX = badge ? badge.left + badge.width / 2 : null;
      const badgeCenterY = badge ? badge.top + badge.height / 2 : null;
      const slotCenterX = dockBox.left + dockBox.width * dockSlotCenterFractions[index];
      const slotCenterY = dockBox.top + dockBox.height / 2;
      const labelCenterX = label ? label.left + label.width / 2 : null;
      return {
        key: item.getAttribute('data-e10-nav-key'),
        label: item.querySelector(':scope > span')?.textContent.trim() || '',
        badge_center_x: badgeCenterX,
        badge_center_y: badgeCenterY,
        slot_center_x: slotCenterX,
        slot_center_y: slotCenterY,
        label_center_x: labelCenterX,
        badge_slot_delta_x: badgeCenterX === null ? null : badgeCenterX - slotCenterX,
        badge_slot_delta_y: badgeCenterY === null ? null : badgeCenterY - slotCenterY,
        label_badge_delta_x: labelCenterX === null || badgeCenterX === null ? null : labelCenterX - badgeCenterX,
      };
    }) : [];
    const roundDockValue = (value) => value === null ? null : Math.round(value * 100) / 100;
    const dockBadgeCentersY = dockGeometryItems.map((item) => item.badge_center_y).filter(Number.isFinite);
    const dockSlotCentersX = dockGeometryItems.map((item) => item.slot_center_x).filter(Number.isFinite);
    const dockSlotSpacings = dockSlotCentersX.slice(1).map((value, index) => value - dockSlotCentersX[index]);
    const currentZone = document.querySelector('[data-player-location="true"]');
    const marker = [
      document.querySelector('#e9-world-stage-player'),
      ...document.querySelectorAll('.e10-current-hero'),
    ].find(isVisible) || null;
    const currentNodeBox = currentZone?.getBoundingClientRect();
    const markerBox = marker?.getBoundingClientRect();
    const currentPlaqueBox = currentZone?.querySelector('.e9-zone__plaque')?.getBoundingClientRect();
    const markerUnion = currentNodeBox && markerBox
      ? rectFromEdges(
        Math.min(currentNodeBox.left, markerBox.left),
        Math.min(currentNodeBox.top, markerBox.top),
        Math.max(currentNodeBox.right, markerBox.right),
        Math.max(currentNodeBox.bottom, markerBox.bottom)
      )
      : null;
    const markerLabelGap = markerUnion && currentPlaqueBox
      ? Math.max(
        0,
        currentPlaqueBox.left - markerUnion.right,
        markerUnion.left - currentPlaqueBox.right,
        currentPlaqueBox.top - markerUnion.bottom,
        markerUnion.top - currentPlaqueBox.bottom
      )
      : null;
    const panelNumber = document.querySelector('[data-e10-zone-number]')?.getBoundingClientRect();
    const panelState = document.querySelector('#e10-drawer-zone-state')?.getBoundingClientRect();
    const panelBody = document.querySelector('#e10-drawer-zone-body')?.getBoundingClientRect();
    const viewportBottomElement = document.elementFromPoint(window.innerWidth / 2, window.innerHeight - 2);
    const viewportBottomStyle = viewportBottomElement ? getComputedStyle(viewportBottomElement) : null;
    const targetMeasurements = allTargets.map((element) => {
      const target = element.getBoundingClientRect();
      return {
        element,
        width: target.width,
        height: target.height,
        minimum: Math.min(target.width, target.height),
      };
    });
    const minimumTargetElement = targetMeasurements.reduce((smallest, candidate) => (
      !smallest || candidate.minimum < smallest.minimum ? candidate : smallest
    ), null);
    return {
      activeShell: document.body.getAttribute('data-adventure-shell-active'),
      skin: document.body.getAttribute('data-e10-visual-skin'),
      artKit: document.body.getAttribute('data-e10-art-kit'),
      shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
      shellArtKit: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-art-kit'),
      lang: window.I18n?.getLang?.(),
      nodeCount: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
      landmarkCount: document.querySelectorAll('#e9-world-stage-zones .e10-zone-landmark').length,
      drawerLandmarkVisible: isVisible(document.querySelector('#e10-drawer-zone-landmark')),
      portraitLandmarkVisible: isVisible(document.querySelector('#e9-world-stage-details-landmark')),
      playerLocationCount: document.querySelectorAll('#e9-world-stage-zones [data-player-location="true"]').length,
      playerLocationZone: document.querySelector('#e9-world-stage-zones [data-player-location="true"]')?.getAttribute('data-zone'),
      selectedZone: document.querySelector('#e9-world-stage-zones .is-selected')?.getAttribute('data-zone'),
      zoneIdentities: {
        currentPlayerZoneKey: worldState.currentPlayerZoneKey || null,
        selectedZoneKey: worldState.selectedZoneKey || null,
        challengeTargetZoneKey: worldState.challengeTargetZoneKey || null,
      },
      visibleHeroCount: [
        document.querySelector('#e9-world-stage-player'),
        ...document.querySelectorAll('.e10-current-hero'),
      ].filter(isVisible).length,
      landmarkRequestCount: performance.getEntriesByType('resource')
        .filter((entry) => entry.name.includes('/assets/maps/e10-vs1f-landmarks/')).length,
      landmarkRequestUrls: [...new Set(performance.getEntriesByType('resource')
        .filter((entry) => entry.name.includes('/assets/maps/e10-vs1f-landmarks/'))
        .map((entry) => new URL(entry.name).pathname))],
      legacyVisible: Array.from(document.querySelectorAll(
        '#welcome-state > .guild-hall-hero, #welcome-state > .guild-entry-grid, #skill-map, #welcome-state > .home-left-col, #welcome-state > .home-report'
      )).some((element) => !element.hidden),
      map: roundRect(rect('#e9-map-stage')),
      shell: roundRect(rect('#e9-adventure-shell')),
      stage: roundRect(rect('#adventure-stage')),
      nav: roundRect(rect('#left-nav')),
      drawer: roundRect(rect('#e9-right-drawer-panel')),
      topHud: roundRect(rect('#e9-top-hud-slot')),
      titlePlaque: roundRect(rect('.e10-hud-brand')),
      bottomDock: roundRect(rect('#e9-bottom-dock-slot')),
      leftBadgeIcon: roundRect(rect('.e9-nav__icon')),
      bottomMedallion: roundRect(rect('.e9-dock__icon')),
      primaryCtaCopy: roundRect(rect('.e10-map-primary-cta__copy')),
      playerMarker: roundRect(rect('#e9-world-stage-player')),
      currentZoneNumber: roundRect(rect('[data-player-location="true"] .e9-zone__number')),
      plaqueLayout: {
        display: playerIdentity ? getComputedStyle(playerIdentity).display : null,
        columns: playerIdentity ? getComputedStyle(playerIdentity).gridTemplateColumns : null,
        avatar: roundRect(playerAvatar?.getBoundingClientRect()),
        name: roundRect(playerNameBox),
        level: roundRect(playerLevelBox),
        content: roundRect(playerContentBox),
        dropdown: roundRect(playerDropdown?.getBoundingClientRect()),
        nameOverflow: playerName ? Math.max(0, playerName.scrollWidth - playerName.clientWidth) : null,
      },
      dockMaterial: {
        backgroundImage: dockStyle?.backgroundImage || '',
        backgroundColor: dockStyle?.backgroundColor || '',
        filter: dockStyle?.filter || '',
        backdropFilter: dockStyle?.backdropFilter || '',
        overflow: dockStyle?.overflow || '',
        boxShadow: dockStyle?.boxShadow || '',
        parentBackgroundColor: dockParent ? getComputedStyle(dockParent).backgroundColor : '',
        parentBackgroundImage: dockParent ? getComputedStyle(dockParent).backgroundImage : '',
        beforeBackground: dockBefore?.background || '',
        afterBackground: dockAfter?.background || '',
      },
      dockGeometry: {
        items: dockGeometryItems.map((item) => Object.fromEntries(
          Object.entries(item).map(([key, value]) => [key, typeof value === 'number' ? roundDockValue(value) : value])
        )),
        max_badge_slot_delta_x: roundDockValue(Math.max(0, ...dockGeometryItems.map((item) => Math.abs(item.badge_slot_delta_x || 0)))),
        max_badge_slot_delta_y: roundDockValue(Math.max(0, ...dockGeometryItems.map((item) => Math.abs(item.badge_slot_delta_y || 0)))),
        max_label_badge_delta_x: roundDockValue(Math.max(0, ...dockGeometryItems.map((item) => Math.abs(item.label_badge_delta_x || 0)))),
        max_badge_center_y_spread: roundDockValue(dockBadgeCentersY.length
          ? Math.max(...dockBadgeCentersY) - Math.min(...dockBadgeCentersY)
          : 0),
        max_slot_spacing_variance: roundDockValue(dockSlotSpacings.length
          ? Math.max(...dockSlotSpacings) - Math.min(...dockSlotSpacings)
          : 0),
        dock_stage_center_delta_x: roundDockValue(dockBox && map
          ? (dockBox.left + dockBox.width / 2) - (map.left + map.width / 2)
          : null),
      },
      playerMarkerContract: {
        node: roundRect(currentNodeBox),
        marker: roundRect(markerBox),
        relativeToNode: markerBox && currentNodeBox ? roundRect(rectFromEdges(
          markerBox.left - currentNodeBox.left,
          markerBox.top - currentNodeBox.top,
          markerBox.right - currentNodeBox.left,
          markerBox.bottom - currentNodeBox.top
        )) : null,
        union: roundRect(markerUnion),
        maximumDiameterRatio: markerUnion && currentNodeBox
          ? Math.max(markerUnion.right - markerUnion.left, markerUnion.bottom - markerUnion.top)
            / Math.max(currentNodeBox.width, currentNodeBox.height)
          : null,
        labelGap: markerLabelGap === null ? null : Math.round(markerLabelGap * 100) / 100,
      },
      routeContract: {
        count: routeSegments.length,
        topology: routeSegments.map((segment) => `${segment.dataset.e10RouteFrom}>${segment.dataset.e10RouteTo}`),
        styles: routeSegments.map((segment) => {
          const style = getComputedStyle(segment);
          return { cap: style.strokeLinecap, join: style.strokeLinejoin, width: Number.parseFloat(style.strokeWidth), dash: style.strokeDasharray };
        }),
      },
      nodeHudOverlap: (() => {
        const hudRects = ['#e9-top-hud-slot', '#e9-left-nav-slot', '#e9-bottom-dock-slot', '.e10-adventure-progress', '.e10-map-primary-cta']
          .map((selector) => document.querySelector(selector)?.getBoundingClientRect()).filter(Boolean);
        return Array.from(document.querySelectorAll('#e9-world-stage-zones [data-zone]')).filter((node) => (
          hudRects.some((hud) => intersects(node.getBoundingClientRect(), hud))
        )).map((node) => node.dataset.zone);
      })(),
      zone1: roundRect(rect('[data-zone="k26_30"]')),
      zone10: roundRect(rect('[data-zone="d7_plus"]')),
      panelHeading: {
        kind: document.querySelector('.e10-drawer-zone-summary__kicker')?.getAttribute('data-zone-heading'),
        text: document.querySelector('.e10-drawer-zone-summary__kicker')?.textContent.trim(),
        title: document.querySelector('#e10-drawer-zone-title')?.textContent.trim(),
        status: document.querySelector('#e10-drawer-zone-state')?.textContent.trim(),
      },
      panelInformation: {
        row: roundRect(rect('[data-e10-zone-information]')),
        number: panelNumber ? roundRect(panelNumber) : null,
        state: panelState ? roundRect(panelState) : null,
        body: panelBody ? roundRect(panelBody) : null,
        collisionCount: [panelState, panelBody].filter((copyRect) => intersects(panelNumber, copyRect)).length,
        columns: document.querySelector('[data-e10-zone-information]')
          ? getComputedStyle(document.querySelector('[data-e10-zone-information]')).gridTemplateColumns
          : '',
      },
      immersiveViewport: {
        topGap: document.querySelector('#e9-adventure-shell')?.getBoundingClientRect().top,
        bottomGap: document.querySelector('#e9-adventure-shell')
          ? window.innerHeight - document.querySelector('#e9-adventure-shell').getBoundingClientRect().bottom
          : null,
        bottomElement: viewportBottomElement
          ? `${viewportBottomElement.tagName.toLowerCase()}#${viewportBottomElement.id}.${viewportBottomElement.className}`
          : '',
        bottomBackgroundColor: viewportBottomStyle?.backgroundColor || '',
        bottomBackgroundImage: viewportBottomStyle?.backgroundImage || '',
      },
      ctas: {
        primary: {
          target: document.querySelector('#e9-world-stage-primary-cta')?.getAttribute('data-challenge-target-zone'),
          disabled: document.querySelector('#e9-world-stage-primary-cta')?.disabled,
          label: document.querySelector('#e9-world-stage-primary-cta strong')?.textContent.trim(),
        },
        panel: {
          target: document.querySelector('[data-e10-zone-cta]')?.getAttribute('data-challenge-target-zone'),
          disabled: document.querySelector('[data-e10-zone-cta]')?.disabled,
          label: document.querySelector('[data-e10-zone-cta]')?.textContent.trim(),
        },
      },
      primaryCta: roundRect(rect('#e9-world-stage-primary-cta:not([hidden])')),
      progressOverlay: roundRect(rect('[data-e10-adventure-progress]')),
      details: roundRect(rect('#e9-world-stage-details:not([hidden]), #e9-newbie-mainline:not([hidden])')),
      plaqueCount: document.querySelectorAll('#e9-world-stage-zones .e9-zone__plaque').length,
      plaqueStatusCount: document.querySelectorAll('#e9-world-stage-zones .e9-zone__status-text').length,
      drawerExpanded: document.querySelector('#e9-right-drawer-toggle')?.getAttribute('aria-expanded'),
      detailsVisible: !!document.querySelector('#e9-world-stage-details:not([hidden]), #e9-newbie-mainline:not([hidden])'),
      inlineDetailsVisible: !!document.querySelector('.e9-zone[aria-pressed="true"] > .e9-zone__inline-details'),
      bottomDockVisible: (() => {
        const dock = document.querySelector('#bottom-dock');
        if (!dock) return false;
        const style = getComputedStyle(dock);
        const box = dock.getBoundingClientRect();
        return style.display !== 'none' && box.width > 0 && box.height > 0;
      })(),
      navPosition: getComputedStyle(document.querySelector('#left-nav')).position,
      navSlotPosition: getComputedStyle(document.querySelector('#e9-left-nav-slot')).position,
      navColumns: getComputedStyle(document.querySelector('.e9-nav__list')).gridTemplateColumns,
      navItemCount: navItems.length,
      navRowCount: new Set(navItemRects.map((box) => Math.round(box.top))).size,
      navLabelWrapCount: labelWrapCount,
      navLabelOverTwoLineCount: labelOverTwoLineCount,
      navKeys: navItems.map((item) => item.getAttribute('data-e10-nav-key')),
      navVisualKeys: navItems.slice().sort((a, b) => (
        a.getBoundingClientRect().left - b.getBoundingClientRect().left
      )).map((item) => item.getAttribute('data-e10-nav-key')),
      moreOverlayVisible: isVisible(document.querySelector('#e10-all-features-overlay')),
      settingsOverlayVisible: isVisible(document.querySelector('#e10-settings-overlay')),
      focusedId: document.activeElement?.id || null,
      navOverlapCount: overlapCount(navItemRects),
      zoneOverlapCount: overlapCount(zoneRects),
      journeyTailGap: map && lastZone ? Math.round((map.bottom - lastZone.bottom) * 100) / 100 : null,
      lastZoneDockClearance: lastZone && nav ? Math.round((nav.top - lastZone.bottom) * 100) / 100 : null,
      dockBottomClearance: nav ? Math.round((window.innerHeight - nav.bottom) * 100) / 100 : null,
      horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
      minimumTarget: minimumTargetElement ? minimumTargetElement.minimum : Number.POSITIVE_INFINITY,
      minimumTargetElement: minimumTargetElement ? {
        tag: minimumTargetElement.element.tagName.toLowerCase(),
        id: minimumTargetElement.element.id || null,
        className: minimumTargetElement.element.className || null,
        navKey: minimumTargetElement.element.getAttribute('data-e10-nav-key'),
        width: minimumTargetElement.width,
        height: minimumTargetElement.height,
      } : null,
      duplicateIds: [...new Set(duplicateIds)],
      rpgIconCount: document.querySelectorAll('#e9-adventure-shell .e10-rpg-icon[data-e10-icon-id]').length,
      artAssetNodeCount: document.querySelectorAll('#e9-adventure-shell [data-e10-art-asset]').length,
      artAssetRequestCount: performance.getEntriesByType('resource')
        .filter((entry) => entry.name.includes('/assets/e10/ui/')).length,
      artAssetErrorCount: Array.from(document.querySelectorAll('#e9-adventure-shell img[src*="/assets/e10/ui/"]'))
        .filter((image) => !image.complete || image.naturalWidth === 0).length,
      playerMarkerPortraitCount: document.querySelectorAll(
        '#e9-world-stage-player .e10-player-marker-portrait, .e10-current-hero .e10-player-marker-portrait'
      ).length,
      artSurfaces: {
        playerPlaque: getComputedStyle(document.querySelector('.e9-hud__player')).backgroundImage,
        titlePlaque: getComputedStyle(document.querySelector('.e10-hud-brand')).backgroundImage,
        utilityFrame: getComputedStyle(document.querySelector('.e10-utility-control')).backgroundImage,
        leftBadge: getComputedStyle(document.querySelector('.e9-nav__icon')).backgroundImage,
        dockFrame: getComputedStyle(document.querySelector('.e9-dock')).backgroundImage,
        primaryCta: getComputedStyle(document.querySelector('.e10-map-primary-cta')).backgroundImage,
      },
      visibleControlMissingIconCount: visibleNavigationControls.filter((control) => (
        !control.querySelector('.e10-rpg-icon[data-e10-icon-id]')
      )).length,
      svgTextCount: document.querySelectorAll('#e9-adventure-shell svg text').length,
      iconIds: [...new Set(Array.from(document.querySelectorAll('#e9-adventure-shell [data-e10-icon-id]'))
        .map((icon) => icon.getAttribute('data-e10-icon-id')))].sort(),
      adventureCurrent: document.querySelector('[data-e10-nav-key="adventure"]')?.getAttribute('aria-current'),
      avatarFit: getComputedStyle(document.querySelector('#top-hud-avatar-image')).objectFit,
      moreColumns: getComputedStyle(document.querySelector('.e10-more-grid')).gridTemplateColumns.split(' ').length,
      soundToggle: (() => {
        const input = document.querySelector('#e10-settings-sound');
        const track = document.querySelector('.e10-settings-switch__track');
        const state = document.querySelector('#e10-settings-sound-state');
        return {
          type: input?.type,
          appearance: input ? getComputedStyle(input).appearance : null,
          trackWidth: track?.getBoundingClientRect().width || 0,
          state: state?.textContent.trim() || '',
          ariaLabel: input?.getAttribute('aria-label') || '',
        };
      })(),
      legacyNavCount: document.querySelectorAll('.cg-nav-link[data-nav-key]').length,
      sessionControls: {
        presence: !!document.querySelector('#cg-presence-chip'),
        language: isVisible(document.querySelector('.cg-nav-lang'))
          || !!document.querySelector('#e10-settings-language'),
        logout: isVisible(document.querySelector('.cg-nav-logout'))
          || !!document.querySelector('[data-e10-player-logout]'),
      },
      cleanMap: {
        src: document.querySelector('.e9-map-stage__base')?.getAttribute('src'),
        marker: document.querySelector('.e9-map-stage__base')?.getAttribute('data-e10-vs1f-clean-map'),
        requests: performance.getEntriesByType('resource')
          .filter((entry) => entry.name.includes('/assets/maps/e10_world_stage_v2_clean.webp')).length,
        legacyRequests: performance.getEntriesByType('resource')
          .filter((entry) => entry.name.includes('/assets/maps/e10_world_stage_v1_base.webp')).length,
      },
      avatar: {
        src: document.querySelector('#top-hud-avatar-image')?.getAttribute('src'),
        fallback: document.querySelector('#top-hud-avatar-image')?.hasAttribute('data-e10-avatar-fallback'),
        identityLabel: document.querySelector('.e9-hud__player')?.getAttribute('aria-label'),
      },
      playerIdentity: roundRect(rect('.e9-hud__player')),
      utilityGroup: roundRect(rect('.e10-hud__right')),
      drawerCloseVisible: isVisible(document.querySelector('#e10-right-drawer-close')),
      backpack: {
        disabled: document.querySelector('[data-e10-nav-key="backpack"]')?.disabled,
        ariaDisabled: document.querySelector('[data-e10-nav-key="backpack"]')?.getAttribute('aria-disabled'),
        href: document.querySelector('[data-e10-nav-key="backpack"]')?.getAttribute('href'),
        label: document.querySelector('[data-e10-nav-key="backpack"] > span:not(.e10-nav-status-lock)')?.textContent.trim(),
        lockVisible: isVisible(document.querySelector('[data-e10-nav-key="backpack"] .e10-nav-status-lock')),
      },
      bossAnchorsVisibility: getComputedStyle(document.querySelector('#e9-world-stage-boss-anchors')).visibility,
      aria: {
        drawerControls: document.querySelector('#e9-right-drawer-toggle')?.getAttribute('aria-controls'),
        mapLabel: document.querySelector('#e9-map-stage')?.getAttribute('aria-label'),
      },
    };
  });
}

async function saveViewportScreenshot(page, outputDir, filename) {
  const output = path.join(outputDir, filename);
  await page.screenshot({ path: output, fullPage: false });
  return output;
}

async function resetViewportScroll(page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.querySelector('main')?.scrollTo(0, 0);
    document.querySelector('.practice')?.scrollTo(0, 0);
  });
}

async function runCase(browser, origin, outputDir, spec) {
  const page = await browser.newPage({ viewport: spec.viewport });
  const browserErrors = [];
  const playerName = spec.playerName || (spec.lang === 'en' ? 'Starward Knight' : '晨星騎士');
  await installApiFixture(
    page,
    browserErrors,
    spec.avatarKey || 'mage',
    spec.fixtureMode || 'default',
    playerName
  );
  labelPageDiagnostics(page, spec.specName);
  const url = `${origin}/index.html?lang=${spec.lang}&${shellFlags}`;
  await page.goto(url, { waitUntil: 'networkidle' });
  await waitForShell(page);

  if (spec.safeAreaBottom) {
    await page.locator('#e9-adventure-shell').evaluate((shell, safeAreaBottom) => {
      shell.style.setProperty('--e10-safe-area-bottom', `${safeAreaBottom}px`);
    }, spec.safeAreaBottom);
  }

  if (spec.longLabelStress) {
    await page.locator('.e9-nav__item').evaluateAll((items) => {
      const stressLabels = {
        adventure: 'Adventure',
        hero: 'Hero',
        equipment: 'Equipment',
        go_spirit: 'Go Spirit Companion',
        backpack: 'Backpack',
        shop: 'Shop',
      };
      items.forEach((item) => {
        const label = item.querySelector(':scope > span:not(.e10-nav-status-lock)');
        if (label) label.textContent = stressLabels[item.dataset.e10NavKey];
      });
    });
  }

  let detailMapBefore = null;
  let detailMapAfterSelection = null;
  if (spec.zone) {
    detailMapBefore = await runtimeSnapshot(page);
    const zone = page.locator(`[data-zone="${spec.zone}"]`);
    if (await zone.count() !== 1) throw new Error(`missing unique zone ${spec.zone}`);
    await zone.scrollIntoViewIfNeeded();
    if (await zone.isEnabled() || !spec.playable) {
      // Dispatch the real DOM activation without Playwright waiting for the
      // content-driven inline expansion to become geometrically stable. A
      // locked tile is aria-disabled for actionability, but remains a valid
      // read-only inspection surface for this contract.
      await zone.evaluate((element) => element.click());
    }
    detailMapAfterSelection = await runtimeSnapshot(page);
  }

  let beforeOpen = null;
  let afterOpen = null;
  let escaped = null;
  if (spec.progressDrawerCheck) {
    beforeOpen = await runtimeSnapshot(page);
    const toggle = page.locator('#e9-right-drawer-toggle');
    if (await toggle.count() !== 1) throw new Error('drawer toggle is not unique');
    await toggle.click();
    await page.locator('#e9-right-drawer-panel').waitFor({ state: 'visible' });
    await resetViewportScroll(page);
    afterOpen = await runtimeSnapshot(page);
    if (spec.escapeCheck) {
      await page.keyboard.press('Escape');
      escaped = await page.locator('#e9-right-drawer-toggle').getAttribute('aria-expanded');
      await resetViewportScroll(page);
      await toggle.click();
      await page.locator('#e9-right-drawer-panel').waitFor({ state: 'visible' });
      await resetViewportScroll(page);
    }
  }

  if (spec.openMore) {
    const trigger = page.locator('[data-e10-vs1f-nav="more"]');
    if (await trigger.isVisible()) await trigger.click();
    else await trigger.evaluate((element) => element.click());
    await page.locator('#e10-all-features-overlay').waitFor({ state: 'visible' });
  }
  if (spec.openSettings) {
    const visibleSettings = page.locator('[data-e10-nav-key="settings"]:visible').first();
    await visibleSettings.click();
    await page.locator('#e10-settings-overlay').waitFor({ state: 'visible' });
  }

  let adventureCommand = null;
  if (spec.adventureCommandCheck) {
    const zone = page.locator('[data-zone="k1_5"]');
    await zone.evaluate((element) => element.click());
    const drawerToggle = page.locator('#e9-right-drawer-toggle');
    if (await drawerToggle.getAttribute('aria-expanded') !== 'true') {
      await drawerToggle.evaluate((element) => element.click());
    }
    const more = page.locator('[data-e10-vs1f-nav="more"]');
    await more.click();
    const before = await runtimeSnapshot(page);
    const beforeUrl = page.url();
    await page.evaluate(() => {
      window.__e10ChallengeCalls = 0;
      const original = window.E9.startAdventureFromE9;
      window.E9.startAdventureFromE9 = function () { window.__e10ChallengeCalls += 1; };
      window.E9.runAdventureCommand();
      window.E9.startAdventureFromE9 = original;
    });
    const after = await runtimeSnapshot(page);
    adventureCommand = {
      before,
      after,
      beforeUrl,
      afterUrl: page.url(),
      challengeCalls: await page.evaluate(() => window.__e10ChallengeCalls),
    };
  }

  let challengeAction = null;
  if (spec.challengeActionCheck || spec.lockedChallengeCheck) {
    const before = await runtimeSnapshot(page);
    await page.evaluate(() => {
      window.__e10ChallengeTargets = [];
      window.__e10OriginalStart = window.E9.startAdventureFromE9;
      window.E9.startAdventureFromE9 = function (zoneKey) { window.__e10ChallengeTargets.push(zoneKey); };
    });
    await page.locator('#e9-world-stage-primary-cta').evaluate((element) => element.click());
    const after = await runtimeSnapshot(page);
    const targets = await page.evaluate(() => {
      const values = window.__e10ChallengeTargets.slice();
      window.E9.startAdventureFromE9 = window.__e10OriginalStart;
      delete window.__e10OriginalStart;
      return values;
    });
    challengeAction = { before, after, targets };
  }

  const snapshot = await runtimeSnapshot(page);
  const screenshot = await saveViewportScreenshot(page, outputDir, spec.filename);
  await page.close();
  return {
    ...spec,
    screenshot,
    beforeOpen,
    afterOpen,
    escaped,
    detailMapBefore,
    detailMapAfterSelection,
    adventureCommand,
    challengeAction,
    snapshot,
    browserErrors,
  };
}

async function capturePolishStateEvidence(browser, origin, outputDir) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors, 'mage');
  labelPageDiagnostics(page, 'polish-state-evidence');
  await page.goto(`${origin}/index.html?lang=en&${shellFlags}`, { waitUntil: 'networkidle' });
  await waitForShell(page);

  const captures = [];
  async function capture(locator, filename) {
    const target = locator.first();
    if (await target.count() !== 1) throw new Error(`state evidence target missing: ${filename}`);
    const outputPath = path.join(outputDir, filename);
    await target.screenshot({ path: outputPath });
    captures.push(outputPath);
  }
  async function measureDockControl(locator) {
    return locator.evaluate((element) => {
      const dock = element.closest('.e9-dock');
      const items = Array.from(dock.querySelectorAll('.e9-dock__item'));
      const itemIndex = items.indexOf(element);
      const dockBox = dock.getBoundingClientRect();
      const badge = element.querySelector('.e9-dock__icon').getBoundingClientRect();
      const label = element.querySelector(':scope > span').getBoundingClientRect();
      const slotFractions = [260, 450, 640, 830, 1020].map((value) => value / 1280);
      const round = (value) => Math.round(value * 100) / 100;
      return {
        key: element.getAttribute('data-e10-nav-key'),
        badge_center_x: round(badge.left + badge.width / 2),
        badge_center_y: round(badge.top + badge.height / 2),
        slot_center_x: round(dockBox.left + dockBox.width * slotFractions[itemIndex]),
        slot_center_y: round(dockBox.top + dockBox.height / 2),
        label_center_x: round(label.left + label.width / 2),
      };
    });
  }
  async function captureStates(prefix, rootSelector, selectors, synthesizeDisabled = false) {
    const root = page.locator(rootSelector);
    const controls = Object.fromEntries(
      Object.entries(selectors).map(([state, selector]) => [state, root.locator(selector)])
    );
    const stateGeometry = prefix === 'bottom-dock' ? {} : null;
    if (stateGeometry) {
      for (const [state, control] of Object.entries(controls)) {
        stateGeometry[state] = { before: await measureDockControl(control) };
      }
    }
    async function recordGeometry(state) {
      if (!stateGeometry) return;
      const after = await measureDockControl(controls[state]);
      const before = stateGeometry[state].before;
      stateGeometry[state].after = after;
      stateGeometry[state].deltas = Object.fromEntries(
        ['badge_center_x', 'badge_center_y', 'slot_center_x', 'slot_center_y', 'label_center_x']
          .map((key) => [key, Math.round(Math.abs(after[key] - before[key]) * 100) / 100])
      );
    }
    await capture(controls.default, `${prefix}-state-default.png`);
    await recordGeometry('default');
    await controls.hover.hover();
    await capture(controls.hover, `${prefix}-state-hover.png`);
    await recordGeometry('hover');
    await controls.focus.focus();
    await capture(controls.focus, `${prefix}-state-focus.png`);
    await recordGeometry('focus');
    await controls.pressed.hover();
    const box = await controls.pressed.boundingBox();
    if (!box) throw new Error(`state evidence pressed target hidden: ${prefix}`);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await capture(controls.pressed, `${prefix}-state-pressed.png`);
    await recordGeometry('pressed');
    await page.mouse.move(1, 1);
    await page.mouse.up();
    await controls.active.evaluate((element) => {
      element.classList.add('is-active');
      element.setAttribute('data-e10-state', 'active');
      element.setAttribute('aria-current', 'page');
    });
    await capture(controls.active, `${prefix}-state-active.png`);
    await recordGeometry('active');
    if (synthesizeDisabled) {
      await controls.disabled.evaluate((element) => {
        element.classList.remove('is-active');
        element.removeAttribute('aria-current');
        element.setAttribute('data-e10-state', 'locked');
        element.setAttribute('aria-disabled', 'true');
        if ('disabled' in element) element.disabled = true;
      });
    }
    await capture(controls.disabled, `${prefix}-state-disabled.png`);
    await recordGeometry('disabled');
    return stateGeometry;
  }

  await captureStates('left-rail', '#left-nav', {
    default: '[data-e10-nav-key="hero"]',
    hover: '[data-e10-nav-key="equipment"]',
    focus: '[data-e10-nav-key="go_spirit"]',
    pressed: '[data-e10-nav-key="shop"]',
    active: '[data-e10-nav-key="hero"]',
    disabled: '[data-e10-nav-key="backpack"]',
  }, true);
  const dockInteractionGeometry = await captureStates('bottom-dock', '#bottom-dock', {
    default: '[data-e10-nav-key="battle_log"]',
    hover: '[data-e10-nav-key="tavern"]',
    focus: '[data-e10-nav-key="star_chart"]',
    pressed: '[data-e10-nav-key="arena"]',
    active: '[data-e10-nav-key="soul_records"]',
    disabled: '[data-e10-nav-key="soul_records"]',
  }, true);
  await captureStates('primary-cta', '#e9-map-stage', {
    default: '#e9-world-stage-primary-cta',
    hover: '#e9-world-stage-primary-cta',
    focus: '#e9-world-stage-primary-cta',
    pressed: '#e9-world-stage-primary-cta',
    active: '#e9-world-stage-primary-cta',
    disabled: '#e9-world-stage-primary-cta',
  }, true);
  await capture(page.locator('.e9-hud__player'), 'avatar-runtime-closeup.png');
  await capture(page.locator('.e10-hud__right'), 'utility-group-closeup.png');
  await page.close();
  return { captures, browserErrors, dockInteractionGeometry };
}

function assertCase(result) {
  const failures = [];
  const { snapshot, specName, browserErrors } = result;
  if (snapshot.activeShell !== 'e9') failures.push(`${specName}: E9 shell not active`);
  if (snapshot.skin !== 'immersive-rpg' || snapshot.shellSkin !== 'immersive-rpg') {
    failures.push(`${specName}: RPG skin marker missing`);
  }
  if (snapshot.artKit !== 'runtime-v1' || snapshot.shellArtKit !== 'runtime-v1') {
    failures.push(`${specName}: art-directed runtime ownership marker missing`);
  }
  if (snapshot.nodeCount !== 10) failures.push(`${specName}: node count ${snapshot.nodeCount}`);
  if (
    snapshot.cleanMap.src !== '/assets/maps/e10_world_stage_v2_clean.webp'
    || snapshot.cleanMap.marker !== 'v2'
    || snapshot.cleanMap.requests !== 1
    || snapshot.cleanMap.legacyRequests !== 0
  ) failures.push(`${specName}: exact VS1F clean-map ownership failed ${JSON.stringify(snapshot.cleanMap)}`);
  if (snapshot.plaqueCount !== 10 || snapshot.plaqueStatusCount !== 10) {
    failures.push(`${specName}: persistent map plaques are incomplete`);
  }
  if (snapshot.legacyVisible) failures.push(`${specName}: Legacy shell remains visible`);
  if (snapshot.legacyNavCount !== 0) failures.push(`${specName}: Legacy header navigation remains in exact VS1F`);
  if (!Object.values(snapshot.sessionControls).every(Boolean)) failures.push(`${specName}: session controls are not reachable`);
  if (!snapshot.avatar.src || snapshot.avatar.src.includes('GO')) failures.push(`${specName}: runtime avatar is missing`);
  if (!snapshot.avatar.identityLabel) failures.push(`${specName}: player identity accessible name is missing`);
  if (snapshot.avatarFit !== 'cover') failures.push(`${specName}: runtime avatar is not portrait-cropped`);
  if (snapshot.rpgIconCount < 22) failures.push(`${specName}: RPG icon registry render is incomplete (${snapshot.rpgIconCount})`);
  if (snapshot.artAssetNodeCount < 22 || snapshot.artAssetRequestCount < 22 || snapshot.artAssetErrorCount !== 0) {
    failures.push(`${specName}: runtime art asset contract ${snapshot.artAssetNodeCount}/${snapshot.artAssetRequestCount}/${snapshot.artAssetErrorCount}`);
  }
  if (snapshot.playerMarkerPortraitCount !== 1) failures.push(`${specName}: player marker portrait count ${snapshot.playerMarkerPortraitCount}`);
  const landscapeContract = result.viewport.width >= 768 && result.viewport.width > result.viewport.height;
  if (landscapeContract) {
    const plaque = snapshot.plaqueLayout;
    if (
      plaque.display !== 'grid'
      || !plaque.avatar
      || !plaque.content
      || !plaque.name
      || !plaque.level
      || !plaque.dropdown
      || plaque.avatar.right >= plaque.content.left
      || plaque.content.right >= plaque.dropdown.left
      || plaque.avatar.right >= plaque.name.left
      || plaque.avatar.right >= plaque.level.left
      || plaque.name.right >= plaque.dropdown.left
      || plaque.level.right >= plaque.dropdown.left
      || plaque.nameOverflow > 1
    ) failures.push(`${specName}: player plaque columns overlap ${JSON.stringify(plaque)}`);

    const dock = snapshot.dockMaterial;
    if (
      dock.backgroundColor !== 'rgba(0, 0, 0, 0)'
      || !dock.backgroundImage.includes('/assets/e10/ui/frames/legacy-dock-frame.webp')
      || dock.filter !== 'none'
      || dock.backdropFilter !== 'none'
      || dock.overflow !== 'visible'
      || dock.boxShadow !== 'none'
    ) failures.push(`${specName}: dock base material is not transparent ${JSON.stringify(dock)}`);

    const geometry = snapshot.dockGeometry;
    if (
      geometry.items.length !== 5
      || geometry.max_badge_slot_delta_x > 1
      || geometry.max_badge_slot_delta_y > 1
      || geometry.max_label_badge_delta_x > 1
      || geometry.max_badge_center_y_spread > 1
      || geometry.max_slot_spacing_variance > 1
      || Math.abs(geometry.dock_stage_center_delta_x) > 1
    ) failures.push(`${specName}: bottom dock badge-slot alignment ${JSON.stringify(geometry)}`);
  }
  if (
    !snapshot.playerMarkerContract.marker
    || Math.abs(snapshot.playerMarkerContract.marker.width - 31) > .1
    || Math.abs(snapshot.playerMarkerContract.marker.height - 38) > .1
  ) failures.push(`${specName}: player marker pin geometry ${JSON.stringify(snapshot.playerMarkerContract)}`);
  if (result.layout === 'rail' && (
    snapshot.playerMarkerContract.maximumDiameterRatio < 1.2
    || snapshot.playerMarkerContract.maximumDiameterRatio > 1.35
    || snapshot.playerMarkerContract.labelGap < 6
    || snapshot.playerMarkerContract.labelGap > 10
  )) failures.push(`${specName}: player marker stack geometry ${JSON.stringify(snapshot.playerMarkerContract)}`);
  if (Object.values(snapshot.artSurfaces).some((value) => !value.includes('/assets/e10/ui/'))) {
    failures.push(`${specName}: one or more art-directed shell surfaces are missing`);
  }
  if (snapshot.visibleControlMissingIconCount !== 0) failures.push(`${specName}: visible navigation control lacks an RPG icon`);
  if (snapshot.svgTextCount !== 0) failures.push(`${specName}: text was embedded inside SVG icons`);
  if (snapshot.adventureCurrent !== 'page') failures.push(`${specName}: Adventure active/current state is missing`);
  if (snapshot.backpack.disabled || snapshot.backpack.ariaDisabled === 'true'
    || snapshot.backpack.lockVisible || snapshot.backpack.href !== '/inventory') {
    failures.push(`${specName}: Backpack independent destination is not enabled ${JSON.stringify(snapshot.backpack)}`);
  }
  if (snapshot.backpack.label !== (snapshot.lang === 'en' ? 'Backpack' : '背包')) failures.push(`${specName}: Backpack main label includes status text`);
  if (snapshot.horizontalOverflow !== 0) failures.push(`${specName}: horizontal overflow ${snapshot.horizontalOverflow}`);
  if (snapshot.minimumTarget < 44) failures.push(`${specName}: interactive target below 44px (${snapshot.minimumTarget})`);
  if (snapshot.duplicateIds.length) failures.push(`${specName}: duplicate IDs ${snapshot.duplicateIds.join(', ')}`);
  if (snapshot.bossAnchorsVisibility !== 'hidden') failures.push(`${specName}: Boss anchors visible`);
  if (snapshot.aria.drawerControls !== 'e9-right-drawer-panel') failures.push(`${specName}: aria-controls drift`);
  if (!snapshot.aria.mapLabel) failures.push(`${specName}: map accessible label missing`);
  if (snapshot.playerLocationCount !== 1 || snapshot.visibleHeroCount !== 1) {
    failures.push(`${specName}: authoritative player marker count ${snapshot.playerLocationCount}/${snapshot.visibleHeroCount}`);
  }
  const expectedCurrent = result.fixtureMode === 'placement-high' ? 'k1_5' : 'k21_25';
  if (snapshot.playerLocationZone !== expectedCurrent) {
    failures.push(`${specName}: authoritative player location ${snapshot.playerLocationZone}`);
  }
  if (snapshot.zoneIdentities.currentPlayerZoneKey !== expectedCurrent) {
    failures.push(`${specName}: currentPlayerZoneKey ${snapshot.zoneIdentities.currentPlayerZoneKey}`);
  }
  const expectedSelected = result.zone || expectedCurrent;
  if (snapshot.zoneIdentities.selectedZoneKey !== expectedSelected || snapshot.selectedZone !== expectedSelected) {
    failures.push(`${specName}: selectedZoneKey ${snapshot.zoneIdentities.selectedZoneKey}/${snapshot.selectedZone}`);
  }
  const expectedChallenge = result.zone === 'd1_2' ? null : expectedCurrent;
  if (snapshot.zoneIdentities.challengeTargetZoneKey !== expectedChallenge) {
    failures.push(`${specName}: challengeTargetZoneKey ${snapshot.zoneIdentities.challengeTargetZoneKey}`);
  }
  if (snapshot.ctas.primary.target !== (expectedChallenge || '') || snapshot.ctas.panel.target !== (expectedChallenge || '')) {
    failures.push(`${specName}: dual CTA target mismatch ${snapshot.ctas.primary.target}/${snapshot.ctas.panel.target}`);
  }
  if (snapshot.ctas.primary.disabled !== snapshot.ctas.panel.disabled || snapshot.ctas.primary.disabled !== (expectedChallenge === null)) {
    failures.push(`${specName}: dual CTA enabled state mismatch`);
  }
  const expectedTopology = ['k26_30>k21_25','k21_25>k16_20','k16_20>k11_15','k11_15>k6_10','k6_10>k1_5','k1_5>d1_2','d1_2>d3_4','d3_4>d5_6','d5_6>d7_plus'];
  if (snapshot.routeContract.count !== 9 || snapshot.routeContract.topology.join(',') !== expectedTopology.join(',')) {
    failures.push(`${specName}: route topology ${snapshot.routeContract.topology.join(',')}`);
  }
  snapshot.routeContract.styles.forEach((style, index) => {
    const dash = String(style.dash).match(/[0-9.]+/g)?.map(Number) || [];
    if (style.cap !== 'round' || style.join !== 'round' || style.width > 2.5 || dash.length < 2 || dash[0] > 1 || dash[1] > 6) {
      failures.push(`${specName}: route segment ${index + 1} style ${JSON.stringify(style)}`);
    }
  });
  if (result.detailMapBefore && (
    result.detailMapBefore.playerLocationZone !== snapshot.playerLocationZone
    || result.detailMapBefore.visibleHeroCount !== snapshot.visibleHeroCount
  )) failures.push(`${specName}: selection moved the player marker`);
  if (result.detailMapBefore && result.detailMapAfterSelection) {
    const coordinateSpace = result.layout === 'rail' ? 'marker' : 'relativeToNode';
    const before = result.detailMapBefore.playerMarkerContract[coordinateSpace];
    const after = result.detailMapAfterSelection.playerMarkerContract[coordinateSpace];
    if (!before || !after || ['x', 'y', 'width', 'height'].some((key) => Math.abs(before[key] - after[key]) > .1)) {
      failures.push(`${specName}: selection changed player marker bounds ${JSON.stringify({ before, after })}`);
    }
  }
  if (browserErrors.length) failures.push(`${specName}: browser errors ${JSON.stringify(browserErrors)}`);
  if (result.beforeOpen && result.afterOpen) {
    const before = result.beforeOpen.map;
    const after = result.afterOpen.map;
    if (before.width !== after.width || before.height !== after.height) {
      failures.push(`${specName}: overlay drawer changed map geometry`);
    }
  }
  if (result.progressDrawerCheck && (
    snapshot.drawerExpanded !== 'true'
    || !snapshot.drawer
    || snapshot.drawer.width <= 0
    || snapshot.drawer.height <= 0
  )) failures.push(`${specName}: open screenshot does not contain the quest drawer`);
  if (result.progressDrawerCheck && !snapshot.drawerCloseVisible) failures.push(`${specName}: drawer close control is not visible`);
  if (result.progressDrawerCheck) {
    const expectedHeading = expectedSelected === expectedCurrent ? 'current' : 'selected';
    if (snapshot.panelHeading.kind !== expectedHeading) failures.push(`${specName}: panel heading ${snapshot.panelHeading.kind}`);
    if (!snapshot.panelHeading.title.startsWith(`Zone ${zones.findIndex((zone) => zone.key === expectedSelected) + 1}`)) {
      failures.push(`${specName}: panel title ${snapshot.panelHeading.title}`);
    }
    if (!snapshot.panelInformation.row || snapshot.panelInformation.collisionCount !== 0) {
      failures.push(`${specName}: panel information collision ${snapshot.panelInformation.collisionCount}`);
    }
    if (snapshot.panelInformation.columns.trim().split(/\s+/).length !== 2) {
      failures.push(`${specName}: panel information grid ${snapshot.panelInformation.columns}`);
    }
  }
  if (result.escapeCheck && result.escaped !== 'false') failures.push(`${specName}: Escape did not close drawer`);
  if (result.layout === 'rail') {
    if (snapshot.playerIdentity && snapshot.utilityGroup && snapshot.playerIdentity.left >= snapshot.utilityGroup.left) {
      failures.push(`${specName}: player identity is not left of utility group`);
    }
    if (snapshot.landmarkCount !== 0) {
      failures.push(`${specName}: full landmark art duplicated the Desktop map`);
    }
    if (snapshot.landmarkRequestUrls.length > 1) {
      failures.push(`${specName}: Desktop landmark URLs ${snapshot.landmarkRequestUrls.join(',')}`);
    }
    if (!snapshot.nav || !snapshot.map || snapshot.nav.left < snapshot.map.left || snapshot.nav.right > snapshot.map.right) {
      failures.push(`${specName}: floating navigation badges are outside the map frame`);
    }
    if (!snapshot.shell || !snapshot.map || (snapshot.map.width * snapshot.map.height) / (snapshot.shell.width * snapshot.shell.height) < .75) {
      failures.push(`${specName}: map does not cover at least 75% of the shell`);
    }
    if (!snapshot.primaryCta || !snapshot.progressOverlay) {
      failures.push(`${specName}: closed-state map CTA/progress overlay missing`);
    }
    if (snapshot.nodeHudOverlap.length) failures.push(`${specName}: nodes overlap HUD ${snapshot.nodeHudOverlap.join(',')}`);
    if (!snapshot.topHud || !snapshot.shell || snapshot.topHud.height / snapshot.shell.height < .10 || snapshot.topHud.height / snapshot.shell.height > .12) {
      failures.push(`${specName}: top HUD ratio drift`);
    }
    if (!snapshot.titlePlaque || snapshot.titlePlaque.width / snapshot.shell.width < .38 || snapshot.titlePlaque.width / snapshot.shell.width > .46) {
      failures.push(`${specName}: title plaque ratio drift`);
    }
    if (!snapshot.leftBadgeIcon || snapshot.leftBadgeIcon.width < 70) failures.push(`${specName}: left badge scale drift`);
    if (!snapshot.bottomMedallion || snapshot.bottomMedallion.width < 58) failures.push(`${specName}: bottom medallion scale drift`);
    if (result.zone && !snapshot.drawerLandmarkVisible) {
      failures.push(`${specName}: selected landmark is missing from the quest panel`);
    }
    if (result.immersiveViewportCheck) {
      const color = snapshot.immersiveViewport.bottomBackgroundColor.match(/[0-9.]+/g)?.map(Number) || [];
      const isDark = color.length >= 3 && (color[0] + color[1] + color[2]) / 3 < 90;
      if (!isDark || snapshot.immersiveViewport.bottomBackgroundImage === 'none') {
        failures.push(`${specName}: viewport letterbox is not intentionally dark/art-directed`);
      }
      if (Math.abs(snapshot.immersiveViewport.topGap - snapshot.immersiveViewport.bottomGap) > 3) {
        failures.push(`${specName}: stage is not vertically centered ${snapshot.immersiveViewport.topGap}/${snapshot.immersiveViewport.bottomGap}`);
      }
    }
  }
  if (result.layout === 'bottom-dock') {
    if (result.viewport.width < 768) {
      if (snapshot.navPosition !== 'fixed' && snapshot.navSlotPosition !== 'fixed') {
        failures.push(`${specName}: navigation is not a fixed bottom dock`);
      }
      if (!snapshot.navColumns || snapshot.navColumns.split(' ').length !== 6) {
        failures.push(`${specName}: bottom dock is not one six-item row`);
      }
      if (snapshot.landmarkCount !== 10) {
        failures.push(`${specName}: mobile landmark card count ${snapshot.landmarkCount}`);
      }
      if (snapshot.navItemCount !== 6 || snapshot.navRowCount !== 1) {
        failures.push(`${specName}: mobile dock is not one six-item row`);
      }
      if (snapshot.navLabelOverTwoLineCount !== 0) {
        failures.push(`${specName}: mobile dock label exceeds two lines ${snapshot.navLabelOverTwoLineCount}`);
      }
      if (snapshot.navOverlapCount !== 0) {
        failures.push(`${specName}: mobile dock overlap ${snapshot.navOverlapCount}`);
      }
      if (snapshot.zoneOverlapCount !== 0) {
        failures.push(`${specName}: mobile journey overlap ${snapshot.zoneOverlapCount}`);
      }
      if (result.zoneTailCheck && snapshot.journeyTailGap > 32) {
        failures.push(`${specName}: abnormal journey tail ${snapshot.journeyTailGap}px`);
      }
      if (result.zoneTailCheck && snapshot.lastZoneDockClearance < 0) {
        failures.push(`${specName}: last zone is obscured by the dock`);
      }
      if (result.safeAreaBottom && snapshot.dockBottomClearance < result.safeAreaBottom + 5) {
        failures.push(`${specName}: safe-area clearance ${snapshot.dockBottomClearance}px`);
      }
      if (snapshot.bottomDockVisible) failures.push(`${specName}: secondary dock competes with primary navigation`);
      if (snapshot.navVisualKeys.join(',') !== 'adventure,hero,equipment,go_spirit,backpack,shop') {
        failures.push(`${specName}: mobile navigation order ${snapshot.navVisualKeys.join(',')}`);
      }
    } else if (result.viewport.width > result.viewport.height) {
      if (snapshot.navItemCount !== 5 || snapshot.navRowCount !== 5) failures.push(`${specName}: landscape floating badge structure drifted`);
      if (!snapshot.bottomDockVisible) failures.push(`${specName}: landscape Legacy medallion dock is missing`);
      if (!snapshot.primaryCta || !snapshot.progressOverlay) failures.push(`${specName}: landscape bottom HUD is incomplete`);
    } else {
      if (snapshot.navPosition !== 'fixed' && snapshot.navSlotPosition !== 'fixed') failures.push(`${specName}: portrait navigation is not fixed`);
      if (snapshot.navItemCount !== 6 || snapshot.navRowCount !== 1) failures.push(`${specName}: portrait dock is not one six-item row`);
      if (snapshot.bottomDockVisible) failures.push(`${specName}: portrait secondary dock competes with primary navigation`);
    }
  }
  if (result.openMore && !result.openSettings && !result.snapshot.moreOverlayVisible) failures.push(`${specName}: All Features did not open`);
  if (result.openMore && !result.openSettings) {
    const expectedColumns = result.viewport.width <= 600 ? 2 : 3;
    if (snapshot.moreColumns !== expectedColumns) failures.push(`${specName}: All Features columns ${snapshot.moreColumns}`);
  }
  if (result.openSettings && !result.snapshot.settingsOverlayVisible) failures.push(`${specName}: Settings did not open`);
  if (result.openSettings && (
    snapshot.soundToggle.type !== 'checkbox'
    || snapshot.soundToggle.appearance !== 'none'
    || snapshot.soundToggle.trackWidth < 44
    || !snapshot.soundToggle.state
    || !snapshot.soundToggle.ariaLabel
  )) failures.push(`${specName}: custom semantic Sound toggle contract failed`);
  if (result.adventureCommand) {
    const command = result.adventureCommand;
    if (command.before.selectedZone !== command.after.selectedZone) failures.push(`${specName}: Adventure changed selected zone`);
    if (command.before.playerLocationZone !== command.after.playerLocationZone) failures.push(`${specName}: Adventure moved player location`);
    if (command.challengeCalls !== 0 || command.beforeUrl !== command.afterUrl) failures.push(`${specName}: Adventure started challenge navigation`);
    if (command.after.drawerExpanded !== 'false' || command.after.moreOverlayVisible || command.after.settingsOverlayVisible) {
      failures.push(`${specName}: Adventure did not close overlays`);
    }
    if (command.after.focusedId !== 'e9-map-stage') failures.push(`${specName}: Adventure did not focus map top`);
  }
  if (result.challengeAction) {
    const action = result.challengeAction;
    const expectedTargets = result.lockedChallengeCheck ? [] : [snapshot.zoneIdentities.challengeTargetZoneKey];
    if (action.targets.join(',') !== expectedTargets.join(',')) failures.push(`${specName}: challenge targets ${action.targets.join(',')}`);
    if (action.before.playerLocationZone !== action.after.playerLocationZone) failures.push(`${specName}: starting challenge immediately moved player`);
    if (action.before.zoneIdentities.currentPlayerZoneKey !== action.after.zoneIdentities.currentPlayerZoneKey) {
      failures.push(`${specName}: starting challenge changed authoritative frontier`);
    }
  }
  if (result.portraitContext) {
    if (!snapshot.detailsVisible || !snapshot.details) failures.push(`${specName}: detail overlay is not visible`);
    if (snapshot.details && snapshot.map && snapshot.details.top < snapshot.map.bottom) {
      failures.push(`${specName}: portrait quest context is not below the map`);
    }
    if (result.detailMapBefore && (
      result.detailMapBefore.map.width !== snapshot.map.width
      || result.detailMapBefore.map.height !== snapshot.map.height
    )) failures.push(`${specName}: opening details changed map size`);
    if (!snapshot.portraitLandmarkVisible) {
      failures.push(`${specName}: selected portrait landmark is missing`);
    }
  }
  if (result.mobileInline) {
    if (!snapshot.inlineDetailsVisible || snapshot.detailsVisible) {
      failures.push(`${specName}: mobile details are not selected-card inline only`);
    }
  }
  return failures;
}

async function runLegacyCase(browser, origin, outputDir) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  labelPageDiagnostics(page, 'legacy-nonallowlisted');
  await page.goto(
    `${origin}/index.html?lang=zh&e9Shell=1&e9WorldStage=1&host=godokoro.com`,
    { waitUntil: 'networkidle' }
  );
  await page.locator('#welcome-state').waitFor({ state: 'visible' });
  const snapshot = await page.evaluate(() => ({
    activeShell: document.body.getAttribute('data-adventure-shell-active'),
    skin: document.body.getAttribute('data-e10-visual-skin'),
    artKit: document.body.getAttribute('data-e10-art-kit'),
    shellHidden: document.querySelector('#e9-adventure-shell')?.hidden,
    worldNodes: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
    drawerVisible: !!document.querySelector('#e9-right-drawer-toggle'),
  }));
  const screenshot = await saveViewportScreenshot(page, outputDir, 'legacy-nonallowlisted-1440x900-zh.png');
  await page.close();
  const failures = [];
  if (snapshot.activeShell !== 'legacy') failures.push('Legacy: query/host activated E9 shell');
  if (snapshot.skin !== null || snapshot.artKit !== null) failures.push('Legacy: RPG skin/art marker leaked');
  if (!snapshot.shellHidden) failures.push('Legacy: E9 shell is not hidden');
  if (snapshot.worldNodes !== 0 || snapshot.drawerVisible) failures.push('Legacy: World Stage UI leaked');
  if (browserErrors.length) failures.push(`Legacy: browser errors ${JSON.stringify(browserErrors)}`);
  return { specName: 'legacy-nonallowlisted', screenshot, snapshot, browserErrors, failures };
}

async function runLifecycleCase(browser, origin) {
  const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  labelPageDiagnostics(page, 'lifecycle');
  await page.goto(`${origin}/index.html?lang=en&${shellFlags}`, { waitUntil: 'networkidle' });
  await waitForShell(page);
  const beforeGeneration = await page.evaluate(() => window.E9.getLifecycleGeneration());
  const destroyed = await page.evaluate(() => {
    window.E9.destroyShell();
    return {
      activeShell: document.body.getAttribute('data-adventure-shell-active'),
      bodySkin: document.body.getAttribute('data-e10-visual-skin'),
      bodyArtKit: document.body.getAttribute('data-e10-art-kit'),
      shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
      shellArtKit: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-art-kit'),
      shellHidden: document.querySelector('#e9-adventure-shell')?.hidden,
      mountedSlots: document.querySelectorAll('[data-e9-loaded], [data-e9-inited]').length,
    };
  });
  await page.evaluate(() => {
    window.__GO_E9_ACTIVE_SHELL__ = 'e9';
    window.E9.initShell();
  });
  await waitForShell(page);
  const remounted = await runtimeSnapshot(page);
  const afterGeneration = await page.evaluate(() => window.E9.getLifecycleGeneration());
  await page.close();
  const failures = [];
  if (
    destroyed.activeShell !== 'legacy'
    || destroyed.bodySkin !== null
    || destroyed.bodyArtKit !== null
    || destroyed.shellSkin !== null
    || destroyed.shellArtKit !== null
    || !destroyed.shellHidden
    || destroyed.mountedSlots !== 0
  ) failures.push('lifecycle: destroy did not clean shell and skin ownership');
  if (
    remounted.activeShell !== 'e9'
    || remounted.skin !== 'immersive-rpg'
    || remounted.artKit !== 'runtime-v1'
    || remounted.nodeCount !== 10
    || remounted.duplicateIds.length
    || afterGeneration <= beforeGeneration
  ) failures.push('lifecycle: clean remount did not converge');
  if (browserErrors.length) failures.push(`lifecycle: browser errors ${JSON.stringify(browserErrors)}`);
  return { beforeGeneration, afterGeneration, destroyed, remounted, browserErrors, failures };
}

async function runIpadInteractionRecoveryCase(browser, origin, outputDir, spec) {
  const page = await browser.newPage({ viewport: spec.viewport });
  const browserErrors = [];
  await installApiFixture(page, browserErrors, 'mage', spec.fixtureMode || 'default',
    spec.lang === 'en' ? 'Starward Knight' : '晨星騎士');
  labelPageDiagnostics(page, spec.name);
  const actionTrace = [];
  page.on('request', (request) => {
    const pathname = new URL(request.url()).pathname;
    if (pathname.includes('adventure') || pathname.includes('question')) {
      actionTrace.push({ method: request.method(), pathname, resourceType: request.resourceType() });
    }
  });
  await page.goto(`${origin}/index.html?lang=${spec.lang}&${shellFlags}`, { waitUntil: 'domcontentloaded' });
  await waitForShell(page);

  const target = page.locator(`[data-zone="${spec.zone}"]`);
  if (await target.count() !== 1) throw new Error(`${spec.name}: target zone is not unique`);
  const nodePointer = await target.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const candidates = [
      [0.5, 0.25], [0.25, 0.25], [0.75, 0.25],
      [0.5, 0.5], [0.25, 0.5], [0.75, 0.5],
    ];
    const candidateHits = [];
    for (const [xRatio, yRatio] of candidates) {
      const clientX = box.left + box.width * xRatio;
      const clientY = box.top + box.height * yRatio;
      const hit = document.elementFromPoint(clientX, clientY);
      candidateHits.push({
        clientX,
        clientY,
        hit: hit ? (hit.id || hit.className || hit.tagName) : null,
        withinTarget: !!(hit && (hit === element || element.contains(hit))),
      });
      if (hit && (hit === element || element.contains(hit))) {
        return {
          hit: hit.id || hit.className || hit.tagName,
          withinTarget: true,
          localX: box.width * xRatio,
          localY: box.height * yRatio,
          clientX,
          clientY,
          targetRect: box.toJSON(),
          candidateHits,
        };
      }
    }
    const center = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    return {
      hit: center ? (center.id || center.className || center.tagName) : null,
      withinTarget: false,
      localX: box.width / 2,
      localY: box.height / 2,
      clientX: box.left + box.width / 2,
      clientY: box.top + box.height / 2,
      targetRect: box.toJSON(),
      candidateHits,
    };
  });
  if (!nodePointer.withinTarget) {
    await fs.writeFile(
      path.join(outputDir, `${spec.name}-node-pointer-failure.json`),
      JSON.stringify(nodePointer, null, 2)
    );
    await page.screenshot({ path: path.join(outputDir, `${spec.name}-node-pointer-failure.png`), fullPage: false });
    throw new Error(`${spec.name}: no real pointer hit point exists for target zone`);
  }
  // Locked zones are intentionally aria-disabled: they remain inspectable
  // through the real pointer surface, but Playwright's locator.click()
  // refuses an aria-disabled control before dispatching that pointer event.
  // Use the measured hit point for the read-only inspection case so the
  // contract still exercises the browser event path without treating the
  // locked tile as an actionable challenge target.
  if (spec.playable) {
    await target.click({ position: { x: nodePointer.localX, y: nodePointer.localY } });
  } else {
    await page.mouse.click(nodePointer.clientX, nodePointer.clientY);
  }

  const selected = await page.evaluate(() => {
    const state = document.querySelector('#e9-world-stage-slot').__e9WorldStageState;
    const detail = document.querySelector('#e9-world-stage-details');
    const cta = document.querySelector('#e9-world-stage-details-cta');
    const player = document.querySelector('#e9-world-stage-player');
    const inlineCta = document.querySelector('.e9-zone__inline-cta');
    const navSlot = document.querySelector('#e9-left-nav-slot');
    const nav = document.querySelector('#left-nav');
    const shell = document.querySelector('#e9-adventure-shell');
    const practice = document.querySelector('main .practice');
    const box = cta.getBoundingClientRect();
    const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
    const rect = (element) => {
      if (!element) return null;
      const value = element.getBoundingClientRect();
      return {
        left: value.left, top: value.top, right: value.right, bottom: value.bottom,
        width: value.width, height: value.height,
      };
    };
    const inlineBox = inlineCta ? inlineCta.getBoundingClientRect() : null;
    const inlineHit = inlineBox
      ? document.elementFromPoint(inlineBox.left + inlineBox.width / 2, inlineBox.top + inlineBox.height / 2)
      : null;
    return {
      currentZoneKey: state.currentPlayerZoneKey,
      selectedZoneKey: state.selectedZoneKey,
      challengeTargetZoneKey: state.challengeTargetZoneKey,
      detailTargetZoneKey: cta.getAttribute('data-challenge-target-zone'),
      detailLabel: document.querySelector('#e9-world-stage-details-label').textContent,
      detailStatus: document.querySelector('#e9-world-stage-details-state').textContent,
      detailProgress: document.querySelector('#e9-world-stage-details-progress').textContent,
      detailRegionProgress: document.querySelector('#e9-world-stage-details-region-progress').textContent,
      detailZoneNumber: document.querySelector('#e9-world-stage-details-number').textContent,
      detailStars: document.querySelector('#e9-world-stage-details-stars').textContent,
      detailSummary: document.querySelector('#e9-world-stage-details-summary').textContent,
      detailHidden: detail.hidden,
      ctaText: cta.textContent,
      ctaDisabled: cta.disabled,
      ctaVisible: !cta.hidden && getComputedStyle(cta).display !== 'none' && box.width > 0 && box.height > 0,
      ctaHit: hit ? (hit.id || hit.className || hit.tagName) : null,
      currentTileOwnsPlayer: !!document.querySelector(`[data-zone="${state.currentPlayerZoneKey}"][data-player-location="true"]`),
      selectedTileOwnsPlayer: !!document.querySelector(`[data-zone="${state.selectedZoneKey}"][data-player-location="true"]`),
      selectedCount: document.querySelectorAll('[data-zone].is-selected').length,
      playerCount: document.querySelectorAll('[data-player-location="true"]').length,
      inlineTargetZoneKey: document.querySelector('.e9-zone__inline-cta')?.getAttribute('data-challenge-target-zone') || null,
      interactionGeometry: {
        viewport: { width: window.innerWidth, height: window.innerHeight },
        inlineCta: rect(inlineCta),
        inlineCtaHit: inlineHit ? (inlineHit.id || inlineHit.className || inlineHit.tagName) : null,
        navSlot: rect(navSlot),
        nav: rect(nav),
        shell: rect(shell),
        shellPosition: shell ? getComputedStyle(shell).position : null,
        shellTransform: shell ? getComputedStyle(shell).transform : null,
        practiceScrollTop: practice ? practice.scrollTop : null,
        practiceScrollHeight: practice ? practice.scrollHeight : null,
        practiceClientHeight: practice ? practice.clientHeight : null,
      },
      inertCount: document.querySelectorAll('[inert]').length,
      latestSelection: window.E9.latestZoneSelection,
      drawerToggleVisible: document.querySelector('#e9-right-drawer-toggle').checkVisibility
        ? document.querySelector('#e9-right-drawer-toggle').checkVisibility()
        : getComputedStyle(document.querySelector('#e9-right-drawer-toggle')).display !== 'none',
      drawerSlotHidden: document.querySelector('#e9-right-cards-slot').hidden,
      drawerSlotInert: document.querySelector('#e9-right-cards-slot').inert,
      drawerSlotAriaHidden: document.querySelector('#e9-right-cards-slot').getAttribute('aria-hidden'),
      drawerDetailOwner: document.querySelector('#e9-right-cards-slot').getAttribute('data-e10-detail-owner'),
      drawerToggleTabIndex: document.querySelector('#e9-right-drawer-toggle').tabIndex,
    };
  });
  const expectedActionZoneKey = selected.latestSelection?.challengeTargetZoneKey
    || (spec.playable ? selected.detailTargetZoneKey : null)
    || (spec.playable ? spec.zone : null);
  const selectedScreenshot = path.join(outputDir, `${spec.name}-selected-detail.png`);
  await page.screenshot({ path: selectedScreenshot, fullPage: false });
  await fs.writeFile(
    path.join(outputDir, `${spec.name}-interaction-diagnostics.json`),
    JSON.stringify({ nodePointer, selected }, null, 2)
  );

  const panelCycles = [];
  let panelCtaClicks = [];
  if (spec.drawerLifecycle) {
    const toggle = page.locator('#e9-right-drawer-toggle');
    const close = page.locator('#e10-right-drawer-close');
    await page.evaluate(() => {
      window.__e10PanelCtaCalls = [];
      window.__e10PanelCtaOriginal = window.E9.startAdventureFromE9;
      window.E9.startAdventureFromE9 = function (zoneKey) {
        window.__e10PanelCtaCalls.push(zoneKey);
        return true;
      };
    });
    for (let cycle = 1; cycle <= 3; cycle += 1) {
      await toggle.click();
      await page.locator('#e9-right-drawer-panel').waitFor({ state: 'visible' });
      const opened = await page.evaluate(() => {
        const cta = document.querySelector('[data-e10-zone-cta]');
        const backdrop = document.querySelector('.e10-drawer-backdrop');
        const box = cta.getBoundingClientRect();
        const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return {
          ctaDisabled: cta.disabled,
          ctaHit: hit ? (hit.getAttribute('data-e10-zone-cta') !== null ? 'panel-cta' : hit.className || hit.id || hit.tagName) : null,
          backdrop: {
            hidden: backdrop.hidden,
            display: getComputedStyle(backdrop).display,
            pointerEvents: getComputedStyle(backdrop).pointerEvents,
            zIndex: getComputedStyle(backdrop).zIndex,
          },
          slotZIndex: getComputedStyle(document.querySelector('#e9-right-cards-slot')).zIndex,
          inertCount: document.querySelectorAll('[inert]').length,
          bodyClass: document.body.className,
          shellClass: document.querySelector('.e9-body').className,
        };
      });
      if (cycle === 1) {
        await page.screenshot({ path: path.join(outputDir, `${spec.name}-panel-open.png`), fullPage: false });
      }
      if (spec.playable) await page.locator('[data-e10-zone-cta]').click();
      panelCtaClicks = await page.evaluate(() => window.__e10PanelCtaCalls.slice());
      await close.click();
      await page.locator('#e9-right-drawer-panel').waitFor({ state: 'hidden' });
      const closed = await page.evaluate(() => {
        const backdrop = document.querySelector('.e10-drawer-backdrop');
        return {
          backdropHidden: backdrop.hidden,
          backdropDisplay: getComputedStyle(backdrop).display,
          drawerOpen: document.querySelector('#e9-right-drawer-toggle').getAttribute('aria-expanded'),
          shellDrawerClass: document.querySelector('.e9-body').classList.contains('is-right-drawer-open'),
          inertCount: document.querySelectorAll('[inert]').length,
          activeElement: document.activeElement && document.activeElement.id,
        };
      });
      panelCycles.push({ cycle, opened, closed });
    }
    await page.evaluate(() => {
      window.E9.startAdventureFromE9 = window.__e10PanelCtaOriginal;
      delete window.__e10PanelCtaOriginal;
    });
  }

  let questionEntry = null;
  if (spec.journey) {
    const journeyZoneKey = expectedActionZoneKey || spec.zone;
    await page.evaluate((zoneKey) => {
      const canonical = ADVENTURE_ZONES.find((zone) => zone.key === zoneKey);
      const topic = canonical && canonical.books && canonical.books[0];
      allQuestions = [{
        id: 910001, topic, source: 'e10-ipad-interaction-fixture',
        rank: '20k', difficulty: '20k', locked: false,
      }];
      window.__e10QuestionStarts = [];
      window.__e10AdventureCommands = [];
      document.addEventListener('e9:adventure-command', (event) => {
        if (event.detail && event.detail.action === 'start-zone-challenge') {
          window.__e10AdventureCommands.push(event.detail);
        }
      }, { once: true });
      window.loadQuestion = function (question) {
        window.__e10QuestionStarts.push({ id: question.id, zoneKey });
        const board = document.querySelector('#board-canvas-wrap');
        board.innerHTML = '<section data-e10-question-state><h2>Adventure Question</h2><p>'
          + zoneKey + '</p></section>';
        return Promise.resolve();
      };
    }, journeyZoneKey);
    const ctaSelector = spec.journeySurface === 'inline'
      ? '.e9-zone__inline-cta'
      : (spec.portrait ? '#e9-world-stage-details-cta' : '#e9-world-stage-primary-cta');
    const cta = page.locator(ctaSelector);
    const actionTraceStart = actionTrace.length;
    let startsBeforeReady = null;
    if (spec.deferRuntimeReady) await page.evaluate(() => { window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = false; });
    else await page.waitForFunction(() => window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ === true);
    await cta.click();
    if (spec.deferRuntimeReady) {
      startsBeforeReady = await page.evaluate(() => window.__e10QuestionStarts.length);
      await page.evaluate(() => {
        window.__GO_ADVENTURE_QUESTION_RUNTIME_READY__ = true;
        document.dispatchEvent(new CustomEvent('adventure:question-runtime-ready'));
      });
    }
    await page.locator('[data-e10-question-state]').waitFor({ state: 'visible' });
    questionEntry = await page.evaluate(() => ({
      starts: window.__e10QuestionStarts,
      commands: window.__e10AdventureCommands,
      url: location.href,
      activeShell: window.__GO_E9_ACTIVE_SHELL__,
      bodyShell: document.body.getAttribute('data-adventure-shell-active'),
      welcomeHidden: document.querySelector('#welcome-state').classList.contains('hidden'),
      welcomeDisplay: getComputedStyle(document.querySelector('#welcome-state')).display,
      e9ShellDisplay: getComputedStyle(document.querySelector('#e9-adventure-shell')).display,
      boardHidden: document.querySelector('#board-canvas-wrap').classList.contains('hidden'),
      legacyMapVisible: (() => {
        const legacy = document.querySelector('#adventure-map-shell');
        if (!legacy) return false;
        if (typeof legacy.checkVisibility === 'function') return legacy.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
        const style = getComputedStyle(legacy);
        const box = legacy.getBoundingClientRect();
        return !legacy.hidden && style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
      })(),
      questionVisible: !!document.querySelector('[data-e10-question-state]'),
    }));
    questionEntry.startsBeforeReady = startsBeforeReady;
    questionEntry.actionTrace = actionTrace.slice(actionTraceStart);
    await page.screenshot({ path: path.join(outputDir, `${spec.name}-question-state.png`), fullPage: false });
  }

  const failures = [];
  if (selected.selectedZoneKey !== spec.zone
    || (spec.playable ? selected.challengeTargetZoneKey !== spec.zone : selected.challengeTargetZoneKey !== null)) {
    failures.push(`${spec.name}: selected/challenge target did not converge on ${spec.zone}`);
  }
  if (selected.selectedCount !== 1
    || (spec.portrait && (selected.detailTargetZoneKey !== (spec.playable ? expectedActionZoneKey : '') || selected.detailHidden))
    || (spec.viewport.width < 768 && selected.inlineTargetZoneKey !== expectedActionZoneKey)) {
    failures.push(`${spec.name}: responsive selected detail did not synchronise uniquely`);
  }
  const canonicalDetail = selected.latestSelection;
  if (spec.portrait && (!canonicalDetail
    || selected.detailLabel !== canonicalDetail.name
    || selected.detailStatus !== canonicalDetail.statusText
    || selected.detailProgress !== `${canonicalDetail.seen} / ${canonicalDetail.total}`
    || selected.detailRegionProgress !== `${canonicalDetail.zoneNumber} / 10`
    || selected.detailZoneNumber !== `Zone ${canonicalDetail.zoneNumber}`
    || selected.detailStars !== `★ ${canonicalDetail.stars}`
    || selected.detailTargetZoneKey !== (canonicalDetail.challengeTargetZoneKey || '')
    || !selected.detailSummary)) {
    failures.push(`${spec.name}: portrait detail does not exactly match canonical selected-zone information`);
  }
  if (spec.expectDrawerHidden && (selected.drawerToggleVisible || !selected.drawerSlotHidden
    || !selected.drawerSlotInert || selected.drawerSlotAriaHidden !== 'true'
    || selected.drawerDetailOwner !== 'lower-card' || selected.drawerToggleTabIndex !== -1)) {
    failures.push(`${spec.name}: stacked detail surface retained an interactive drawer control`);
  }
  if (spec.drawerLifecycle && (!selected.drawerToggleVisible || selected.drawerSlotHidden
    || selected.drawerSlotInert || selected.drawerDetailOwner !== 'side-panel')) {
    failures.push(`${spec.name}: landscape/desktop side-panel handle was not preserved`);
  }
  if (!selected.currentTileOwnsPlayer || selected.playerCount !== 1
    || (selected.selectedZoneKey !== selected.currentZoneKey && selected.selectedTileOwnsPlayer)) {
    failures.push(`${spec.name}: selection moved or duplicated the authoritative player marker`);
  }
  if (spec.portrait && spec.playable && (!selected.ctaVisible || selected.ctaDisabled || selected.ctaHit !== 'e9-world-stage-details-cta')) {
    failures.push(`${spec.name}: portrait detail CTA is not directly hit-testable`);
  }
  for (const cycle of panelCycles) {
    if (cycle.opened.ctaHit !== 'panel-cta') failures.push(`${spec.name}: panel CTA missed hit test on cycle ${cycle.cycle}`);
    if (cycle.opened.slotZIndex === 'auto' || Number(cycle.opened.slotZIndex) <= Number(cycle.opened.backdrop.zIndex)) {
      failures.push(`${spec.name}: panel stack is not above backdrop on cycle ${cycle.cycle}`);
    }
    if (!cycle.closed.backdropHidden || cycle.closed.backdropDisplay !== 'none' || cycle.closed.drawerOpen !== 'false'
      || cycle.closed.shellDrawerClass || cycle.closed.activeElement !== 'e9-right-drawer-toggle'
      || cycle.closed.inertCount !== selected.inertCount) {
      failures.push(`${spec.name}: drawer lifecycle residue on cycle ${cycle.cycle}`);
    }
  }
  const expectedPanelClicks = spec.drawerLifecycle && spec.playable ? 3 : 0;
  if (spec.drawerLifecycle && (panelCtaClicks.length !== expectedPanelClicks
    || panelCtaClicks.some((zoneKey) => zoneKey !== expectedActionZoneKey))) {
    failures.push(`${spec.name}: panel CTA was not directly clickable exactly once per lifecycle cycle`);
  }
  if (spec.journey && (!questionEntry || questionEntry.starts.length !== 1
    || questionEntry.starts[0].zoneKey !== expectedActionZoneKey || !questionEntry.questionVisible
    || questionEntry.commands.length !== 1 || questionEntry.commands[0].zoneKey !== expectedActionZoneKey
    || (spec.deferRuntimeReady && questionEntry.startsBeforeReady !== 0)
    || questionEntry.actionTrace.some((entry) => entry.resourceType === 'document')
    || !questionEntry.welcomeHidden || questionEntry.welcomeDisplay !== 'none' || questionEntry.boardHidden
    || questionEntry.activeShell !== 'e9' || questionEntry.bodyShell !== 'e9'
    || questionEntry.legacyMapVisible)) {
    failures.push(`${spec.name}: CTA did not enter the expected in-page question state exactly once`);
  }
  if (!spec.playable && !selected.ctaDisabled) failures.push(`${spec.name}: locked CTA is not disabled`);
  if (browserErrors.length) failures.push(`${spec.name}: browser errors ${JSON.stringify(browserErrors)}`);
  await page.close();
  return { ...spec, nodePointer, selected, panelCycles, panelCtaClicks, questionEntry, actionTrace, browserErrors, failures };
}

async function runStackedDetailOwnershipTransition(browser, origin, outputDir) {
  const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  labelPageDiagnostics(page, 'orientation-transition');
  await page.goto(`${origin}/index.html?lang=en&${shellFlags}`, { waitUntil: 'domcontentloaded' });
  await waitForShell(page);
  const toggle = page.locator('#e9-right-drawer-toggle');
  await toggle.click();
  await page.locator('#e9-right-drawer-panel').waitFor({ state: 'visible' });
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.waitForFunction(() => document.querySelector('#e9-right-cards-slot')?.dataset.e10DetailOwner === 'lower-card');
  const portrait = await page.evaluate(() => {
    const slot = document.querySelector('#e9-right-cards-slot');
    const panel = document.querySelector('#e9-right-drawer-panel');
    const toggleElement = document.querySelector('#e9-right-drawer-toggle');
    const backdrop = document.querySelector('.e10-drawer-backdrop');
    const details = document.querySelector('#e9-world-stage-details');
    const cta = document.querySelector('#e9-world-stage-details-cta');
    const map = document.querySelector('#e9-map-stage');
    const detailsRect = details?.getBoundingClientRect();
    const ctaRect = cta?.getBoundingClientRect();
    const ctaHit = ctaRect && document.elementFromPoint(ctaRect.left + ctaRect.width / 2, ctaRect.top + ctaRect.height / 2);
    return {
      slotHidden: slot.hidden,
      slotInert: slot.inert,
      slotAriaHidden: slot.getAttribute('aria-hidden'),
      detailOwner: slot.dataset.e10DetailOwner,
      panelHidden: panel.hidden,
      toggleTabIndex: toggleElement.tabIndex,
      toggleVisible: toggleElement.checkVisibility ? toggleElement.checkVisibility() : getComputedStyle(toggleElement).display !== 'none',
      backdropHidden: !backdrop || backdrop.hidden,
      shellDrawerOpen: document.querySelector('.e9-body').classList.contains('is-right-drawer-open'),
      lowerCardHidden: details?.hidden,
      lowerCardPosition: details ? getComputedStyle(details).position : null,
      lowerCardTop: detailsRect?.top ?? null,
      mapBottom: map?.getBoundingClientRect().bottom ?? null,
      ctaVisible: !!(ctaRect && ctaRect.width > 0 && ctaRect.height > 0),
      ctaHit: ctaHit ? (ctaHit.id || ctaHit.className || ctaHit.tagName) : null,
    };
  });
  await page.screenshot({ path: path.join(outputDir, 'ipad-orientation-switch-portrait-lower-card-owner.png'), fullPage: false });
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.waitForFunction(() => document.querySelector('#e9-right-cards-slot')?.dataset.e10DetailOwner === 'side-panel');
  const landscape = await page.evaluate(() => {
    const slot = document.querySelector('#e9-right-cards-slot');
    const panel = document.querySelector('#e9-right-drawer-panel');
    const toggleElement = document.querySelector('#e9-right-drawer-toggle');
    const backdrop = document.querySelector('.e10-drawer-backdrop');
    const details = document.querySelector('#e9-world-stage-details');
    return {
      slotHidden: slot.hidden,
      slotInert: slot.inert,
      slotAriaHidden: slot.getAttribute('aria-hidden'),
      detailOwner: slot.dataset.e10DetailOwner,
      panelHidden: panel.hidden,
      toggleTabIndex: toggleElement.tabIndex,
      toggleVisible: toggleElement.checkVisibility ? toggleElement.checkVisibility() : getComputedStyle(toggleElement).display !== 'none',
      backdropHidden: !backdrop || backdrop.hidden,
      shellDrawerOpen: document.querySelector('.e9-body').classList.contains('is-right-drawer-open'),
      lowerCardHidden: details?.hidden,
      lowerCardDisplay: details ? getComputedStyle(details).display : null,
    };
  });
  const failures = [];
  if (!portrait.slotHidden || !portrait.slotInert || portrait.slotAriaHidden !== 'true'
    || portrait.detailOwner !== 'lower-card' || !portrait.panelHidden || portrait.toggleTabIndex !== -1
    || portrait.toggleVisible || !portrait.backdropHidden || portrait.shellDrawerOpen
    || portrait.lowerCardHidden || portrait.lowerCardPosition !== 'static'
    || portrait.lowerCardTop < portrait.mapBottom || !portrait.ctaVisible
    || portrait.ctaHit !== 'e9-world-stage-details-cta') {
    failures.push('orientation-transition: portrait retained stale side-panel interaction state');
  }
  if (landscape.slotHidden || landscape.slotInert || landscape.slotAriaHidden !== 'false'
    || landscape.detailOwner !== 'side-panel' || !landscape.panelHidden || !landscape.toggleVisible
    || !landscape.backdropHidden || landscape.shellDrawerOpen
    || !landscape.lowerCardHidden || landscape.lowerCardDisplay !== 'none') {
    failures.push('orientation-transition: landscape side-panel did not restore closed and usable');
  }
  if (browserErrors.length) failures.push(`orientation-transition: browser errors ${JSON.stringify(browserErrors)}`);
  await page.close();
  return { portrait, landscape, browserErrors, failures };
}

async function captureIpadInteractionRecoveryEvidence(browser, origin, outputDir) {
  const specs = [
    { name: 'ipad-768x1024-selected', viewport: { width: 768, height: 1024 }, lang: 'zh', zone: 'k1_5', portrait: true, expectDrawerHidden: true, playable: true, journey: true, deferRuntimeReady: true },
    { name: 'ipad-820x1180-selected', viewport: { width: 820, height: 1180 }, lang: 'en', zone: 'k16_20', portrait: true, expectDrawerHidden: true, playable: true, journey: true },
    { name: 'ipad-768x1024-locked', viewport: { width: 768, height: 1024 }, lang: 'en', zone: 'd1_2', portrait: true, expectDrawerHidden: true, playable: false },
    { name: 'ipad-834x1194-selected', viewport: { width: 834, height: 1194 }, lang: 'zh', zone: 'k16_20', portrait: true, expectDrawerHidden: true, playable: true },
    { name: 'ipad-1024x1366-current', viewport: { width: 1024, height: 1366 }, lang: 'en', zone: 'k21_25', portrait: true, expectDrawerHidden: true, playable: true },
    { name: 'ipad-1024x768-current', viewport: { width: 1024, height: 768 }, lang: 'zh', zone: 'k21_25', portrait: false, drawerLifecycle: true, playable: true, journey: true },
    { name: 'ipad-1180x820-selected', viewport: { width: 1180, height: 820 }, lang: 'en', zone: 'k16_20', portrait: false, playable: true, journey: true },
    { name: 'ipad-1366x1024-completed', viewport: { width: 1366, height: 1024 }, lang: 'en', zone: 'k26_30', portrait: false, playable: true, journey: true },
    { name: 'mobile-430x932-parity', viewport: { width: 430, height: 932 }, lang: 'zh', zone: 'k16_20', portrait: false, drawerLifecycle: false, expectDrawerHidden: true, playable: true, journey: true, journeySurface: 'inline' },
  ];
  const results = [];
  for (const spec of specs) {
    process.stdout.write(`capture ${spec.name}\n`);
    results.push(await runIpadInteractionRecoveryCase(browser, origin, outputDir, spec));
  }
  const orientationTransition = await runStackedDetailOwnershipTransition(browser, origin, outputDir);
  const report = {
    contract: 'e10-ipad-adventure-interaction-recovery-v1',
    ok: results.every((result) => result.failures.length === 0) && orientationTransition.failures.length === 0,
    results,
    orientationTransition,
    failures: results.flatMap((result) => result.failures).concat(orientationTransition.failures),
  };
  await fs.writeFile(path.join(outputDir, 'e10-ipad-adventure-interaction-contract.json'), JSON.stringify(report, null, 2));
  return report;
}

function serializeRunnerError(error) {
  if (!error) return null;
  return {
    name: error.name || 'Error',
    message: error.message || String(error),
    stack: error.stack || null,
  };
}

export function buildDiagnosticsHealthSummary(instrumentation = runnerInstrumentation) {
  const pages = Array.isArray(instrumentation.pages) ? instrumentation.pages : [];
  const servers = Array.isArray(instrumentation.servers) ? instrumentation.servers : [];
  const instrumentationErrors = pages.flatMap((page) => page.instrumentation_errors || []);
  return {
    cdp_network_enabled: pages.length > 0 && pages.every((page) => page.cdp_network_enabled === true),
    instrumentation_errors: instrumentationErrors.length,
    instrumentation_error_details: instrumentationErrors.slice(0, 20),
    pages: pages.length,
    servers: servers.length,
  };
}

export async function persistRunnerDiagnostics(outputDir, origin, instrumentation = runnerInstrumentation) {
  const health = buildDiagnosticsHealthSummary(instrumentation);
  const target = path.join(outputDir, 'formal-runner-requestfailed-instrumentation.json');
  try {
    await fs.writeFile(
      target,
      JSON.stringify({
        source_root: repoRoot,
        runtime_origin: origin,
        captured_at: observedAt(),
        diagnostic_health: {
          ...health,
          diagnostic_persistence_status: 'PASS',
        },
        ...instrumentation,
      }, null, 2)
    );
  } catch (error) {
    error.diagnosticsHealth = {
      ...health,
      diagnostic_persistence_status: 'FAIL',
      instrumentation_error_details: [
        ...health.instrumentation_error_details,
        { kind: 'diagnostic_persistence', text: error.stack || String(error) },
      ].slice(0, 20),
    };
    throw error;
  }
  return {
    path: target,
    summary: {
      ...health,
      diagnostic_persistence_status: 'PASS',
    },
  };
}

export function closeServerSafely(server) {
  return new Promise((resolve, reject) => {
    if (!server || typeof server.close !== 'function') {
      resolve();
      return;
    }
    let settled = false;
    const finish = (error = null) => {
      if (settled) return;
      settled = true;
      if (error) reject(error);
      else resolve();
    };
    try {
      server.close(finish);
    } catch (error) {
      finish(error);
    }
  });
}

async function attemptLifecycleStep(kind, operation) {
  try {
    await operation();
    return { kind, error: null };
  } catch (error) {
    return { kind, error };
  }
}

export function composeRunnerErrors({
  contractError = null,
  diagnosticsError = null,
  diagnosticsSummary = null,
  cleanupErrors = [],
  cleanupSummary = null,
} = {}) {
  const normalizedCleanupErrors = cleanupErrors
    .filter((entry) => entry && entry.error)
    .map((entry) => ({ kind: entry.kind, error: entry.error }));
  const primaryError = contractError || diagnosticsError || normalizedCleanupErrors[0]?.error || null;
  const primaryErrorKind = contractError
    ? 'CONTRACT'
    : (diagnosticsError ? 'DIAGNOSTICS' : (normalizedCleanupErrors.length ? 'CLEANUP' : 'NONE'));
  const secondaryErrors = [];
  if (contractError && diagnosticsError) secondaryErrors.push({ kind: 'DIAGNOSTICS', error: diagnosticsError });
  if (contractError || diagnosticsError) {
    secondaryErrors.push(...normalizedCleanupErrors.map((entry) => ({ kind: 'CLEANUP', error: entry.error })));
  }
  const serializedSecondaryErrors = secondaryErrors.map((entry) => ({
    kind: entry.kind,
    error: serializeRunnerError(entry.error),
  }));
  const serializedCleanupErrors = normalizedCleanupErrors.map((entry) => ({
    kind: entry.kind,
    error: serializeRunnerError(entry.error),
  }));
  const outcome = {
    run_result: primaryError ? 'FAIL' : 'PASS',
    contract_status: contractError ? 'FAIL' : 'PASS',
    contract_failure_count: contractError ? 1 : 0,
    primary_error_kind: primaryErrorKind,
    primary_error: serializeRunnerError(primaryError),
    secondary_errors: serializedSecondaryErrors,
    secondary_error_count: serializedSecondaryErrors.length,
    secondary_error_kinds: serializedSecondaryErrors.map((entry) => entry.kind),
    cleanup_errors: serializedCleanupErrors,
    diagnostic_persistence_status: diagnosticsError ? 'FAIL' : (diagnosticsSummary ? 'PASS' : 'NOT_RUN'),
    diagnostics_health: diagnosticsSummary,
    cleanup_status: cleanupSummary?.cleanup_status || (normalizedCleanupErrors.length ? 'FAIL' : 'NOT_RUN'),
    browser_close_status: cleanupSummary?.browser_close_status || 'NOT_RUN',
    server_close_status: cleanupSummary?.server_close_status || 'NOT_RUN',
  };
  if (!primaryError) return { error: null, outcome };
  primaryError.runnerOutcome = outcome;
  if (diagnosticsError) primaryError.diagnosticPersistenceError = diagnosticsError;
  if (normalizedCleanupErrors.length) primaryError.cleanupErrors = normalizedCleanupErrors.map((entry) => entry.error);
  return { error: primaryError, outcome };
}

export async function finalizeRunnerLifecycle({
  contractError = null,
  successPayload = null,
  browser,
  server,
  compatibilityServers = [],
  outputDir,
  origin,
  persistDiagnostics = persistRunnerDiagnostics,
} = {}) {
  const cleanupResults = [];
  cleanupResults.push(await attemptLifecycleStep('BROWSER_CLOSE', () => browser.close()));
  cleanupResults.push(await attemptLifecycleStep('SERVER_CLOSE', () => closeServerSafely(server)));
  for (const compatibilityServer of compatibilityServers) {
    cleanupResults.push(await attemptLifecycleStep('COMPATIBILITY_SERVER_CLOSE', () => closeServerSafely(compatibilityServer)));
  }

  let diagnosticsResult = null;
  let diagnosticsError = null;
  try {
    diagnosticsResult = await persistDiagnostics(outputDir, origin);
  } catch (error) {
    diagnosticsError = error;
  }

  const browserCloseFailed = cleanupResults.some((entry) => entry.kind === 'BROWSER_CLOSE' && entry.error);
  const serverCloseFailed = cleanupResults.some((entry) => (
    (entry.kind === 'SERVER_CLOSE' || entry.kind === 'COMPATIBILITY_SERVER_CLOSE') && entry.error
  ));
  const cleanupErrors = cleanupResults.filter((entry) => entry.error);
  const cleanupSummary = {
    cleanup_status: cleanupErrors.length ? 'FAIL' : 'PASS',
    browser_close_status: browserCloseFailed ? 'FAIL' : 'PASS',
    server_close_status: serverCloseFailed ? 'FAIL' : 'PASS',
    browser_close_attempted: true,
    server_close_attempted: true,
  };
  const composed = composeRunnerErrors({
    contractError,
    diagnosticsError,
    diagnosticsSummary: diagnosticsResult?.summary || diagnosticsError?.diagnosticsHealth || null,
    cleanupErrors,
    cleanupSummary,
  });
  return {
    successPayload,
    diagnosticsResult,
    diagnosticsError,
    cleanupResults,
    outcome: composed.outcome,
    error: composed.error,
  };
}

export function formatRunnerFailureSummary(error) {
  const outcome = error?.runnerOutcome || {
    run_result: 'FAIL',
    contract_status: 'FAIL',
    primary_error_kind: 'UNKNOWN',
    primary_error: serializeRunnerError(error),
    secondary_errors: [],
    secondary_error_count: 0,
    secondary_error_kinds: [],
    cleanup_errors: [],
    diagnostic_persistence_status: 'NOT_RUN',
    diagnostics_health: null,
    cleanup_status: 'NOT_RUN',
    browser_close_status: 'NOT_RUN',
    server_close_status: 'NOT_RUN',
  };
  return JSON.stringify({
    RUN_RESULT: outcome.run_result,
    CONTRACT_STATUS: outcome.contract_status,
    CONTRACT_FAILURE_COUNT: outcome.contract_failure_count,
    CDP_NETWORK_ENABLED: outcome.diagnostics_health?.cdp_network_enabled ? 'YES' : 'NO',
    INSTRUMENTATION_ERRORS: outcome.diagnostics_health?.instrumentation_errors ?? null,
    PRIMARY_ERROR_KIND: outcome.primary_error_kind,
    PRIMARY_CONTRACT_FAILURE: outcome.primary_error_kind === 'CONTRACT' ? outcome.primary_error : null,
    PRIMARY_ERROR: outcome.primary_error,
    DIAGNOSTIC_PERSISTENCE_FAILURE: outcome.primary_error_kind === 'DIAGNOSTICS'
      ? outcome.primary_error
      : outcome.secondary_errors?.find((entry) => entry.kind === 'DIAGNOSTICS')?.error || null,
    CLEANUP_FAILURES: outcome.cleanup_errors,
    SECONDARY_ERROR_COUNT: outcome.secondary_error_count,
    SECONDARY_ERROR_KINDS: outcome.secondary_error_kinds,
    DIAGNOSTIC_PERSISTENCE_STATUS: outcome.diagnostic_persistence_status,
    DIAGNOSTIC_HEALTH: outcome.diagnostics_health,
    CLEANUP_STATUS: outcome.cleanup_status,
    BROWSER_CLOSE_STATUS: outcome.browser_close_status,
    SERVER_CLOSE_STATUS: outcome.server_close_status,
  }, null, 2);
}

async function launchDefaultBrowser() {
  return chromium.launch({ headless: true, executablePath: findChrome() });
}

async function main({
  createServer = startStaticServer,
  launchBrowser = launchDefaultBrowser,
  persistDiagnostics = persistRunnerDiagnostics,
} = {}) {
  const args = process.argv.slice(2);
  const outputIndex = args.indexOf('--out');
  if (outputIndex < 0 || !args[outputIndex + 1]) throw new Error('--out <unique-directory> is required');
  const outputDir = path.resolve(args[outputIndex + 1]);
  if (fssync.existsSync(outputDir)) throw new Error(`output directory already exists: ${outputDir}`);
  await fs.mkdir(outputDir, { recursive: true });

  const { server, origin } = await createServer();
  const browser = await launchBrowser();
  const compatibilityServers = [];
  let contractError = null;
  let diagnosticsResult = null;
  let diagnosticsError = null;
  let lifecycleOutcome = null;
  let successPayload = null;
  try {
    if (args.includes('--ipad-interaction-only')) {
      const ipadInteractionRecovery = await captureIpadInteractionRecoveryEvidence(browser, origin, outputDir);
      await fs.writeFile(
        path.join(outputDir, 'e10-vs1f-visual-contract.json'),
        JSON.stringify({
          ok: ipadInteractionRecovery.ok,
          source_root: repoRoot,
          runtime_origin: origin,
          ipadInteractionRecovery,
          failures: ipadInteractionRecovery.failures,
        }, null, 2)
      );
      if (!ipadInteractionRecovery.ok) throw new Error(ipadInteractionRecovery.failures.join('\n'));
      successPayload = { ok: true, output_dir: outputDir, cases: ipadInteractionRecovery.results.length };
    } else {
      const specs = [
      { specName: 'desktop-1920-closed', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-closed-zh.png', layout: 'rail' },
      { specName: 'desktop-1920-closed-en', viewport: { width: 1920, height: 1080 }, lang: 'en', filename: 'desktop-1920x1080-closed-en.png', layout: 'rail' },
      { specName: 'desktop-1920-details', viewport: { width: 1920, height: 1080 }, lang: 'en', filename: 'desktop-1920x1080-drawer-open-en.png', zone: 'k1_5', layout: 'rail', progressDrawerCheck: true, escapeCheck: true, challengeActionCheck: true },
      { specName: 'desktop-1920-current-details', viewport: { width: 1920, height: 1080 }, lang: 'en', filename: 'desktop-1920x1080-current-zone-en.png', zone: 'k21_25', layout: 'rail', progressDrawerCheck: true },
      { specName: 'desktop-1920-current-details-zh', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-current-zone-zh.png', zone: 'k21_25', layout: 'rail', progressDrawerCheck: true },
      { specName: 'desktop-1920-selected-details-zh', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-selected-zone-zh.png', zone: 'k1_5', layout: 'rail', progressDrawerCheck: true },
      { specName: 'desktop-1920-locked-details-en', viewport: { width: 1920, height: 1080 }, lang: 'en', filename: 'desktop-1920x1080-locked-zone-en.png', zone: 'd1_2', layout: 'rail', progressDrawerCheck: true, lockedChallengeCheck: true },
      { specName: 'desktop-1920-locked-details', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-locked-zone-zh.png', zone: 'd1_2', layout: 'rail', progressDrawerCheck: true, lockedChallengeCheck: true },
      { specName: 'desktop-1920-completed-details', viewport: { width: 1920, height: 1080 }, lang: 'en', filename: 'desktop-1920x1080-completed-zone-en.png', zone: 'k26_30', layout: 'rail', progressDrawerCheck: true },
      { specName: 'desktop-1920-skipped-details', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-skipped-zone-zh.png', zone: 'k21_25', layout: 'rail', fixtureMode: 'placement-high', progressDrawerCheck: true },
      { specName: 'desktop-1920-placement-high', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-placement-high-zh.png', layout: 'rail', fixtureMode: 'placement-high' },
      { specName: 'desktop-1440-closed', viewport: { width: 1440, height: 900 }, lang: 'en', filename: 'desktop-1440x900-closed-en.png', layout: 'rail', immersiveViewportCheck: true },
      { specName: 'desktop-1440-closed-zh', viewport: { width: 1440, height: 900 }, lang: 'zh', filename: 'desktop-1440x900-closed-zh.png', layout: 'rail', immersiveViewportCheck: true },
      { specName: 'desktop-1440-panel-open', viewport: { width: 1440, height: 900 }, lang: 'en', filename: 'desktop-1440x900-panel-open-en.png', zone: 'k1_5', layout: 'rail', progressDrawerCheck: true, immersiveViewportCheck: true },
      { specName: 'desktop-1440-settings', viewport: { width: 1440, height: 900 }, lang: 'en', filename: 'desktop-1440x900-settings-en.png', layout: 'rail', openSettings: true, immersiveViewportCheck: true },
      { specName: 'desktop-1440-more', viewport: { width: 1440, height: 900 }, lang: 'zh', filename: 'desktop-1440x900-all-features-zh.png', layout: 'rail', openMore: true, immersiveViewportCheck: true },
      { specName: 'desktop-1440-avatar-fallback', viewport: { width: 1440, height: 900 }, lang: 'zh', filename: 'desktop-1440x900-avatar-fallback-zh.png', layout: 'rail', avatarKey: 'unknown-character', immersiveViewportCheck: true },
      { specName: 'tablet-1180-landscape-closed', viewport: { width: 1180, height: 820 }, lang: 'zh', filename: 'tablet-1180x820-closed-zh.png', layout: 'bottom-dock' },
      { specName: 'tablet-1180-landscape-more', viewport: { width: 1180, height: 820 }, lang: 'en', filename: 'tablet-1180x820-all-features-en.png', layout: 'bottom-dock', openMore: true },
      { specName: 'tablet-1024-landscape-closed', viewport: { width: 1024, height: 768 }, lang: 'zh', filename: 'tablet-1024x768-closed-zh.png', layout: 'bottom-dock' },
      { specName: 'tablet-1024-landscape-details', viewport: { width: 1024, height: 768 }, lang: 'zh', filename: 'tablet-1024x768-drawer-open-zh.png', zone: 'k1_5', layout: 'bottom-dock', progressDrawerCheck: true, escapeCheck: true },
      { specName: 'tablet-820-portrait-more', viewport: { width: 820, height: 1180 }, lang: 'en', filename: 'tablet-820x1180-all-features-en.png', layout: 'bottom-dock', openMore: true },
      { specName: 'tablet-820-portrait-settings', viewport: { width: 820, height: 1180 }, lang: 'zh', filename: 'tablet-820x1180-settings-zh.png', layout: 'bottom-dock', openMore: true, openSettings: true },
      { specName: 'tablet-768-portrait-details', viewport: { width: 768, height: 1024 }, lang: 'zh', filename: 'tablet-768x1024-portrait-lower-card-zh.png', zone: 'k1_5', portraitContext: true, layout: 'bottom-dock' },
      { specName: 'mobile-430-closed', viewport: { width: 430, height: 932 }, lang: 'en', filename: 'mobile-430x932-closed-en.png', layout: 'bottom-dock' },
      { specName: 'mobile-430-more', viewport: { width: 430, height: 932 }, lang: 'en', filename: 'mobile-430x932-all-features-en.png', layout: 'bottom-dock', openMore: true },
      { specName: 'mobile-430-settings', viewport: { width: 430, height: 932 }, lang: 'zh', filename: 'mobile-430x932-settings-zh.png', layout: 'bottom-dock', openMore: true, openSettings: true },
      { specName: 'mobile-390-long-label', viewport: { width: 390, height: 844 }, lang: 'en', filename: 'mobile-390x844-long-label-en.png', zone: 'k1_5', longLabelStress: true, adventureCommandCheck: true, layout: 'bottom-dock' },
      { specName: 'mobile-360-safe-area', viewport: { width: 360, height: 800 }, lang: 'zh', filename: 'mobile-360x800-safe-area-zh.png', safeAreaBottom: 24, layout: 'bottom-dock' },
    ];
      const results = [];
      for (const spec of specs) {
        process.stdout.write(`capture ${spec.specName}\n`);
        results.push(await runCase(browser, origin, outputDir, spec));
      }
      const polishStateEvidence = await capturePolishStateEvidence(browser, origin, outputDir);
      const ipadInteractionRecovery = await captureIpadInteractionRecoveryEvidence(browser, origin, outputDir);
      const legacy = await runLegacyCase(browser, origin, outputDir);
      const lifecycle = await runLifecycleCase(browser, origin);
      const compatibilityBridge = [];
      for (const contractCase of ['missing', 'wrong', 'current-v209']) {
        const fixture = await startStaticServer({ contractCase });
        compatibilityServers.push(fixture.server);
        const fallbackOrigin = contractCase === 'wrong'
          ? fixture.origin.replace('127.0.0.1', 'localhost')
          : fixture.origin;
        compatibilityBridge.push(
          await runCompatibilityFallbackCase(browser, fallbackOrigin, contractCase, outputDir)
        );
      }
    const dockGeometryViewports = results
      .filter((result) => result.viewport.width >= 768 && result.viewport.width > result.viewport.height)
      .map((result) => ({
        spec_name: result.specName,
        viewport: result.viewport,
        language: result.lang,
        geometry: result.snapshot.dockGeometry,
      }));
    const dockGeometryFailures = dockGeometryViewports.flatMap((entry) => {
      const geometry = entry.geometry;
      const failures = [];
      if (geometry.items.length !== 5) failures.push(`${entry.spec_name}: expected five dock items`);
      if (geometry.max_badge_slot_delta_x > 1) failures.push(`${entry.spec_name}: badge-slot X delta ${geometry.max_badge_slot_delta_x}`);
      if (geometry.max_badge_slot_delta_y > 1) failures.push(`${entry.spec_name}: badge-slot Y delta ${geometry.max_badge_slot_delta_y}`);
      if (geometry.max_label_badge_delta_x > 1) failures.push(`${entry.spec_name}: label-badge X delta ${geometry.max_label_badge_delta_x}`);
      if (geometry.max_badge_center_y_spread > 1) failures.push(`${entry.spec_name}: badge Y spread ${geometry.max_badge_center_y_spread}`);
      if (geometry.max_slot_spacing_variance > 1) failures.push(`${entry.spec_name}: slot spacing variance ${geometry.max_slot_spacing_variance}`);
      if (Math.abs(geometry.dock_stage_center_delta_x) > 1) failures.push(`${entry.spec_name}: dock-stage X delta ${geometry.dock_stage_center_delta_x}`);
      return failures;
    });
    const geometryReport = {
      contract: 'e10-bottom-dock-badge-slot-alignment-v1',
      slot_source: {
        asset: 'assets/e10/ui/frames/legacy-dock-frame.webp',
        dimensions: { width: 1280, height: 384 },
        slot_centers: [
          { x: 260, y: 192 }, { x: 450, y: 192 }, { x: 640, y: 192 },
          { x: 830, y: 192 }, { x: 1020, y: 192 },
        ],
      },
      ok: dockGeometryFailures.length === 0,
      max_badge_slot_delta_x: Math.max(0, ...dockGeometryViewports.map((entry) => entry.geometry.max_badge_slot_delta_x)),
      max_badge_slot_delta_y: Math.max(0, ...dockGeometryViewports.map((entry) => entry.geometry.max_badge_slot_delta_y)),
      max_badge_center_y_spread: Math.max(0, ...dockGeometryViewports.map((entry) => entry.geometry.max_badge_center_y_spread)),
      max_slot_spacing_variance: Math.max(0, ...dockGeometryViewports.map((entry) => entry.geometry.max_slot_spacing_variance)),
      max_label_badge_delta_x: Math.max(0, ...dockGeometryViewports.map((entry) => entry.geometry.max_label_badge_delta_x)),
      max_dock_stage_center_delta_x: Math.max(0, ...dockGeometryViewports.map((entry) => Math.abs(entry.geometry.dock_stage_center_delta_x))),
      interaction_states: polishStateEvidence.dockInteractionGeometry,
      viewports: dockGeometryViewports,
      failures: dockGeometryFailures,
    };
    await fs.writeFile(path.join(outputDir, 'bottom-dock-geometry.json'), JSON.stringify(geometryReport, null, 2));
    const failures = results.flatMap(assertCase).concat(
      polishStateEvidence.browserErrors.map((error) => `polish state evidence: ${error}`),
      Object.entries(polishStateEvidence.dockInteractionGeometry || {}).flatMap(([state, measurement]) => {
        const failures = [];
        for (const key of ['badge_center_x', 'badge_center_y', 'slot_center_x', 'slot_center_y', 'label_center_x']) {
          if (measurement.deltas[key] > 1) failures.push(`bottom-dock ${state}: ${key} moved ${measurement.deltas[key]}px`);
        }
        return failures;
      }),
      dockGeometryFailures,
      legacy.failures,
      lifecycle.failures,
      ipadInteractionRecovery.failures,
      compatibilityBridge.flatMap((result) => result.failures),
    );
    const report = {
      ok: failures.length === 0,
      source_root: repoRoot,
      runtime_origin: origin,
      results,
      polishStateEvidence,
      legacy,
      lifecycle,
      ipadInteractionRecovery,
      compatibilityBridge,
      failures,
    };
      await fs.writeFile(path.join(outputDir, 'e10-vs1f-visual-contract.json'), JSON.stringify(report, null, 2));
      if (failures.length) throw new Error(failures.join('\n'));
      successPayload = {
        ok: true,
        output_dir: outputDir,
        screenshots: results.length + 1 + polishStateEvidence.captures.length
          + ipadInteractionRecovery.results.reduce((count, result) => count + 1 + (result.journey ? 1 : 0) + (result.portrait ? 1 : 0), 0),
      };
    }
  } catch (error) {
    contractError = error;
  } finally {
    const lifecycleResult = await finalizeRunnerLifecycle({
      contractError,
      successPayload,
      browser,
      server,
      compatibilityServers,
      outputDir,
      origin,
      persistDiagnostics,
    });
    diagnosticsResult = lifecycleResult.diagnosticsResult;
    diagnosticsError = lifecycleResult.diagnosticsError;
    lifecycleOutcome = lifecycleResult.outcome;
    if (lifecycleResult.error) throw lifecycleResult.error;
  }
  process.stdout.write(JSON.stringify({
    ...successPayload,
    ...lifecycleOutcome,
    diagnostics_health: diagnosticsResult.summary,
  }, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(formatRunnerFailureSummary(error));
    process.exitCode = 1;
  });
}
