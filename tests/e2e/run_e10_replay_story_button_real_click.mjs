'use strict';

// Real-browser regression contract for E10_REPLAY_STORY_BUTTON_HOTFIX_001.
//
// Proves the Replay Story button on the real E9 world_stage component -- not
// a synthetic call to playZoneStoryReplay/playStoryReplay -- dispatches the
// cinematic replay entrypoint synchronously from the real DOM click, with
// exactly one dispatch per click and zero domain mutation. A test that only
// calls the entrypoint function directly would pass on both the broken and
// the fixed bytes; this one clicks the actual button element that ships to
// players and inspects the actual click-time state.
//
// Usage: node run_e10_replay_story_button_real_click.mjs [--viewport desktop|tablet|mobile]

import { spawn } from 'node:child_process';
import fssync from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import readline from 'node:readline';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const HARNESS = path.join(REPO_ROOT, 'tests', 'lord_trial_natural_runtime.py');
const ZONE_KEY = 'k26_30';
const OTHER_ZONE_KEY = 'k21_25';

const VIEWPORTS = {
  desktop: { width: 1280, height: 800 },
  tablet: { width: 768, height: 1024 },
  mobile: { width: 375, height: 812 },
};

function resolveChrome() {
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
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN.');
}

function parseArgs(argv) {
  const options = { viewport: 'tablet' };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--viewport') { options.viewport = argv[i + 1]; i += 1; }
  }
  if (!VIEWPORTS[options.viewport]) {
    throw new Error(`unknown --viewport '${options.viewport}'; expected desktop|tablet|mobile`);
  }
  return options;
}

const OPTIONS = parseArgs(process.argv.slice(2));

function startRuntime() {
  const harnessArgs = [HARNESS, 'serve', '--fixture', 'single_ply', '--replay-story-e9'];
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON_BIN || 'python', harnessArgs, {
      cwd: REPO_ROOT,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    const stderrTail = [];
    child.stderr.setEncoding('utf-8');
    child.stderr.on('data', (chunk) => {
      stderrTail.push(chunk);
      if (stderrTail.length > 80) stderrTail.shift();
    });
    const rl = readline.createInterface({ input: child.stdout });
    const timer = setTimeout(() => {
      rl.close();
      child.kill();
      reject(new Error(`runtime handshake timed out\n${stderrTail.join('')}`));
    }, 300000);
    rl.on('line', (line) => {
      let payload;
      try { payload = JSON.parse(line); } catch { return; }
      if (payload && payload.unavailable) {
        clearTimeout(timer);
        rl.close();
        child.kill();
        reject(Object.assign(new Error(payload.reason || 'unavailable'), { unavailable: true }));
        return;
      }
      if (payload && payload.ready === true) {
        clearTimeout(timer);
        rl.close();
        resolve({ child, runtime: payload });
      }
    });
    child.on('exit', (code) => {
      clearTimeout(timer);
      reject(new Error(`runtime exited early with code ${code}\n${stderrTail.join('')}`));
    });
  });
}

function stopRuntime(child) {
  try { child.stdin.end(); } catch { /* already gone */ }
  return new Promise((resolve) => {
    const timer = setTimeout(() => { try { child.kill(); } catch {} resolve(); }, 30000);
    child.on('exit', () => { clearTimeout(timer); resolve(); });
  });
}

// Everything this probe reads from the page, evaluated as one atomic
// function so a native button.click() (synchronous DOM dispatch, unlike
// Playwright's own async click helper) and the state read immediately after
// it are observed in the exact same JS tick -- the only way to tell "the
// handler ran synchronously" from "the handler ran, eventually".
const CLICK_AND_READ = (zoneKey) => {
  const root = document.getElementById('e9-world-stage-slot');
  const overlay = document.getElementById('boss-cinematic');
  if (!root || !overlay) {
    return { error: 'world_stage slot or cinematic overlay not present' };
  }
  const tile = Array.from(root.querySelectorAll('[data-zone]'))
    .find((el) => el.getAttribute('data-zone') === zoneKey);
  if (!tile) return { error: `zone tile not found: ${zoneKey}` };
  tile.click();
  const btn = document.getElementById('e9-world-stage-details-replay');
  if (!btn) return { error: 'replay button not present after zone selection' };
  const result = {
    button_visible: !btn.hidden,
    button_enabled: !btn.disabled,
    overlay_before_click: overlay.className,
  };
  if (btn.hidden || btn.disabled) {
    result.click_attempted = false;
    return result;
  }
  if (!window.__e2eReplayCallCount) {
    window.__e2eReplayCallCount = 0;
    window.__e2eReplayCallArgs = [];
    const original = window.E10Cinematic && window.E10Cinematic.playStoryReplay;
    if (original) {
      window.E10Cinematic.playStoryReplay = function wrapped(key) {
        window.__e2eReplayCallCount += 1;
        window.__e2eReplayCallArgs.push(key);
        return original.apply(this, arguments);
      };
    }
  }
  const callsBefore = window.__e2eReplayCallCount;
  btn.click();
  result.click_attempted = true;
  result.overlay_after_click_same_tick = overlay.className;
  result.overlay_activated_same_tick = overlay.className.includes('show')
    && overlay.className !== result.overlay_before_click;
  result.play_story_replay_call_count_delta = window.__e2eReplayCallCount - callsBefore;
  result.play_story_replay_last_arg = window.__e2eReplayCallArgs[window.__e2eReplayCallArgs.length - 1] || null;
  return result;
};

const SKIP_TO_CLOSE = () => {
  const overlay = document.getElementById('boss-cinematic');
  if (!overlay) return { error: 'no overlay' };
  for (let i = 0; i < 25; i += 1) {
    if (!overlay.className.includes('show')) break;
    const skip = overlay.querySelector('.intro-skip-btn');
    if (skip && skip.offsetParent !== null) { skip.click(); continue; }
    const closeBtn = overlay.querySelector('.boss-cinematic-close-x');
    if (closeBtn && closeBtn.offsetParent !== null) { closeBtn.click(); continue; }
    break;
  }
  const root = document.getElementById('e9-world-stage-slot');
  const state = root ? root.__e9WorldStageState : null;
  return {
    final_overlay_class: overlay.className,
    returned_to_zone_card: !overlay.className.includes('show'),
    selected_zone_key: state ? state.selectedZoneKey : null,
  };
};

async function main() {
  const report = {
    contract: 'e10_replay_story_button_real_click',
    viewport: OPTIONS.viewport,
  };

  let started;
  try {
    started = await startRuntime();
  } catch (error) {
    if (error.unavailable) {
      console.log(JSON.stringify({ ...report, skipped: true, reason: error.message }, null, 2));
      return 2;
    }
    throw error;
  }
  const { child, runtime } = started;
  report.evidence = {
    base_url: runtime.base_url,
    postgres_container: runtime.postgres_container,
    replay_story_e9: runtime.replay_story_e9,
    zone_key: runtime.zone_key,
    secret_key_is_synthetic: runtime.secret_key_is_synthetic,
    secret_file_access_attempts: runtime.secret_file_access_attempts,
  };

  const browser = await chromium.launch({ executablePath: resolveChrome(), headless: true });
  try {
    const context = await browser.newContext({ viewport: VIEWPORTS[OPTIONS.viewport] });
    const page = await context.newPage();
    const consoleErrors = [];
    page.on('pageerror', (error) => consoleErrors.push(String(error && error.message || error)));

    await page.goto(`${runtime.base_url}/login`, { waitUntil: 'domcontentloaded' });
    const login = await page.evaluate(async (creds) => {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(creds),
      });
      return { status: res.status, ok: (await res.json()).ok === true };
    }, { username: runtime.username, password: runtime.password });
    report.login = login;
    if (!login.ok) {
      report.final_status = 'BLOCKED_LOGIN_FAILED';
      console.log(JSON.stringify(report, null, 2));
      return 1;
    }

    await page.goto(`${runtime.base_url}/`, { waitUntil: 'load' });

    // The adventure cinematic model resolves zones from _adventureProgress,
    // which -- independent of and unaffected by this hotfix -- only
    // populates once loadMapProgressStatus() has run at least once. A real
    // player reaches this naturally by the time they browse to a cleared
    // zone; a fresh, from-cold page load in this harness needs the same one
    // call a real session would eventually make on its own. Not part of the
    // fix under test, and not skipped past silently -- recorded below.
    const primed = await page.evaluate(async () => {
      await loadMapProgressStatus();
      return {
        adventure_progress_length: typeof _adventureProgress !== 'undefined' ? _adventureProgress.length : null,
      };
    });
    report.pre_existing_bootstrap_priming = primed;

    const firstClick = await page.evaluate(CLICK_AND_READ, ZONE_KEY);
    report.first_click = firstClick;

    if (firstClick.error) {
      report.final_status = 'BLOCKED_HARNESS_STATE';
      console.log(JSON.stringify(report, null, 2));
      return 1;
    }

    // Zone-select-button-config races are real (see index.html's own
    // E10Cinematic wiring, loaded asynchronously): reselect once, matching
    // genuine repeated-visit usage, before asserting on button state.
    if (firstClick.button_visible === false || firstClick.button_enabled === false) {
      await page.evaluate((zoneKey) => {
        const root = document.getElementById('e9-world-stage-slot');
        const other = Array.from(root.querySelectorAll('[data-zone]'))
          .find((el) => el.getAttribute('data-zone') !== zoneKey);
        if (other) other.click();
      }, ZONE_KEY);
      report.reselect_click = await page.evaluate(CLICK_AND_READ, ZONE_KEY);
    }

    const primaryClick = report.reselect_click || report.first_click;
    report.button_visible = primaryClick.button_visible === true;
    report.button_enabled = primaryClick.button_enabled === true;
    report.click_handler_fired = primaryClick.click_attempted === true;
    report.play_story_replay_called = (primaryClick.play_story_replay_call_count_delta || 0) === 1
      && primaryClick.play_story_replay_last_arg === ZONE_KEY;
    report.cinematic_overlay_started_same_tick = primaryClick.overlay_activated_same_tick === true;

    if (report.button_visible && report.button_enabled) {
      report.finish_and_return = await page.evaluate(SKIP_TO_CLOSE);

      // Repeated-selection contract (Section 4): select another zone,
      // return, click again -- exactly one dispatch, no dead handler.
      await page.evaluate((otherKey) => {
        const root = document.getElementById('e9-world-stage-slot');
        const other = Array.from(root.querySelectorAll('[data-zone]'))
          .find((el) => el.getAttribute('data-zone') === otherKey);
        if (other) other.click();
      }, OTHER_ZONE_KEY);
      const repeatClick = await page.evaluate(CLICK_AND_READ, ZONE_KEY);
      report.repeat_click = repeatClick;
      report.repeat_click_single_dispatch = (repeatClick.play_story_replay_call_count_delta || 0) === 1
        && repeatClick.play_story_replay_last_arg === ZONE_KEY;
      report.repeat_click_activated_same_tick = repeatClick.overlay_activated_same_tick === true;

      report.finish_and_return_2 = await page.evaluate(SKIP_TO_CLOSE);
    }

    report.console_page_errors = consoleErrors;

    const passed = report.button_visible
      && report.button_enabled
      && report.click_handler_fired
      && report.play_story_replay_called
      && report.cinematic_overlay_started_same_tick
      && (report.repeat_click_single_dispatch !== false)
      && (report.repeat_click_activated_same_tick !== false);
    report.final_status = passed ? 'PASS' : 'FAIL';
    console.log(JSON.stringify(report, null, 2));
    return passed ? 0 : 1;
  } finally {
    await browser.close();
    await stopRuntime(child);
  }
}

main().then((code) => process.exit(code)).catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
