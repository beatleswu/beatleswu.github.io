import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const context = { console };
vm.createContext(context);

for (const relativePath of [
  'js/e9/journey_onboarding_content.js',
  'js/e9/journey_onboarding_spine.js',
]) {
  vm.runInContext(fs.readFileSync(path.join(root, relativePath), 'utf8'), context, {
    filename: relativePath,
  });
}

const content = context.GoOdysseyJourneyOnboardingContent;
const factory = context.GoOdysseyJourneyOnboarding;
assert.ok(content);
assert.ok(factory);

let checks = 0;
function check(condition, message) {
  checks += 1;
  assert.ok(condition, message);
}

function event(type, detail, eventId) {
  return { type, detail: { ...detail, ...(eventId ? { eventId } : {}) } };
}

function advance(controller, type, detail, eventId, expectedStep) {
  const result = controller.accept(event(type, detail, eventId));
  check(result.accepted === true, `${type} should be accepted: ${result.reason || 'unknown reason'}`);
  if (expectedStep) check(result.state.step === expectedStep, `${type} should display ${expectedStep}`);
  return result;
}

const controller = factory.create({ content });
check(controller.getState().active === false, 'opening must not activate without the existing session gate');
check(controller.getState().step === 'opening', 'opening is the first displayed card');

advance(controller, content.eventTypes.openingReady, {
  authenticated: true,
  firstSession: true,
  authoritySource: 'existing_onboarding',
}, 'session-1', 'opening');
check(controller.getState().active === true, 'existing first-session signal activates the guide');

advance(controller, content.eventTypes.worldRevealed, {
  visible: true,
  presentationState: 'legacy',
  authoritySource: 'existing_shell',
}, 'shell-1', 'world_reveal');

advance(controller, content.eventTypes.heroCompanionIntroduced, {
  heroReady: true,
  companionReady: true,
  authoritySource: 'existing_profile',
}, 'profile-1', 'hero_companion');

advance(controller, content.eventTypes.adventureStarted, {
  started: true,
  authoritative: true,
  zoneKey: content.zoneKeys.zone1,
  source: 'canonical_adventure',
}, 'adventure-1', 'first_adventure');

advance(controller, content.eventTypes.questionReady, {
  authoritative: true,
  boardReady: true,
  questionId: 'question-1',
  zoneKey: content.zoneKeys.zone1,
  source: 'canonical_question_runtime',
}, 'question-1', 'first_question');

advance(controller, content.eventTypes.reviewCommitted, {
  committed: true,
  authoritative: true,
  questionId: 'question-1',
  grade: 3,
  source: 'canonical_srs_review',
}, 'review-1', 'answer_feedback');

advance(controller, content.eventTypes.attackResolved, {
  authoritative: true,
  result: 'CORRECT',
  damage_to_monster: 1,
  source: 'map_battle_v1',
}, 'battle-hit-1', 'attack_hit');

advance(controller, content.eventTypes.encounterVictory, {
  authoritative: true,
  monster_defeated: true,
  source: 'map_battle_v1',
}, 'battle-win-1', 'first_victory');

advance(controller, content.eventTypes.rewardRevealed, {
  authoritative: true,
  rewardProjection: true,
  rewardEventId: 'reward-1',
  rewardStatus: 'GRANTED',
  replay: false,
  source: 'battlefield_reward_consumer',
}, 'reward-1', 'reward_reveal');

const duplicateReward = controller.accept(event(content.eventTypes.rewardRevealed, {
  authoritative: true,
  rewardProjection: true,
  rewardEventId: 'reward-1',
  rewardStatus: 'GRANTED',
  replay: false,
  source: 'battlefield_reward_consumer',
}, 'reward-duplicate'));
check(duplicateReward.accepted === false, 'a repeated reward event must be rejected');
check(duplicateReward.reason === 'duplicate_reward_event', 'duplicate reward rejection must be explicit');
check(controller.getState().rewardEventIds.length === 1, 'replay must not duplicate reward IDs');

const replayReward = controller.accept(event(content.eventTypes.rewardRevealed, {
  authoritative: true,
  rewardProjection: true,
  rewardEventId: 'reward-replay',
  rewardStatus: 'GRANTED',
  replay: true,
  source: 'battlefield_reward_consumer',
}, 'reward-replay'));
check(replayReward.accepted === false, 'replay reward projections must be rejected');

advance(controller, content.eventTypes.growthFeedback, {
  authoritative: true,
  xpProjection: true,
  xpGain: 25,
  source: 'committed_review_presentation',
}, 'growth-1', 'growth_feedback');

advance(controller, content.eventTypes.nextAction, {
  authoritative: true,
  nextAction: { kind: 'return_to_adventure_map' },
  source: 'adventure_bootstrap',
}, 'next-1', 'next_action');

advance(controller, content.eventTypes.zoneProgressed, {
  authoritative: true,
  zones: [
    { key: content.zoneKeys.zone1, status: 'completed' },
    { key: content.zoneKeys.zone2, status: 'unlocked', canEnter: true },
  ],
  source: 'adventure_bootstrap',
}, 'progress-1', 'zone_progression');

const boundary = advance(controller, content.eventTypes.zone3Arrived, {
  authoritative: true,
  zoneKey: content.zoneKeys.zone3,
  zones: [
    { key: content.zoneKeys.zone1, status: 'completed' },
    { key: content.zoneKeys.zone2, status: 'completed' },
    { key: content.zoneKeys.zone3, status: 'unlocked', canEnter: true },
  ],
  source: 'adventure_bootstrap',
}, 'zone3-1', 'zone3_arrival');
check(boundary.action === 'reach_style_lock_boundary', 'Zone 3 must end at the style-lock boundary');
check(boundary.blockedByStyleLock === true, 'Zone 3 details must be explicitly style-lock blocked');
check(controller.getState().styleLock === 'BLOCKED_BY_STYLE_LOCK', 'style-lock state must be visible to the shell writer');

const skipController = factory.create({ content });
advance(skipController, content.eventTypes.openingReady, {
  authenticated: true,
  firstSession: true,
  authoritySource: 'existing_onboarding',
}, 'skip-session', 'opening');
const skipped = skipController.skipHint();
check(skipped.accepted === true && skipped.presentationOnly === true, 'skip is presentation-only');
check(skipped.advancesJourney === false, 'skip cannot advance the spine');
check(skipController.getState().step === 'opening', 'skip leaves the authority boundary pending');
const replayed = skipController.replayHint();
check(replayed.accepted === false, 'an uncompleted hint cannot be replayed');
advance(skipController, content.eventTypes.worldRevealed, {
  visible: true,
  presentationState: 'e9',
  authoritySource: 'existing_shell',
}, 'skip-shell', 'world_reveal');
const openingReplay = skipController.replayHint('opening');
check(openingReplay.accepted === true && openingReplay.presentationOnly === true, 'completed hints can be replayed');
check(openingReplay.advancesJourney === false, 'hint replay cannot advance progression');

const invalid = factory.create({ content });
advance(invalid, content.eventTypes.openingReady, {
  authenticated: true,
  firstSession: true,
  authoritySource: 'existing_onboarding',
}, 'invalid-session', 'opening');
const fakeVictory = invalid.accept(event(content.eventTypes.encounterVictory, {
  authoritative: false,
  monster_defeated: true,
  source: 'client',
}, 'fake-win'));
check(fakeVictory.accepted === false, 'client-only victory claims must not advance the spine');

console.log(JSON.stringify({
  status: 'PASS',
  checks,
  failures: 0,
  rewardEventIds: controller.getState().rewardEventIds,
  finalStep: controller.getState().step,
  styleLock: controller.getState().styleLock,
}));
