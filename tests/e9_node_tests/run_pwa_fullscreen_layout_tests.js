'use strict';

/**
 * A_E10_PWA_FULLSCREEN_STORY_AND_BATTLE_LAYOUT_CORRECTIVE_013
 *
 * Static contract for the A013 section of css/e9/reference_world_map.css.  The
 * behavioural proof is tests/e2e/run_a013_pwa_fullscreen_story_battle_contract.mjs
 * (a real engine at the Owner-evidence viewports); this harness pins the structure
 * that keeps the corrective narrow: what it is scoped to, what it may scale, and
 * what it must never touch.
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const css = fs.readFileSync(path.join(REPO_ROOT, 'css', 'e9', 'reference_world_map.css'), 'utf8');
const shellCss = fs.readFileSync(path.join(REPO_ROOT, 'css', 'e9', 'shell.css'), 'utf8');
const indexHtml = fs.readFileSync(path.join(REPO_ROOT, 'index.html'), 'utf8');

const tests = [];
function test(name, fn) { tests.push([name, fn]); }

const SECTION_START = css.indexOf('A_E10_PWA_FULLSCREEN_STORY_AND_BATTLE_LAYOUT_CORRECTIVE_013');
const SECTION_END = css.indexOf('@media (prefers-reduced-motion: reduce)', SECTION_START);
assert.ok(SECTION_START !== -1 && SECTION_END > SECTION_START, 'A013 section not found');
const section = css.slice(SECTION_START, SECTION_END);

// Minimal block parser: returns [{ query, rules: [{ selector, body }] }] for every
// top-level @media block of the A013 section (comments stripped).
function parseMediaBlocks(text) {
  const src = text.replace(/\/\*[\s\S]*?\*\//g, '');
  const blocks = [];
  let i = 0;
  while (i < src.length) {
    const at = src.indexOf('@media', i);
    if (at === -1) break;
    const open = src.indexOf('{', at);
    const query = src.slice(at + 6, open).trim();
    let depth = 0;
    let j = open;
    for (; j < src.length; j++) {
      if (src[j] === '{') depth++;
      else if (src[j] === '}') { depth--; if (depth === 0) break; }
    }
    const inner = src.slice(open + 1, j);
    const rules = [];
    const re = /([^{}]+)\{([^{}]*)\}/g;
    let m;
    while ((m = re.exec(inner))) rules.push({ selector: m[1].trim().replace(/\s+/g, ' '), body: m[2].trim() });
    blocks.push({ query, rules });
    i = j + 1;
  }
  return blocks;
}
const blocks = parseMediaBlocks(section);
const allRules = blocks.flatMap((b) => b.rules.map((r) => ({ ...r, query: b.query })));

const COMBAT = '#main-row[data-a032-combat-surface="v1"] #board-canvas-wrap:not(.hidden)';
const isBattleRule = (r) => r.selector.includes('#main-row[data-a032-combat-surface') || r.selector.includes('--a013-') || /\bBODY\b/.test(r.selector);

test('the A013 section is parsed (story + portrait battle + landscape battle blocks exist)', () => {
  assert.ok(blocks.length >= 6, `expected >= 6 media blocks, got ${blocks.length}`);
  assert.ok(allRules.length >= 30, `expected >= 30 rules, got ${allRules.length}`);
});

test('the portrait mirror restores the native companion rule: an active question hides #welcome-state', () => {
  const nativeHide = /body\[data-adventure-shell-active="e9"\] #main-row #main-left #welcome-state\.hidden\s*\{\s*display:\s*none !important;/;
  assert.ok(nativeHide.test(shellCss), 'the native pair (shell.css) is missing -- this test has nothing to mirror');
  const mirrorShow = css.indexOf('html[data-go-portrait-tablet-override] body[data-e10-visual-skin="immersive-rpg"][data-adventure-shell-active="e9"] #main-row #main-left #welcome-state {');
  const mirrorHide = css.indexOf('html[data-go-portrait-tablet-override] body[data-e10-visual-skin="immersive-rpg"][data-adventure-shell-active="e9"] #main-row #main-left #welcome-state.hidden {');
  assert.ok(mirrorShow !== -1, 'the mirror show rule must still exist (A007)');
  assert.ok(mirrorHide !== -1, 'the portrait mirror must carry the .hidden companion rule');
  assert.ok(mirrorHide > mirrorShow, 'the .hidden rule must come after the show rule (same specificity + !important)');
  const hideBody = css.slice(css.indexOf('{', mirrorHide), css.indexOf('}', mirrorHide));
  assert.ok(/display:\s*none\s*!important/.test(hideBody), 'the .hidden companion must be display:none !important');
  // Both live in the same @media (min-width:1280px) mirror block.
  const blockStart = css.lastIndexOf('@media (min-width: 1280px) {', mirrorShow);
  const nextMedia = css.indexOf('\n@media', mirrorShow);
  assert.ok(blockStart !== -1 && mirrorHide < nextMedia, 'the companion rule must be inside the same media block as the show rule');
});

test('every battle-layout rule is gated by the combat-surface signal (the map is never restyled)', () => {
  const battle = allRules.filter((r) => /--a013-(m|z|chrome)|#main-row|\.q-header|#srs-progress|#side-col|\.quiz-board-anchor|#board-col|#msg-box|#board-layout|#main-left|\.practice|\.q-meta/.test(r.selector) && !r.selector.includes('#boss-cinematic'));
  assert.ok(battle.length >= 20, `expected >= 20 battle rules, got ${battle.length}`);
  for (const r of battle) {
    assert.ok(r.selector.split(',').every((s) => s.includes(COMBAT)), `battle rule not gated by the combat signal: ${r.selector.slice(0, 140)}`);
  }
});

test('portrait battle rules are scoped to the classified installed tablet; landscape rules to a standalone, touch, very wide landscape viewport', () => {
  const portrait = allRules.filter((r) => r.selector.includes('html[data-go-portrait-tablet-override]') && r.selector.includes(COMBAT));
  const landscape = allRules.filter((r) => r.selector.includes('html[data-go-display-mode="standalone"]') && r.selector.includes(COMBAT));
  assert.ok(portrait.length >= 10, 'portrait battle rules missing');
  assert.ok(landscape.length >= 10, 'landscape battle rules missing');
  for (const r of allRules.filter((x) => x.selector.includes(COMBAT))) {
    const ok = r.selector.split(',').every((s) => s.includes('html[data-go-portrait-tablet-override]') || s.includes('html[data-go-display-mode="standalone"]'));
    assert.ok(ok, `unscoped battle rule: ${r.selector.slice(0, 140)}`);
  }
  for (const r of landscape) {
    assert.ok(/\(min-width:\s*1900px\)/.test(r.query) && /\(orientation:\s*landscape\)/.test(r.query) && /\(hover:\s*none\)/.test(r.query), `landscape rule outside the PWA-scale media query: ${r.query}`);
  }
  for (const r of portrait) assert.ok(/\(min-width:\s*(768|1280)px\)/.test(r.query), `portrait rule outside a tablet media query: ${r.query}`);
});

test('story rules are scoped to the E10 intro-film overlay on tablet/desktop widths and never use the old fixed caps', () => {
  const story = allRules.filter((r) => r.selector.includes('#boss-cinematic'));
  assert.ok(story.length >= 8, `expected >= 8 story rules, got ${story.length}`);
  for (const r of story) {
    assert.ok(r.selector.split(',').every((s) => s.includes('body[data-e10-visual-skin="immersive-rpg"] #boss-cinematic.intro-film')), `story rule not scoped to the E10 intro film: ${r.selector.slice(0, 120)}`);
    assert.ok(/\(min-width:\s*768px\)/.test(r.query), `story rule outside (min-width: 768px): ${r.query}`);
    assert.ok(!/\b(900|560|960)px\b/.test(r.body), `old fixed cap found in a story rule: ${r.body.slice(0, 120)}`);
  }
  const text = story.map((r) => r.body).join('\n');
  for (const side of ['top', 'right', 'bottom', 'left']) assert.ok(text.includes(`env(safe-area-inset-${side}`), `safe-area-inset-${side} is not honoured`);
  assert.ok(/100dvh/.test(section), 'dynamic viewport height is not used');
  assert.ok(/aspect-ratio:\s*16 \/ 9/.test(text), 'the landscape frame must keep its 16:9 ratio');
  assert.ok(/object-fit:\s*contain/.test(text), 'portrait art must stay undistorted (contain)');
});

test('the film READY card is never clipped: overflow / max-height on the subtitle card exist only for the playing film', () => {
  // index.html: .boss-cinematic.intro-film .boss-cinematic-btn { position:absolute; bottom: calc(100% + 12px) } -- the primary
  // CTA sits OUTSIDE the card box, so any overflow clip on the card hides it (an earlier revision of this section did).
  assert.ok(/\.boss-cinematic\.intro-film \.boss-cinematic-btn\s*\{[^}]*bottom:\s*calc\(100% \+ 12px\)/.test(indexHtml), 'the contract this guard protects moved -- re-derive');
  const cardRules = allRules.filter((r) => /\.boss-cinematic-content$/.test(r.selector.split(',').pop().trim()));
  assert.ok(cardRules.length >= 2, 'card rules missing');
  for (const r of cardRules) {
    const decls = r.body.split(';').map((d) => d.trim()).filter(Boolean).map((d) => [d.slice(0, d.indexOf(':')).trim(), d.slice(d.indexOf(':') + 1).trim()]);
    // only a declaration that can actually clip counts (overflow other than visible, max-height other than none)
    const clips = decls.some(([n, v]) => ((n === 'overflow' || n === 'overflow-y') && v !== 'visible') || (n === 'max-height' && v !== 'none'));
    if (clips) assert.ok(r.selector.includes('.intro-film:not(.ready)'), `a clip on the subtitle card must be limited to the playing film: ${r.selector.slice(0, 150)}`);
  }
  assert.ok(cardRules.some((r) => r.selector.includes('.intro-film:not(.ready)') && /overflow:\s*auto/.test(r.body)), 'the playing-film card should still scroll a very long line');
  // ...and the ready card is reset explicitly so the native Zone 2 / Zone 4 portrait rules (max-height + overflow:auto, index.html)
  // cannot clip the CTA on an iPad in Safari portrait.
  const reset = cardRules.find((r) => r.selector.includes('.intro-film.ready'));
  assert.ok(reset && /max-height:\s*none/.test(reset.body) && /overflow:\s*visible/.test(reset.body), 'the ready card must reset max-height and overflow explicitly');
  assert.ok(/#boss-cinematic\.intro-film\[data-zone-key="k21_25"\] \.boss-cinematic-content[^}]*overflow:\s*auto/.test(indexHtml.replace(/\s+/g, ' ')), 'the native zone rule this reset outranks moved -- re-derive');
});

test('the board is never scaled: no zoom / transform / aspect-ratio rule targets the board wrapper, anchor or canvas', () => {
  for (const r of allRules) {
    const last = r.selector.split(',').map((s) => s.trim().split(' ').pop());
    const targetsBoard = last.some((t) => /#board-canvas-wrap|\.quiz-board-anchor|canvas|\.wgo-board/.test(t));
    if (!targetsBoard) continue;
    assert.ok(!/(^|;)\s*(zoom|transform|scale|aspect-ratio)\s*:/.test(r.body), `the board is scaled by: ${r.selector.slice(0, 140)} { ${r.body.slice(0, 100)} }`);
  }
});

test('zoom is the only scale mechanism, it uses one named factor, and only non-board blocks receive it', () => {
  const allowed = /(\.q-header|#srs-progress|\.btn-row|\.sgf-report-widget|#msg-box|#side-col)$/;
  const zoomRules = allRules.filter((r) => /(^|;)\s*zoom\s*:/.test(r.body));
  assert.ok(zoomRules.length >= 8, 'expected the HUD / header / controls to be scaled by the factor');
  for (const r of zoomRules) {
    const value = /zoom\s*:\s*([^;]+)/.exec(r.body)[1].trim();
    assert.ok(/^(var\(--a013-z\)|calc\(var\(--a013-z\) \+ \.2\))$/.test(value), `zoom must use the named factor, got: ${value}`);
    for (const s of r.selector.split(',')) assert.ok(allowed.test(s.trim()), `zoom applied to a non-HUD element: ${s.trim().slice(0, 140)}`);
  }
});

test('lengths that live inside a zoomed block are divided by the same factor (report row)', () => {
  const rule = allRules.find((r) => r.selector.includes('.sgf-report-widget') && /width\s*:/.test(r.body));
  assert.ok(rule, 'the landscape report-row width rule is missing');
  assert.ok(/calc\(\(100dvh - var\(--a013-chrome-l\)\) \/ var\(--a013-z\)\)/.test(rule.body), `report width must divide by the zoom factor: ${rule.body}`);
});

test('the corrective never touches the accepted world map or the A007 Replay placement', () => {
  for (const r of allRules) {
    assert.ok(!/#e9-|\.e9-zone|\.e10-map|e9-world-stage/.test(r.selector), `A013 rule touches the world map: ${r.selector.slice(0, 140)}`);
  }
  // A007: the portrait Replay CTA is still a grid cell of the selected-zone card.
  assert.ok(/\.e9-zone-details__story-replay[^}]*grid-area:\s*9 \/ 1 \/ 10 \/ 2/.test(css), 'A007 portrait Replay placement rule is missing');
  assert.ok(/\.e9-zone-details__landmark\s*\{[^}]*grid-area:\s*3 \/ 1 \/ 9 \/ 2/.test(css), 'A007 landmark grid-area rule is missing');
});

test('the board keeps its layout-derived size: landscape and portrait cap it from the viewport, not from a fixed pixel size', () => {
  const anchors = allRules.filter((r) => r.selector.includes('.quiz-board-anchor'));
  assert.ok(anchors.length >= 2, 'portrait + landscape anchor rules expected');
  for (const r of anchors) assert.ok(/100dvh - var\(--a013-chrome-(p|l)\)/.test(r.body), `board size must derive from the viewport: ${r.body}`);
  assert.ok(/max-width:[^;]*!important/.test(anchors.find((r) => r.selector.includes('html[data-go-portrait-tablet-override]')).body), 'the portrait cap must beat the native !important practice-state cap');
});

test('the viewport meta and the standalone classifier are untouched by A013', () => {
  assert.ok(indexHtml.includes('<meta name="viewport" content="width=device-width, initial-scale=1.0">'));
  assert.ok(indexHtml.includes('function computeOverride() {'));
  assert.ok(indexHtml.includes("document.documentElement.toggleAttribute('data-go-portrait-tablet-override', active);"));
  assert.ok(indexHtml.includes("document.documentElement.setAttribute('data-go-display-mode', standalone ? 'standalone' : 'browser');"));
});

test('the section adds no generic, unscoped rule', () => {
  for (const r of allRules) {
    for (const s of r.selector.split(',')) {
      assert.ok(s.trim().startsWith('body[data-e10-visual-skin="immersive-rpg"]') || s.trim().startsWith('html[data-go-'), `unscoped selector: ${s.trim().slice(0, 140)}`);
    }
  }
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log('ok   - ' + name); } catch (err) { failed += 1; console.log('FAIL - ' + name); console.log('       ' + err.message); }
}
console.log('');
console.log((tests.length - failed) + '/' + tests.length + ' passed');
process.exit(failed === 0 ? 0 : 1);
