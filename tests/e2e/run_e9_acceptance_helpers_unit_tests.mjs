// Focused unit tests for the pure/near-pure helpers exported by
// run_e9_acceptance_journey.mjs: the production-target guard's URL
// normalization/rejection logic, the strict rollout-flag assertion, and the
// exit-classification matrix. None of these require a browser, a real
// backend, or network access -- evaluateProductionGuard takes an injectable
// DNS resolver specifically so it can be verified this way. Run directly:
//   node run_e9_acceptance_helpers_unit_tests.mjs
'use strict';

import assert from 'node:assert/strict';
import {
  evaluateProductionGuard,
  assertFlagsAllEqual,
  classifyOutcome,
  exitCodeForClassification,
} from './run_e9_acceptance_journey.mjs';

const registered = [];
function test(name, fn) {
  registered.push({ name, fn });
}

// A resolver that never actually touches DNS -- every "misleading but safe"
// case below is expected to be judged safe purely from URL parsing, without
// needing (or being allowed to depend on) real network resolution.
async function noopResolver() {
  return [];
}

// --- Production guard: must BLOCK every representation of the protected host/IP ---

const BLOCKED_CASES = [
  ['exact hostname', 'http://godokoro.com/'],
  ['uppercase hostname', 'http://GODOKORO.COM/'],
  ['mixed-case hostname', 'http://GoDoKoRo.CoM/'],
  ['trailing dot', 'http://godokoro.com./'],
  ['multiple trailing dots', 'http://godokoro.com../'],
  ['percent-encoded terminal dot', 'http://godokoro.com%2E/'],
  ['explicit port 80', 'http://godokoro.com:80/'],
  ['explicit port 443 on https', 'https://godokoro.com:443/'],
  ['non-standard explicit port', 'http://godokoro.com:8443/'],
  ['userinfo (username:password@)', 'http://user:pass@godokoro.com/'],
  ['userinfo with unusual chars', 'http://ad:min@godokoro.com/'],
  ['subdomain', 'http://www.godokoro.com/'],
  ['deep subdomain', 'http://a.b.godokoro.com/'],
  ['subdomain with port and userinfo combined', 'https://u:p@www.godokoro.com:8443/some/path?x=1'],
  ['known production IPv4 literal', 'http://152.69.200.105/'],
  ['known production IPv4 literal, explicit port', 'http://152.69.200.105:8080/'],
  ['IPv4-mapped IPv6, dotted-quad form', 'http://[::ffff:152.69.200.105]/'],
  ['IPv4-mapped IPv6, hex-group form', 'http://[::ffff:9845:c869]/'],
];

for (const [label, url] of BLOCKED_CASES) {
  test(`production guard blocks: ${label} (${url})`, async () => {
    const verdict = await evaluateProductionGuard(url, { resolveHostnameIps: noopResolver });
    assert.equal(verdict.blocked, true, `expected blocked=true for ${url}, got ${JSON.stringify(verdict)}`);
  });
}

const ALLOWED_CASES = [
  ['localhost', 'http://localhost:5000/'],
  ['127.0.0.1', 'http://127.0.0.1:5000/'],
  ['unrelated staging domain', 'http://staging.example.test/'],
  ['hostname containing the domain as a longer suffix owner, not a subdomain', 'http://notgodokoro.com/'],
  ['production domain as a longer host suffix (not a real subdomain boundary)', 'http://evilgodokoro.com/'],
  ['production domain embedded as a sibling label prefix', 'http://godokoro.com.example.test/'],
  ['production domain in the path only', 'http://example.test/path/godokoro.com'],
  ['production domain in a query parameter only', 'http://example.test/?x=godokoro.com'],
  ['production IP in a query parameter only', 'http://example.test/?ip=152.69.200.105'],
  ['production domain in a path AND query, host is safe', 'http://example.test/godokoro.com?x=152.69.200.105'],
  ['unrelated IPv4 literal', 'http://203.0.113.5/'],
  ['unrelated IPv6 literal', 'http://[2001:db8::1]/'],
];

// Integer-encoded IPv4 host obfuscation is a well-known SSRF-bypass class
// (decimal/octal/hex forms of an IP that a naive dotted-quad-only check
// would miss). These are all correctly caught today purely because the
// guard reads url.hostname, which WHATWG URL parsing already canonicalizes
// into standard dotted-quad notation before this code ever sees it — not
// because of any bespoke integer-parsing logic here. Locking this in as a
// regression test since it was previously unverified.
const OBFUSCATED_IP_BLOCKED_CASES = [
  ['decimal-encoded 32-bit integer', 'http://2554710121/'],
  ['hex-encoded 32-bit integer', 'http://0x9845c869/'],
  ['per-octet octal (leading zeros)', 'http://0230.0105.0310.0151/'],
  ['per-octet hex', 'http://0x98.0x45.0xc8.0x69/'],
  ['mixed octal/decimal octets', 'http://152.0105.200.105/'],
];

for (const [label, url] of OBFUSCATED_IP_BLOCKED_CASES) {
  test(`production guard blocks obfuscated production IP: ${label} (${url})`, async () => {
    const verdict = await evaluateProductionGuard(url, { resolveHostnameIps: noopResolver });
    assert.equal(verdict.blocked, true, `expected blocked=true for ${url}, got ${JSON.stringify(verdict)}`);
  });
}

for (const [label, url] of ALLOWED_CASES) {
  test(`production guard allows: ${label} (${url})`, async () => {
    const verdict = await evaluateProductionGuard(url, { resolveHostnameIps: noopResolver });
    assert.equal(verdict.blocked, false, `expected blocked=false for ${url}, got ${JSON.stringify(verdict)}`);
  });
}

test('production guard blocks a hostname that only resolves to the production IP via DNS', async () => {
  const verdict = await evaluateProductionGuard('http://sneaky-alias.example.test/', {
    resolveHostnameIps: async () => ['152.69.200.105'],
  });
  assert.equal(verdict.blocked, true);
});

// A bracketed IPv6 zone-ID literal (e.g. "[fe80::1%eth0]") is not
// constructible as a `new URL(...)` at all -- WHATWG URL parsing rejects it
// outright, confirmed empirically -- so a raw E2E_BASE_URL can never reach
// the guard carrying one. The zone-stripping logic instead matters for
// addresses a DNS *resolver* might hand back (some resolvers include a
// scope id on link-local-style results); this exercises that actually
// reachable path directly via the injectable resolver.
test('production guard blocks a DNS-resolved address that carries an IPv6 zone id', async () => {
  const verdict = await evaluateProductionGuard('http://sneaky-alias-2.example.test/', {
    resolveHostnameIps: async () => ['::ffff:152.69.200.105%eth0'],
  });
  assert.equal(verdict.blocked, true);
});

test('production guard does not block on a DNS resolution failure', async () => {
  const verdict = await evaluateProductionGuard('http://does-not-resolve.example.test/', {
    resolveHostnameIps: async () => { throw new Error('ENOTFOUND'); },
  });
  assert.equal(verdict.blocked, false);
  assert.ok(verdict.dnsError);
});

test('production guard throws a clear error for an unparseable URL', async () => {
  await assert.rejects(
    () => evaluateProductionGuard('not a url at all', { resolveHostnameIps: noopResolver }),
    /could not be parsed/,
  );
});

// --- Strict flag assertions: a missing/malformed field must never be
// mistaken for "correctly all false" or "correctly all true" ---

const ALL_TRUE = {
  e9Shell: true, e9TopHud: true, e9LeftNav: true, e9RightCards: true, e9BottomDock: true, e9WorldStage: true,
};
const ALL_FALSE = {
  e9Shell: false, e9TopHud: false, e9LeftNav: false, e9RightCards: false, e9BottomDock: false, e9WorldStage: false,
};

test('assertFlagsAllEqual passes for a correct all-true object', () => {
  assertFlagsAllEqual(ALL_TRUE, true, 'unit');
});
test('assertFlagsAllEqual passes for a correct all-false object', () => {
  assertFlagsAllEqual(ALL_FALSE, false, 'unit');
});

test('assertFlagsAllEqual throws when effective_flags is undefined', () => {
  assert.throws(() => assertFlagsAllEqual(undefined, false, 'unit'));
});
test('assertFlagsAllEqual throws when effective_flags is null', () => {
  assert.throws(() => assertFlagsAllEqual(null, false, 'unit'));
});
test('assertFlagsAllEqual throws when effective_flags is an array', () => {
  assert.throws(() => assertFlagsAllEqual([], false, 'unit'));
});
test('assertFlagsAllEqual throws when a required key is missing entirely', () => {
  const { e9Shell, ...rest } = ALL_FALSE;
  assert.throws(() => assertFlagsAllEqual(rest, false, 'unit'));
});
test('assertFlagsAllEqual throws when a required key is present only via the prototype chain', () => {
  const proto = { e9Shell: false };
  const flags = Object.assign(Object.create(proto), {
    e9TopHud: false, e9LeftNav: false, e9RightCards: false, e9BottomDock: false, e9WorldStage: false,
  });
  assert.throws(() => assertFlagsAllEqual(flags, false, 'unit'));
});
test('assertFlagsAllEqual throws when a value is the string "false" instead of boolean false', () => {
  assert.throws(() => assertFlagsAllEqual({ ...ALL_FALSE, e9Shell: 'false' }, false, 'unit'));
});
test('assertFlagsAllEqual throws when a value is the number 0 instead of boolean false', () => {
  assert.throws(() => assertFlagsAllEqual({ ...ALL_FALSE, e9Shell: 0 }, false, 'unit'));
});
test('assertFlagsAllEqual throws when a value is the number 1 instead of boolean true', () => {
  assert.throws(() => assertFlagsAllEqual({ ...ALL_TRUE, e9Shell: 1 }, true, 'unit'));
});
test('assertFlagsAllEqual throws when a value is explicitly undefined (own key, undefined value)', () => {
  assert.throws(() => assertFlagsAllEqual({ ...ALL_FALSE, e9Shell: undefined }, false, 'unit'));
});
test('assertFlagsAllEqual throws on a genuine value mismatch (expected true, one key false)', () => {
  assert.throws(() => assertFlagsAllEqual({ ...ALL_TRUE, e9WorldStage: false }, true, 'unit'));
});
test('assertFlagsAllEqual throws on a genuine value mismatch (expected false, one key true)', () => {
  assert.throws(() => assertFlagsAllEqual({ ...ALL_FALSE, e9WorldStage: true }, false, 'unit'));
});

// --- Exit-code / summary classification matrix (Phase 9) ---

test('classifyOutcome: all pass, nothing skipped -> COMPLETE_PASS / exit 0', () => {
  const c = classifyOutcome({ failed: 0, skipped: 0, allowIncomplete: false });
  assert.equal(c, 'COMPLETE_PASS');
  assert.equal(exitCodeForClassification(c), 0);
});
test('classifyOutcome: one failure -> FAILED / exit 1, regardless of allowIncomplete', () => {
  for (const allowIncomplete of [false, true]) {
    const c = classifyOutcome({ failed: 1, skipped: 0, allowIncomplete });
    assert.equal(c, 'FAILED');
    assert.equal(exitCodeForClassification(c), 1);
  }
});
test('classifyOutcome: all skipped, no opt-in -> INCOMPLETE_BLOCKED / exit 2 (never a silent success)', () => {
  const c = classifyOutcome({ failed: 0, skipped: 6, allowIncomplete: false });
  assert.equal(c, 'INCOMPLETE_BLOCKED');
  assert.equal(exitCodeForClassification(c), 2);
});
test('classifyOutcome: all skipped, explicit opt-in -> INCOMPLETE_PASS_OPTED_IN / exit 0', () => {
  const c = classifyOutcome({ failed: 0, skipped: 6, allowIncomplete: true });
  assert.equal(c, 'INCOMPLETE_PASS_OPTED_IN');
  assert.equal(exitCodeForClassification(c), 0);
});
test('classifyOutcome: partial skip (some passed, some skipped), no opt-in -> INCOMPLETE_BLOCKED / exit 2', () => {
  const c = classifyOutcome({ failed: 0, skipped: 2, allowIncomplete: false });
  assert.equal(c, 'INCOMPLETE_BLOCKED');
  assert.equal(exitCodeForClassification(c), 2);
});
test('exitCodeForClassification: PRODUCTION_TARGET_REJECTED -> exit 1', () => {
  assert.equal(exitCodeForClassification('PRODUCTION_TARGET_REJECTED'), 1);
});
test('exitCodeForClassification throws on an unknown classification (fail closed on programmer error)', () => {
  assert.throws(() => exitCodeForClassification('NOT_A_REAL_CLASSIFICATION'));
});

// --- Runner: sequential, so async production-guard cases are fully awaited
// before the pass/fail totals are read. ---
let passCount = 0;
const failures = [];

for (const { name, fn } of registered) {
  try {
    await fn();
    passCount += 1;
  } catch (err) {
    failures.push({ name, error: (err && err.stack) || String(err) });
  }
}

if (failures.length) {
  console.error('FAILURES:');
  failures.forEach((f) => console.error(`  - ${f.name}\n    ${f.error.split('\n').join('\n    ')}`));
  console.error(`\n${passCount} passed, ${failures.length} failed`);
  process.exit(1);
} else {
  console.log(`${passCount} passed, 0 failed`);
  process.exit(0);
}
