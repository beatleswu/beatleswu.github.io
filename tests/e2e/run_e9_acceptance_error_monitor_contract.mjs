// Real-browser (but backend-free) contract test for the acceptance
// journey's browser-error monitoring: installBrowserErrorMonitor,
// installUnhandledRejectionCapture, and drainUnhandledRejections. Loads a
// self-contained `data:` URL fixture that deliberately triggers a
// console.error, an uncaught exception, and an unhandled promise rejection,
// then asserts each is captured exactly once with no double-counting.
//
// Why this needs a real browser rather than a pure unit test: it exists
// specifically because an empirical check during the E9 Stage C2.2
// hardening pass found that this Chromium/CDP build ALSO surfaces a
// genuinely unhandled promise rejection through Playwright's own
// 'pageerror' event, not just synchronous throws -- so the naive
// implementation double-counted one real problem as two report entries
// under different `kind` labels. That's a real-browser-behavior fact, not
// something a pure-function unit test can observe. Fixed via message-text
// deduplication in drainUnhandledRejections(); this script is the
// regression test locking that fix in.
//
// Usage: node run_e9_acceptance_error_monitor_contract.mjs
'use strict';

import fssync from 'node:fs';
import { chromium } from 'playwright-core';
import {
  installBrowserErrorMonitor,
  installUnhandledRejectionCapture,
  drainUnhandledRejections,
} from './run_e9_acceptance_journey.mjs';

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
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN to run this contract test.');
}

const FIXTURE_HTML = `<!doctype html><html><body>
<script>
console.error('deliberate test console.error');
setTimeout(() => { throw new Error('deliberate test uncaught exception'); }, 10);
setTimeout(() => { Promise.reject(new Error('deliberate test unhandled rejection')); }, 20);
</script>
</body></html>`;

async function main() {
  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  let sink;
  try {
    const page = await browser.newPage();
    sink = [];
    await installUnhandledRejectionCapture(page);
    installBrowserErrorMonitor(page, sink);
    await page.goto('data:text/html,' + encodeURIComponent(FIXTURE_HTML));
    await page.waitForTimeout(500); // let both setTimeout callbacks fire
    await drainUnhandledRejections(page, sink);
  } finally {
    await browser.close();
  }

  const failures = [];
  const hasConsoleError = sink.some((e) => e.kind === 'console.error' && e.text === 'deliberate test console.error');
  const hasException = sink.some((e) => e.text === 'deliberate test uncaught exception');
  const hasRejection = sink.some((e) => e.text === 'deliberate test unhandled rejection');
  if (!hasConsoleError) failures.push('console.error was not captured');
  if (!hasException) failures.push('uncaught exception (pageerror) was not captured');
  if (!hasRejection) failures.push('unhandled promise rejection was not captured');
  if (sink.length !== 3) {
    failures.push(`expected exactly 3 captured entries (one per distinct real problem), got ${sink.length}: ${JSON.stringify(sink)}`);
  }

  if (failures.length) {
    console.error('FAILURES:');
    failures.forEach((f) => console.error(`  - ${f}`));
    console.error(`\n0 passed, ${failures.length} failed`);
    process.exit(1);
  }
  console.log('3 passed, 0 failed');
  process.exit(0);
}

main().catch((err) => {
  console.error(err.stack || String(err));
  process.exit(1);
});
