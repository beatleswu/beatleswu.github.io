import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const context = { console };
context.globalThis = context;
vm.createContext(context);

for (const file of [
  'js/e9/journey_zone3_vertical_slice_content.js',
  'js/e9/journey_zone3_vertical_slice.js',
]) {
  vm.runInContext(fs.readFileSync(path.join(ROOT, file), 'utf8'), context, { filename: file });
}

const content = context.GoOdysseyJourneyZone3Content;
const api = context.GoOdysseyJourneyZone3;
const types = content.eventTypes;
const failures = [];
let checks = 0;

function check(condition, message) {
  checks += 1;
  if (!condition) failures.push(message);
}

function send(controller, type, detail) {
  return controller.accept({ type, detail });
}

function accept(controller, type, detail, label) {
  const outcome = send(controller, type, detail);
  check(outcome.accepted === true, `${label}: ${JSON.stringify(outcome)}`);
  return outcome;
}

function reject(controller, type, detail, label) {
  const outcome = send(controller, type, detail);
  check(outcome.accepted === false, `${label}: ${JSON.stringify(outcome)}`);
  return outcome;
}

function zone(key, status, extra = {}) {
  return { key, status, canEnter: status !== 'locked', ...extra };
}

function zonesFor(zone3, zone4) {
  return [
    zone('k26_30', 'completed', { cleared: true }),
    zone('k21_25', 'completed', { cleared: true }),
    zone3,
    zone4,
  ];
}

const zone3 = zone('k16_20', 'unlocked', { bossAvailable: false });
const zone4Locked = zone('k11_15', 'locked');
const zone4Open = zone('k11_15', 'unlocked');
const initialZones = zonesFor(zone3, zone4Locked);

check(content.zone3Key === 'k16_20', 'manifest must bind Zone 3 to k16_20');
check(content.zone4Key === 'k11_15', 'manifest must bind Zone 4 hook to k11_15');
check(content.noFakeFinalAssets === true, 'manifest must reject fake final assets');
const presentation = content.cinematicPresentation;
check(presentation?.shots?.length === 10, 'World presentation must bind all ten shots');
check(content.assetSlots.zone3Entry.status === 'READY', 'entry slot must be manifest-ready');
check(content.assetSlots.zone3PostClear.status === 'READY', 'post-clear slot must be manifest-ready');
check(content.assetSlots.zone3Entry.runtimeAsset?.manifest === presentation.cinematicManifestPath,
  'entry slot must point at the committed cinematic manifest');
check(content.assetSlots.zone3PostClear.runtimeAsset?.manifest === presentation.cinematicManifestPath,
  'post-clear slot must point at the committed cinematic manifest');
check(JSON.stringify(presentation.lifecycle.FIRST_ENTRY) === JSON.stringify(['SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05']),
  'first-entry lifecycle must be SHOT01-SHOT05');
check(JSON.stringify(presentation.lifecycle.BOSS_READY) === JSON.stringify(['SHOT06', 'SHOT07']),
  'boss-ready lifecycle must be SHOT06-SHOT07');
check(JSON.stringify(presentation.lifecycle.POST_CLEAR) === JSON.stringify(['SHOT08', 'SHOT09', 'SHOT10']),
  'post-clear lifecycle must be SHOT08-SHOT10');
check(presentation.responsiveCounts.ipadPortraitGenericSafe === 2,
  'iPad portrait generic-safe count must come from WORLD records');
check(presentation.responsiveCounts.ipadPortraitCustomPositionRequired === 2,
  'iPad portrait custom-position count must come from WORLD records');
check(presentation.responsiveCounts.mobileGenericSafe === 2,
  'mobile generic-safe count must come from WORLD records');
check(presentation.responsiveCounts.mobileCustomPositionRequired === 2,
  'mobile custom-position count must come from WORLD records');
check(presentation.shots[8].ipadPortraitPresentation.objectPosition === '58% 50%'
  && presentation.shots[9].ipadPortraitPresentation.objectPosition === '58% 50%',
  'Shots 09-10 must retain the reviewed portrait position');
check(presentation.shots[8].mobilePresentation.objectPosition === '58% 50%'
  && presentation.shots[9].mobilePresentation.objectPosition === '58% 50%',
  'Shots 09-10 must retain the reviewed mobile position');
check(content.stageContracts.lord_trial.startEndpoint === '/api/adventure/boss/start', 'Lord start contract must reuse the existing route');
check(content.stageContracts.lord_trial.finishEndpoint === '/api/adventure/boss/finish', 'Lord finish contract must reuse the existing route');

const controller = api.create({ content });
const selected = accept(controller, types.zoneSelected, {
  authoritative: true,
  source: 'adventure_bootstrap',
  selectedZoneKey: 'k16_20',
  currentZoneKey: 'k21_25',
  zone3,
  zones: initialZones,
  eventId: 'zone3-select-1',
}, 'Zone 3 selection');
check(selected.state.selectedZoneKey === 'k16_20', 'selection should be retained as presentation state');
check(selected.state.progressionZoneKey === 'k21_25', 'selection must not move progression');

accept(controller, types.entry, {
  authoritative: true,
  source: 'adventure_bootstrap',
  zoneKey: 'k16_20',
  zone3,
  currentZoneKey: 'k21_25',
  zones: initialZones,
  eventId: 'zone3-entry-1',
}, 'Zone 3 entry');

accept(controller, types.firstEntryCinematic, {
  authoritative: true,
  source: 'world_manifest',
  completed: true,
  safeFallback: false,
  presentationOnly: true,
  assetSlot: 'zone3_entry_cinematic',
  assetStatus: 'READY',
  zoneKey: 'k16_20',
  replay: false,
  eventId: 'zone3-entry-cinematic-1',
}, 'first-entry safe cinematic');

accept(controller, types.gameplayHandoff, {
  authoritative: true,
  source: 'canonical_adventure_entry',
  serverBound: true,
  started: true,
  zoneKey: 'k16_20',
  attemptId: 'map-attempt-1',
  questionId: '31194',
  eventId: 'zone3-handoff-1',
}, 'gameplay handoff');

accept(controller, types.mapBattle, {
  authoritative: true,
  source: 'map_battle_v1',
  serverBound: true,
  boardReady: true,
  zoneKey: 'k16_20',
  attemptId: 'map-attempt-1',
  questionId: '31194',
  adventureMonster: { id: 'server-monster-3', hp: 100 },
  eventId: 'zone3-map-board-1',
}, 'Map Battle board handoff');

accept(controller, types.mapBattle, {
  authoritative: true,
  source: 'map_battle_v1',
  serverBound: true,
  zoneKey: 'k16_20',
  attemptId: 'map-attempt-1',
  questionId: '31194',
  result: 'CORRECT',
  damage_to_monster: 20,
  next_action: 'continue',
  monsterDefeated: false,
  eventId: 'zone3-map-answer-1',
}, 'Map Battle answer feedback');

accept(controller, types.mapBattle, {
  authoritative: true,
  source: 'map_battle_v1',
  serverBound: true,
  zoneKey: 'k16_20',
  attemptId: 'map-attempt-1',
  questionId: '31195',
  result: 'CORRECT',
  damage_to_monster: 80,
  next_action: 'boss_ready_check',
  monsterDefeated: true,
  eventId: 'zone3-map-answer-2',
}, 'Map Battle defeat');

accept(controller, types.battlefieldBossProgress, {
  authoritative: true,
  source: 'map_battle_v1',
  serverBound: true,
  zoneKey: 'k16_20',
  attemptId: 'map-attempt-1',
  questionId: '31195',
  result: 'CORRECT',
  monsterDefeated: true,
  eventId: 'zone3-battlefield-progress-1',
}, 'Battlefield Boss progression');

const readyZone3 = zone('k16_20', 'unlocked', { bossAvailable: true });
const readyZones = zonesFor(readyZone3, zone4Locked);
accept(controller, types.lordReady, {
  authoritative: true,
  source: 'adventure_bootstrap',
  lordReady: true,
  autoStart: false,
  currentZoneKey: 'k16_20',
  selectedZoneKey: 'k16_20',
  primaryAction: { kind: 'challenge_lord', zoneKey: 'k16_20' },
  zone3: readyZone3,
  zones: readyZones,
  eventId: 'zone3-lord-ready-1',
}, 'Lord-ready presentation');

accept(controller, types.lordCta, {
  clicked: true,
  presentationOnly: true,
  source: 'existing_lord_cta',
  autoStart: false,
}, 'explicit Lord CTA');

accept(controller, types.lordTrialStarted, {
  authoritative: true,
  source: 'adventure_boss_start',
  serverBound: true,
  zoneKey: 'k16_20',
  attemptId: 'lord-attempt-1',
  replay: false,
  eventId: 'zone3-lord-start-1',
}, 'Lord Trial start');

accept(controller, types.lordTrialProgress, {
  authoritative: true,
  source: 'adventure_boss_review',
  serverBound: true,
  committed: true,
  zoneKey: 'k16_20',
  attemptId: 'lord-attempt-1',
  questionId: 31196,
  grade: 'GOOD',
  eventId: 'zone3-lord-review-1',
}, 'Lord Trial review');

const clearedZone3 = zone('k16_20', 'completed', { cleared: true, bossAvailable: false });
const clearedZones = zonesFor(clearedZone3, zone4Locked);
accept(controller, types.lordClear, {
  authoritative: true,
  source: 'adventure_boss_finish',
  serverBound: true,
  passed: true,
  zoneCleared: true,
  firstClear: true,
  replay: false,
  attemptId: 'lord-attempt-1',
  zoneKey: 'k16_20',
  zone3: clearedZone3,
  zones: clearedZones,
  correct: 16,
  total: 20,
  eventId: 'zone3-lord-clear-1',
}, 'authoritative Lord clear');

const rewardId = 'adventure:first_clear:42:k16_20';
accept(controller, types.reward, {
  authoritative: true,
  source: 'battlefield_reward_consumer',
  rewardProjection: true,
  firstClear: true,
  entitlementConsumed: true,
  replay: false,
  rewardEventId: rewardId,
  rewardZoneKey: 'k16_20',
  rewardStatus: 'GRANTED',
  reward: { id: 'server-item-3', source: 'player_wardrobe' },
  eventId: 'zone3-reward-presentation-1',
}, 'authoritative first-clear reward');
check(controller.getState().rewardEventIds.length === 1, 'one reward event should be remembered');

const duplicateReward = reject(controller, types.reward, {
  authoritative: true,
  source: 'battlefield_reward_consumer',
  rewardProjection: true,
  firstClear: true,
  entitlementConsumed: true,
  replay: false,
  rewardEventId: rewardId,
  rewardZoneKey: 'k16_20',
  rewardStatus: 'GRANTED',
  reward: { id: 'server-item-3' },
  eventId: 'zone3-reward-presentation-duplicate',
}, 'duplicate reward presentation');
check(duplicateReward.reason === 'duplicate_reward_event', 'duplicate reward must be rejected by server identity');

reject(controller, types.reward, {
  authoritative: true,
  source: 'battlefield_reward_consumer',
  rewardProjection: true,
  firstClear: false,
  entitlementConsumed: true,
  replay: true,
  rewardEventId: 'replay-reward-should-not-exist',
  rewardZoneKey: 'k16_20',
  rewardStatus: 'NO_REWARD',
  eventId: 'zone3-replay-reward-1',
}, 'replay reward');

accept(controller, types.postClear, {
  authoritative: true,
  authoritativeClear: true,
  presentationOnly: true,
  safeFallback: false,
  source: 'world_manifest',
  assetSlot: 'zone3_post_clear_cinematic',
  assetStatus: 'READY',
  replay: false,
  rewardSettled: true,
  zoneKey: 'k16_20',
  zone3: clearedZone3,
  zones: clearedZones,
  eventId: 'zone3-post-clear-1',
}, 'post-clear safe cinematic');

const hookZones = zonesFor(clearedZone3, zone4Open);
accept(controller, types.zone4Hook, {
  authoritative: true,
  source: 'adventure_bootstrap',
  zone3Cleared: true,
  hookOnly: true,
  autoNavigate: false,
  zone3: clearedZone3,
  zone4: zone4Open,
  zones: hookZones,
  zone4Key: 'k11_15',
  targetZoneKey: 'k11_15',
  eventId: 'zone3-zone4-hook-1',
}, 'Zone 4 hook');

const returned = accept(controller, types.returnToMap, {
  presentationOnly: true,
  replaySafe: true,
  source: 'canonical_return',
  eventId: 'zone3-return-1',
}, 'replay-safe return');
check(returned.state.phase === 'RETURN', 'return should end the presentation sequence');

// A replay walks the same playback grammar but deliberately has no reward
// transition. This catches accidental reward coupling to a replay finish.
const replayController = api.create({ content });
const replayPrefix = 'replay-';
accept(replayController, types.zoneSelected, {
  authoritative: true, source: 'adventure_bootstrap', selectedZoneKey: 'k16_20',
  currentZoneKey: 'k16_20', zone3, zones: initialZones, eventId: `${replayPrefix}select`,
}, 'replay selection');
accept(replayController, types.entry, {
  authoritative: true, source: 'adventure_bootstrap', zoneKey: 'k16_20', zone3,
  zones: initialZones, eventId: `${replayPrefix}entry`,
}, 'replay entry');
accept(replayController, types.firstEntryCinematic, {
  authoritative: true, source: 'world_manifest', completed: true,
  safeFallback: false, presentationOnly: true, assetSlot: 'zone3_entry_cinematic',
  assetStatus: 'READY', eventId: `${replayPrefix}cinematic`,
}, 'replay entry cinematic');
accept(replayController, types.gameplayHandoff, {
  authoritative: true, source: 'canonical_adventure_entry', serverBound: true,
  started: true, zoneKey: 'k16_20', attemptId: 'replay-map', questionId: 'r1',
  eventId: `${replayPrefix}handoff`,
}, 'replay gameplay handoff');
accept(replayController, types.mapBattle, {
  authoritative: true, source: 'map_battle_v1', serverBound: true, boardReady: true,
  zoneKey: 'k16_20', attemptId: 'replay-map', questionId: 'r1', eventId: `${replayPrefix}board`,
}, 'replay map board');
accept(replayController, types.mapBattle, {
  authoritative: true, source: 'map_battle_v1', serverBound: true, result: 'CORRECT',
  monsterDefeated: true, zoneKey: 'k16_20', attemptId: 'replay-map', questionId: 'r2',
  eventId: `${replayPrefix}defeat`,
}, 'replay battlefield progress');
accept(replayController, types.lordReady, {
  authoritative: true, source: 'adventure_bootstrap', lordReady: true, autoStart: false,
  zone3: readyZone3, zones: readyZones, eventId: `${replayPrefix}ready`,
}, 'replay Lord-ready state');
accept(replayController, types.lordCta, {
  clicked: true, presentationOnly: true, source: 'existing_lord_cta', autoStart: false,
}, 'replay Lord CTA');
accept(replayController, types.lordTrialStarted, {
  authoritative: true, source: 'adventure_boss_start', serverBound: true, zoneKey: 'k16_20',
  attemptId: 'replay-lord', replay: true, eventId: `${replayPrefix}lord-start`,
}, 'replay Lord start');
accept(replayController, types.lordClear, {
  authoritative: true, source: 'adventure_boss_finish', serverBound: true, passed: true,
  zoneCleared: true, firstClear: false, replay: true, attemptId: 'replay-lord',
  zoneKey: 'k16_20', zone3: clearedZone3, zones: clearedZones,
  eventId: `${replayPrefix}lord-clear`,
}, 'replay Lord clear');
check(replayController.getState().rewardSettled === false, 'replay clear cannot settle a reward');
reject(replayController, types.reward, {
  authoritative: true, source: 'battlefield_reward_consumer', rewardProjection: true,
  firstClear: true, entitlementConsumed: true, replay: true,
  rewardEventId: 'replay-reward', rewardZoneKey: 'k16_20', rewardStatus: 'NO_REWARD',
  eventId: `${replayPrefix}reward`,
}, 'replay reward hard stop');
accept(replayController, types.postClear, {
  authoritative: true, authoritativeClear: true, presentationOnly: true, safeFallback: false,
  source: 'world_manifest', assetSlot: 'zone3_post_clear_cinematic',
  assetStatus: 'READY', replay: true, rewardSettled: false,
  eventId: `${replayPrefix}post-clear`,
}, 'replay post-clear');
reject(replayController, types.zone4Hook, {
  authoritative: false, source: 'adventure_bootstrap', zone3Cleared: true, hookOnly: true,
  autoNavigate: false, zone3: clearedZone3, zone4: zone4Open, zones: hookZones,
  targetZoneKey: 'k11_15', eventId: `${replayPrefix}fake-hook`,
}, 'client-only Zone 4 unlock');
accept(replayController, types.zone4Hook, {
  authoritative: true, source: 'adventure_bootstrap', zone3Cleared: true, hookOnly: true,
  autoNavigate: false, zone3: clearedZone3, zone4: zone4Open, zones: hookZones,
  targetZoneKey: 'k11_15', eventId: `${replayPrefix}hook`,
}, 'replay Zone 4 hook');
accept(replayController, types.returnToMap, {
  presentationOnly: true, replaySafe: true, source: 'canonical_return',
  eventId: `${replayPrefix}return`,
}, 'replay-safe return');

// Negative controls: no client-only selection/unlock and no out-of-sequence
// clear can advance a fresh controller.
const negativeController = api.create({ content });
reject(negativeController, types.zoneSelected, {
  authoritative: false, source: 'client_state', selectedZoneKey: 'k16_20', zone3,
  zones: initialZones, eventId: 'negative-client-selection',
}, 'client-only selection');
reject(negativeController, types.lordClear, {
  authoritative: true, source: 'adventure_boss_finish', serverBound: true, passed: true,
  zoneCleared: true, firstClear: true, replay: false, attemptId: 'forged',
  zoneKey: 'k16_20', zone3: clearedZone3, eventId: 'negative-forged-clear',
}, 'out-of-sequence clear');

// A server-reported completed/replay-ready Zone 3 may surface the Lord CTA
// immediately after selection; it must still be bootstrap-authorized and
// must not require a client-side unlock flag.
const readyAtEntryController = api.create({ content });
accept(readyAtEntryController, types.zoneSelected, {
  authoritative: true, source: 'adventure_bootstrap', selectedZoneKey: 'k16_20',
  currentZoneKey: 'k16_20', zone3: readyZone3, zones: readyZones,
  eventId: 'ready-at-entry-selection',
}, 'already-ready Zone 3 selection');
accept(readyAtEntryController, types.lordReady, {
  authoritative: true, source: 'adventure_bootstrap', lordReady: true, autoStart: false,
  zone3: readyZone3, zones: readyZones, eventId: 'ready-at-entry-lord-ready',
}, 'already-ready Lord CTA');
check(readyAtEntryController.getState().phase === 'LORD_READY', 'ready-at-entry path should show Lord CTA');

const finalState = controller.getState();
check(finalState.selectedZoneKey === 'k16_20', 'selected Zone 3 must remain presentation state');
check(finalState.progressionZoneKey === 'k16_20', 'progression must come from server current-zone facts');
check(finalState.rewardEventIds.length === 1, 'primary flow must retain one reward identity');

const output = {
  status: failures.length === 0 ? 'PASS' : 'FAIL',
  checks,
  failures,
  primaryPhase: finalState.phase,
  replayPhase: replayController.getState().phase,
  rewardIds: finalState.rewardEventIds,
  styleLock: content.styleLock.status,
};
process.stdout.write(JSON.stringify(output));
if (failures.length) process.exitCode = 1;
