const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const HERO_PATH = path.join(REPO_ROOT, 'hero.html');
const SW_PATH = path.join(REPO_ROOT, 'sw.js');
const HERO_SOURCE = fs.readFileSync(HERO_PATH, 'utf8');
const A028_START = '// ── A028 Player Presentation read-only adoption';
const A028_END = '// ── End A028 Player Presentation read-only adoption';
const A028_START_OFFSET = HERO_SOURCE.indexOf(A028_START);
const A028_BLOCK_START = HERO_SOURCE.indexOf('\n', A028_START_OFFSET) + 1;
const A028_BLOCK_END = HERO_SOURCE.indexOf(A028_END);
const A028_BLOCK = HERO_SOURCE.slice(A028_BLOCK_START, A028_BLOCK_END);

assert(A028_BLOCK.includes("fetch('/api/player/presentation'"));
assert.strictEqual((HERO_SOURCE.match(/fetch\('\/api\/player\/presentation'/g) || []).length, 1);
assert(A028_BLOCK.includes("contract_version !== A028_PLAYER_PRESENTATION_CONTRACT"));
assert(A028_BLOCK.includes("payload.projection_status !== 'OK'"));
assert(A028_BLOCK.includes("progression.xp"));
assert(A028_BLOCK.includes("progression.level"));
assert(A028_BLOCK.includes("progression.rank_level"));
assert(A028_BLOCK.includes("progression.go_rank"));
for (const forbidden of [
  'total_correct',
  'current_streak',
  'max_streak',
  'selectedZone',
  'progressionZone',
  'encounter_hp',
  'combat_stats',
  'premium',
  'localStorage',
]) {
  assert(!A028_BLOCK.includes(forbidden), `A028 must not consume ${forbidden}`);
}
assert(HERO_SOURCE.includes("fetch('/api/skills/profile'"), 'legacy profile fallback must remain');
assert(HERO_SOURCE.indexOf('renderHeroOverview();') < HERO_SOURCE.indexOf('a028ApplyPlayerPresentationSafeFields(playerPresentation, res)'));
for (const retainedAuthority of [
  "fetch('/api/player/appearance'",
  "fetch('/api/player/inventory'",
  "fetch('/api/pet/status'",
  "fetch('/api/skills/equip'",
  "fetch('/api/pet/choose'",
]) {
  assert(HERO_SOURCE.includes(retainedAuthority), `existing authority must remain: ${retainedAuthority}`);
}
for (const forbiddenAuthority of [
  '/api/player/inventory',
  '/api/pet/status',
  '/api/skills/equip',
  'localStorage',
]) {
  assert(!A028_BLOCK.includes(forbiddenAuthority), `A028 must not absorb ${forbiddenAuthority}`);
}

function createDocument() {
  const elements = {};
  for (const id of [
    'char-name',
    'badge-lv',
    'badge-go',
    'char-xp',
    'char-xp-bar',
    'char-xp-pct',
    'hero-overview-name',
    'hero-overview-rank',
    'hero-overview-xp',
  ]) {
    elements[id] = { textContent: '', style: {} };
  }
  return {
    elements,
    getElementById(id) { return elements[id] || null; },
  };
}

function createContext(responseFactory) {
  const document = createDocument();
  const context = {
    console: { warn() {} },
    document,
    I18n: { t() { return ''; } },
    fetch: responseFactory,
    Promise,
    Number,
    Object,
    Array,
    Error,
  };
  vm.runInNewContext(`${A028_BLOCK}\nthis.__a028 = {
    loadPlayerPresentationSnapshot,
    a028NormalizePlayerPresentationSnapshot,
    a028HeroOverviewView,
    a028ApplyPlayerPresentationSafeFields,
  };`, context, { filename: 'hero.html#a028' });
  return { context, document };
}

function healthyPayload() {
  return {
    contract_version: 'PLAYER_PRESENTATION_API_V1',
    player_id: 17,
    projection_status: 'OK',
    hero: { hero_id: 'apprentice' },
    progression: {
      xp: 321,
      level: 12,
      rank_level: 'LV12',
      go_rank: '1d',
      total_correct: 999,
      current_streak: 88,
      max_streak: 100,
    },
    display_identity: { display_name: 'Server Hero', username: 'qa' },
    equipment: { combat_stats: { damage: 999 } },
    premium: { active: true },
  };
}

async function main() {
  const calls = [];
  const healthy = createContext(async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => healthyPayload() };
  });

  const first = await healthy.context.__a028.loadPlayerPresentationSnapshot();
  const second = await healthy.context.__a028.loadPlayerPresentationSnapshot();
  assert.strictEqual(calls.length, 1, 'one bounded fetch per hydration lifecycle');
  assert.strictEqual(calls[0].url, '/api/player/presentation');
  assert.strictEqual(calls[0].options.credentials, 'include');
  assert.strictEqual(calls[0].options.cache, 'no-store');
  assert.strictEqual(first.projection_status, 'OK');
  assert.strictEqual(first.hero.hero_id, 'apprentice');
  assert.strictEqual(first.progression.xp, 321);
  assert.strictEqual(first.progression.level, 12);
  assert.strictEqual(first.progression.rank_level, 'LV12');
  assert.strictEqual(first.progression.go_rank, '1d');
  assert.strictEqual(second, first, 'in-flight/result promise is reused safely');
  assert(!JSON.stringify(first).includes('total_correct'));
  assert(!JSON.stringify(first).includes('current_streak'));
  assert(!JSON.stringify(first).includes('max_streak'));
  assert(!JSON.stringify(first).includes('combat_stats'));
  assert(!JSON.stringify(first).includes('premium'));

  const legacyProfile = {
    display_name: 'Legacy Name',
    username: 'legacy',
    character_key: 'apprentice_girl',
    xp: 1,
    xp_next: 1000,
    level: 1,
    rank_level: 'OLD',
    go_rank: '30k',
  };
  const view = healthy.context.__a028.a028HeroOverviewView(legacyProfile);
  assert.strictEqual(view.source, 'player_presentation');
  assert.strictEqual(view.heroId, 'apprentice');
  assert.strictEqual(view.displayName, 'Server Hero');
  assert.strictEqual(view.xp, 321);
  assert.strictEqual(view.level, 12);
  assert.strictEqual(view.rankLevel, 'LV12');
  assert.strictEqual(view.goRank, '1d');
  healthy.context.__a028.a028ApplyPlayerPresentationSafeFields(first, legacyProfile);
  assert.strictEqual(healthy.document.elements['char-name'].textContent, 'Server Hero');
  assert.strictEqual(healthy.document.elements['badge-lv'].textContent, 'LV12');
  assert.strictEqual(healthy.document.elements['badge-go'].textContent, '1d');
  assert.strictEqual(healthy.document.elements['char-xp'].textContent, '321 / 1,000 XP');
  assert.strictEqual(healthy.document.elements['hero-overview-rank'].textContent, 'LV12 · 1d');
  assert.strictEqual(healthy.document.elements['hero-overview-xp'].textContent, '321 / 1,000 XP');
  assert.strictEqual(healthy.document.elements['char-xp-bar'].style.width, '32%');
  assert.strictEqual(healthy.document.elements['char-xp-pct'].textContent, '32%');

  const invalid = createContext(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ ...healthyPayload(), projection_status: 'INVALID_STATE' }),
  }));
  assert.strictEqual(await invalid.context.__a028.loadPlayerPresentationSnapshot(), null);
  const invalidView = invalid.context.__a028.a028HeroOverviewView(legacyProfile);
  assert.strictEqual(invalidView.source, 'legacy_profile_fallback');
  assert.strictEqual(invalidView.xp, 1);
  assert.strictEqual(invalidView.rankLevel, 'OLD');

  const unavailable = createContext(async () => ({ ok: false, status: 503, json: async () => ({}) }));
  assert.strictEqual(await unavailable.context.__a028.loadPlayerPresentationSnapshot(), null);

  const malformed = createContext(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ contract_version: 'WRONG', projection_status: 'OK' }),
  }));
  assert.strictEqual(await malformed.context.__a028.loadPlayerPresentationSnapshot(), null);

  const sw = fs.readFileSync(SW_PATH, 'utf8');
  assert.strictEqual(
    (sw.match(/^const VERSION\s*=\s*'[^']+';/m) || [])[0],
    "const VERSION     = 'v240-a028-hero-player-presentation-readonly';",
  );
  console.log('A028 Hero Player Presentation tests: 14 passed');
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
