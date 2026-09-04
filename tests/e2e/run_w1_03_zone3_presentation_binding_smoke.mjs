/* Bounded real-Chromium smoke for the manifest-backed Zone 3 binding. */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const FIXTURE = '/tests/e2e/fixtures/w1_03_zone3_presentation_binding.html';
const SHOT_IDS = Object.freeze([
    'SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05',
    'SHOT06', 'SHOT07', 'SHOT08', 'SHOT09', 'SHOT10',
]);
const VIEWPORTS = Object.freeze([
    ['DESKTOP', { width: 1440, height: 900 }],
    ['IPAD_LANDSCAPE', { width: 1180, height: 820 }],
    ['IPAD_PORTRAIT', { width: 834, height: 1194 }],
    ['MOBILE_PORTRAIT', { width: 430, height: 932 }],
]);

function findChrome() {
    const localAppData = process.env.LOCALAPPDATA || '';
    const candidates = [
        process.env.CHROME_BIN,
        'C:/Program Files/Google/Chrome/Application/chrome.exe',
        'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
        path.join(localAppData, 'Google/Chrome/Application/chrome.exe'),
        'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
        'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    ].filter(Boolean);
    return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function contentType(filePath) {
    return ({
        '.html': 'text/html; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.mp3': 'audio/mpeg',
    })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

async function startStaticServer() {
    const server = http.createServer(async (request, response) => {
        try {
            const requestUrl = new URL(request.url || '/', 'http://127.0.0.1');
            let relative = decodeURIComponent(requestUrl.pathname);
            if (relative === '/') relative = FIXTURE;
            const absolute = path.resolve(ROOT, `.${relative}`);
            const insideRoot = absolute === ROOT || absolute.startsWith(`${ROOT}${path.sep}`);
            if (!insideRoot) {
                response.writeHead(404);
                response.end('not found');
                return;
            }
            const stat = await fsPromises.stat(absolute).catch(() => null);
            if (!stat?.isFile()) {
                response.writeHead(404);
                response.end('not found');
                return;
            }
            response.writeHead(200, { 'Content-Type': contentType(absolute) });
            fs.createReadStream(absolute).pipe(response);
        } catch (error) {
            response.writeHead(500);
            response.end(String(error));
        }
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

async function exercise(page, origin, reducedMotion, viewportLabel) {
    const browserErrors = [];
    page.on('pageerror', (error) => browserErrors.push(`pageerror:${error.message}`));
    page.on('console', (message) => {
        if (message.type() === 'error') browserErrors.push(`console:${message.text()}`);
    });
    await page.goto(`${origin}${FIXTURE}`, { waitUntil: 'domcontentloaded' });
    try {
        await page.waitForFunction(() => window.__z3BindingReady === true, { timeout: 20000 });
    } catch (error) {
        const state = await page.evaluate(() => ({
            ready: window.__z3BindingReady,
            result: window.__z3BindingReadyResult,
            status: window.GoOdysseyZone3Presentation?.getStatus?.(),
        })).catch(() => null);
        throw new Error(`${error.message}; binding=${JSON.stringify(state)}; browserErrors=${JSON.stringify(browserErrors)}`);
    }
    const report = await page.evaluate(({ shotIds, reduced, viewport }) => {
        const binding = window.GoOdysseyZone3Presentation;
        const stage = document.getElementById('intro-film-stage');
        const zh = binding.getLocaleConfig('zh-TW');
        const en = binding.getLocaleConfig('en-US');
        const responsiveKey = {
            DESKTOP: 'desktop',
            IPAD_LANDSCAPE: 'ipadLandscape',
            IPAD_PORTRAIT: 'ipadPortrait',
            MOBILE_PORTRAIT: 'mobilePortrait',
        }[viewport];
        const prepared = binding.prepareStage(stage);
        const transitions = shotIds.map((shotId) => {
            const item = zh.allTimeline.find((entry) => entry.shotId === shotId);
            stage.querySelectorAll('.film-shot').forEach((entry) => entry.classList.remove('active'));
            const result = binding.transitionShot(shotId, item, { reducedMotion: reduced });
            const activeEffects = binding.getFxResourceStats().activeEffectCount;
            binding.stopFx();
            return { shotId, result, activeEffects };
        });
        const first = zh.allTimeline[0];
        const ninth = zh.allTimeline[8];
        const firstImg = stage.querySelector('[data-z3-shot-id="SHOT01"] img');
        const ninthImg = stage.querySelector('[data-z3-shot-id="SHOT09"] img');
        const responsiveRows = zh.allTimeline.map((item) => {
            const img = stage.querySelector(`[data-z3-shot-id="${item.shotId}"] img`);
            const descriptor = item.responsive[responsiveKey];
            const styles = getComputedStyle(img);
            return {
                shotId: item.shotId,
                safe: descriptor.safe,
                expectedMode: descriptor.mode,
                expectedPosition: descriptor.position,
                actualMode: styles.objectFit,
                actualPosition: styles.objectPosition,
            };
        });
        const stressResults = [];
        for (let cycle = 0; cycle < 50; cycle += 1) {
            const item = zh.allTimeline[cycle % zh.allTimeline.length];
            stressResults.push(binding.transitionShot(item.shotId, item, { reducedMotion: reduced }));
            binding.stopFx();
        }
        const stressCleanup = binding.getFxResourceStats();
        const invalid = binding.transitionShot('SHOT_NOT_REAL', first, { reducedMotion: reduced });
        return {
            status: binding.getStatus(),
            contract: binding.getContract(),
            prepared,
            wrapperCount: stage.querySelectorAll('[data-z3-camera-target]').length,
            zhShotIds: zh.allTimeline.map((entry) => entry.shotId),
            enShotIds: en.allTimeline.map((entry) => entry.shotId),
            zhBeatCount: zh.allTimeline.reduce((sum, entry) => sum + entry.beats.length, 0),
            enBeatCount: en.allTimeline.reduce((sum, entry) => sum + entry.beats.length, 0),
            enFirstAudio: en.allTimeline[0].beats[0].audioSrc,
            zhFirstAudio: zh.allTimeline[0].beats[0].audioSrc,
            transitionCount: transitions.length,
            transitionsOk: transitions.every((entry) => entry.result.ok === true),
            effectsStarted: transitions.every((entry) => entry.activeEffects > 0),
            afterCleanup: binding.getFxResourceStats(),
            invalidNoOp: invalid.ok === false && invalid.skipped === true,
            firstObjectFit: getComputedStyle(firstImg).objectFit,
            firstObjectPosition: getComputedStyle(firstImg).objectPosition,
            ninthObjectFit: getComputedStyle(ninthImg).objectFit,
            ninthObjectPosition: getComputedStyle(ninthImg).objectPosition,
            responsiveRows,
            stressIterations: stressResults.length,
            stressPassed: stressResults.every((entry) => entry.ok === true),
            stressCleanup,
        };
    }, { shotIds: SHOT_IDS, reduced: reducedMotion, viewport: viewportLabel });
    assert.equal(report.status.status, 'ready');
    assert.equal(report.contract.shotCount, 10);
    assert.equal(report.contract.responsiveClassificationCoverage, '10/10');
    assert.deepEqual(report.zhShotIds, SHOT_IDS);
    assert.deepEqual(report.enShotIds, SHOT_IDS);
    assert.equal(report.zhBeatCount, 97);
    assert.equal(report.enBeatCount, 97);
    assert.match(report.zhFirstAudio, /\/zone3\/dialogue\/zh-TW\//);
    assert.match(report.enFirstAudio, /\/zone3\/dialogue\/en-US\//);
    assert.equal(report.prepared.ok, true);
    assert.equal(report.prepared.shotCount, 10);
    assert.equal(report.wrapperCount, 10);
    assert.equal(report.transitionCount, 10);
    assert.equal(report.transitionsOk, true);
    assert.equal(report.effectsStarted, true);
    assert.equal(report.invalidNoOp, true);
    assert.equal(report.responsiveRows.length, 10);
    assert.ok(report.responsiveRows.every((row) => (
        row.expectedMode === row.actualMode
        && row.expectedPosition === row.actualPosition
    )), JSON.stringify(report.responsiveRows));
    assert.equal(report.stressIterations, 50);
    assert.equal(report.stressPassed, true);
    assert.equal(report.stressCleanup.activeTimerCount, 0);
    assert.equal(report.stressCleanup.activeRafCount, 0);
    assert.equal(report.stressCleanup.temporaryEffectNodeCount, 0);
    assert.equal(report.stressCleanup.activeEventListenerCount, 0);
    assert.equal(report.afterCleanup.activeTimerCount, 0);
    assert.equal(report.afterCleanup.activeRafCount, 0);
    assert.equal(report.afterCleanup.temporaryEffectNodeCount, 0);
    assert.equal(report.afterCleanup.activeEventListenerCount, 0);
    if (reducedMotion) {
        assert.equal(report.firstObjectFit, 'contain');
    }
    return report;
}

async function run() {
    const executablePath = findChrome();
    assert.ok(executablePath, 'Chrome/Edge executable is required for binding smoke');
    const { server, origin } = await startStaticServer();
    const browser = await chromium.launch({ headless: true, executablePath });
    try {
        for (const [label, viewport] of VIEWPORTS) {
            const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
            const page = await context.newPage();
            await page.emulateMedia({ reducedMotion: 'no-preference' });
            await exercise(page, origin, false, label);
            await context.close();
            console.log(`${label}=PASS`);
        }
        const reducedContext = await browser.newContext({
            viewport: { width: 430, height: 932 },
            deviceScaleFactor: 1,
        });
        const reducedPage = await reducedContext.newPage();
        await reducedPage.emulateMedia({ reducedMotion: 'reduce' });
        await exercise(reducedPage, origin, true, 'MOBILE_PORTRAIT');
        await reducedContext.close();
        console.log('REDUCED_MOTION=PASS');
        console.log('RESPONSIVE_CLASSIFICATION_COVERAGE=10/10');
        console.log('LIFECYCLE_STRESS_ITERATIONS=50');
        console.log('TASK_OWNED_RESOURCE_LEAK=NO');
        console.log('PHYSICAL_DEVICE_ACCEPTANCE=NOT_PERFORMED');
    } finally {
        await browser.close();
        await new Promise((resolve) => server.close(resolve));
    }
}

run().catch((error) => {
    console.error(`BINDING_SMOKE=FAIL ${error.stack || error}`);
    process.exitCode = 1;
});
