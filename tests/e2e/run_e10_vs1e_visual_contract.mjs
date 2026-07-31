import fs from 'node:fs/promises';
import fssync from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
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
}));

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

async function startStaticServer({ contractCase = 'target', indexOverridePath = null } = {}) {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url, 'http://127.0.0.1');
      const relative = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
      const absolute = path.resolve(repoRoot, `.${relative}`);
      if (!absolute.startsWith(repoRoot)) throw new Error('path outside repository');
      const stat = await fs.stat(absolute).catch(() => null);
      if (!stat?.isFile()) {
        response.writeHead(404);
        response.end('not found');
        return;
      }
      if (relative === '/index.html' && (contractCase !== 'target' || indexOverridePath)) {
        let html = await fs.readFile(indexOverridePath || absolute, 'utf8');
        if (contractCase === 'missing') {
          html = html.replace(staticContractMarker, '');
        } else if (contractCase === 'wrong') {
          html = html.replace(
            staticContractMarker,
            '<meta name="go-odyssey-static-contract" content="v209-e10-world-stage-v1d1-i18n-a11y">'
          );
        } else if (!indexOverridePath) {
          throw new Error(`unknown contract case: ${contractCase}`);
        }
        response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        response.end(html);
        return;
      }
      response.writeHead(200, { 'Content-Type': contentTypeFor(absolute) });
      fssync.createReadStream(absolute).pipe(response);
    } catch (error) {
      response.writeHead(500);
      response.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

async function runCompatibilityFallbackCase(browser, origin, contractCase, outputDir) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
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
    shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
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
    vs1fPlayerCount: document.querySelectorAll('[data-player-location], .e10-current-hero').length,
    vs1fIconCount: document.querySelectorAll('[data-e10-vs1f-icon], .e9-dock__icon').length,
    nav32Count: document.querySelectorAll('.e9-nav__icon[viewBox="0 0 32 32"]').length,
    oversizedBlackSvgCount: [...document.querySelectorAll('svg path, svg polygon')]
      .filter((shape) => {
        const style = getComputedStyle(shape);
        const box = shape.getBoundingClientRect();
        return style.fill === 'rgb(0, 0, 0)' && box.width * box.height > 4096;
      }).length,
  }));
  const screenshot = await saveViewportScreenshot(
    page,
    outputDir,
    `compatibility-${contractCase}-vs1d-fallback-1440x900-en.png`
  );
  await page.close();
  const failures = [];
  if (snapshot.activeShell !== 'e9') failures.push(`${contractCase}: E9 shell did not mount`);
  if (snapshot.bodySkin !== null || snapshot.shellSkin !== null) {
    failures.push(`${contractCase}: VS1E skin was enabled without the exact static marker`);
  }
  if (snapshot.nodeCount !== 10) failures.push(`${contractCase}: VS1D node rendering is incomplete`);
  if (snapshot.plaqueCount !== 0 || snapshot.selectedCount !== 0 || !snapshot.primaryCtaHidden) {
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
    || snapshot.vs1fPlayerCount !== 0
    || snapshot.vs1fIconCount !== 0
    || snapshot.nav32Count !== 0
    || snapshot.oversizedBlackSvgCount !== 0
  ) failures.push(`${contractCase}: VS1F SVG/mask/landmark DOM leaked into fallback`);
  if (browserErrors.length) failures.push(`${contractCase}: browser errors ${JSON.stringify(browserErrors)}`);
  return { contractCase, screenshot, snapshot, browserErrors, failures };
}

function apiResponse(pathname, method) {
  if (pathname === '/api/auth/me') {
    return {
      logged_in: true,
      user_id: 42,
      username: 'visual_fixture',
      nickname: '晨星騎士',
      display_name: '晨星騎士',
      is_admin: false,
      is_premium: false,
      needs_onboarding_choice: false,
      tour_done: true,
      elo_rating: 1450,
      newbie_quest_eligible: false,
    };
  }
  if (pathname === '/api/skills/profile') return { display_name: '晨星騎士', rank_level: 'LV12' };
  if (pathname === '/api/user/coins') return { coins: 123456 };
  if (pathname === '/api/adventure/bootstrap') return { zones };
  if (pathname === '/api/daily-challenge/today') return { submitted: false };
  if (pathname === '/api/srs/due') return { count: 17, due: [] };
  if (pathname === '/api/mistakes/stats') return { total: 28, corrected: 9, worst5: [] };
  if (pathname === '/api/questions') return [];
  if (pathname === '/api/subscription/status') return { daily_limit: 20, remaining: 10 };
  if (pathname === '/api/analytics/events' || method === 'POST') return null;
  return { ok: true };
}

async function installApiFixture(page, browserErrors) {
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors.push({ kind: 'console', text: message.text() });
  });
  page.on('pageerror', (error) => browserErrors.push({ kind: 'pageerror', text: String(error) }));
  page.on('requestfailed', (request) => {
    browserErrors.push({ kind: 'requestfailed', text: `${request.method()} ${request.url()}` });
  });
  page.on('response', (response) => {
    if (response.status() >= 500) {
      browserErrors.push({ kind: 'http5xx', text: `${response.status()} ${response.url()}` });
    }
  });
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const payload = apiResponse(new URL(request.url()).pathname, request.method());
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
    return {
      activeShell: document.body.getAttribute('data-adventure-shell-active'),
      skin: document.body.getAttribute('data-e10-visual-skin'),
      shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
      lang: window.I18n?.getLang?.(),
      nodeCount: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
      landmarkCount: document.querySelectorAll('#e9-world-stage-zones .e10-zone-landmark').length,
      drawerLandmarkVisible: isVisible(document.querySelector('#e10-drawer-zone-landmark')),
      portraitLandmarkVisible: isVisible(document.querySelector('#e9-world-stage-details-landmark')),
      playerLocationCount: document.querySelectorAll('#e9-world-stage-zones [data-player-location="true"]').length,
      playerLocationZone: document.querySelector('#e9-world-stage-zones [data-player-location="true"]')?.getAttribute('data-zone'),
      selectedZone: document.querySelector('#e9-world-stage-zones .is-selected')?.getAttribute('data-zone'),
      visibleHeroCount: [
        document.querySelector('#e9-world-stage-player'),
        ...document.querySelectorAll('.e10-current-hero'),
      ].filter(isVisible).length,
      landmarkRequestCount: performance.getEntriesByType('resource')
        .filter((entry) => entry.name.includes('/assets/maps/e10-vs1f-landmarks/')).length,
      legacyVisible: Array.from(document.querySelectorAll(
        '#welcome-state > .guild-hall-hero, #welcome-state > .guild-entry-grid, #skill-map, #welcome-state > .home-left-col, #welcome-state > .home-report'
      )).some((element) => !element.hidden),
      map: roundRect(rect('#e9-map-stage')),
      stage: roundRect(rect('#adventure-stage')),
      nav: roundRect(rect('#left-nav')),
      drawer: roundRect(rect('#e9-right-drawer-panel')),
      primaryCta: roundRect(rect('#e9-world-stage-primary-cta:not([hidden])')),
      progressOverlay: roundRect(rect('#e9-world-stage-status')),
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
      minimumTarget: allTargets.reduce((smallest, element) => {
        const target = element.getBoundingClientRect();
        return Math.min(smallest, target.width, target.height);
      }, Number.POSITIVE_INFINITY),
      duplicateIds: [...new Set(duplicateIds)],
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
  await installApiFixture(page, browserErrors);
  const url = `${origin}/index.html?lang=${spec.lang}&${shellFlags}`;
  await page.goto(url, { waitUntil: 'networkidle' });
  await waitForShell(page);

  if (spec.safeAreaBottom) {
    await page.locator('#e9-adventure-shell').evaluate((shell, safeAreaBottom) => {
      shell.style.setProperty('--e10-safe-area-bottom', `${safeAreaBottom}px`);
    }, spec.safeAreaBottom);
  }

  if (spec.longLabelStress) {
    await page.locator('.e9-nav__item > span').evaluateAll((labels) => {
      const stressLabels = [
        'Hero',
        'Equipment',
        'Backpack',
        'Go Spirit Companion',
        'Shop',
        'Adventure',
      ];
      labels.forEach((label, index) => {
        label.textContent = stressLabels[index];
      });
    });
  }

  let detailMapBefore = null;
  if (spec.zone) {
    detailMapBefore = await runtimeSnapshot(page);
    const zone = page.locator(`[data-zone="${spec.zone}"]`);
    if (await zone.count() !== 1) throw new Error(`missing unique zone ${spec.zone}`);
    await zone.scrollIntoViewIfNeeded();
    if (await zone.isEnabled()) {
      // Dispatch the real DOM activation without Playwright waiting for the
      // content-driven inline expansion to become geometrically stable.
      await zone.evaluate((element) => element.click());
    }
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
    await trigger.click();
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

  const snapshot = await runtimeSnapshot(page);
  const screenshot = await saveViewportScreenshot(page, outputDir, spec.filename);
  await page.close();
  return { ...spec, screenshot, beforeOpen, afterOpen, escaped, detailMapBefore, adventureCommand, snapshot, browserErrors };
}

function assertCase(result) {
  const failures = [];
  const { snapshot, specName, browserErrors } = result;
  if (snapshot.activeShell !== 'e9') failures.push(`${specName}: E9 shell not active`);
  if (snapshot.skin !== 'immersive-rpg' || snapshot.shellSkin !== 'immersive-rpg') {
    failures.push(`${specName}: RPG skin marker missing`);
  }
  if (snapshot.nodeCount !== 10) failures.push(`${specName}: node count ${snapshot.nodeCount}`);
  if (snapshot.plaqueCount !== 10 || snapshot.plaqueStatusCount !== 10) {
    failures.push(`${specName}: persistent map plaques are incomplete`);
  }
  if (snapshot.legacyVisible) failures.push(`${specName}: Legacy shell remains visible`);
  if (snapshot.horizontalOverflow !== 0) failures.push(`${specName}: horizontal overflow ${snapshot.horizontalOverflow}`);
  if (snapshot.minimumTarget < 44) failures.push(`${specName}: interactive target below 44px (${snapshot.minimumTarget})`);
  if (snapshot.duplicateIds.length) failures.push(`${specName}: duplicate IDs ${snapshot.duplicateIds.join(', ')}`);
  if (snapshot.bossAnchorsVisibility !== 'hidden') failures.push(`${specName}: Boss anchors visible`);
  if (snapshot.aria.drawerControls !== 'e9-right-drawer-panel') failures.push(`${specName}: aria-controls drift`);
  if (!snapshot.aria.mapLabel) failures.push(`${specName}: map accessible label missing`);
  if (snapshot.playerLocationCount !== 1 || snapshot.visibleHeroCount !== 1) {
    failures.push(`${specName}: authoritative player marker count ${snapshot.playerLocationCount}/${snapshot.visibleHeroCount}`);
  }
  if (snapshot.playerLocationZone !== 'k21_25') {
    failures.push(`${specName}: authoritative player location ${snapshot.playerLocationZone}`);
  }
  if (result.detailMapBefore && (
    result.detailMapBefore.playerLocationZone !== snapshot.playerLocationZone
    || result.detailMapBefore.visibleHeroCount !== snapshot.visibleHeroCount
  )) failures.push(`${specName}: selection moved the player marker`);
  if (browserErrors.length) failures.push(`${specName}: browser errors ${JSON.stringify(browserErrors)}`);
  if (result.beforeOpen && result.afterOpen) {
    const before = result.beforeOpen.map;
    const after = result.afterOpen.map;
    for (const key of ['left', 'right', 'width', 'height']) {
      if (before[key] !== after[key]) failures.push(`${specName}: drawer changed map ${key}`);
    }
  }
  if (result.progressDrawerCheck && (
    snapshot.drawerExpanded !== 'true'
    || !snapshot.drawer
    || snapshot.drawer.width <= 0
    || snapshot.drawer.height <= 0
  )) failures.push(`${specName}: open screenshot does not contain the quest drawer`);
  if (result.escapeCheck && result.escaped !== 'false') failures.push(`${specName}: Escape did not close drawer`);
  if (result.layout === 'rail') {
    if (snapshot.landmarkCount !== 0) {
      failures.push(`${specName}: full landmark art duplicated the Desktop map`);
    }
    const expectedLandmarkRequests = result.zone ? 1 : 0;
    if (snapshot.landmarkRequestCount !== expectedLandmarkRequests) {
      failures.push(`${specName}: Desktop landmark requests ${snapshot.landmarkRequestCount}`);
    }
    if (!snapshot.nav || !snapshot.map || snapshot.nav.right > snapshot.map.left) {
      failures.push(`${specName}: vertical navigation rail is not left of map`);
    }
    if (!snapshot.primaryCta || !snapshot.progressOverlay) {
      failures.push(`${specName}: closed-state map CTA/progress overlay missing`);
    }
    if (result.zone && !snapshot.drawerLandmarkVisible) {
      failures.push(`${specName}: selected landmark is missing from the quest panel`);
    }
  }
  if (result.layout === 'bottom-dock') {
    if (snapshot.navPosition !== 'fixed' && snapshot.navSlotPosition !== 'fixed') {
      failures.push(`${specName}: navigation is not a fixed bottom dock`);
    }
    if (!snapshot.navColumns || snapshot.navColumns.split(' ').length !== 6) {
      failures.push(`${specName}: bottom dock is not one six-item row`);
    }
    if (result.viewport.width < 768) {
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
    }
    if (snapshot.bottomDockVisible) failures.push(`${specName}: secondary dock competes with primary navigation`);
    if (snapshot.navVisualKeys.join(',') !== 'adventure,hero,equipment,go_spirit,backpack,shop') {
      failures.push(`${specName}: mobile navigation order ${snapshot.navVisualKeys.join(',')}`);
    }
    if (result.viewport.width >= 768 && (!snapshot.primaryCta || !snapshot.progressOverlay)) {
      failures.push(`${specName}: portrait map CTA/progress overlay missing`);
    }
  }
  if (result.openMore && !result.openSettings && !result.snapshot.moreOverlayVisible) failures.push(`${specName}: All Features did not open`);
  if (result.openSettings && !result.snapshot.settingsOverlayVisible) failures.push(`${specName}: Settings did not open`);
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
  await page.goto(
    `${origin}/index.html?lang=zh&e9Shell=1&e9WorldStage=1&host=godokoro.com`,
    { waitUntil: 'networkidle' }
  );
  await page.locator('#welcome-state').waitFor({ state: 'visible' });
  const snapshot = await page.evaluate(() => ({
    activeShell: document.body.getAttribute('data-adventure-shell-active'),
    skin: document.body.getAttribute('data-e10-visual-skin'),
    shellHidden: document.querySelector('#e9-adventure-shell')?.hidden,
    worldNodes: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
    drawerVisible: !!document.querySelector('#e9-right-drawer-toggle'),
  }));
  const screenshot = await saveViewportScreenshot(page, outputDir, 'legacy-nonallowlisted-1440x900-zh.png');
  await page.close();
  const failures = [];
  if (snapshot.activeShell !== 'legacy') failures.push('Legacy: query/host activated E9 shell');
  if (snapshot.skin !== null) failures.push('Legacy: RPG skin marker leaked');
  if (!snapshot.shellHidden) failures.push('Legacy: E9 shell is not hidden');
  if (snapshot.worldNodes !== 0 || snapshot.drawerVisible) failures.push('Legacy: World Stage UI leaked');
  if (browserErrors.length) failures.push(`Legacy: browser errors ${JSON.stringify(browserErrors)}`);
  return { specName: 'legacy-nonallowlisted', screenshot, snapshot, browserErrors, failures };
}

async function runLifecycleCase(browser, origin) {
  const page = await browser.newPage({ viewport: { width: 1024, height: 768 } });
  const browserErrors = [];
  await installApiFixture(page, browserErrors);
  await page.goto(`${origin}/index.html?lang=en&${shellFlags}`, { waitUntil: 'networkidle' });
  await waitForShell(page);
  const beforeGeneration = await page.evaluate(() => window.E9.getLifecycleGeneration());
  const destroyed = await page.evaluate(() => {
    window.E9.destroyShell();
    return {
      activeShell: document.body.getAttribute('data-adventure-shell-active'),
      bodySkin: document.body.getAttribute('data-e10-visual-skin'),
      shellSkin: document.querySelector('#e9-adventure-shell')?.getAttribute('data-e10-visual-skin'),
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
    || destroyed.shellSkin !== null
    || !destroyed.shellHidden
    || destroyed.mountedSlots !== 0
  ) failures.push('lifecycle: destroy did not clean shell and skin ownership');
  if (
    remounted.activeShell !== 'e9'
    || remounted.skin !== 'immersive-rpg'
    || remounted.nodeCount !== 10
    || remounted.duplicateIds.length
    || afterGeneration <= beforeGeneration
  ) failures.push('lifecycle: clean remount did not converge');
  if (browserErrors.length) failures.push(`lifecycle: browser errors ${JSON.stringify(browserErrors)}`);
  return { beforeGeneration, afterGeneration, destroyed, remounted, browserErrors, failures };
}

async function main() {
  const args = process.argv.slice(2);
  const outputIndex = args.indexOf('--out');
  if (outputIndex < 0 || !args[outputIndex + 1]) throw new Error('--out <unique-directory> is required');
  const outputDir = path.resolve(args[outputIndex + 1]);
  const currentIndexArgument = args.indexOf('--current-index');
  const currentIndexPath = currentIndexArgument >= 0
    ? path.resolve(args[currentIndexArgument + 1] || '')
    : null;
  if (currentIndexArgument >= 0 && !fssync.existsSync(currentIndexPath)) {
    throw new Error(`--current-index does not exist: ${currentIndexPath}`);
  }
  if (fssync.existsSync(outputDir)) throw new Error(`output directory already exists: ${outputDir}`);
  await fs.mkdir(outputDir, { recursive: true });

  const { server, origin } = await startStaticServer();
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  const compatibilityServers = [];
  try {
    const specs = [
      { specName: 'desktop-1920-closed', viewport: { width: 1920, height: 1080 }, lang: 'zh', filename: 'desktop-1920x1080-closed-zh.png', layout: 'rail' },
      { specName: 'desktop-1920-details', viewport: { width: 1920, height: 1080 }, lang: 'en', filename: 'desktop-1920x1080-drawer-open-en.png', zone: 'k1_5', layout: 'rail', progressDrawerCheck: true, escapeCheck: true },
      { specName: 'desktop-1440-settings', viewport: { width: 1440, height: 900 }, lang: 'en', filename: 'desktop-1440x900-settings-en.png', layout: 'rail', openSettings: true },
      { specName: 'tablet-1180-landscape-closed', viewport: { width: 1180, height: 820 }, lang: 'zh', filename: 'tablet-1180x820-closed-zh.png', layout: 'bottom-dock' },
      { specName: 'tablet-1180-landscape-more', viewport: { width: 1180, height: 820 }, lang: 'en', filename: 'tablet-1180x820-all-features-en.png', layout: 'bottom-dock', openMore: true },
      { specName: 'tablet-1024-landscape-details', viewport: { width: 1024, height: 768 }, lang: 'zh', filename: 'tablet-1024x768-drawer-open-zh.png', zone: 'k1_5', layout: 'bottom-dock', progressDrawerCheck: true, escapeCheck: true },
      { specName: 'tablet-820-portrait-more', viewport: { width: 820, height: 1180 }, lang: 'en', filename: 'tablet-820x1180-all-features-en.png', layout: 'bottom-dock', openMore: true },
      { specName: 'tablet-768-portrait-details', viewport: { width: 768, height: 1024 }, lang: 'zh', filename: 'tablet-768x1024-portrait-drawer-open-zh.png', zone: 'k1_5', portraitContext: true, layout: 'bottom-dock', progressDrawerCheck: true, escapeCheck: true },
      { specName: 'mobile-430-more', viewport: { width: 430, height: 932 }, lang: 'en', filename: 'mobile-430x932-all-features-en.png', layout: 'bottom-dock', openMore: true },
      { specName: 'mobile-430-settings', viewport: { width: 430, height: 932 }, lang: 'zh', filename: 'mobile-430x932-settings-zh.png', layout: 'bottom-dock', openMore: true, openSettings: true },
      { specName: 'mobile-390-long-label', viewport: { width: 390, height: 844 }, lang: 'en', filename: 'mobile-390x844-long-label-en.png', longLabelStress: true, adventureCommandCheck: true, layout: 'bottom-dock' },
      { specName: 'mobile-360-safe-area', viewport: { width: 360, height: 800 }, lang: 'zh', filename: 'mobile-360x800-safe-area-zh.png', safeAreaBottom: 24, layout: 'bottom-dock' },
    ];
    const results = [];
    for (const spec of specs) {
      process.stdout.write(`capture ${spec.specName}\n`);
      results.push(await runCase(browser, origin, outputDir, spec));
    }
    const legacy = await runLegacyCase(browser, origin, outputDir);
    const lifecycle = await runLifecycleCase(browser, origin);
    const compatibilityBridge = [];
    for (const contractCase of ['missing', 'wrong']) {
      const fixture = await startStaticServer({ contractCase });
      compatibilityServers.push(fixture.server);
      const fallbackOrigin = contractCase === 'wrong'
        ? fixture.origin.replace('127.0.0.1', 'localhost')
        : fixture.origin;
      compatibilityBridge.push(
        await runCompatibilityFallbackCase(browser, fallbackOrigin, contractCase, outputDir)
      );
    }
    if (currentIndexPath) {
      const fixture = await startStaticServer({
        contractCase: 'current-v209',
        indexOverridePath: currentIndexPath,
      });
      compatibilityServers.push(fixture.server);
      compatibilityBridge.push(
        await runCompatibilityFallbackCase(browser, fixture.origin, 'current-v209', outputDir)
      );
    }
    const failures = results.flatMap(assertCase).concat(
      legacy.failures,
      lifecycle.failures,
      compatibilityBridge.flatMap((result) => result.failures),
    );
    const report = {
      ok: failures.length === 0,
      source_root: repoRoot,
      runtime_origin: origin,
      results,
      legacy,
      lifecycle,
      compatibilityBridge,
      failures,
    };
    await fs.writeFile(path.join(outputDir, 'e10-vs1f-visual-contract.json'), JSON.stringify(report, null, 2));
    if (failures.length) throw new Error(failures.join('\n'));
    process.stdout.write(JSON.stringify({ ok: true, output_dir: outputDir, screenshots: results.length + 1 }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
    for (const compatibilityServer of compatibilityServers) {
      await new Promise((resolve) => compatibilityServer.close(resolve));
    }
  }
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
