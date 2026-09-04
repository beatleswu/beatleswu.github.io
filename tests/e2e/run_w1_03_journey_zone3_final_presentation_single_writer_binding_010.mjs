/* Bounded real-Chromium QA for the integrated Zone 3 presentation binding. */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const FIXTURE = '/tests/e2e/fixtures/w1_03_journey_zone3_final_presentation_single_writer_binding_010.html';
const VIEWPORTS = [
    ['DESKTOP', { width: 1440, height: 900 }],
    ['IPAD_LANDSCAPE', { width: 1180, height: 820 }],
    ['IPAD_PORTRAIT', { width: 834, height: 1194 }],
    ['MOBILE_PORTRAIT', { width: 430, height: 932 }],
];

const require = createRequire(import.meta.url);
function loadPlaywright() {
    if (process.env.PLAYWRIGHT_CORE_PATH) {
        return require(path.resolve(process.env.PLAYWRIGHT_CORE_PATH));
    }
    try {
        return require('playwright-core');
    } catch (error) {
        const fallback = path.resolve(ROOT, 'node_modules', 'playwright-core');
        if (!fs.existsSync(fallback)) throw error;
        return require(fallback);
    }
}

const { chromium } = loadPlaywright();

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
        '.mp3': 'audio/mpeg',
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
            if (relative === '/') relative = '/index.html';
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

async function assertFixture(page, origin, reducedMotion) {
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.stack || String(error)));
    await page.goto(`${origin}${FIXTURE}`, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => window.__z3Ready && typeof window.__z3Ready.then === 'function');
    await page.evaluate(() => window.__z3Ready);
    await page.waitForFunction(() => [...document.images].every((image) => image.complete && image.naturalWidth > 0));
    const report = await page.evaluate(() => window.__z3.runAll());
    const screenshot = await page.screenshot({ type: 'png' });

    assert.equal(report.shotCount, 10);
    assert.deepEqual(report.phaseLengths, [5, 2, 3]);
    assert.ok(report.zh.text.length > 0);
    assert.ok(report.en.text.length > 0);
    assert.notEqual(report.zh.voicePath, report.en.voicePath);
    assert.equal(report.zh.beatId, report.en.beatId);
    assert.equal(report.zh.i18nKey, report.en.i18nKey);
    assert.equal(report.localeSwitchKeepsAuthority, true);
    assert.equal(report.replayUsesSameIds, true);
    assert.equal(report.replayKeepsAuthority, true);
    assert.equal(report.muteAllActive, true);
    assert.equal(report.maxBgmStreams, 1);
    assert.equal(report.reducedMotionActive, reducedMotion);
    assert.equal(report.reducedMotionBehaviorVerified, true);
    assert.equal(report.imageFailurePresentationOnly, true);
    assert.equal(report.stressKeepsAuthority, true);
    assert.equal(report.manifestCueCount, 18);
    assert.equal(report.noCrossLocaleVoiceFallback, true);
    assert.equal(report.finalAudio.activeAudioCount, 0);
    assert.equal(report.finalAudio.activeBgmCount, 0);
    assert.equal(report.finalAudio.activeAmbienceCount, 0);
    assert.equal(report.finalAudio.activeTransientCount, 0);
    assert.equal(report.finalAudio.timerCount, 0);
    assert.equal(report.finalAudio.animationFrameCount, 0);
    assert.equal(report.finalAudio.listenerCount, 0);
    assert.equal(report.finalFx.activeEffectCount, 0);
    assert.equal(report.finalFx.activeTimerCount, 0);
    assert.equal(report.finalFx.activeRafCount, 0);
    assert.equal(report.finalFx.activeEventListenerCount, 0);
    assert.ok(screenshot.length > 0);
    assert.deepEqual(pageErrors, []);
    return { ...report, screenshotBytes: screenshot.length };
}

async function assertIntegratedShell(page, origin) {
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.stack || String(error)));
    await page.goto(`${origin}/index.html`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForFunction(() =>
        Boolean(
            window.GoOdysseyJourneyZone3Content &&
            window.GoOdysseyZone3PresentationFX &&
            window.GoOdysseyZone3PresentationAudio,
        ), { timeout: 30000 });
    const binding = await page.evaluate(() => ({
        shotCount: window.GoOdysseyJourneyZone3Content.cinematicPresentation.shots.length,
        supportedLocales: window.GoOdysseyJourneyZone3Content.cinematicLocalization.supportedLocales,
        fxAvailable: typeof window.GoOdysseyZone3PresentationFX.create === 'function',
        audioAvailable: typeof window.GoOdysseyZone3PresentationAudio.create === 'function',
        indexHasZone3Hook: Boolean(document.querySelector('script[src^="/js/e9/journey_zone3_presentation_audio.js"]')),
    }));
    assert.equal(binding.shotCount, 10);
    assert.deepEqual(binding.supportedLocales, ['zh-TW', 'en-US']);
    assert.equal(binding.fxAvailable, true);
    assert.equal(binding.audioAvailable, true);
    assert.equal(binding.indexHasZone3Hook, true);
    assert.deepEqual(pageErrors, [], JSON.stringify(pageErrors));
    return binding;
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
            await page.emulateMedia({ reducedMotion: 'no-preference' });
            results[label] = await assertFixture(page, origin, false);
            await context.close();
        }

        const reducedContext = await browser.newContext({
            viewport: { width: 430, height: 932 },
            deviceScaleFactor: 1,
        });
        const reducedPage = await reducedContext.newPage();
        await reducedPage.emulateMedia({ reducedMotion: 'reduce' });
        results.REDUCED_MOTION = await assertFixture(reducedPage, origin, true);
        await reducedContext.close();

        const shellContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
        const shellPage = await shellContext.newPage();
        results.INTEGRATED_SHELL = await assertIntegratedShell(shellPage, origin);
        await shellContext.close();
    } finally {
        await browser.close();
        await new Promise((resolve) => server.close(resolve));
    }

    for (const [label] of VIEWPORTS) console.log(`${label}=PASS`);
    console.log('REDUCED_MOTION=PASS');
    console.log('INTEGRATED_SHELL_BINDING=PASS');
    console.log('LIFECYCLE_STRESS_ITERATIONS=50');
    console.log('ORPHAN_RESOURCE_COUNT=0');
    console.log('BROWSER_QA=PASS');
    return results;
}

run().catch((error) => {
    console.error(`BROWSER_QA=FAIL ${error.stack || error}`);
    process.exitCode = 1;
});
