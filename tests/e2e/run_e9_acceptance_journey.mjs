// E9 acceptance journey — target-agnostic Playwright/E2E scaffold.
//
// Exercises the real backend (no API mocking): admin login, reload, logout +
// relogin, shell destroy/remount lifecycle (including listener-cleanup and
// duplicate-mount checks), admin gate, and non-admin Legacy boundary. This is
// a scaffold for repeatable acceptance evidence — it is not wired into CI and
// does not run automatically against anything.
//
// Safety, by design:
//   - Target is driven entirely by E2E_BASE_URL (defaults to localhost).
//     Before any browser is launched, the target hostname is normalized
//     (lowercased, trailing dot(s) stripped) and checked against the
//     godokoro.com domain (and all its subdomains) and a known production IP
//     denylist. If the hostname is neither a literal IP nor a direct domain
//     match, it is resolved via DNS and every resolved address is checked
//     against the same IP denylist too — so a hostname that isn't obviously
//     "production" today but resolves to production infrastructure is still
//     refused. A DNS resolution failure is never treated as evidence of
//     production (that would fail the safe case), but it does not weaken the
//     direct hostname/IP checks, which run first and don't depend on DNS.
//     Any of this refuses to proceed unless the caller explicitly opts in via
//     E2E_ALLOW_PRODUCTION.
//   - Credentials are read from env vars only. Nothing is hardcoded or
//     defaulted to a real account. Scenarios needing credentials that are not
//     set are SKIPPED, not failed.
//   - Only exercises actions any normal user/admin can take through the UI
//     (login, reload, logout, relogin, destroy/remount via the exposed E9
//     globals). Never touches E9_ROLLOUT_* config, DB rows, or deploy tooling.
//   - The result distinguishes "no failures" (ok) from "every scenario
//     actually ran and passed" (complete) — a run where credential-dependent
//     scenarios were skipped is never reported as a complete acceptance pass
//     (see exit code semantics below).
//
// Env vars:
//   E2E_BASE_URL              target origin, e.g. http://localhost:5000 (default)
//   E2E_ADMIN_USERNAME        admin test account username
//   E2E_ADMIN_PASSWORD        admin test account password
//   E2E_NONADMIN_USERNAME     non-admin test account username (optional)
//   E2E_NONADMIN_PASSWORD     non-admin test account password (optional)
//   E2E_ALLOW_PRODUCTION      must equal I_UNDERSTAND_PRODUCTION_RISK to allow
//                             a production-host target; otherwise refused
//   E2E_ALLOW_INCOMPLETE      set to "1" to allow a run with skipped
//                             scenarios to exit 0 anyway (still reports
//                             complete=false). Without it, an incomplete run
//                             (no failures, but something was skipped) exits 2.
//   CHROME_BIN                path to a Chrome/Edge executable (existing
//                             convention, same as run_e9_fetch_contract.mjs)
//
// Exit codes:
//   0  every scenario that ran passed AND nothing was skipped (complete=true)
//      — or complete=false but E2E_ALLOW_INCOMPLETE=1 was explicitly set
//   1  at least one scenario failed
//   2  no failures, but one or more scenarios were skipped and
//      E2E_ALLOW_INCOMPLETE was not set — i.e. this is NOT a complete pass
//
// Usage: node run_e9_acceptance_journey.mjs

import fssync from 'node:fs';
import net from 'node:net';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright-core';

const PRODUCTION_HOST_DENYLIST = ['godokoro.com'];
// Known production IP as of the 2026-07-22 reconciliation audit. IPs can
// change — this list, plus the DNS-resolution check below, is the mitigation
// for that: even if this literal goes stale, a hostname that starts
// resolving TO whatever the current production IP is would need this list
// updated too. There is no fully future-proof IP-based check; treat this as
// defense in depth alongside the domain-name denylist, not a replacement for
// keeping it current. This is a comparison against known, specific
// representations of that IP (plain IPv4, and IPv4-mapped IPv6 in both its
// dotted-quad and pure-hex-group textual forms) — it is not general-purpose
// protection against every possible network alias, proxy, hosts-file
// mapping, NAT64 translation, or a future production IP.
const PRODUCTION_IP_DENYLIST = ['152.69.200.105'];
const PRODUCTION_OPT_IN_VALUE = 'I_UNDERSTAND_PRODUCTION_RISK';
const INCOMPLETE_OPT_IN_VALUE = '1';

const ALL_E9_FLAG_KEYS = [
  'e9Shell', 'e9TopHud', 'e9LeftNav', 'e9RightCards', 'e9BottomDock', 'e9WorldStage',
];

// Slot/shell roots instrumented by the lifecycle listener spy. Deliberately
// narrow (not `document`, not `window`) to keep the signal attributable to
// E9's own on()-registered listeners rather than picking up unrelated
// document/window-level listeners from other app code. See the lifecycle
// scenario for what this does and does not prove.
const E9_INSTRUMENTED_SELECTORS = [
  '#e9-adventure-shell',
  '#e9-world-stage-slot',
  '#e9-top-hud-slot',
  '#e9-left-nav-slot',
  '#e9-right-cards-slot',
  '#e9-bottom-dock-slot',
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
  throw new Error('No Chrome/Edge executable found. Set CHROME_BIN to run the E9 acceptance journey.');
}

function normalizeHostname(hostname) {
  return String(hostname || '').toLowerCase().replace(/\.+$/, '');
}

function isProductionHostname(normalizedHost) {
  return PRODUCTION_HOST_DENYLIST.some((domain) => normalizedHost === domain || normalizedHost.endsWith('.' + domain));
}

// Strips a surrounding "[...]" (as produced by URL.hostname for IPv6
// literals) and an IPv6 zone identifier ("%eth0" / "%25eth0"), if present.
// A zone ID only scopes *which interface* a link-local/multicast address
// applies to — it is never part of the address's numeric identity — so
// discarding it before comparing against a denylist is correct, not lossy:
// it can only affect scoping, never turn one address into a different one.
function stripBracketsAndZone(raw) {
  let addr = String(raw || '').trim();
  if (addr.startsWith('[') && addr.endsWith(']')) {
    addr = addr.slice(1, -1);
  }
  const zoneIdx = addr.indexOf('%');
  if (zoneIdx !== -1) {
    addr = addr.slice(0, zoneIdx);
  }
  return addr;
}

// Given a syntactically-valid (per net.isIP) IPv6 address, returns the
// mapped IPv4 dotted-quad string if it is an IPv4-mapped IPv6 address
// (RFC 4291 ::ffff:a.b.c.d), recognizing both textual spellings that show
// up in practice: the dotted-quad suffix form as typed by a person, and the
// pure hex-group form ("::ffff:9845:c869") that WHATWG URL parsing and some
// resolvers normalize IPv4-mapped addresses into. Returns null for any other
// IPv6 address (including malformed attempts at this form — net.isIP already
// rejects e.g. "::ffff:999.999.999.999" as invalid IPv6 before this is ever
// called, and a regex mismatch here rejects anything net.isIP might still
// accept but isn't actually this specific mapped form).
function extractIpv4MappedAddress(ipv6Address) {
  const lower = ipv6Address.toLowerCase();
  const dotted = lower.match(/^::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/);
  if (dotted) {
    return net.isIPv4(dotted[1]) ? dotted[1] : null;
  }
  const hex = lower.match(/^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/);
  if (hex) {
    const hi = parseInt(hex[1], 16);
    const lo = parseInt(hex[2], 16);
    const combined = ((hi & 0xffff) << 16) | (lo & 0xffff);
    return [
      (combined >>> 24) & 0xff,
      (combined >>> 16) & 0xff,
      (combined >>> 8) & 0xff,
      combined & 0xff,
    ].join('.');
  }
  return null;
}

// Returns the canonical plain-IPv4 form of `raw` if it represents an IPv4
// address at all — directly, or via a recognized IPv4-mapped-IPv6 spelling —
// else null (including: not a valid IP address at all, or a valid IPv6
// address that isn't an IPv4-mapped one, e.g. ::1 or 2001:db8::1). This is
// deliberately narrow: it does not attempt general IPv6 canonicalization,
// only what's needed to recognize known spellings of an IPv4 production IP.
function canonicalIpv4Equivalent(raw) {
  const addr = stripBracketsAndZone(raw).toLowerCase();
  const family = net.isIP(addr);
  if (family === 4) return addr;
  if (family === 6) return extractIpv4MappedAddress(addr);
  return null;
}

function isLiteralIpAddress(raw) {
  return net.isIP(stripBracketsAndZone(raw)) !== 0;
}

function isProductionIp(rawAddress) {
  const canonical = canonicalIpv4Equivalent(rawAddress);
  return canonical !== null && PRODUCTION_IP_DENYLIST.includes(canonical);
}

async function defaultResolveHostnameIps(hostname) {
  const dns = await import('node:dns/promises');
  const records = await dns.lookup(hostname, { all: true });
  return records.map((r) => r.address);
}

// Pure-ish guard evaluator, deliberately taking an injectable resolver so it
// can be verified with a harmless hostname substitution (see the guard
// regression probes run during review) without touching real DNS or
// Production. Never throws for "target unreachable" reasons — that's the
// caller's problem to surface later as a normal connectivity failure.
export async function evaluateProductionGuard(rawUrl, { resolveHostnameIps = defaultResolveHostnameIps } = {}) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch (err) {
    throw new Error('E2E_BASE_URL could not be parsed as a URL.');
  }
  const normalizedHost = normalizeHostname(url.hostname);

  if (isProductionHostname(normalizedHost)) {
    return { blocked: true, origin: url.origin, reason: `hostname "${normalizedHost}" matches the production domain denylist` };
  }

  if (isLiteralIpAddress(normalizedHost)) {
    if (isProductionIp(normalizedHost)) {
      return {
        blocked: true,
        origin: url.origin,
        reason: `hostname is an IP representation of the known production IP (canonical ${canonicalIpv4Equivalent(normalizedHost)})`,
      };
    }
    return { blocked: false, origin: url.origin };
  }

  try {
    const addresses = await resolveHostnameIps(normalizedHost);
    for (const addr of addresses || []) {
      if (isProductionIp(addr)) {
        return {
          blocked: true,
          origin: url.origin,
          reason: `hostname "${normalizedHost}" resolves to known production IP (canonical ${canonicalIpv4Equivalent(addr)}, via ${addr})`,
        };
      }
    }
    return { blocked: false, origin: url.origin };
  } catch (dnsErr) {
    // DNS resolution failure is not itself evidence of production. Do not
    // block here; let the real connectivity check fail naturally later with
    // its own genuine network error if the target truly can't be reached.
    return { blocked: false, origin: url.origin, dnsError: String((dnsErr && dnsErr.message) || dnsErr) };
  }
}

async function resolveBaseUrl() {
  const raw = process.env.E2E_BASE_URL || 'http://localhost:5000';
  const verdict = await evaluateProductionGuard(raw);
  if (verdict.blocked && process.env.E2E_ALLOW_PRODUCTION !== PRODUCTION_OPT_IN_VALUE) {
    throw new Error(
      `Refusing to run against a production target (${verdict.reason}). ` +
      `This scaffold defaults to local/staging only. If a controlled, owner-approved ` +
      `production run is genuinely intended, set E2E_ALLOW_PRODUCTION=${PRODUCTION_OPT_IN_VALUE} explicitly.`
    );
  }
  return verdict.origin;
}

function credsFromEnv(prefix) {
  const username = process.env[`E2E_${prefix}_USERNAME`];
  const password = process.env[`E2E_${prefix}_PASSWORD`];
  if (!username || !password) return null;
  return { username, password };
}

async function fetchMe(page) {
  return page.evaluate(async () => {
    const r = await fetch('/api/auth/me', { credentials: 'include' });
    return r.ok ? r.json() : { logged_in: false, _status: r.status };
  });
}

async function loginViaForm(page, baseUrl, creds) {
  await page.goto(baseUrl + '/login', { waitUntil: 'networkidle' });
  await page.fill('#username', creds.username);
  await page.fill('#password', creds.password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 }),
    page.click('#login-btn'),
  ]);
}

async function logoutViaApp(page) {
  await page.evaluate(() => {
    if (typeof window.doLogout === 'function') return window.doLogout();
    return fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
      .then(() => { window.location.href = '/login'; });
  });
  await page.waitForURL((url) => url.pathname.startsWith('/login'), { timeout: 15000 });
}

async function shellSnapshot(page) {
  return page.evaluate(() => {
    const hasE9 = !!(window.E9 && typeof window.E9.getActiveShell === 'function');
    return {
      hasE9Runtime: hasE9,
      activeShell: hasE9 ? window.E9.getActiveShell() : null,
      bodyShellAttr: document.body.getAttribute('data-adventure-shell-active'),
      e9RootHidden: document.querySelector('#e9-adventure-shell')?.hidden ?? null,
      legacyHomeHidden: document.querySelector('#welcome-state .guild-hall-hero')?.hidden ?? null,
    };
  });
}

// Requires effective_flags to exist, be a plain object, contain every
// expected key as its OWN property (not merely inherited via the prototype
// chain — a real API response's flags must actually be present in the JSON
// payload itself, not incidentally satisfied by something on Object.prototype
// or a crafted test double), and hold real booleans — a missing/inherited-only
// key or a malformed object fails for *both* expected=true and expected=false,
// so a malformed/absent payload can no longer be mistaken for "correctly all
// false".
export function assertFlagsAllEqual(flags, expected, label) {
  if (flags === null || flags === undefined || typeof flags !== 'object' || Array.isArray(flags)) {
    throw new Error(`${label}: expected rollout.effective_flags to be an object, got ${JSON.stringify(flags)}`);
  }
  const missingKeys = ALL_E9_FLAG_KEYS.filter((key) => !Object.prototype.hasOwnProperty.call(flags, key));
  if (missingKeys.length) {
    throw new Error(`${label}: rollout.effective_flags is missing own key(s) [${missingKeys.join(', ')}] (got ${JSON.stringify(flags)})`);
  }
  const nonBoolean = ALL_E9_FLAG_KEYS.filter((key) => typeof flags[key] !== 'boolean');
  if (nonBoolean.length) {
    throw new Error(`${label}: rollout.effective_flags key(s) [${nonBoolean.join(', ')}] are not boolean (got ${JSON.stringify(flags)})`);
  }
  const mismatches = ALL_E9_FLAG_KEYS.filter((key) => flags[key] !== expected);
  if (mismatches.length) {
    throw new Error(`${label}: expected all flags === ${expected}, mismatches on [${mismatches.join(', ')}] (got ${JSON.stringify(flags)})`);
  }
}

// Installs a narrowly-scoped addEventListener/removeEventListener spy on the
// E9 shell + slot roots (not document/window — see E9_INSTRUMENTED_SELECTORS
// above). Safe to call again after a destroy/remount cycle; each call
// re-installs on whatever matches the selectors right now.
export async function installListenerSpy(page) {
  await page.evaluate((selectors) => {
    // The log object must persist across repeated installListenerSpy()
    // calls (the lifecycle scenario re-installs after each remount, on
    // elements that may already be instrumented from an earlier call) --
    // creating a fresh log every call would orphan counts from
    // already-wrapped elements, whose closures still reference the old log.
    if (!window.__E9_TEST_LISTENER_SPY__) {
      window.__E9_TEST_LISTENER_SPY__ = { add: 0, remove: 0 };
    }
    const log = window.__E9_TEST_LISTENER_SPY__;
    const targets = new Set();
    selectors.forEach((sel) => {
      const el = document.querySelector(sel);
      if (el) targets.add(el);
    });
    targets.forEach((target) => {
      if (target.__e9TestSpyInstalled) return;
      target.__e9TestSpyInstalled = true;
      const origAdd = target.addEventListener.bind(target);
      const origRemove = target.removeEventListener.bind(target);
      target.addEventListener = function (...args) {
        log.add += 1;
        return origAdd(...args);
      };
      target.removeEventListener = function (...args) {
        log.remove += 1;
        return origRemove(...args);
      };
    });
  }, E9_INSTRUMENTED_SELECTORS);
}

export async function readListenerSpyDelta(page) {
  return page.evaluate(() => {
    const log = window.__E9_TEST_LISTENER_SPY__ || { add: 0, remove: 0 };
    const delta = { add: log.add, remove: log.remove };
    log.add = 0;
    log.remove = 0;
    return delta;
  });
}

async function main() {
  const baseUrl = await resolveBaseUrl();
  const adminCreds = credsFromEnv('ADMIN');
  const nonAdminCreds = credsFromEnv('NONADMIN');
  const report = { base_url: baseUrl, cases: [] };

  const browser = await chromium.launch({ headless: true, executablePath: findChrome() });
  try {
    // Connectivity smoke check — always runs, no credentials required.
    await runScenario('connectivity_login_page_reachable', async () => {
      const page = await browser.newPage();
      try {
        await page.goto(baseUrl + '/login', { waitUntil: 'networkidle', timeout: 20000 });
        const hasForm = await page.evaluate(() => (
          !!document.querySelector('#username') &&
          !!document.querySelector('#password') &&
          !!document.querySelector('#login-btn')
        ));
        if (!hasForm) throw new Error('login form (#username/#password/#login-btn) not found');
        return { reachable: true };
      } finally {
        await page.close();
      }
    }, report);

    if (!adminCreds) {
      const reason = 'E2E_ADMIN_USERNAME/E2E_ADMIN_PASSWORD not set';
      skipScenario('admin_login_journey_and_gate', reason, report);
      skipScenario('reload_stability', reason, report);
      skipScenario('lifecycle_destroy_remount', reason, report);
      skipScenario('relogin_journey', reason, report);
    } else {
      const page = await browser.newPage();
      try {
        await runScenario('admin_login_journey_and_gate', async () => {
          await loginViaForm(page, baseUrl, adminCreds);
          await page.goto(baseUrl + '/', { waitUntil: 'networkidle' });
          const me = await fetchMe(page);
          if (!me.logged_in) throw new Error('expected logged_in=true after admin login');
          if (!me.is_admin) throw new Error('expected is_admin=true for the configured admin account');
          const rollout = me.e9_rollout || {};
          if (rollout.eligible !== true) throw new Error(`expected e9_rollout.eligible=true, got ${JSON.stringify(rollout)}`);
          if (rollout.reason !== 'admin_entitled') throw new Error(`expected reason=admin_entitled, got ${rollout.reason}`);
          assertFlagsAllEqual(rollout.effective_flags, true, 'admin_login_journey_and_gate');
          const shell = await shellSnapshot(page);
          if (shell.activeShell !== 'e9') throw new Error(`expected active shell 'e9', got ${JSON.stringify(shell)}`);
          return { rollout_reason: rollout.reason, shell };
        }, report);

        await runScenario('reload_stability', async () => {
          await page.reload({ waitUntil: 'networkidle' });
          const me = await fetchMe(page);
          const rollout = me.e9_rollout || {};
          if (rollout.eligible !== true) throw new Error(`post-reload expected eligible=true, got ${JSON.stringify(rollout)}`);
          const shell = await shellSnapshot(page);
          if (shell.activeShell !== 'e9') throw new Error(`post-reload expected active shell 'e9', got ${JSON.stringify(shell)}`);
          return { shell };
        }, report);

        await runScenario('lifecycle_destroy_remount', async () => {
          const beforeGen = await page.evaluate(() => window.E9.getLifecycleGeneration());

          // --- Cycle 1: destroy, assert listeners actually got removed ---
          await installListenerSpy(page);
          const destroyed1 = await page.evaluate(() => {
            window.E9.destroyShell();
            return window.E9.getActiveShell();
          });
          if (destroyed1 !== 'legacy') throw new Error(`expected 'legacy' immediately after destroyShell(), got ${destroyed1}`);
          const destroy1Delta = await readListenerSpyDelta(page);
          if (!(destroy1Delta.remove > 0)) {
            throw new Error(`expected destroyShell() to call removeEventListener at least once on E9 roots, got remove=${destroy1Delta.remove}`);
          }

          // --- Remount: assert listeners get re-registered, generation advances, mountStarted was reset ---
          const remounted1 = await page.evaluate(() => {
            window.primeInitialE9ShellOwnership();
            window.E9.initShell();
            return window.E9.getActiveShell();
          });
          if (remounted1 !== 'e9') throw new Error(`expected 'e9' after first remount, got ${remounted1}`);
          const midGen = await page.evaluate(() => window.E9.getLifecycleGeneration());
          if (!(midGen > beforeGen)) throw new Error(`expected lifecycle generation to advance on first remount (before=${beforeGen}, mid=${midGen})`);
          await installListenerSpy(page); // re-attach to freshly (re-)rendered slot roots
          const remount1Delta = await readListenerSpyDelta(page);
          if (!(remount1Delta.add >= 0)) throw new Error('listener spy read failed after first remount');

          // --- Cycle 2: destroy again; removes on THIS destroy must not be
          // fewer than what the immediately-preceding remount added, i.e.
          // the second destroy cannot "lose track of" listeners the remount
          // just registered. This is the direct anti-duplication/anti-leak
          // check: a regression that skips cleanup registration on remount
          // would show up here as remove << add, not as a generation/
          // activeShell mismatch. >= rather than strict equality tolerates
          // benign defensive extra removeEventListener calls (a no-op on an
          // already-detached listener), which is not itself a bug.
          const destroyed2 = await page.evaluate(() => {
            window.E9.destroyShell();
            return window.E9.getActiveShell();
          });
          if (destroyed2 !== 'legacy') throw new Error(`expected 'legacy' after second destroyShell(), got ${destroyed2}`);
          const destroy2Delta = await readListenerSpyDelta(page);
          if (destroy2Delta.remove < remount1Delta.add) {
            throw new Error(
              `second destroy removed fewer listeners (${destroy2Delta.remove}) than the prior remount added ` +
              `(${remount1Delta.add}) — possible listener leak/accumulation across a destroy/remount cycle`
            );
          }

          // --- Remount again: second cycle stays stable ---
          const remounted2 = await page.evaluate(() => {
            window.primeInitialE9ShellOwnership();
            window.E9.initShell();
            return window.E9.getActiveShell();
          });
          if (remounted2 !== 'e9') throw new Error(`expected 'e9' after second remount, got ${remounted2}`);
          const afterGen = await page.evaluate(() => window.E9.getLifecycleGeneration());
          if (!(afterGen > midGen)) throw new Error(`expected lifecycle generation to advance again on second remount (mid=${midGen}, after=${afterGen})`);

          // --- Stale in-flight async callback: delay one non-critical
          // slot's fragment fetch with a deterministic, engineered delay
          // (not a blind sleep — the delay is fixed by us, and we wait
          // slightly longer than that fixed delay before asserting), destroy
          // mid-flight, and confirm the late-arriving completion did not
          // resurrect the destroyed slot's mounted markers. ---
          const STALE_DELAY_MS = 1200;
          await page.route('**/components/adventure/top_hud.html', async (route) => {
            await new Promise((resolve) => setTimeout(resolve, STALE_DELAY_MS));
            await route.continue();
          });
          try {
            await page.evaluate(() => {
              window.E9.destroyShell();
              window.primeInitialE9ShellOwnership();
              window.E9.initShell(); // kicks off the delayed top_hud fetch, in-flight
              window.E9.destroyShell(); // invalidate that generation before the fetch resolves
            });
            await page.waitForTimeout(STALE_DELAY_MS + 400);
            const staleState = await page.evaluate(() => {
              const slot = document.querySelector('#e9-top-hud-slot');
              return {
                activeShell: window.E9.getActiveShell(),
                slotLoaded: slot ? slot.hasAttribute('data-e9-loaded') : null,
                slotInited: slot ? slot.hasAttribute('data-e9-inited') : null,
              };
            });
            if (staleState.activeShell !== 'legacy') {
              throw new Error(`stale-callback check: expected shell to remain 'legacy', got ${staleState.activeShell}`);
            }
            if (staleState.slotLoaded || staleState.slotInited) {
              throw new Error(`stale-callback check: top_hud slot shows mounted markers after the owning generation was destroyed (${JSON.stringify(staleState)}) — a stale async callback may have mutated the DOM after invalidation`);
            }
          } finally {
            await page.unroute('**/components/adventure/top_hud.html');
          }

          // Leave the page back in a mounted 'e9' state for later scenarios
          // in this shared session (relogin_journey navigates away next
          // anyway, but keep this scenario's exit state unsurprising).
          await page.evaluate(() => {
            window.primeInitialE9ShellOwnership();
            window.E9.initShell();
          });

          return { beforeGen, midGen, afterGen, destroy1Delta, remount1Delta, destroy2Delta };
        }, report);

        await runScenario('relogin_journey', async () => {
          await logoutViaApp(page);
          const meAfterLogout = await fetchMe(page);
          if (meAfterLogout.logged_in) throw new Error('expected logged_in=false after logout');
          await loginViaForm(page, baseUrl, adminCreds);
          await page.goto(baseUrl + '/', { waitUntil: 'networkidle' });
          const me = await fetchMe(page);
          if (!me.logged_in) throw new Error('expected logged_in=true after relogin');
          const rollout = me.e9_rollout || {};
          if (rollout.eligible !== true) throw new Error(`post-relogin expected eligible=true, got ${JSON.stringify(rollout)}`);
          const shell = await shellSnapshot(page);
          if (shell.activeShell !== 'e9') throw new Error(`post-relogin expected active shell 'e9', got ${JSON.stringify(shell)}`);
          return { shell };
        }, report);
      } finally {
        await page.close();
      }
    }

    if (!nonAdminCreds) {
      skipScenario('non_admin_legacy_boundary', 'E2E_NONADMIN_USERNAME/E2E_NONADMIN_PASSWORD not set', report);
    } else {
      const page = await browser.newPage();
      try {
        await runScenario('non_admin_legacy_boundary', async () => {
          await loginViaForm(page, baseUrl, nonAdminCreds);
          await page.goto(baseUrl + '/', { waitUntil: 'networkidle' });
          const me = await fetchMe(page);
          if (!me.logged_in) throw new Error('expected logged_in=true after non-admin login');
          if (me.is_admin) throw new Error('configured non-admin account unexpectedly has is_admin=true');
          const rollout = me.e9_rollout || {};
          if (rollout.eligible !== false) throw new Error(`expected e9_rollout.eligible=false for non-admin, got ${JSON.stringify(rollout)}`);
          assertFlagsAllEqual(rollout.effective_flags, false, 'non_admin_legacy_boundary');
          const shell = await shellSnapshot(page);
          if (shell.activeShell !== 'legacy') throw new Error(`expected non-admin active shell 'legacy', got ${JSON.stringify(shell)}`);
          return { rollout_reason: rollout.reason, shell };
        }, report);
      } finally {
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }

  const passed = report.cases.filter((c) => c.status === 'passed').length;
  const skipped = report.cases.filter((c) => c.status === 'skipped').length;
  const failed = report.cases.filter((c) => c.status === 'failed').length;
  const ok = failed === 0;
  const complete = failed === 0 && skipped === 0;

  Object.assign(report, { ok, complete, passed, skipped, failed });
  console.log(JSON.stringify(report, null, 2));

  if (failed > 0) {
    process.exit(1);
  }
  if (!complete) {
    if (process.env.E2E_ALLOW_INCOMPLETE === INCOMPLETE_OPT_IN_VALUE) {
      console.warn(
        `[INCOMPLETE] ${skipped} scenario(s) were skipped (missing credentials). Exiting 0 only because ` +
        `E2E_ALLOW_INCOMPLETE=${INCOMPLETE_OPT_IN_VALUE} was set explicitly. This is NOT a complete acceptance pass.`
      );
      process.exit(0);
    }
    console.error(
      `[INCOMPLETE] ${skipped} scenario(s) were skipped (missing credentials) — this is not a complete acceptance ` +
      `pass. Supply the missing credentials, or set E2E_ALLOW_INCOMPLETE=${INCOMPLETE_OPT_IN_VALUE} to allow an ` +
      `intentional partial local run to exit 0 anyway.`
    );
    process.exit(2);
  }
  process.exit(0);
}

async function runScenario(name, fn, report) {
  try {
    const detail = await fn();
    report.cases.push({ name, status: 'passed', detail: detail ?? null });
    console.log(`[PASS] ${name}`);
  } catch (err) {
    report.cases.push({ name, status: 'failed', detail: String((err && err.message) || err) });
    console.error(`[FAIL] ${name}: ${(err && err.message) || err}`);
  }
}

function skipScenario(name, reason, report) {
  report.cases.push({ name, status: 'skipped', detail: reason });
  console.log(`[SKIP] ${name}: ${reason}`);
}

// Only auto-run when executed directly (node run_e9_acceptance_journey.mjs),
// not when imported by a verification probe — importing evaluateProductionGuard
// for a controlled guard test must not trigger a live browser run as a
// side effect.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => {
    console.error(err.stack || String(err));
    process.exit(1);
  });
}
