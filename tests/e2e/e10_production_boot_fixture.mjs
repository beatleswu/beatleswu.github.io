/*
 * Production-boot-path fixture for the E10 Adventure Shell (A_E10_RUNTIME_
 * AUTHORITY_RECON_BEFORE_PWA_CORRECTIVE_006).
 *
 * Why this exists. The E10 world map is not a separate page: it is the E9
 * component shell mounted with the E10 presentation (data-world-presentation-
 * state="e10", body[data-e10-visual-skin="immersive-rpg"]). Production turns it
 * on for a real player through the server: /api/auth/me returns
 * e9_rollout.effective_flags (app.py _e9_rollout_decision; Production runs
 * E9_ROLLOUT_SCOPE=authenticated, GLOBAL_ENABLED=true, all six flags), and
 * index.html applies them via window.__GO_E9_SERVER_FLAGS__.
 *
 * The query-string overrides (?E9_DEBUG=1&e9Shell=1&...) are NOT that path:
 * js/e9/feature_flags.js honours them only on a debug hostname (localhost,
 * 127.0.0.1, *.local, *.test). A page served from any other host -- a LAN review
 * URL, for instance -- silently ignores them and falls back to the LEGACY
 * Adventure Map, which is what an earlier review harness showed the Owner.
 *
 * So a test that wants the CURRENT E10 runtime must boot through the rollout
 * decision, with no query flags, and must answer the endpoints the shell reads
 * with the real response shapes (otherwise the HUD, the SRS/question runtime and
 * the map's authority all degrade into "unavailable"/Retry states that
 * Production never shows).
 */

import fs from 'node:fs';

// The real GET /api/adventure/bootstrap payload (see the fixture's _provenance)
// is the key/shape authority: real zone names, boss blocks, stages, placement
// and cinematics, rather than a hand-made subset.
const REAL_BOOTSTRAP = JSON.parse(fs.readFileSync(new URL('./fixtures/e10_real_bootstrap_shape.json', import.meta.url), 'utf8')).payload;

export const ZONE_KEYS = ['k26_30', 'k21_25', 'k16_20', 'k11_15', 'k6_10', 'k1_5', 'd1_2', 'd3_4', 'd5_6', 'd7_plus'];

export const ALL_E9_FLAGS = Object.freeze({
  e9Shell: true, e9TopHud: true, e9LeftNav: true, e9RightCards: true, e9BottomDock: true, e9WorldStage: true,
});

// The URL a real player's browser opens: no E9 flags at all.
export const PRODUCTION_SHELL_QUERY = '?lang=zh';

const QUESTIONS = Array.from({ length: 20 }, (_, i) => ({ id: 7001 + i, topic: 'life_death', rank: '15k' }));

export function authMeBody(overrides = {}) {
  return {
    logged_in: true, user_id: 7, username: 'e10_fixture', nickname: '', display_name: 'Review Player',
    is_admin: false, plan: 'premium', is_premium: true, is_premium_live: true, go_rank: '15k',
    tour_done: true, needs_onboarding_choice: false, newbie_quest_eligible: false,
    e9_rollout: {
      eligible: true, reason: 'authenticated', effective_flags: { ...ALL_E9_FLAGS },
      decision_version: 'e9-rollout-v1-fixture', kill_switch: false,
    },
    ...overrides,
  };
}

const clone = (value) => JSON.parse(JSON.stringify(value));
const UNMET_BOSS = { available: false, challenge_threshold: 9, remaining_to_challenge: 9 };
const MET_BOSS = { available: true, challenge_threshold: 9, remaining_to_challenge: 0 };

/*
 * A bootstrap payload in the REAL shape with the zones set to the requested
 * states (one of 'completed' | 'skipped' | 'unlocked' | 'bossready' | 'unlocked_no_entry' | 'locked' per zone, in
 * ZONE_KEYS order). Only the fields the server derives from those states are
 * rewritten (see app.py's adventure bootstrap: status, can_enter, cleared,
 * completed, skipped_by_placement, stars, boss availability); everything else --
 * names, labels, boss identity, stages, cinematics -- stays as the real payload.
 * 'skipped' zones reproduce the server's rule: placement started at a later zone,
 * the zone is enterable, and it was never cleared.
 *
 * Lord readiness is real, not implied: the client treats a Lord as ready when
 * boss.available is true OR boss.remaining_to_challenge <= 0 (index.html
 * _adventureBossReady), and the story model unlocks a zone's boss-ready segment
 * from that. So 'unlocked' and 'skipped' zones carry a real, unmet threshold
 * (remaining > 0), and 'bossready' is the state where it has been met. (The
 * captured payload's zeros are an artefact of the harness's empty corpus.)
 *
 * 'unlocked_no_entry' is NOT emitted by the real server (an unenterable zone is
 * 'locked'). It exists only to prove that the story model, and not the zone's
 * status label, decides Replay availability.
 */
export function realBootstrap(zoneStates, { current = null, primary = null, secondary = null, seenIntro = [] } = {}) {
  if (!Array.isArray(zoneStates) || zoneStates.length !== ZONE_KEYS.length) {
    throw new Error(`realBootstrap needs ${ZONE_KEYS.length} zone states`);
  }
  const payload = clone(REAL_BOOTSTRAP);
  // Selecting a zone whose first-entry film has not been seen launches that film as
  // a full-screen overlay (shipped behaviour). Tests that need the zone CARD to be
  // the visible surface mark the opening as seen; only the pre-play marker is set,
  // so which story segments are unlocked does not change.
  ZONE_KEYS.forEach((key, index) => {
    if (seenIntro.includes(key) && payload.cinematics && payload.cinematics[`e10_zone${index + 1}_intro_v1`]) {
      payload.cinematics[`e10_zone${index + 1}_intro_v1`] = { seen: true, seen_at: '2026-01-01T00:00:00' };
    }
  });
  const lastSkipped = zoneStates.lastIndexOf('skipped');
  const placementStart = lastSkipped >= 0 ? ZONE_KEYS[Math.min(lastSkipped + 1, ZONE_KEYS.length - 1)] : payload.placement.effective_start_zone_key;
  payload.zones = payload.zones.map((zone, index) => {
    const next = { ...zone };
    const state = zoneStates[index];
    const set = (fields) => Object.assign(next, fields);
    const stage = (status) => { next.stages = (zone.stages || []).map((entry) => ({ ...entry, status, skipped_by_placement: state === 'skipped', can_enter: next.can_enter, completed: next.completed })); };
    if (state === 'completed') {
      set({ status: 'completed', unlocked: true, can_enter: true, cleared: true, completed: true, skipped_by_placement: false, stars: 3, zone_authority_stars: 3, legacy_visible_stars: 3, boss_ready: false, path_shines_to_next: true });
      next.boss = { ...zone.boss, available: false, replay_available: true };
      stage('completed');
    } else if (state === 'skipped') {
      set({ status: 'skipped_by_placement', unlocked: true, can_enter: true, cleared: false, completed: false, skipped_by_placement: true, stars: 0, zone_authority_stars: 0, legacy_visible_stars: 0, boss_ready: false, placement_unlocked: true, placement_start_zone: placementStart });
      next.boss = { ...zone.boss, ...UNMET_BOSS };
      stage('skipped_by_placement');
    } else if (state === 'unlocked') {
      set({ status: 'unlocked', unlocked: true, can_enter: true, cleared: false, completed: false, skipped_by_placement: false, stars: 0, zone_authority_stars: 0, legacy_visible_stars: 0, boss_ready: false });
      next.boss = { ...zone.boss, ...UNMET_BOSS };
      stage('unlocked');
    } else if (state === 'bossready') {
      set({ status: 'unlocked', unlocked: true, can_enter: true, cleared: false, completed: false, skipped_by_placement: false, stars: 0, zone_authority_stars: 0, legacy_visible_stars: 0, boss_ready: true });
      next.boss = { ...zone.boss, ...MET_BOSS };
      stage('unlocked');
    } else if (state === 'unlocked_no_entry') {
      set({ status: 'unlocked', unlocked: false, can_enter: false, cleared: false, completed: false, skipped_by_placement: false, stars: 0, zone_authority_stars: 0, legacy_visible_stars: 0, boss_ready: false });
      next.boss = { ...zone.boss, ...UNMET_BOSS };
      stage('unlocked');
    } else if (state === 'locked') {
      set({ status: 'locked', unlocked: false, can_enter: false, cleared: false, completed: false, skipped_by_placement: false, stars: 0, zone_authority_stars: 0, legacy_visible_stars: 0, boss_ready: false });
      next.boss = { ...zone.boss, available: false };
      stage('locked');
    } else {
      throw new Error(`unknown zone state ${state}`);
    }
    return next;
  });
  const firstOpen = ZONE_KEYS.find((key, index) => ['unlocked', 'bossready', 'skipped'].includes(zoneStates[index]) && zoneStates.slice(index).some((x) => x === 'unlocked' || x === 'bossready')) || ZONE_KEYS.find((key, index) => zoneStates[index] === 'unlocked' || zoneStates[index] === 'bossready') || null;
  const currentKey = current || firstOpen || payload.current_zone_key;
  payload.current_zone_key = currentKey;
  payload.active_zone_key = currentKey;
  payload.primary_action = primary;
  payload.secondary_action = secondary;
  payload.recommended = { ...payload.recommended, zone_key: currentKey, stage_key: currentKey };
  payload.selected = { ...payload.selected, zone_key: currentKey, stage_key: currentKey };
  payload.placement = { ...payload.placement, effective_start_zone_key: placementStart };
  payload.zones.forEach((zone) => { zone.recommended = zone.key === currentKey; zone.selected = zone.key === currentKey; zone.effective_start_zone_key = placementStart; });
  return payload;
}

/*
 * Registers, in the order Playwright resolves them (the most recently registered
 * route wins, so the catch-all goes first), every endpoint the shell reads.
 * `bootstrap` is a full /api/adventure/bootstrap payload in the real shape.
 */
export async function installProductionBootRoutes(page, { bootstrap } = {}) {
  if (!bootstrap) throw new Error('installProductionBootRoutes needs a bootstrap payload (see realBootstrap)');
  const ok = (body) => (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  await page.route('**/api/**', ok({}));
  await page.route('**/api/auth/me', ok(authMeBody()));
  await page.route('**/api/adventure/bootstrap**', ok(bootstrap));
  await page.route('**/api/skills/profile', ok({ display_name: 'Review Player', rank_level: 'LV7' }));
  await page.route('**/api/user/coins', ok({ coins: 1250, challenge_wins: 3 }));
  await page.route('**/api/player/appearance', ok({ character_key: 'swordsman' }));
  await page.route('**/api/daily-challenge/today', ok({ user_submitted: false }));
  await page.route('**/api/mistakes/stats', ok({ total: 5 }));
  await page.route('**/api/srs/due', ok({
    due: QUESTIONS.slice(0, 12).map((q) => ({ question_id: q.id, ease: 2.5, interval: 1 })), count: 12,
  }));
  await page.route('**/api/srs/all', ok(QUESTIONS.slice(0, 12).map((q) => ({ question_id: q.id, ease: 2.5, interval: 1 }))));
  await page.route('**/api/badges/definitions', ok([]));
  await page.route('**/api/badges/earned', ok([]));
  await page.route('**/api/questions*', ok(QUESTIONS));
}

// The proof that a page really booted the E10 runtime and not the legacy map or a
// degraded shell. Every test that claims to exercise the current E10 UI asserts it.
export function readBootIdentity(page) {
  return page.evaluate(() => {
    const stageRoot = document.querySelector('#e9-world-stage-slot');
    const stageState = stageRoot && stageRoot.__e9WorldStageState;
    return {
      hostname: location.hostname,
      debugHost: !!(window.E9 && window.E9.isDebugEnvironment && window.E9.isDebugEnvironment()),
      queryFlags: /[?&]e9[A-Z]/.test(location.search),
      serverFlags: window.__GO_E9_SERVER_FLAGS__ || null,
      worldPresentation: document.documentElement.getAttribute('data-world-presentation-state'),
      shellActive: document.body.getAttribute('data-adventure-shell-active'),
      skin: document.body.getAttribute('data-e10-visual-skin'),
      legacyNodes: document.querySelectorAll('#adventure-map-nodes .adventure-node').length,
      e10Zones: document.querySelectorAll('#e9-world-stage-zones [data-zone]').length,
      questionRuntimeState: stageState ? stageState.questionRuntimeState : null,
      authorityUnavailable: stageState ? stageState.authorityUnavailable === true : null,
    };
  });
}

export function isCurrentE10(boot) {
  return boot.worldPresentation === 'e10'
    && boot.shellActive === 'e9'
    && boot.skin === 'immersive-rpg'
    && boot.legacyNodes === 0
    && boot.e10Zones > 0
    && boot.queryFlags === false
    && !!boot.serverFlags && boot.serverFlags.e9Shell === true
    && boot.questionRuntimeState === 'ready'
    && boot.authorityUnavailable === false;
}
