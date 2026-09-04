/* Bounded real-Chromium QA for the standalone Zone 3 visual-effects package. */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const FIXTURE = '/tests/e2e/fixtures/w1_01_zone3_presentation_fx.html';
const EFFECT_IDS = [
    'Z3_L01', 'Z3_V01', 'Z3_V02', 'Z3_V03', 'Z3_V04', 'Z3_V05',
    'Z3_V06', 'Z3_V07', 'Z3_V08', 'Z3_V09', 'Z3_V10', 'Z3_T01_VISUAL',
];
const SHOT_IDS = [
    'SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05',
    'SHOT06', 'SHOT07', 'SHOT08', 'SHOT09', 'SHOT10',
];
const VIEWPORTS = [
    ['DESKTOP', { width: 1440, height: 900 }],
    ['IPAD_LANDSCAPE', { width: 1180, height: 820 }],
    ['IPAD_PORTRAIT', { width: 834, height: 1194 }],
    ['MOBILE_PORTRAIT', { width: 430, height: 932 }],
];

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
        '.svg': 'image/svg+xml',
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

async function exercisePage(page, reducedMotion) {
    await page.goto(`${page.__origin}${FIXTURE}`, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => window.__z3Ready === true);
    const report = await page.evaluate(async ({ effectIds, shotIds, reduced }) => {
        const fx = window.__z3;
        const contract = fx.getContract();
        const image = document.querySelector('img');
        const pageErrors = [];

        const started = effectIds.map((effectId) => fx.start(effectId, {
            shotId: 'SHOT05',
            durationMs: 400,
            reducedMotion: reduced,
        }));
        const activeNodes = document.querySelectorAll('[data-z3-effect-id]').length;
        const activeStats = fx.getResourceStats();
        fx.startCameraCue('SHOT05', { reducedMotion: reduced });
        const cameraActive = document.documentElement &&
            document.getElementById('stage').classList.contains('z3-camera-active');
        fx.stopAll();
        const afterInitialCleanup = fx.getResourceStats();

        const cameraResults = shotIds.map((shotId) => {
            const result = fx.startCameraCue(shotId, {
                reducedMotion: reduced,
                durationMs: 20,
            });
            fx.stopCamera();
            return result;
        });

        const transitionResults = [];
        for (let index = 0; index < 20; index += 1) {
            const shotId = shotIds[index % shotIds.length];
            transitionResults.push(fx.transitionShot(shotId, ['Z3_L01', 'Z3_V01'], {
                reducedMotion: reduced,
            }));
            fx.stopAll();
        }

        const defaultShotResults = shotIds.map((shotId) => {
            const expected = fx.getShotEffects(shotId);
            const result = fx.transitionShot(shotId, undefined, {
                reducedMotion: reduced,
            });
            const activeIds = fx.getActiveEffectIds();
            fx.stopAll();
            return {
                result,
                expected,
                activeIds,
            };
        });

        let automaticCleanup = true;
        if (!reduced) {
            fx.start('Z3_V05', { shotId: 'SHOT05', durationMs: 20 });
            await new Promise((resolve) => setTimeout(resolve, 45));
            const effectExpired = fx.getResourceStats();
            fx.startCameraCue('SHOT05', { durationMs: 20 });
            await new Promise((resolve) => setTimeout(resolve, 45));
            const cameraExpired = fx.getResourceStats();
            automaticCleanup = effectExpired.temporaryEffectNodeCount === 0 &&
                cameraExpired.activeCamera === false &&
                cameraExpired.activeTimerCount === 0 &&
                cameraExpired.activeRafCount === 0;
            fx.stopAll();
        }

        for (let index = 0; index < 50; index += 1) {
            const result = fx.start('Z3_V05', {
                shotId: 'SHOT05',
                durationMs: 100,
                reducedMotion: reduced,
            });
            if (result.ok !== true) throw new Error('stress_start_failed');
            fx.stop('Z3_V05');
        }
        const afterStress = fx.getResourceStats();

        const missing = fx.start('Z3_NOT_A_REAL_EFFECT', {
            shotId: 'SHOT05',
            reducedMotion: reduced,
        });
        const afterMissing = fx.getResourceStats();
        const destroyed = fx.destroy();
        const afterDestroy = fx.getResourceStats();
        const afterDestroyStart = fx.start('Z3_V01', { shotId: 'SHOT01' });

        pageErrors.push(...(window.__z3PageErrors || []));
        return {
            contractEffectCount: contract.effectIds.length,
            contractShotCount: contract.shotIds.length,
            imageLoaded: Boolean(image?.complete && image.naturalWidth > 0),
            startedAll: started.every((entry) => entry.ok === true),
            startedReduced: started.every((entry) => entry.reducedMotion === reduced),
            activeNodes,
            activeStats,
            cameraActive,
            initialCleanup: afterInitialCleanup,
            cameraResultsOk: cameraResults.every((entry) => entry.ok === true),
            transitionResultsOk: transitionResults.every((entry) => entry.ok === true),
            defaultShotResultsOk: defaultShotResults.every((entry) =>
                entry.result.ok === true &&
                JSON.stringify(entry.expected) === JSON.stringify(entry.activeIds)),
            automaticCleanup,
            afterStress,
            missingNoOp: missing.ok === false && missing.skipped === true,
            missingNoOpStats: afterMissing,
            destroyed,
            afterDestroy,
            afterDestroyStartNoOp: afterDestroyStart.ok === false,
            pageErrors,
        };
    }, { effectIds: EFFECT_IDS, shotIds: SHOT_IDS, reduced: reducedMotion });

    assert.equal(report.contractEffectCount, 12);
    assert.equal(report.contractShotCount, 10);
    assert.equal(report.imageLoaded, true);
    assert.equal(report.startedAll, true);
    assert.equal(report.startedReduced, true);
    assert.equal(report.activeNodes, 12);
    assert.equal(report.activeStats.activeEffectCount, 12);
    assert.ok(report.activeStats.temporaryEffectNodeCount >= 12);
    assert.equal(report.cameraActive, true);
    assert.equal(report.cameraResultsOk, true);
    assert.equal(report.transitionResultsOk, true);
    assert.equal(report.defaultShotResultsOk, true);
    assert.equal(report.automaticCleanup, true);
    assert.equal(report.afterStress.activeTimerCount, 0);
    assert.equal(report.afterStress.activeRafCount, 0);
    assert.equal(report.afterStress.temporaryEffectNodeCount, 0);
    assert.equal(report.afterStress.activeEventListenerCount, 0);
    assert.equal(report.missingNoOp, true);
    assert.equal(report.missingNoOpStats.temporaryEffectNodeCount, 0);
    assert.equal(report.destroyed, true);
    assert.equal(report.afterDestroy.activeTimerCount, 0);
    assert.equal(report.afterDestroy.activeRafCount, 0);
    assert.equal(report.afterDestroy.temporaryEffectNodeCount, 0);
    assert.equal(report.afterDestroy.activeEventListenerCount, 0);
    assert.equal(report.afterDestroyStartNoOp, true);
    assert.deepEqual(report.pageErrors, []);
    return report;
}

async function run() {
    const executablePath = findChrome();
    assert.ok(executablePath, 'Chrome/Edge executable is required for browser QA');
    const { server, origin } = await startStaticServer();
    const browser = await chromium.launch({ headless: true, executablePath });
    const results = {};
    try {
        for (const [label, viewport] of VIEWPORTS) {
            const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
            const page = await context.newPage();
            page.__origin = origin;
            page.on('pageerror', (error) => {
                page.evaluate((message) => {
                    window.__z3PageErrors = [...(window.__z3PageErrors || []), message];
                }, String(error)).catch(() => {});
            });
            await page.emulateMedia({ reducedMotion: 'no-preference' });
            results[label] = await exercisePage(page, false);
            await context.close();
        }

        const reducedContext = await browser.newContext({
            viewport: { width: 430, height: 932 },
            deviceScaleFactor: 1,
        });
        const reducedPage = await reducedContext.newPage();
        reducedPage.__origin = origin;
        reducedPage.on('pageerror', (error) => {
            reducedPage.evaluate((message) => {
                window.__z3PageErrors = [...(window.__z3PageErrors || []), message];
            }, String(error)).catch(() => {});
        });
        await reducedPage.emulateMedia({ reducedMotion: 'reduce' });
        results.REDUCED_MOTION = await exercisePage(reducedPage, true);
        await reducedContext.close();
    } finally {
        await browser.close();
        await new Promise((resolve) => server.close(resolve));
    }

    for (const [label] of VIEWPORTS) console.log(`${label}=PASS`);
    console.log('REDUCED_MOTION=PASS');
    console.log('LIFECYCLE_STRESS_ITERATIONS=50');
    console.log('TASK_OWNED_RESOURCE_LEAK=NO');
    console.log('BROWSER_QA=PASS');
    return results;
}

run().catch((error) => {
    console.error(`BROWSER_QA=FAIL ${error.stack || error}`);
    process.exitCode = 1;
});
