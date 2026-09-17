import fssync from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..', '..');
const widgetPath = path.join(repoRoot, 'sgf_report_widget.js');

function chromePath() {
  const candidates = [process.env.CHROME_BIN,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].filter(Boolean);
  const found = candidates.find((candidate) => fssync.existsSync(candidate));
  if (!found) throw new Error('No Chrome/Edge executable found; set CHROME_BIN.');
  return found;
}

async function inspectScenario(browser, { label, isAdmin, mode }) {
  const context = await browser.newContext({ viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  page.on('pageerror', (error) => console.error(`${label} pageerror: ${error.stack || error.message}`));
  await page.setContent('<!doctype html><html><body data-sgf-report-surface="main_practice"><div id="board-col"></div></body></html>');
  await page.evaluate(({ admin }) => {
    window.__p0FetchUrls = [];
    window.fetch = async (input) => {
      const url = String(input);
      window.__p0FetchUrls.push(url);
      if (url === '/api/auth/me') {
        return new Response(JSON.stringify({ logged_in: true, user_id: 991111, is_admin: admin }), { status: 200 });
      }
      if (url === '/api/admin/sgf-workbench/bootstrap') {
        return new Response(JSON.stringify(admin ? {
          ok: true,
          security: { csrf_header: 'X-CSRF', csrf_token: 'test-token' },
        } : { error: 'forbidden' }), { status: admin ? 200 : 403 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    };
  }, { admin: isAdmin });
  await page.addScriptTag({ path: widgetPath });
  await page.evaluate((scenario) => {
    window.SGFReportWidget.setContext({
      question_id: 431,
      gameplay_surface: scenario.mode,
      surface: 'main_practice',
    });
  }, { mode });
  if (isAdmin) {
    await page.waitForFunction(() => document.querySelectorAll('[data-sgf-inline-review-bar]').length === 1, null, { timeout: 5000 }).catch(async (error) => {
      const timeoutState = await page.evaluate(() => ({
        fetchUrls: window.__p0FetchUrls,
        templates: document.querySelectorAll('template[data-sgf-admin-controls-template]').length,
        html: document.querySelector('.sgf-report-widget')?.innerHTML.slice(0, 1000),
      }));
      console.error(`${label} timeout state: ${JSON.stringify(timeoutState)}`);
      throw error;
    });
  }
  const result = await page.evaluate(() => ({
    liveToolbarCount: document.querySelectorAll('[data-sgf-inline-review-bar]').length,
    liveActionCount: document.querySelectorAll('[data-sgf-inline-action]').length,
    adminToolsCount: document.querySelectorAll('[data-sgf-admin-tools]').length,
    templateCount: document.querySelectorAll('template[data-sgf-admin-controls-template]').length,
    toolbarHidden: document.querySelector('[data-sgf-inline-review-bar]')?.hidden ?? null,
    normalReportControlCount: document.querySelectorAll('[data-sgf-report-trigger]').length,
  }));
  await context.close();
  return { label, isAdmin, mode, ...result };
}

const browser = await chromium.launch({ headless: true, executablePath: chromePath() });
const results = [];
try {
  for (const mode of ['adventure', 'practice']) {
    results.push(await inspectScenario(browser, { label: `non-admin ${mode}`, isAdmin: false, mode }));
    results.push(await inspectScenario(browser, { label: `admin ${mode}`, isAdmin: true, mode }));
  }
} finally {
  await browser.close();
}

const failures = [];
for (const result of results) {
  const expectedAdmin = result.isAdmin;
  if (expectedAdmin) {
    if (result.liveToolbarCount !== 1 || result.liveActionCount !== 5 || result.adminToolsCount !== 1
      || result.templateCount !== 0 || result.toolbarHidden !== false) {
      failures.push(`${result.label}: admin controls were not mounted visibly after admin bootstrap: ${JSON.stringify(result)}`);
    }
  } else if (result.liveToolbarCount !== 0 || result.liveActionCount !== 0 || result.adminToolsCount !== 0
    || result.templateCount !== 2 || result.normalReportControlCount !== 1) {
    failures.push(`${result.label}: privileged controls leaked into non-admin DOM: ${JSON.stringify(result)}`);
  }
}
if (failures.length) throw new Error(failures.join('\n'));
console.log('P0 non-admin review toolbar browser contract PASS: Adventure/Practice x non-admin/admin');
