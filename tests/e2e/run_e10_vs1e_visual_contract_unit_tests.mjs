import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  buildDiagnosticsHealthSummary,
  composeRunnerErrors,
  finalizeRunnerLifecycle,
  formatRunnerFailureSummary,
  persistRunnerDiagnostics,
} from './run_e10_vs1e_visual_contract.mjs';

function fixtureError(message) {
  return new Error(message);
}

function healthySummary() {
  return {
    cdp_network_enabled: true,
    instrumentation_errors: 0,
    instrumentation_error_details: [],
    pages: 1,
    servers: 1,
    diagnostic_persistence_status: 'PASS',
  };
}

function lifecycleFixture({
  contractError = null,
  browserCloseError = null,
  serverCloseError = null,
  diagnosticsError = null,
} = {}) {
  const events = [];
  return {
    contractError,
    browser: {
      async close() {
        events.push('browser.close');
        if (browserCloseError) throw browserCloseError;
      },
    },
    server: {
      close(callback) {
        events.push('server.close');
        callback(serverCloseError);
      },
    },
    persistDiagnostics: async () => {
      events.push('diagnostics');
      if (diagnosticsError) throw diagnosticsError;
      return { summary: healthySummary() };
    },
    events,
  };
}

async function runLifecycleFixture(options = {}) {
  const fixture = lifecycleFixture(options);
  const result = await finalizeRunnerLifecycle({
    contractError: fixture.contractError,
    successPayload: { ok: true },
    browser: fixture.browser,
    server: fixture.server,
    persistDiagnostics: fixture.persistDiagnostics,
    outputDir: 'fixture-output',
    origin: 'http://127.0.0.1:12345',
  });
  return { ...result, events: fixture.events };
}

function diagnosticFixture() {
  const viewport = { width: 1920, height: 1080 };
  return {
    pages: [{
      page_id: 'page-1',
      label: 'desktop-1920-details',
      created_at: '2026-08-04T00:00:00.000Z',
      initial_url: 'http://127.0.0.1:12345/index.html',
      viewport,
      cdp_network_enabled: true,
      instrumentation_errors: [],
      events: [{
        kind: 'requestfailed',
        timestamp: '2026-08-04T00:00:01.000Z',
        url: 'http://127.0.0.1:12345/assets/maps/zone-06-royal-castle.webp',
        method: 'GET',
        resource_type: 'image',
        failure_text: 'net::ERR_FAILED',
        frame: 'http://127.0.0.1:12345/index.html',
        page_url: 'http://127.0.0.1:12345/index.html',
        viewport,
      }],
      cdp_events: [{
        kind: 'Network.loadingFailed',
        timestamp: '2026-08-04T00:00:01.001Z',
        request_id: '42',
        error_text: 'net::ERR_FAILED',
        blocked_reason: null,
        canceled: false,
        type: 'Image',
        page_url: 'http://127.0.0.1:12345/index.html',
        viewport,
      }],
      browser_events: [],
    }],
    servers: [{
      server_id: 'server-1',
      events: [],
    }],
  };
}

async function withPersistedFixture(callback) {
  const outputDir = await fs.mkdtemp(path.join(os.tmpdir(), 'e10-runner-diagnostics-'));
  try {
    return await callback(outputDir);
  } finally {
    await fs.rm(outputDir, { recursive: true, force: true });
  }
}

async function testOriginalContractErrorPreservedOnDiagnosticWriteSuccess() {
  const contractError = fixtureError('injected fixture error');
  await withPersistedFixture(async (outputDir) => {
    const diagnosticsResult = await persistRunnerDiagnostics(outputDir, 'http://127.0.0.1:12345', diagnosticFixture());
    const result = composeRunnerErrors({ contractError, diagnosticsSummary: diagnosticsResult.summary });
    assert.equal(result.error, contractError);
    assert.equal(result.outcome.primary_error.message, 'injected fixture error');
    assert.equal(result.outcome.diagnostic_persistence_status, 'PASS');
    assert.equal(result.outcome.primary_error_kind, 'CONTRACT');
  });
}

async function testContractAndDiagnosticsDoubleFailure() {
  await withPersistedFixture(async (outputDir) => {
    const contractError = fixtureError('original contract failure');
    let diagnosticsError = null;
    try {
      await persistRunnerDiagnostics(path.join(outputDir, 'missing-parent'), 'http://127.0.0.1:12345', diagnosticFixture());
    } catch (error) {
      diagnosticsError = error;
    }
    assert.ok(diagnosticsError);
    assert.equal(diagnosticsError.diagnosticsHealth.diagnostic_persistence_status, 'FAIL');
    const result = composeRunnerErrors({ contractError, diagnosticsError, diagnosticsSummary: diagnosticsError.diagnosticsHealth });
    assert.equal(result.error, contractError);
    assert.equal(result.error.diagnosticPersistenceError, diagnosticsError);
    assert.equal(result.outcome.primary_error.message, 'original contract failure');
    assert.equal(result.outcome.secondary_errors[0].error.message, diagnosticsError.message);
    assert.deepEqual(result.outcome.secondary_error_kinds, ['DIAGNOSTICS']);
    const summary = formatRunnerFailureSummary(result.error);
    const parsed = JSON.parse(summary);
    assert.equal(parsed.PRIMARY_ERROR_KIND, 'CONTRACT');
    assert.equal(parsed.DIAGNOSTIC_PERSISTENCE_STATUS, 'FAIL');
    assert.equal(parsed.DIAGNOSTIC_HEALTH.cdp_network_enabled, true);
    assert.match(summary, /PRIMARY_CONTRACT_FAILURE/);
    assert.match(summary, /DIAGNOSTIC_PERSISTENCE_FAILURE/);
  });
}

async function testGreenContractDiagnosticFailureFailsClosed() {
  await withPersistedFixture(async (outputDir) => {
    let diagnosticsError = null;
    try {
      await persistRunnerDiagnostics(path.join(outputDir, 'missing-parent'), 'http://127.0.0.1:12345', diagnosticFixture());
    } catch (error) {
      diagnosticsError = error;
    }
    assert.ok(diagnosticsError);
    const result = composeRunnerErrors({ diagnosticsError, diagnosticsSummary: diagnosticsError.diagnosticsHealth });
    assert.equal(result.error, diagnosticsError);
    assert.equal(result.outcome.primary_error_kind, 'DIAGNOSTICS');
    assert.equal(result.outcome.diagnostic_persistence_status, 'FAIL');
  });
}

async function testRequestfailedSerialization() {
  await withPersistedFixture(async (outputDir) => {
    await persistRunnerDiagnostics(outputDir, 'http://127.0.0.1:12345', diagnosticFixture());
    const payload = JSON.parse(await fs.readFile(path.join(outputDir, 'formal-runner-requestfailed-instrumentation.json'), 'utf8'));
    const event = payload.pages[0].events[0];
    assert.equal(payload.diagnostic_health.diagnostic_persistence_status, 'PASS');
    assert.equal(payload.diagnostic_health.cdp_network_enabled, true);
    assert.equal(event.kind, 'requestfailed');
    assert.equal(event.failure_text, 'net::ERR_FAILED');
    assert.equal(event.page_url, 'http://127.0.0.1:12345/index.html');
    assert.deepEqual(event.viewport, { width: 1920, height: 1080 });
  });
}

async function testCdpLoadingFailedSerialization() {
  await withPersistedFixture(async (outputDir) => {
    await persistRunnerDiagnostics(outputDir, 'http://127.0.0.1:12345', diagnosticFixture());
    const payload = JSON.parse(await fs.readFile(path.join(outputDir, 'formal-runner-requestfailed-instrumentation.json'), 'utf8'));
    const event = payload.pages[0].cdp_events[0];
    assert.equal(event.kind, 'Network.loadingFailed');
    assert.equal(event.error_text, 'net::ERR_FAILED');
    assert.equal(event.request_id, '42');
    assert.equal(event.canceled, false);
    assert.deepEqual(event.viewport, { width: 1920, height: 1080 });
  });
}

async function testSuccessSummary() {
  const result = composeRunnerErrors({
    diagnosticsSummary: healthySummary(),
    cleanupSummary: {
      cleanup_status: 'PASS',
      browser_close_status: 'PASS',
      server_close_status: 'PASS',
    },
  });
  assert.equal(result.error, null);
  assert.equal(result.outcome.run_result, 'PASS');
  assert.equal(result.outcome.primary_error_kind, 'NONE');
  assert.equal(result.outcome.diagnostic_persistence_status, 'PASS');
  assert.equal(result.outcome.cleanup_status, 'PASS');
}

async function testFailureSummary() {
  const result = composeRunnerErrors({ contractError: fixtureError('contract failed'), diagnosticsError: fixtureError('write failed') });
  const summary = JSON.parse(formatRunnerFailureSummary(result.error));
  assert.equal(summary.RUN_RESULT, 'FAIL');
  assert.equal(summary.PRIMARY_ERROR_KIND, 'CONTRACT');
  assert.equal(summary.PRIMARY_CONTRACT_FAILURE.message, 'contract failed');
  assert.equal(summary.DIAGNOSTIC_PERSISTENCE_FAILURE.message, 'write failed');
  assert.equal(summary.DIAGNOSTIC_PERSISTENCE_STATUS, 'FAIL');
  assert.equal(summary.CLEANUP_STATUS, 'NOT_RUN');
}

async function testImportDoesNotExecuteBrowser() {
  assert.equal(process.exitCode, undefined);
  const summary = buildDiagnosticsHealthSummary({ pages: [], servers: [] });
  assert.equal(summary.cdp_network_enabled, false);
  assert.equal(summary.pages, 0);
}

async function testContractOnlyFailureLifecycle() {
  const result = await runLifecycleFixture({ contractError: fixtureError('contract failure') });
  assert.equal(result.outcome.primary_error_kind, 'CONTRACT');
  assert.equal(result.outcome.run_result, 'FAIL');
  assert.deepEqual(result.events, ['browser.close', 'server.close', 'diagnostics']);
}

async function testContractAndBrowserCleanupFailureLifecycle() {
  const result = await runLifecycleFixture({
    contractError: fixtureError('contract failure'),
    browserCloseError: fixtureError('browser close failure'),
  });
  assert.equal(result.outcome.primary_error_kind, 'CONTRACT');
  assert.equal(result.outcome.primary_error.message, 'contract failure');
  assert.deepEqual(result.outcome.secondary_error_kinds, ['CLEANUP']);
  assert.equal(result.outcome.cleanup_errors[0].kind, 'BROWSER_CLOSE');
  assert.equal(result.outcome.browser_close_status, 'FAIL');
  assert.equal(result.outcome.server_close_status, 'PASS');
  assert.deepEqual(result.events, ['browser.close', 'server.close', 'diagnostics']);
  const summary = JSON.parse(formatRunnerFailureSummary(result.error));
  assert.equal(summary.PRIMARY_ERROR_KIND, 'CONTRACT');
  assert.equal(summary.CLEANUP_STATUS, 'FAIL');
  assert.deepEqual(summary.SECONDARY_ERROR_KINDS, ['CLEANUP']);
}

async function testContractDiagnosticsCleanupTripleFailureLifecycle() {
  const result = await runLifecycleFixture({
    contractError: fixtureError('contract failure'),
    browserCloseError: fixtureError('browser close failure'),
    diagnosticsError: fixtureError('diagnostics failure'),
  });
  assert.equal(result.outcome.primary_error_kind, 'CONTRACT');
  assert.equal(result.outcome.primary_error.message, 'contract failure');
  assert.deepEqual(result.outcome.secondary_error_kinds, ['DIAGNOSTICS', 'CLEANUP']);
  assert.equal(result.outcome.diagnostic_persistence_status, 'FAIL');
  assert.equal(result.outcome.cleanup_errors[0].kind, 'BROWSER_CLOSE');
  assert.deepEqual(result.events, ['browser.close', 'server.close', 'diagnostics']);
}

async function testGreenContractDiagnosticFailureLifecycle() {
  const result = await runLifecycleFixture({ diagnosticsError: fixtureError('diagnostics failure') });
  assert.equal(result.outcome.primary_error_kind, 'DIAGNOSTICS');
  assert.equal(result.outcome.run_result, 'FAIL');
  assert.equal(result.outcome.contract_failure_count, 0);
  assert.deepEqual(result.events, ['browser.close', 'server.close', 'diagnostics']);
}

async function testGreenContractCleanupFailureLifecycle() {
  const result = await runLifecycleFixture({ browserCloseError: fixtureError('browser close failure') });
  assert.equal(result.outcome.primary_error_kind, 'CLEANUP');
  assert.equal(result.outcome.run_result, 'FAIL');
  assert.equal(result.outcome.contract_failure_count, 0);
  assert.equal(result.outcome.diagnostic_persistence_status, 'PASS');
  assert.equal(result.outcome.cleanup_status, 'FAIL');
  assert.equal(result.outcome.browser_close_status, 'FAIL');
  assert.deepEqual(result.events, ['browser.close', 'server.close', 'diagnostics']);
}

async function testServerShutdownAfterBrowserCloseFailure() {
  const server = http.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  try {
    const result = await finalizeRunnerLifecycle({
      contractError: fixtureError('contract failure'),
      browser: { close: async () => { throw fixtureError('browser close failure'); } },
      server,
      persistDiagnostics: async () => ({ summary: healthySummary() }),
      outputDir: 'fixture-output',
      origin: 'http://127.0.0.1:12345',
    });
    assert.equal(result.outcome.primary_error_kind, 'CONTRACT');
    assert.equal(result.outcome.browser_close_status, 'FAIL');
    assert.equal(result.outcome.server_close_status, 'PASS');
    assert.equal(server.listening, false);
  } finally {
    if (server.listening) await new Promise((resolve) => server.close(resolve));
  }
}

async function testProcessTerminatesWithNonzeroExit() {
  const runnerPath = fileURLToPath(new URL('./run_e10_vs1e_visual_contract.mjs', import.meta.url));
  const runnerUrl = pathToFileURL(runnerPath).href;
  const script = `
    import { finalizeRunnerLifecycle, formatRunnerFailureSummary } from ${JSON.stringify(runnerUrl)};
    const result = await finalizeRunnerLifecycle({
      contractError: new Error('contract failure'),
      browser: { close: async () => { throw new Error('browser close failure'); } },
      server: { close(callback) { callback(); } },
      persistDiagnostics: async () => ({ summary: {
        cdp_network_enabled: true,
        instrumentation_errors: 0,
        instrumentation_error_details: [],
        pages: 1,
        servers: 1,
        diagnostic_persistence_status: 'PASS',
      } }),
      outputDir: 'fixture-output',
      origin: 'http://127.0.0.1:12345',
    });
    if (!result.error) process.exitCode = 2;
    else {
      process.stderr.write(formatRunnerFailureSummary(result.error));
      process.exitCode = 1;
    }
  `;
  const child = await new Promise((resolve, reject) => {
    const processHandle = spawn(process.execPath, ['--input-type=module', '-e', script], {
      cwd: path.dirname(runnerPath),
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, SECRET_KEY: 'e10-pr263-review-fix-process-only' },
    });
    let stderr = '';
    processHandle.stderr.on('data', (chunk) => { stderr += chunk; });
    processHandle.on('error', reject);
    processHandle.on('close', (code, signal) => resolve({ code, signal, stderr }));
  });
  assert.equal(child.signal, null);
  assert.equal(child.code, 1);
  const summary = JSON.parse(child.stderr);
  assert.equal(summary.PRIMARY_ERROR_KIND, 'CONTRACT');
  assert.equal(summary.CLEANUP_STATUS, 'FAIL');
}

const tests = [
  ['contract error preserved on diagnostic write success', testOriginalContractErrorPreservedOnDiagnosticWriteSuccess],
  ['contract and diagnostics double failure', testContractAndDiagnosticsDoubleFailure],
  ['green contract diagnostic failure fails closed', testGreenContractDiagnosticFailureFailsClosed],
  ['requestfailed serialization', testRequestfailedSerialization],
  ['CDP loadingFailed serialization', testCdpLoadingFailedSerialization],
  ['success summary', testSuccessSummary],
  ['failure summary', testFailureSummary],
  ['import does not execute browser', testImportDoesNotExecuteBrowser],
  ['contract-only lifecycle failure', testContractOnlyFailureLifecycle],
  ['contract plus browser cleanup failure', testContractAndBrowserCleanupFailureLifecycle],
  ['contract diagnostics cleanup triple failure', testContractDiagnosticsCleanupTripleFailureLifecycle],
  ['green contract diagnostics failure', testGreenContractDiagnosticFailureLifecycle],
  ['green contract cleanup failure', testGreenContractCleanupFailureLifecycle],
  ['server shutdown after browser close failure', testServerShutdownAfterBrowserCloseFailure],
  ['process terminates with nonzero exit', testProcessTerminatesWithNonzeroExit],
];

for (const [name, test] of tests) {
  await test();
  process.stdout.write(`PASS ${name}\n`);
}
process.stdout.write(`${tests.length} passed\n`);
