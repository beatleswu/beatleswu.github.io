/*
 * W1_03_JOURNEY_ONBOARDING_SPINE_001
 *
 * Authored presentation contract for the first-session journey. This file
 * contains copy keys and authority boundaries only. Localized strings belong
 * in the shared i18n catalog during the separately governed shell-wiring
 * pass; this module must not become a second translation catalog.
 */
(function (global) {
  'use strict';

  var STEP_ORDER = [
    'opening',
    'world_reveal',
    'hero_companion',
    'first_adventure',
    'first_question',
    'answer_feedback',
    'attack_hit',
    'first_victory',
    'reward_reveal',
    'growth_feedback',
    'next_action',
    'zone_progression',
    'zone3_arrival'
  ];

  var STEP_CONTRACTS = {
    opening: {
      copyKey: 'e9.journey.opening',
      authority: 'existing_onboarding_session',
      presentation: 'contextual'
    },
    world_reveal: {
      copyKey: 'e9.journey.world_reveal',
      authority: 'existing_shell_state',
      presentation: 'contextual'
    },
    hero_companion: {
      copyKey: 'e9.journey.hero_companion',
      authority: 'existing_profile_presentation',
      presentation: 'contextual'
    },
    first_adventure: {
      copyKey: 'e9.journey.first_adventure',
      authority: 'canonical_adventure_entry',
      presentation: 'contextual'
    },
    first_question: {
      copyKey: 'e9.journey.first_question',
      authority: 'canonical_question_runtime',
      presentation: 'contextual'
    },
    answer_feedback: {
      copyKey: 'e9.journey.answer_feedback',
      authority: 'committed_review_result',
      presentation: 'contextual'
    },
    attack_hit: {
      copyKey: 'e9.journey.attack_hit',
      authority: 'canonical_battle_result',
      presentation: 'contextual'
    },
    first_victory: {
      copyKey: 'e9.journey.first_victory',
      authority: 'canonical_encounter_result',
      presentation: 'contextual'
    },
    reward_reveal: {
      copyKey: 'e9.journey.reward_reveal',
      authority: 'committed_server_reward_projection',
      presentation: 'contextual'
    },
    growth_feedback: {
      copyKey: 'e9.journey.growth_feedback',
      authority: 'committed_server_growth_projection',
      presentation: 'contextual'
    },
    next_action: {
      copyKey: 'e9.journey.next_action',
      authority: 'server_primary_action',
      presentation: 'contextual'
    },
    zone_progression: {
      copyKey: 'e9.journey.zone_progression',
      authority: 'adventure_bootstrap_state',
      presentation: 'contextual'
    },
    zone3_arrival: {
      copyKey: null,
      authority: 'adventure_bootstrap_state',
      presentation: 'deferred_until_world_style_lock'
    }
  };

  var EVENT_TYPES = {
    openingReady: 'journey:opening-ready',
    worldRevealed: 'journey:world-revealed',
    heroCompanionIntroduced: 'journey:hero-companion-introduced',
    adventureStarted: 'journey:adventure-started',
    questionReady: 'journey:question-ready',
    reviewCommitted: 'journey:review-committed',
    attackResolved: 'journey:attack-resolved',
    encounterVictory: 'journey:encounter-victory',
    rewardRevealed: 'journey:reward-revealed',
    growthFeedback: 'journey:growth-feedback',
    nextAction: 'journey:next-action',
    zoneProgressed: 'journey:zone-progressed',
    zone3Arrived: 'journey:zone3-arrived'
  };

  var CONTROL_COPY_KEYS = {
    ariaLabel: 'e9.journey.aria_label',
    skip: 'e9.journey.skip',
    replay: 'e9.journey.replay'
  };

  var ZONE_KEYS = {
    zone1: 'k26_30',
    zone2: 'k21_25',
    zone3: 'k16_20'
  };

  var STYLE_LOCK = {
    status: 'BLOCKED_BY_STYLE_LOCK',
    zoneKey: ZONE_KEYS.zone3,
    visualDetails: null,
    authoredCopy: null
  };

  function freezeContracts() {
    STEP_ORDER.forEach(function (step) {
      Object.freeze(STEP_CONTRACTS[step]);
    });
    Object.freeze(STEP_CONTRACTS);
    Object.freeze(EVENT_TYPES);
    Object.freeze(CONTROL_COPY_KEYS);
    Object.freeze(ZONE_KEYS);
    Object.freeze(STYLE_LOCK);
    Object.freeze(STEP_ORDER);
  }

  freezeContracts();

  global.GoOdysseyJourneyOnboardingContent = Object.freeze({
    version: 'W1_03_JOURNEY_ONBOARDING_SPINE_V1',
    stepOrder: STEP_ORDER,
    stepContracts: STEP_CONTRACTS,
    eventTypes: EVENT_TYPES,
    controlCopyKeys: CONTROL_COPY_KEYS,
    zoneKeys: ZONE_KEYS,
    styleLock: STYLE_LOCK,
    guidanceMode: 'short_contextual_guidance'
  });
}(typeof window !== 'undefined' ? window : this));
