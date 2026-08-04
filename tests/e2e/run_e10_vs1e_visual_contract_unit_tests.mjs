import assert from 'node:assert/strict';
import http from 'node:http';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

import {
  arbitrateClassification,
  buildPhase0BrowserOriginObservation,
  buildCanonicalNetworkFailureSet,
  buildDiagnosticsHealthSummary,
  buildServerPathSummary,
  composeRunnerErrors,
  evaluateAbortPredicates,
  evaluateBrowserOriginatedPredicate,
  finalizeRunnerLifecycle,
  formatRunnerFailureSummary,
  pathnameFromRawRequestTarget,
  persistRunnerDiagnostics,
  CLASSIFIER_SCHEMA_VERSION,
} from './run_e10_vs1e_visual_contract.mjs';

const TRANSITION_ASSET_URL = 'http://127.0.0.1:12345/assets/maps/fixture-transition.webp';

function networkPageFixture({
  errorText = 'net::ERR_ABORTED',
  assetUrl = TRANSITION_ASSET_URL,
  transition = true,
  successfulResponse = true,
  serverReceived = transition,
  responseCreated = serverReceived && successfulResponse,
  crash = false,
  cdpMapping = true,
  includeRequestWillBeSent = true,
  browserOriginated = false,
  playwrightUrl = null,
  cdpNetworkEnabled = true,
  instrumentationErrors = [],
  finalUiPass = true,
  serverRequestTarget = null,
  serverError = false,
} = {}) {
  const pageUrl = 'http://127.0.0.1:12345/index.html';
  const request = {
    request_id: 'req-transition-1',
    url: assetUrl,
    method: 'GET',
    resource_type: browserOriginated ? 'Other' : 'Image',
    type: browserOriginated ? 'Other' : 'Image',
    frame: pageUrl,
    loader_id: 'loader-1',
    initiator: browserOriginated ? { type: 'other' } : { type: 'parser' },
    timestamp: '2026-08-04T00:00:01.000Z',
    cdp_timestamp: 1,
    request_will_be_sent: includeRequestWillBeSent,
  };
  const cdpEvents = [];
  if (includeRequestWillBeSent) {
    cdpEvents.push({ kind: 'Network.requestWillBeSent', ...request });
  }
  cdpEvents.push({
    kind: 'Network.loadingFailed',
    request_id: request.request_id,
    error_text: errorText,
    blocked_reason: null,
    canceled: errorText === 'net::ERR_ABORTED',
    type: request.type,
    timestamp: '2026-08-04T00:00:01.020Z',
    cdp_timestamp: 1.02,
  });
  const page = {
    page_id: 'page-1',
    label: 'desktop-1920-details',
    initial_url: pageUrl,
    viewport: { width: 1920, height: 1080 },
    final_ui_pass: finalUiPass,
    cdp_network_enabled: cdpNetworkEnabled,
    instrumentation_errors: instrumentationErrors,
    cdp_request_map: cdpMapping ? { [request.request_id]: request } : {},
    playwright_requestfailed: [{
      page_id: 'page-1',
      scenario: 'desktop-1920-details',
      url: playwrightUrl || assetUrl,
      method: 'GET',
      resource_type: request.resource_type,
      failure_text: errorText,
      timestamp: '2026-08-04T00:00:01.020Z',
      page_url: pageUrl,
    }],
    events: successfulResponse ? [{
      kind: 'response',
      url: assetUrl,
      status: 200,
      timestamp: '2026-08-04T00:00:01.030Z',
    }] : [],
    cdp_events: cdpEvents,
    browser_events: crash ? [{ kind: 'crash' }] : [],
  };
  if (transition) {
    page.transition_markers = [{
      kind: 'drawer_close',
      transition_type: 'drawer_close',
      trigger: 'Escape',
      scenario: page.label,
      page_id: page.page_id,
      timestamp: '2026-08-04T00:00:01.005Z',
      page_url: pageUrl,
      dom_transition_evidence_captured_at: '2026-08-04T00:00:01.004Z',
      dom_transition_evidence: [{
        tag: 'IMG',
        id: 'fixture-image',
        before_src: assetUrl,
      }],
      dom_transition_evidence_status: 'PASS',
    }];
    page.transition_lifecycle = [{
      kind: 'src_lifecycle',
      action: 'src_removed',
      scenario: page.label,
      page_id: page.page_id,
      timestamp: '2026-08-04T00:00:01.010Z',
      old_src: assetUrl,
      new_src: null,
    }];
  } else {
    page.transition_markers = [];
    page.transition_lifecycle = [];
  }
  const serverEvents = [];
  if (serverReceived) {
    const requestId = 'server-request-1';
    serverEvents.push({
      kind: 'request',
      request_id: requestId,
      method: 'GET',
      url: serverRequestTarget || new URL(assetUrl).pathname,
      timestamp: '2026-08-04T00:00:01.006Z',
    });
    if (responseCreated) {
      serverEvents.push({
        kind: 'response_created',
        request_id: requestId,
        status: serverError ? 500 : 200,
        timestamp: '2026-08-04T00:00:01.007Z',
      });
      serverEvents.push({
        kind: 'response_finished',
        request_id: requestId,
        status: serverError ? 500 : 200,
        timestamp: '2026-08-04T00:00:01.008Z',
      });
      serverEvents.push({
        kind: 'response_closed',
        request_id: requestId,
        status: serverError ? 500 : 200,
        timestamp: '2026-08-04T00:00:01.009Z',
      });
    }
    if (serverError) {
      serverEvents.push({
        kind: 'response_error',
        request_id: requestId,
        text: 'fixture server error',
        timestamp: '2026-08-04T00:00:01.009Z',
      });
    }
  }
  return {
    page,
    server: {
      server_id: 'server-1',
      origin: 'http://127.0.0.1:12345',
      events: serverEvents,
    },
  };
}

function classifyFixture(options = {}, caseFailures = { 'desktop-1920-details': [] }) {
  const fixture = networkPageFixture(options);
  return buildCanonicalNetworkFailureSet({
    pages: [fixture.page],
    servers: [fixture.server],
    caseFailures,
  });
}

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
        url: TRANSITION_ASSET_URL,
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
    assert.ok(Object.prototype.hasOwnProperty.call(payload.diagnostic_health, 'OTHER_URL_BLIND_SPOT_THIS_RUN'));
    assert.ok(Object.prototype.hasOwnProperty.call(payload.diagnostic_health, 'CDP_CAPTURE_GAP_THIS_RUN'));
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

function testHarnessPreRequestAbortClassified() {
  const result = classifyFixture({
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: true,
  });
  assert.equal(result.HARNESS_PRE_REQUEST_ABORTS, 1);
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 0);
  assert.deepEqual(result.failures, []);
  assert.equal(result.class_a[0].predicate_chain.classification, 'CLASS_A');
  assert.equal(result.class_a[0].predicate_chain.first_failed_condition, 'B1_server_received_request');
}

function testDrawerCloseErrAbortedClassifiedExpected() {
  const result = classifyFixture();
  assert.equal(result.HARNESS_PRE_REQUEST_ABORTS, 0);
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 1);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 0);
  assert.deepEqual(result.failures, []);
  assert.equal(result.class_b[0].predicate_chain.classification, 'CLASS_B');
}

function testClassABMutuallyExclusive() {
  const harness = classifyFixture({
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: true,
  });
  const transition = classifyFixture();
  assert.equal(harness.class_a.length, 1);
  assert.equal(harness.class_b.length, 0);
  assert.equal(transition.class_a.length, 0);
  assert.equal(transition.class_b.length, 1);
}

function testActiveRenderErrAbortedRemainsFailure() {
  const result = classifyFixture({ transition: false });
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
  assert.equal(result.PRIMARY_ERROR_KIND, 'CONTRACT');
}

function testPageOriginatedPreRequestAbortRemainsFailure() {
  const result = classifyFixture({
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: false,
  });
  assert.equal(result.HARNESS_PRE_REQUEST_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
  assert.equal(result.class_a[0], undefined);
  assert.equal(result.class_b[0], undefined);
  assert.equal(result.classification_totals_reconciled, true);
}

function testErrAbortedWithoutTransition() {
  const result = classifyFixture({ transition: false, successfulResponse: true });
  assert.match(result.failures[0], /UNEXPECTED_REQUEST_FAILURE/);
}

function testErrAbortedWithoutSuccessfulResponse() {
  const result = classifyFixture({ transition: true, successfulResponse: false });
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
}

function testErrAbortedWithPageCrash() {
  const result = classifyFixture({ transition: true, crash: true });
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
}

function testErrFailedRemainsFailure() {
  const result = classifyFixture({ errorText: 'net::ERR_FAILED', transition: true });
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
}

function testTransitionAbortWithMismatchedSrcRemainsFailure() {
  const fixture = networkPageFixture({ transition: true });
  fixture.page.transition_markers[0].dom_transition_evidence[0].before_src = `${TRANSITION_ASSET_URL}?different=1`;
  const mismatched = buildCanonicalNetworkFailureSet({ pages: [fixture.page], servers: [fixture.server] });
  assert.equal(mismatched.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(mismatched.UNEXPECTED_REQUEST_FAILURES, 1);
}

function testCdpRequestIdJoin() {
  const result = classifyFixture();
  assert.equal(result.CDP_CORRELATION_MISSES, 0);
  assert.equal(result.JOINED_FAILURES, 1);
  assert.equal(result.canonical_failures[0].url, TRANSITION_ASSET_URL);
  assert.equal(result.canonical_failures[0].loader_id, 'loader-1');
  assert.deepEqual(result.canonical_failures[0].initiator, { type: 'parser' });
}

function testCdpCorrelationMissFails() {
  const result = classifyFixture({ cdpMapping: false, includeRequestWillBeSent: false });
  assert.equal(result.CDP_CORRELATION_MISSES, 1);
  assert.equal(result.cross_validation_valid, false);
  assert.ok(result.failures.some((failure) => failure.startsWith('CDP_CORRELATION_MISS')));
}

function testPlaywrightCdpMismatchRecordedNotGated() {
  const fixture = networkPageFixture();
  fixture.page.playwright_requestfailed = [];
  const result = buildCanonicalNetworkFailureSet({ pages: [fixture.page], servers: [fixture.server] });
  assert.equal(result.PLAYWRIGHT_CDP_MISMATCHES, 1);
  assert.equal(result.PLAYWRIGHT_CDP_MISMATCH_RECORDED, true);
  assert.equal(result.PLAYWRIGHT_CDP_MISMATCH_GATE, false);
  assert.equal(result.cross_validation_valid, true);
  assert.deepEqual(result.failures, []);
  assert.equal(result.CDP_CAPTURE_GAP_THIS_RUN, 'NONE_OBSERVED_THIS_RUN');
}

function testCdpSetupFailureFailsClosed() {
  const fixture = networkPageFixture({
    cdpNetworkEnabled: false,
    instrumentationErrors: [{ kind: 'cdp_setup', text: 'Network.enable failed' }],
  });
  fixture.page.cdp_events = [];
  fixture.page.cdp_request_map = {};
  fixture.page.playwright_requestfailed = [];
  const result = buildCanonicalNetworkFailureSet({ pages: [fixture.page], servers: [fixture.server] });
  assert.equal(result.CDP_NETWORK_ENABLED, false);
  assert.equal(result.CDP_DISABLED_GOVERNED_PAGES[0].page_id, 'page-1');
  assert.equal(result.CDP_DISABLED_GOVERNED_PAGES[0].label, 'desktop-1920-details');
  assert.equal(result.CDP_SETUP_ERRORS[0].page_id, 'page-1');
  assert.equal(result.CDP_SETUP_ERRORS[0].label, 'desktop-1920-details');
  assert.equal(result.PRIMARY_ERROR_KIND, 'CONTRACT');
  assert.equal(result.class_a.length, 0);
  assert.equal(result.class_b.length, 0);
  assert.ok(result.failures.some((failure) => failure.startsWith('CDP_NETWORK_INSTRUMENTATION_DISABLED')));
  const health = buildDiagnosticsHealthSummary({ pages: [fixture.page], servers: [], network_summary: result });
  assert.equal(health.cdp_network_enabled, false);
  assert.deepEqual(health.CDP_DISABLED_GOVERNED_PAGES[0], result.CDP_DISABLED_GOVERNED_PAGES[0]);
  assert.deepEqual(health.GOVERNED_PAGE_ALLOWLIST, []);
}

function testUnmatchedPlaywrightGateInIsolation() {
  const result = classifyFixture({ playwrightUrl: 'http://127.0.0.1:12345/assets/unmatched.webp' });
  assert.equal(result.CDP_NETWORK_ENABLED, true);
  assert.equal(result.CDP_CORRELATION_MISSES, 0);
  assert.equal(result.unmatched_playwright.length, 1);
  assert.equal(result.CDP_CAPTURE_GAP_THIS_RUN[0].url, 'http://127.0.0.1:12345/assets/unmatched.webp');
  assert.equal(result.CDP_CAPTURE_GAP_THIS_RUN[0].page_id, 'page-1');
  assert.equal(result.PRIMARY_ERROR_KIND, 'CONTRACT');
  assert.ok(result.failures.some((failure) => failure.startsWith('CDP_CAPTURE_GAP')));
}

function testCombinedFailClosedCoverageGates() {
  const fixture = networkPageFixture({ cdpNetworkEnabled: false });
  fixture.page.cdp_events = [];
  fixture.page.cdp_request_map = {};
  const result = buildCanonicalNetworkFailureSet({ pages: [fixture.page], servers: [fixture.server] });
  assert.equal(result.CDP_NETWORK_ENABLED, false);
  assert.equal(result.unmatched_playwright.length, 1);
  assert.equal(result.PRIMARY_ERROR_KIND, 'CONTRACT');
  assert.ok(result.failures.some((failure) => failure.startsWith('CDP_NETWORK_INSTRUMENTATION_DISABLED')));
  assert.ok(result.failures.some((failure) => failure.startsWith('CDP_CAPTURE_GAP')));
}

function testHealthyRunHasNoCaptureGap() {
  const fixture = networkPageFixture();
  fixture.page.cdp_events = [];
  fixture.page.cdp_request_map = {};
  fixture.page.playwright_requestfailed = [];
  const result = buildCanonicalNetworkFailureSet({ pages: [fixture.page], servers: [fixture.server] });
  assert.equal(result.CDP_NETWORK_ENABLED, true);
  assert.equal(result.CDP_CAPTURE_GAP_THIS_RUN, 'NONE_OBSERVED_THIS_RUN');
  assert.deepEqual(result.failures, []);
}

function testCdpOnlyFaviconEventsRemainDiagnosticOnly() {
  const fixture = networkPageFixture({
    assetUrl: 'http://127.0.0.1:12345/favicon.ico',
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: true,
  });
  fixture.page.playwright_requestfailed = [];
  const result = buildCanonicalNetworkFailureSet({ pages: [fixture.page], servers: [fixture.server] });
  assert.equal(result.unmatched_cdp.length, 1);
  assert.equal(result.CDP_CAPTURE_GAP_THIS_RUN, 'NONE_OBSERVED_THIS_RUN');
  assert.equal(result.other_url_blind_spot_this_run, 'NONE_OBSERVED_THIS_RUN');
  assert.equal(result.HARNESS_PRE_REQUEST_ABORTS, 1);
  assert.deepEqual(result.failures, []);
}

function testOtherUrlBlindSpotDerivesFromUnexpected() {
  const result = classifyFixture({ transition: false });
  assert.equal(result.unmatched_cdp.length, 0);
  assert.equal(result.other_url_blind_spot_this_run[0].url, TRANSITION_ASSET_URL);
  assert.equal(result.other_url_blind_spot_this_run[0].page_id, 'page-1');
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
}

function testExpectedAbortNotInFailureCount() {
  const result = classifyFixture();
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 1);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 0);
  assert.equal(result.failures.length, 0);
}

function testHarnessAbortNotInFailureCount() {
  const result = classifyFixture({
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: true,
  });
  assert.equal(result.HARNESS_PRE_REQUEST_ABORTS, 1);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 0);
  assert.equal(result.failures.length, 0);
}

function testUnexpectedAbortInFailureCount() {
  const result = classifyFixture({ transition: false });
  assert.equal(result.HARNESS_PRE_REQUEST_ABORTS, 0);
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
  assert.equal(result.failures.length, 1);
}

function testBrowserOriginatedDetection() {
  const browser = evaluateBrowserOriginatedPredicate({
    resource_type: 'Other',
    type: 'Other',
    initiator: { type: 'other' },
  });
  const page = evaluateBrowserOriginatedPredicate({
    resource_type: 'Image',
    type: 'Image',
    initiator: { type: 'parser' },
  });
  assert.equal(browser.matches, true);
  assert.equal(page.matches, false);
  assert.match(browser.source, /CDP initiator\.type/);
}

function testPhase0Observation() {
  const observation = buildPhase0BrowserOriginObservation([
    { request_id: 'favicon', url: '/favicon.ico', resource_type: 'Other', type: 'Other', initiator: { type: 'other' } },
    { request_id: 'image', url: '/hero.webp', resource_type: 'Image', type: 'Image', initiator: { type: 'parser' } },
  ]);
  assert.equal(observation.status, 'COMPLETED_BEFORE_PREDICATE');
  assert.equal(observation.observed_request_count, 2);
  assert.equal(observation.browser_originated_candidate_count, 1);
  assert.equal(observation.page_originated_or_other_candidate_count, 1);
}

function testPathnameComparisonUsesRawServerRequestTarget() {
  const rawTarget = '/assets/maps/a%20b.webp?cache=1';
  const pathname = pathnameFromRawRequestTarget(rawTarget);
  assert.equal(pathname, '/assets/maps/a%20b.webp');
  const summary = buildServerPathSummary([{
    origin: 'http://127.0.0.1:12345',
    events: [
      { kind: 'request', request_id: 'r1', url: rawTarget },
      { kind: 'response_created', request_id: 'r1', status: 200, relative_path: '/repo/assets/maps/a b.webp' },
    ],
  }]);
  assert.equal(summary.get('/assets/maps/a%20b.webp').server_request_count, 1);
  assert.equal(summary.get('/assets/maps/a b.webp'), undefined);
}

function testRealAssetWithoutHttp200RemainsFailure() {
  const result = classifyFixture({ transition: true, successfulResponse: false });
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
  assert.equal(result.class_b[0], undefined);
}

function testRequestReachesServerWithoutTransitionRemainsFailure() {
  const result = classifyFixture({
    transition: false,
    serverReceived: true,
    responseCreated: true,
    successfulResponse: true,
  });
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
  assert.equal(result.class_b[0], undefined);
}

function testProvenanceChainEmittedForExpectedAndUnexpected() {
  const expectedA = classifyFixture({
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: true,
  });
  const expectedB = classifyFixture();
  const unexpected = classifyFixture({ transition: false });
  for (const [result, classification] of [[expectedA, 'CLASS_A'], [expectedB, 'CLASS_B'], [unexpected, 'UNEXPECTED']]) {
    const event = result.class_a[0] || result.class_b[0] || result.unexpected_request_failures[0];
    assert.equal(event.classification, classification);
    assert.equal(event.predicate_chain.classification, classification);
    assert.equal(event.predicate_chain.classifier_schema_version, CLASSIFIER_SCHEMA_VERSION);
    assert.ok(event.predicate_chain.first_failed_condition === null || typeof event.predicate_chain.first_failed_condition === 'string');
  }
}

function testNearMissSamplesClassifiedUnexpected() {
  const a6 = classifyFixture({
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: false,
  });
  assert.equal(a6.unexpected_request_failures[0].predicate_chain.class_a.first_failed_condition, 'A6_browser_originated');
  const b5Fixture = networkPageFixture({ transition: true });
  b5Fixture.page.transition_markers[0].dom_transition_evidence[0].before_src = `${TRANSITION_ASSET_URL}?mismatch=1`;
  const b5 = buildCanonicalNetworkFailureSet({ pages: [b5Fixture.page], servers: [b5Fixture.server] });
  assert.equal(b5.unexpected_request_failures[0].predicate_chain.class_b.first_failed_condition, 'B5_pre_transition_src_exact_match');
  assert.equal(b5.UNEXPECTED_REQUEST_FAILURES, 1);
}

function testExactlyOneClassificationPerEvent() {
  for (const result of [
    classifyFixture({ transition: false, successfulResponse: false, serverReceived: false, browserOriginated: true }),
    classifyFixture(),
    classifyFixture({ transition: false }),
  ]) {
    const classified = result.class_a.length + result.class_b.length + result.unexpected_request_failures.length;
    assert.equal(result.CDP_LOADINGFAILED, 1);
    assert.equal(classified, 1);
    assert.equal(result.classification_totals_reconciled, true);
  }
}

function testMultipleClassificationsRemainsFailure() {
  const arbitration = arbitrateClassification({ classA: true, classB: true });
  assert.equal(arbitration.status, 'FAIL');
  assert.equal(arbitration.classification, null);
  assert.equal(arbitration.reason, 'MULTIPLE_CLASSIFICATIONS');
}

function renameFixture(fixture, pageId, label) {
  fixture.page.page_id = pageId;
  fixture.page.label = label;
  for (const marker of fixture.page.transition_markers || []) {
    marker.page_id = pageId;
    marker.scenario = label;
  }
  for (const lifecycle of fixture.page.transition_lifecycle || []) {
    lifecycle.page_id = pageId;
    lifecycle.scenario = label;
  }
  for (const event of fixture.page.playwright_requestfailed || []) {
    event.page_id = pageId;
    event.scenario = label;
  }
  fixture.server.server_id = `server-${pageId}`;
  return fixture;
}

function testClassificationTotalsReconcileWithCdpTotal() {
  const a = renameFixture(networkPageFixture({
    assetUrl: 'http://127.0.0.1:12345/assets/a.webp',
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: true,
  }), 'page-a', 'a');
  const b = renameFixture(networkPageFixture({
    assetUrl: 'http://127.0.0.1:12345/assets/b.webp',
  }), 'page-b', 'b');
  const u = renameFixture(networkPageFixture({
    assetUrl: 'http://127.0.0.1:12345/assets/u.webp',
    transition: false,
  }), 'page-u', 'u');
  const result = buildCanonicalNetworkFailureSet({
    pages: [a.page, b.page, u.page],
    servers: [a.server, b.server, u.server],
  });
  assert.deepEqual(result.classification_totals, { CLASS_A: 1, CLASS_B: 1, UNEXPECTED: 1 });
  assert.equal(result.CDP_LOADINGFAILED, 3);
  assert.equal(result.classification_totals_reconciled, true);
}

function testClassifierOutputByteIdenticalOnRepeatRun() {
  const fixture = networkPageFixture({
    transition: false,
    successfulResponse: false,
    serverReceived: false,
    browserOriginated: true,
  });
  const input = { pages: [fixture.page], servers: [fixture.server] };
  const first = buildCanonicalNetworkFailureSet(input);
  const second = buildCanonicalNetworkFailureSet(input);
  assert.equal(
    JSON.stringify({ totals: first.classification_totals, failures: first.canonical_failures }),
    JSON.stringify({ totals: second.classification_totals, failures: second.canonical_failures }),
  );
}

function testPostPassClassifier() {
  const result = classifyFixture({ transition: true }, { 'desktop-1920-details': ['final assertion failed'] });
  assert.equal(result.RUNNER_TRANSITION_ABORTS, 0);
  assert.equal(result.UNEXPECTED_REQUEST_FAILURES, 1);
  assert.match(result.failures[0], /UNEXPECTED_REQUEST_FAILURE/);
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
  ['HARNESS_PRE_REQUEST_ABORT_CLASSIFIED', testHarnessPreRequestAbortClassified],
  ['DRAWER_CLOSE_ERR_ABORTED_CLASSIFIED_EXPECTED', testDrawerCloseErrAbortedClassifiedExpected],
  ['CLASS_A_AND_B_MUTUALLY_EXCLUSIVE', testClassABMutuallyExclusive],
  ['ACTIVE_RENDER_ERR_ABORTED_REMAINS_FAILURE', testActiveRenderErrAbortedRemainsFailure],
  ['PAGE_ORIGINATED_PRE_REQUEST_ABORT_REMAINS_FAILURE', testPageOriginatedPreRequestAbortRemainsFailure],
  ['ERR_ABORTED_WITHOUT_TRANSITION', testErrAbortedWithoutTransition],
  ['ERR_ABORTED_WITHOUT_SUCCESSFUL_RESPONSE', testErrAbortedWithoutSuccessfulResponse],
  ['ERR_ABORTED_WITH_PAGE_CRASH', testErrAbortedWithPageCrash],
  ['ERR_FAILED_REMAINS_FAILURE', testErrFailedRemainsFailure],
  ['TRANSITION_ABORT_WITH_MISMATCHED_SRC_REMAINS_FAILURE', testTransitionAbortWithMismatchedSrcRemainsFailure],
  ['CDP_REQUESTID_JOIN', testCdpRequestIdJoin],
  ['CDP_CORRELATION_MISS_FAILS', testCdpCorrelationMissFails],
  ['PLAYWRIGHT_CDP_MISMATCH_RECORDED_NOT_GATED', testPlaywrightCdpMismatchRecordedNotGated],
  ['CDP_SETUP_FAILURE_FAILS_CLOSED', testCdpSetupFailureFailsClosed],
  ['UNMATCHED_PLAYWRIGHT_GATE_IN_ISOLATION', testUnmatchedPlaywrightGateInIsolation],
  ['COMBINED_FAIL_CLOSED_COVERAGE_GATES', testCombinedFailClosedCoverageGates],
  ['HEALTHY_RUN_HAS_NO_CAPTURE_GAP', testHealthyRunHasNoCaptureGap],
  ['CDP_ONLY_FAVICON_EVENTS_REMAIN_DIAGNOSTIC_ONLY', testCdpOnlyFaviconEventsRemainDiagnosticOnly],
  ['OTHER_URL_BLIND_SPOT_DERIVES_FROM_UNEXPECTED', testOtherUrlBlindSpotDerivesFromUnexpected],
  ['EXPECTED_ABORT_NOT_IN_FAILURE_COUNT', testExpectedAbortNotInFailureCount],
  ['EXPECTED_HARNESS_ABORT_NOT_IN_FAILURE_COUNT', testHarnessAbortNotInFailureCount],
  ['UNEXPECTED_ABORT_IN_FAILURE_COUNT', testUnexpectedAbortInFailureCount],
  ['BROWSER_ORIGINATED_DETECTION', testBrowserOriginatedDetection],
  ['PHASE_0_OBSERVATION', testPhase0Observation],
  ['PATHNAME_COMPARISON_USES_RAW_SERVER_REQUEST_TARGET', testPathnameComparisonUsesRawServerRequestTarget],
  ['REAL_ASSET_WITHOUT_HTTP200_REMAINS_FAILURE', testRealAssetWithoutHttp200RemainsFailure],
  ['REQUEST_REACHES_SERVER_WITHOUT_TRANSITION_REMAINS_FAILURE', testRequestReachesServerWithoutTransitionRemainsFailure],
  ['PROVENANCE_CHAIN_EMITTED_FOR_CLASSIFICATIONS', testProvenanceChainEmittedForExpectedAndUnexpected],
  ['NEAR_MISS_SAMPLES_CLASSIFIED_UNEXPECTED', testNearMissSamplesClassifiedUnexpected],
  ['EXACTLY_ONE_CLASSIFICATION_PER_EVENT', testExactlyOneClassificationPerEvent],
  ['MULTIPLE_CLASSIFICATIONS_REMAINS_FAILURE', testMultipleClassificationsRemainsFailure],
  ['CLASSIFICATION_TOTALS_RECONCILE_WITH_CDP_TOTAL', testClassificationTotalsReconcileWithCdpTotal],
  ['CLASSIFIER_OUTPUT_BYTE_IDENTICAL_ON_REPEAT_RUN', testClassifierOutputByteIdenticalOnRepeatRun],
  ['POST_PASS_CLASSIFIER', testPostPassClassifier],
];

for (const [name, test] of tests) {
  await test();
  process.stdout.write(`PASS ${name}\n`);
}
process.stdout.write(`${tests.length} passed\n`);
