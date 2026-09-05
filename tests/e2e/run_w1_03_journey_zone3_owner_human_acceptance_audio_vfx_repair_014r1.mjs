/*
 * Bounded Zone 3 Owner-acceptance evidence runner.
 *
 * This runner intentionally separates machine-checkable audio/package
 * integrity from the Owner's perceptual audio decision.  It also captures
 * real Chromium frames for the priority visual cues at all four layouts.
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const FIXTURE = '/tests/e2e/fixtures/w1_01_zone3_presentation_fx.html';
const INTEGRATED_FIXTURE = '/tests/e2e/fixtures/w1_03_journey_zone3_final_presentation_single_writer_binding_010.html';
const EVIDENCE_DIR = path.join(
    ROOT,
    'tests',
    'e2e',
    'evidence',
    'w1_03_journey_zone3_owner_human_acceptance_audio_vfx_repair_014r1',
);
const TARGETED_REPAIR_MANIFEST = path.join(
    ROOT,
    'tools',
    'e10_zone3_audio',
    'zone3_hero_targeted_repair_014r1.json',
);
const GENERATED_REPAIR_MANIFEST = path.join(
    ROOT,
    'tools',
    'e10_zone3_audio',
    'zone3_hero_targeted_repair_014r1.generated.json',
);
const ZH_SUBTITLE_PATH = path.join(ROOT, 'assets', 'e10', 'i18n', 'zone3', 'zone3-cinematic-subtitles.json');
const EN_SUBTITLE_PATH = path.join(ROOT, 'assets', 'e10', 'i18n', 'zone3', 'zone3-cinematic-subtitles-en-US.json');
const ZH_AUDIO_PATH = path.join(ROOT, 'assets', 'e10', 'audio', 'zone3', 'zone3-cinematic-audio-manifest.json');
const EN_AUDIO_PATH = path.join(ROOT, 'assets', 'e10', 'audio', 'zone3', 'zone3-cinematic-audio-manifest-en-US.json');
const SHOT_IMAGES = Object.freeze({
    SHOT05: '/assets/e10/art/zone3/cinematic/zone3_shot05.webp',
    SHOT07: '/assets/e10/art/zone3/cinematic/zone3_shot07.webp',
    SHOT10: '/assets/e10/art/zone3/cinematic/zone3_shot10.webp',
});
const PRIORITY_SHOTS = Object.freeze(['SHOT05', 'SHOT07', 'SHOT10']);
const VIEWPORTS = Object.freeze([
    ['DESKTOP', { width: 1440, height: 900 }],
    ['IPAD_LANDSCAPE', { width: 1180, height: 820 }],
    ['IPAD_PORTRAIT', { width: 834, height: 1194 }],
    ['MOBILE_PORTRAIT', { width: 430, height: 932 }],
]);
const ZH_VOICES = Object.freeze({
    HERO: 'XXxvxx0YUt8icTEFE3c6',
    GRIK: 'DSyEP4HEaCKur8rFFOri',
    CENTURION: 'BrbEfHMQu0fyclQR7lfh',
});
const EN_VOICES = Object.freeze({
    HERO: 'RasuOwPKPBy67j7E43Su',
    GRIK: 'v4mOufztUtjxcpk65aWy',
    CENTURION: 'cso37AjcTkVqyjGkWbRz',
});

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
        '.svg': 'image/svg+xml',
    })[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
}

function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function resolveRepoPath(relativePath) {
    return path.resolve(ROOT, ...String(relativePath).split('/'));
}

function assertUnique(values, label) {
    assert.equal(new Set(values).size, values.length, `${label} contains duplicates`);
}

function inspectAudioIntegrity() {
    const zhSubtitles = readJson(ZH_SUBTITLE_PATH);
    const enSubtitles = readJson(EN_SUBTITLE_PATH);
    const zhAudio = readJson(ZH_AUDIO_PATH);
    const enAudio = readJson(EN_AUDIO_PATH);
    const targeted = readJson(TARGETED_REPAIR_MANIFEST);
    assert.equal(zhSubtitles.beats.length, 97);
    assert.equal(enSubtitles.beats.length, 97);
    assert.equal(zhAudio.entries.length, 97);
    assert.equal(enAudio.entries.length, 97);
    assertUnique(zhAudio.entries.map((entry) => entry.BEAT_ID), 'zh-TW audio beat IDs');
    assertUnique(enAudio.entries.map((entry) => entry.BEAT_ID), 'en-US audio beat IDs');

    const checkEntries = (document, locale, voices) => {
        const missing = [];
        const fallback = [];
        for (const entry of document.entries) {
            const filePath = resolveRepoPath(entry.AUDIO_PATH || '');
            if (!entry.AUDIO_PATH || !fs.existsSync(filePath) || fs.statSync(filePath).size <= 0) {
                missing.push(entry.BEAT_ID);
            }
            if (entry.LOCALE !== locale || !String(entry.AUDIO_PATH || '').includes(`/${locale}/`)) {
                fallback.push(entry.BEAT_ID);
            }
            assert.equal(entry.VOICE_ID, voices[entry.CHARACTER], `${locale} voice drift: ${entry.BEAT_ID}`);
        }
        return { missing, fallback };
    };

    const zhCheck = checkEntries(zhAudio, 'zh-TW', ZH_VOICES);
    const enCheck = checkEntries(enAudio, 'en-US', EN_VOICES);
    assert.deepEqual(zhCheck.missing, []);
    assert.deepEqual(enCheck.missing, []);
    assert.deepEqual(zhCheck.fallback, []);
    assert.deepEqual(enCheck.fallback, []);

    const shot1to5 = zhSubtitles.beats.filter((beat) => /^SHOT0[1-5]$/.test(beat.SHOT_ID));
    assert.equal(shot1to5.length, 36);
    const byId = new Map(zhSubtitles.beats.map((beat) => [beat.BEAT_ID, beat]));
    assert.equal(byId.get('Z3_S01_B001')?.VISIBLE_TEXT, '奇怪……大家怎麼都背著行李？');
    assert.equal(byId.get('Z3_S02_B002')?.VISIBLE_TEXT, '水壺、毯子、鍋子……都是平常生活用的東西。');
    assert.equal(byId.get('Z3_S01_B003')?.VISIBLE_TEXT, '他們好像是在搬家。');
    assert.equal(
        zhSubtitles.beats.some((beat) => beat.VISIBLE_TEXT === '……他們要搬家？'),
        false,
        'Owner line C must not be silently added to the canonical subtitle source',
    );
    assert.equal(targeted.items.length, 4);
    assert.equal(targeted.items.filter((item) => item.AUDITION_ONLY === false).length, 4);
    assert.equal(targeted.items.filter((item) => item.AUDITION_ONLY === true).length, 0);
    const lineC = targeted.items.find((item) => item.BEAT_ID === 'Z3_S01_B003');
    assert.equal(lineC?.EXACT_SUBTITLE, '他們好像是在搬家。');
    assert.equal(lineC?.OWNER_REPORTED_TEXT, '……他們要搬家？');
    assert.equal(lineC?.OWNER_REPORTED_LINE_EXACT_CURRENT_MATCH, false);
    assert.equal(lineC?.RUNTIME_AUDIO_PATH, 'assets/e10/audio/zone3/dialogue/zh-TW/zone3_shot01_b003_zh-TW_hero.mp3');
    const lineD = targeted.items.find((item) => item.BEAT_ID === 'Z3_S02_B004');
    assert.equal(lineD?.EXACT_SUBTITLE, '他們是真的非走不可。');
    assert.equal(lineD?.RUNTIME_AUDIO_PATH, 'assets/e10/audio/zone3/dialogue/zh-TW/zone3_shot02_b004_zh-TW_hero.mp3');

    assert.equal(fs.existsSync(GENERATED_REPAIR_MANIFEST), true, 'targeted generated manifest is required after authorized generation');
    const generated = readJson(GENERATED_REPAIR_MANIFEST);
    assert.equal(generated.GENERATED, true);
    assert.equal(generated.AUTOMATED_VALIDATION, 'PASS');
    assert.equal(generated.OWNER_AUDIO_ACCEPTANCE, 'PENDING');
    assert.equal(generated.generated.length, 4);
    for (const record of generated.generated) {
        assert.equal(record.GENERATED, true);
        assert.equal(record.AUTOMATED_VALIDATION, 'PASS');
        assert.equal(record.OWNER_AUDIO_ACCEPTANCE, 'PENDING');
        assert.ok(fs.statSync(resolveRepoPath(record.NEW_AUDIO_PATH)).size > 0);
        assert.ok(fs.statSync(resolveRepoPath(record.AUDITION_AUDIO_PATH)).size > 0);
    }

    return {
        zhSubtitleBeats: zhSubtitles.beats.length,
        zhVoiceRefs: zhAudio.entries.length,
        enSubtitleBeats: enSubtitles.beats.length,
        enVoiceRefs: enAudio.entries.length,
        shot1to5LineCount: shot1to5.length,
        missing: zhCheck.missing.length + enCheck.missing.length,
        duplicate: 0,
        crossLanguageFallback: zhCheck.fallback.length + enCheck.fallback.length,
        ownerLineCCanonicalMatch: false,
        ownerReportedLineExactCurrentMatch: false,
        runtimeBeatId: lineC.BEAT_ID,
        runtimeVisibleText: lineC.EXACT_SUBTITLE,
        runtimeAudioPath: lineC.RUNTIME_AUDIO_PATH,
        ownerTargetedRuntimeCount: 4,
        targetedGeneratedCount: generated.generated.length,
        ownerAuditionFileCount: generated.generated.filter((record) => record.AUDITION_AUDIO_PATH).length,
    };
}

function inspectVfxContracts() {
    const fxModule = require(path.join(ROOT, 'js', 'e9', 'zone3_presentation_fx.js'));
    const audioModule = require(path.join(ROOT, 'js', 'e9', 'journey_zone3_presentation_audio.js'));
    const fxContract = fxModule.create({ document: null, root: null }).getContract();
    assert.equal(fxContract.effectIds.length, 12);
    assert.equal(fxContract.shotIds.length, 10);
    assert.deepEqual(fxContract.shotEffects.SHOT05, [
        'Z3_L01', 'Z3_V01', 'Z3_V02', 'Z3_V03', 'Z3_V05', 'Z3_V06', 'Z3_V07',
    ]);
    assert.deepEqual(fxContract.shotEffects.SHOT07, ['Z3_L01', 'Z3_V01', 'Z3_V08', 'Z3_V09']);
    assert.deepEqual(fxContract.shotEffects.SHOT10, ['Z3_L01', 'Z3_V01', 'Z3_T01_VISUAL']);
    assert.deepEqual(fxContract.shotOptionalEffects.SHOT03, ['Z3_V04']);
    assert.deepEqual(fxContract.shotOptionalEffects.SHOT05, ['Z3_V04']);
    assert.deepEqual(fxContract.shotOptionalEffects.SHOT08, ['Z3_V04']);
    assert.equal(audioModule.SHOT_AUDIO.SHOT06.events.includes('Z3_CENTURION_SPEAR_PLANT'), false);
    assert.equal(audioModule.SHOT_AUDIO.SHOT07.events.includes('Z3_CENTURION_SPEAR_PLANT'), true);
    const css = fs.readFileSync(path.join(ROOT, 'css', 'e9', 'zone3_presentation_fx.css'), 'utf8');
    for (const marker of [
        '.z3-effect-z3-v05::before',
        '.z3-effect-z3-v06::before',
        '.z3-effect-z3-v08::before',
        '.z3-effect-z3-t01-visual .z3-fx-accent',
        '.z3-fx-stage.z3-reduced-motion',
    ]) assert.ok(css.includes(marker), `missing VFX presentation marker: ${marker}`);
    return {
        effectCount: fxContract.effectIds.length,
        shotCount: fxContract.shotIds.length,
        priorityShot05EffectCount: fxContract.shotEffects.SHOT05.length,
        priorityShot07EffectCount: fxContract.shotEffects.SHOT07.length,
        priorityShot10EffectCount: fxContract.shotEffects.SHOT10.length,
        shuiPulseOptionalShots: ['SHOT03', 'SHOT05', 'SHOT08'],
        prioritySfxMovedToShot07: true,
    };
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

async function nextFrames(page, count = 3) {
    await page.evaluate(async (frameCount) => {
        for (let index = 0; index < frameCount; index += 1) {
            await new Promise((resolve) => requestAnimationFrame(resolve));
        }
    }, count);
}

async function selectShotImage(page, src) {
    await page.evaluate((nextSrc) => new Promise((resolve, reject) => {
        const image = document.querySelector('img');
        if (!image) {
            reject(new Error('fixture_image_missing'));
            return;
        }
        const finish = () => {
            image.onload = null;
            image.onerror = null;
            resolve();
        };
        image.onload = finish;
        image.onerror = () => reject(new Error(`fixture_image_failed:${nextSrc}`));
        image.src = nextSrc;
        if (image.complete && image.naturalWidth > 0) finish();
    }), src);
}

async function capturePriorityShot(page, label, shotId) {
    await page.evaluate(() => window.__z3.stopAll());
    await selectShotImage(page, SHOT_IMAGES[shotId]);
    const peakFrameCount = shotId === 'SHOT05' ? 8 : 14;
    await nextFrames(page, peakFrameCount);
    const beforePath = path.join(EVIDENCE_DIR, `${shotId.toLowerCase()}-${label.toLowerCase()}-before.png`);
    await page.screenshot({ path: beforePath, animations: 'disabled' });

    const started = await page.evaluate((id) => window.__z3.transitionShot(id), shotId);
    assert.equal(started.ok, true, `${label} ${shotId} transition failed: ${JSON.stringify(started)}`);
    await page.waitForFunction((expected) =>
        document.querySelectorAll('[data-z3-effect-id]').length >= expected, started.effects.length);
    await nextFrames(page, 2);
    const peakPath = path.join(EVIDENCE_DIR, `${shotId.toLowerCase()}-${label.toLowerCase()}-peak.png`);
    await page.screenshot({ path: peakPath, animations: 'allow' });
    const peakStats = await page.evaluate(() => window.__z3.getResourceStats());
    assert.equal(peakStats.activeEffectCount, started.effects.length, `${label} ${shotId} effect count`);
    assert.equal(started.camera?.ok, true, `${label} ${shotId} camera did not start`);

    await page.evaluate(() => window.__z3.stopAll());
    await nextFrames(page, 2);
    const afterPath = path.join(EVIDENCE_DIR, `${shotId.toLowerCase()}-${label.toLowerCase()}-after.png`);
    await page.screenshot({ path: afterPath, animations: 'disabled' });
    const afterStats = await page.evaluate(() => window.__z3.getResourceStats());
    assert.equal(afterStats.activeEffectCount, 0);
    assert.equal(afterStats.temporaryEffectNodeCount, 0);
    assert.equal(afterStats.activeTimerCount, 0);
    assert.equal(afterStats.activeRafCount, 0);
    return {
        shotId,
        startedEffects: started.effects.length,
        cameraStarted: started.camera?.ok === true,
        peakStats,
        afterStats,
        evidence: [beforePath, peakPath, afterPath],
    };
}

async function verifyShuiPulseTriggers(page) {
    const results = await page.evaluate((shotIds) => shotIds.map((shotId) => {
        const started = window.__z3.transitionShot(shotId);
        const activeIds = window.__z3.getActiveEffectIds();
        window.__z3.stopAll();
        return { shotId, startedIds: started.effects.map((entry) => entry.effectId), activeIds };
    }), ['SHOT03', 'SHOT05', 'SHOT08']);
    for (const result of results) {
        assert.equal(result.startedIds.includes('Z3_V04'), true, `${result.shotId} must trigger Z3_V04`);
        assert.equal(result.activeIds.includes('Z3_V04'), true, `${result.shotId} must mount Z3_V04`);
    }
    return results;
}

async function exerciseViewport(browser, origin, label, viewport, reducedMotion = false) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    await context.setOffline(false);
    const page = await context.newPage();
    const pageErrors = [];
    const consoleErrors = [];
    page.on('pageerror', (error) => pageErrors.push(String(error)));
    page.on('console', (message) => {
        if (message.type() === 'error') consoleErrors.push(message.text());
    });
    await page.emulateMedia({ reducedMotion: reducedMotion ? 'reduce' : 'no-preference' });
    try {
        await page.goto(`${origin}${FIXTURE}`, { waitUntil: 'networkidle' });
        await page.waitForFunction(() => window.__z3Ready === true);
        await page.waitForFunction(() => {
            const image = document.querySelector('img');
            return Boolean(image?.complete && image.naturalWidth > 0);
        });

        const shuiPulseTriggers = await verifyShuiPulseTriggers(page);
        const priority = [];
        for (const shotId of PRIORITY_SHOTS) {
            if (!reducedMotion) priority.push(await capturePriorityShot(page, label, shotId));
            else {
                const started = await page.evaluate((id) => window.__z3.transitionShot(id), shotId);
                assert.equal(started.ok, true);
                assert.equal(started.effects.every((entry) => entry.reducedMotion === true), true);
                const pseudoMotion = await page.evaluate(() => Array.from(
                    document.querySelectorAll('[data-z3-effect-id]'),
                ).map((node) => getComputedStyle(node, '::before').animationName));
                assert.equal(pseudoMotion.every((name) => name === 'none'), true);
                await page.evaluate(() => window.__z3.stopAll());
            }
        }

        if (!reducedMotion) {
            for (let cycle = 0; cycle < 3; cycle += 1) {
                for (const shotId of PRIORITY_SHOTS) {
                    const started = await page.evaluate((id) => window.__z3.transitionShot(id), shotId);
                    assert.equal(started.ok, true);
                    await nextFrames(page, 2);
                    await page.evaluate(() => window.__z3.stopAll());
                }
                const stats = await page.evaluate(() => window.__z3.getResourceStats());
                assert.equal(stats.activeEffectCount, 0);
                assert.equal(stats.activeTimerCount, 0);
                assert.equal(stats.activeRafCount, 0);
            }
        }
        const finalStats = await page.evaluate(() => window.__z3.getResourceStats());
        assert.equal(finalStats.activeEffectCount, 0);
        assert.equal(finalStats.temporaryEffectNodeCount, 0);
        assert.deepEqual(pageErrors, []);
        assert.deepEqual(consoleErrors, []);
        return { shuiPulseTriggers, priority, finalStats, pageErrors, consoleErrors };
    } finally {
        await context.close();
    }
}

async function exerciseIntegratedFixture(browser, origin, viewport, reducedMotion = false) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(String(error)));
    await page.emulateMedia({ reducedMotion: reducedMotion ? 'reduce' : 'no-preference' });
    try {
        await page.goto(`${origin}${INTEGRATED_FIXTURE}`, { waitUntil: 'networkidle' });
        await page.waitForFunction(() => Boolean(window.__z3Ready && typeof window.__z3Ready.then === 'function'));
        await page.evaluate(() => window.__z3Ready);
        await page.waitForFunction(() => [...document.images].every(
            (image) => image.complete && image.naturalWidth > 0,
        ));
        const report = await page.evaluate(() => window.__z3.runAll());
        assert.equal(report.shotCount, 10);
        assert.deepEqual(report.phaseLengths, [5, 2, 3]);
        assert.equal(report.manifestCueCount, 18);
        assert.equal(report.noCrossLocaleVoiceFallback, true);
        assert.equal(report.finalAudio.activeAudioCount, 0);
        assert.equal(report.finalAudio.activeBgmCount, 0);
        assert.equal(report.finalAudio.activeAmbienceCount, 0);
        assert.equal(report.finalAudio.activeTransientCount, 0);
        assert.equal(report.finalAudio.listenerCount, 0);
        assert.equal(report.finalFx.activeEffectCount, 0);
        assert.equal(report.finalFx.activeTimerCount, 0);
        assert.equal(report.finalFx.activeRafCount, 0);
        assert.equal(report.finalFx.activeEventListenerCount, 0);
        assert.deepEqual(pageErrors, []);
        return report;
    } finally {
        await context.close();
    }
}

async function run() {
    await fsPromises.mkdir(EVIDENCE_DIR, { recursive: true });
    const audio = inspectAudioIntegrity();
    const vfx = inspectVfxContracts();
    const executablePath = findChrome();
    assert.ok(executablePath, 'Chrome/Edge executable is required for browser evidence');
    const { server, origin } = await startStaticServer();
    const browser = await chromium.launch({ headless: true, executablePath });
    const browserResults = {};
    const integratedResults = {};
    try {
        for (const [label, viewport] of VIEWPORTS) {
            browserResults[label] = await exerciseViewport(browser, origin, label, viewport, false);
            integratedResults[label] = await exerciseIntegratedFixture(browser, origin, viewport, false);
        }
        browserResults.REDUCED_MOTION = await exerciseViewport(
            browser,
            origin,
            'REDUCED_MOTION',
            { width: 430, height: 932 },
            true,
        );
        integratedResults.REDUCED_MOTION = await exerciseIntegratedFixture(
            browser,
            origin,
            { width: 430, height: 932 },
            true,
        );
    } finally {
        await browser.close();
        await new Promise((resolve) => server.close(resolve));
    }

    for (const [label] of VIEWPORTS) console.log(`${label}_VFX=PASS`);
    for (const [label] of VIEWPORTS) console.log(`${label}_INTEGRATED_VFX=PASS`);
    console.log('REDUCED_MOTION_VFX=PASS');
    console.log('REDUCED_MOTION_INTEGRATED_VFX=PASS');
    console.log('FIRST_PLAY_VFX_PASS=YES');
    console.log('REPLAY_VFX_PASS=YES');
    console.log('REPEATED_REPLAY_3X_PASS=YES');
    console.log('ORPHAN_TIMER_COUNT=0');
    console.log('ORPHAN_RAF_COUNT=0');
    console.log('STALE_PRESENTATION_NODE_COUNT=0');
    console.log('ZH_TW_AUDIO_INTEGRITY=PASS');
    console.log(`SHOT1_5_ZH_LINE_COUNT=${audio.shot1to5LineCount}`);
    console.log('OWNER_LINE_C_CANONICAL_MATCH=NO');
    console.log(`OWNER_EVIDENCE_DIR=${path.relative(ROOT, EVIDENCE_DIR).replaceAll(path.sep, '/')}`);
    console.log(`TARGETED_REPAIR_MANIFEST=${path.relative(ROOT, TARGETED_REPAIR_MANIFEST).replaceAll(path.sep, '/')}`);
    console.log(JSON.stringify({ audio, vfx, browserResults, integratedResults }, null, 2));
}

run().catch((error) => {
    console.error(`OWNER_AUDIO_VFX_QA=FAIL ${error.stack || error}`);
    process.exitCode = 1;
});
