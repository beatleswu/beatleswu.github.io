import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import {
  buildDiagnosticsHealthSummary,
  composeRunnerErrors,
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

async function testOriginalContractErrorPreserved() {
  const contractError = fixtureError('injected fixture error');
  const result = composeRunnerErrors({ contractError, diagnosticsSummary: healthySummary() });
  assert.equal(result.error, contractError);
  assert.equal(result.outcome.primary_error.message, 'injected fixture error');
  assert.equal(result.outcome.diagnostic_persistence_status, 'PASS');
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
    assert.equal(result.outcome.secondary_error.message, diagnosticsError.message);
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
    assert.equal(result.outcome.primary_error_kind, 'DIAGNOSTIC_PERSISTENCE');
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
  const result = composeRunnerErrors({ diagnosticsSummary: healthySummary() });
  assert.equal(result.error, null);
  assert.equal(result.outcome.run_result, 'PASS');
  assert.equal(result.outcome.diagnostic_persistence_status, 'PASS');
}

async function testFailureSummary() {
  const result = composeRunnerErrors({ contractError: fixtureError('contract failed'), diagnosticsError: fixtureError('write failed') });
  const summary = JSON.parse(formatRunnerFailureSummary(result.error));
  assert.equal(summary.RUN_RESULT, 'FAIL');
  assert.equal(summary.PRIMARY_ERROR_KIND, 'CONTRACT');
  assert.equal(summary.PRIMARY_CONTRACT_FAILURE.message, 'contract failed');
  assert.equal(summary.DIAGNOSTIC_PERSISTENCE_FAILURE.message, 'write failed');
  assert.equal(summary.DIAGNOSTIC_PERSISTENCE_STATUS, 'FAIL');
}

async function testImportDoesNotExecuteBrowser() {
  assert.equal(process.exitCode, undefined);
  const summary = buildDiagnosticsHealthSummary({ pages: [], servers: [] });
  assert.equal(summary.cdp_network_enabled, false);
  assert.equal(summary.pages, 0);
}

const tests = [
  ['original contract error preserved', testOriginalContractErrorPreserved],
  ['contract and diagnostics double failure', testContractAndDiagnosticsDoubleFailure],
  ['green contract diagnostic failure fails closed', testGreenContractDiagnosticFailureFailsClosed],
  ['requestfailed serialization', testRequestfailedSerialization],
  ['CDP loadingFailed serialization', testCdpLoadingFailedSerialization],
  ['success summary', testSuccessSummary],
  ['failure summary', testFailureSummary],
  ['import does not execute browser', testImportDoesNotExecuteBrowser],
];

for (const [name, test] of tests) {
  await test();
  process.stdout.write(`PASS ${name}\n`);
}
process.stdout.write(`${tests.length} passed\n`);
