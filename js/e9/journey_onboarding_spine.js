/*
 * W1_03_JOURNEY_ONBOARDING_SPINE_001
 *
 * Presentation-only finite-state controller for the first-session journey.
 * It accepts facts emitted by existing server-backed surfaces and returns a
 * renderable state. It owns no progression, reward, equipment, question, or
 * battle authority, and intentionally has no persistence or network access.
 */
(function (global) {
  'use strict';

  var FALLBACK_CONTENT = {
    stepOrder: [],
    stepContracts: {},
    eventTypes: {},
    controlCopyKeys: {},
    zoneKeys: { zone1: 'k26_30', zone2: 'k21_25', zone3: 'k16_20' },
    styleLock: {
      status: 'BLOCKED_BY_STYLE_LOCK',
      zoneKey: 'k16_20',
      visualDetails: null,
      authoredCopy: null
    }
  };

  function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function isArray(value) {
    return Array.isArray(value);
  }

  function hasOwn(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function clone(value) {
    if (isArray(value)) return value.map(clone);
    if (!isObject(value)) return value;
    var result = {};
    Object.keys(value).forEach(function (key) {
      result[key] = clone(value[key]);
    });
    return result;
  }

  function contains(values, value) {
    return values.indexOf(value) !== -1;
  }

  function addUnique(values, value) {
    if (!contains(values, value)) values.push(value);
  }

  function finiteNumber(value) {
    return typeof value === 'number' && isFinite(value);
  }

  function nonEmptyString(value) {
    return typeof value === 'string' && value.trim() !== '';
  }

  function eventFrom(input) {
    if (!isObject(input)) return null;
    var detail = isObject(input.detail) ? input.detail : input;
    var type = input.type || input.eventType || detail.type;
    if (!nonEmptyString(type)) return null;
    return { type: type, detail: detail };
  }

  function firstDefined(object, keys) {
    for (var index = 0; index < keys.length; index += 1) {
      if (hasOwn(object, keys[index]) && object[keys[index]] !== null && object[keys[index]] !== undefined) {
        return object[keys[index]];
      }
    }
    return undefined;
  }

  function normalizedZoneKey(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function zoneRecord(zones, key) {
    if (!isArray(zones)) return null;
    for (var index = 0; index < zones.length; index += 1) {
      var zone = zones[index];
      if (!isObject(zone)) continue;
      var zoneKey = normalizedZoneKey(firstDefined(zone, ['key', 'zoneKey', 'zone_key']));
      if (zoneKey === key) return zone;
    }
    return null;
  }

  function zoneIsEnterable(zone) {
    if (!isObject(zone)) return false;
    if (zone.locked === true) return false;
    if (zone.canEnter === true || zone.can_enter === true) return true;
    return zone.status === 'unlocked' || zone.status === 'completed';
  }

  function zonesContainEnterable(zones, key) {
    return zoneIsEnterable(zoneRecord(zones, key));
  }

  function upper(value) {
    return typeof value === 'string' ? value.toUpperCase() : '';
  }

  function rewardStatusIsExplicit(detail) {
    var status = upper(firstDefined(detail, ['rewardStatus', 'reward_status']));
    return status === 'GRANTED' || status === 'NO_REWARD' || status === 'ALREADY_OWNED';
  }

  function create(options) {
    options = isObject(options) ? options : {};
    var content = options.content || global.GoOdysseyJourneyOnboardingContent || FALLBACK_CONTENT;
    var order = isArray(content.stepOrder) ? content.stepOrder.slice() : [];
    var contracts = isObject(content.stepContracts) ? content.stepContracts : {};
    var events = isObject(content.eventTypes) ? content.eventTypes : {};
    var zones = content.zoneKeys || FALLBACK_CONTENT.zoneKeys;
    var styleLock = content.styleLock || FALLBACK_CONTENT.styleLock;

    if (!order.length) {
      throw new Error('journey onboarding content contract is unavailable');
    }

    var indexByStep = {};
    order.forEach(function (step, index) {
      indexByStep[step] = index;
    });

    var state = {
      active: false,
      status: 'INACTIVE',
      step: order[0],
      completedSteps: [],
      skippedSteps: [],
      replayedSteps: [],
      seenEventIds: [],
      rewardEventIds: [],
      lastEventType: null,
      boundaryReached: false
    };

    function snapshot() {
      return clone({
        active: state.active,
        status: state.status,
        step: state.step,
        completedSteps: state.completedSteps,
        skippedSteps: state.skippedSteps,
        replayedSteps: state.replayedSteps,
        rewardEventIds: state.rewardEventIds,
        lastEventType: state.lastEventType,
        boundaryReached: state.boundaryReached,
        styleLock: state.boundaryReached ? styleLock.status : null,
        stepContract: contracts[state.step] || null
      });
    }

    function result(accepted, action, extra) {
      var output = {
        accepted: accepted,
        action: action,
        presentationOnly: action === 'skip_hint' || action === 'replay_hint',
        state: snapshot()
      };
      if (isObject(extra)) {
        Object.keys(extra).forEach(function (key) {
          output[key] = clone(extra[key]);
        });
      }
      return output;
    }

    function reject(reason, extra) {
      var details = { reason: reason };
      if (isObject(extra)) {
        Object.keys(extra).forEach(function (key) {
          details[key] = extra[key];
        });
      }
      return result(false, 'ignored', details);
    }

    function detailHasAuthoritativeSource(detail, source) {
      return detail.authoritative === true && (!source || detail.source === source);
    }

    function validOpening(detail) {
      return detail.authenticated === true &&
        detail.firstSession === true &&
        detail.authoritySource === 'existing_onboarding';
    }

    function validWorldReveal(detail) {
      return detail.visible === true &&
        (detail.presentationState === 'legacy' || detail.presentationState === 'e9') &&
        detail.authoritySource === 'existing_shell';
    }

    function validHeroCompanion(detail) {
      return detail.heroReady === true &&
        detail.companionReady === true &&
        detail.authoritySource === 'existing_profile';
    }

    function validAdventureStart(detail) {
      return detail.started === true &&
        detail.authoritative === true &&
        normalizedZoneKey(detail.zoneKey) === zones.zone1 &&
        detail.source === 'canonical_adventure';
    }

    function validQuestion(detail) {
      return detail.authoritative === true &&
        detail.boardReady === true &&
        nonEmptyString(detail.questionId) &&
        normalizedZoneKey(detail.zoneKey) === zones.zone1 &&
        detail.source === 'canonical_question_runtime';
    }

    function validReview(detail) {
      return detail.committed === true &&
        detail.authoritative === true &&
        nonEmptyString(detail.questionId) &&
        typeof detail.grade === 'number' &&
        detail.source === 'canonical_srs_review';
    }

    function validAttack(detail) {
      var damage = firstDefined(detail, ['damageToMonster', 'damage_to_monster']);
      return detail.authoritative === true &&
        upper(firstDefined(detail, ['result', 'battleResult', 'battle_result'])) === 'CORRECT' &&
        finiteNumber(damage) &&
        damage > 0 &&
        detail.source === 'map_battle_v1';
    }

    function validVictory(detail) {
      var defeated = firstDefined(detail, ['monsterDefeated', 'monster_defeated']);
      return detail.authoritative === true &&
        defeated === true &&
        detail.source === 'map_battle_v1';
    }

    function validReward(detail) {
      var rewardEventId = firstDefined(detail, ['rewardEventId', 'reward_event_id']);
      var replay = detail.replay === true || detail.attemptMode === 'replay' || detail.attempt_mode === 'replay';
      var hasProjection = detail.rewardProjection === true || detail.reward_projection === true;
      var hasPayload = isObject(detail.reward) || rewardStatusIsExplicit(detail);
      return detail.authoritative === true &&
        replay !== true &&
        hasProjection &&
        nonEmptyString(rewardEventId) &&
        hasPayload &&
        detail.source === 'battlefield_reward_consumer';
    }

    function validGrowth(detail) {
      return detail.authoritative === true &&
        detail.xpProjection === true &&
        (finiteNumber(firstDefined(detail, ['xpGain', 'xp_gain'])) || detail.rankedUp === true || detail.ranked_up === true) &&
        detail.source === 'committed_review_presentation';
    }

    function validNextAction(detail) {
      var nextAction = firstDefined(detail, ['nextAction', 'next_action', 'primaryAction', 'primary_action']);
      return detail.authoritative === true &&
        isObject(nextAction) &&
        nonEmptyString(firstDefined(nextAction, ['kind', 'type', 'action'])) &&
        detail.source === 'adventure_bootstrap';
    }

    function validZoneProgression(detail) {
      return detail.authoritative === true &&
        isArray(detail.zones) &&
        zonesContainEnterable(detail.zones, zones.zone2) &&
        detail.source === 'adventure_bootstrap';
    }

    function validZone3Arrival(detail) {
      return detail.authoritative === true &&
        normalizedZoneKey(firstDefined(detail, ['zoneKey', 'zone_key', 'currentZoneKey', 'current_zone_key'])) === zones.zone3 &&
        zonesContainEnterable(detail.zones, zones.zone3) &&
        detail.source === 'adventure_bootstrap';
    }

    function transitionFor(event) {
      var detail = event.detail;
      var current = state.step;
      if (current === 'opening') {
        if (event.type === events.openingReady) {
          if (!validOpening(detail)) return null;
          return { activate: true };
        }
        if (event.type !== events.worldRevealed || !validWorldReveal(detail)) return null;
        return { nextStep: 'world_reveal' };
      }
      if (current === 'world_reveal') {
        if (event.type !== events.heroCompanionIntroduced || !validHeroCompanion(detail)) return null;
        return { nextStep: 'hero_companion' };
      }
      if (current === 'hero_companion') {
        if (event.type !== events.adventureStarted || !validAdventureStart(detail)) return null;
        return { nextStep: 'first_adventure' };
      }
      if (current === 'first_adventure') {
        if (event.type !== events.questionReady || !validQuestion(detail)) return null;
        return { nextStep: 'first_question' };
      }
      if (current === 'first_question') {
        if (event.type !== events.reviewCommitted || !validReview(detail)) return null;
        return { nextStep: 'answer_feedback' };
      }
      if (current === 'answer_feedback') {
        if (event.type !== events.attackResolved || !validAttack(detail)) return null;
        return { nextStep: 'attack_hit' };
      }
      if (current === 'attack_hit') {
        if (event.type !== events.encounterVictory || !validVictory(detail)) return null;
        return { nextStep: 'first_victory' };
      }
      if (current === 'first_victory') {
        if (event.type !== events.rewardRevealed || !validReward(detail)) return null;
        return {
          nextStep: 'reward_reveal',
          rewardEventId: firstDefined(detail, ['rewardEventId', 'reward_event_id'])
        };
      }
      if (current === 'reward_reveal') {
        if (event.type !== events.growthFeedback || !validGrowth(detail)) return null;
        return { nextStep: 'growth_feedback' };
      }
      if (current === 'growth_feedback') {
        if (event.type !== events.nextAction || !validNextAction(detail)) return null;
        return { nextStep: 'next_action' };
      }
      if (current === 'next_action') {
        if (event.type !== events.zoneProgressed || !validZoneProgression(detail)) return null;
        return { nextStep: 'zone_progression' };
      }
      if (current === 'zone_progression') {
        if (event.type !== events.zone3Arrived || !validZone3Arrival(detail)) return null;
        return { nextStep: 'zone3_arrival', boundary: true };
      }
      return null;
    }

    function accept(input) {
      var event = eventFrom(input);
      if (!event) return reject('invalid_event');
      if (state.boundaryReached) return reject('style_lock_boundary_reached');
      if (event.detail.eventId && contains(state.seenEventIds, event.detail.eventId)) {
        return reject('duplicate_event', { eventId: event.detail.eventId });
      }
      var rewardEventId = firstDefined(event.detail, ['rewardEventId', 'reward_event_id']);
      if (event.type === events.rewardRevealed && rewardEventId && contains(state.rewardEventIds, rewardEventId)) {
        return reject('duplicate_reward_event', { rewardEventId: rewardEventId });
      }
      var transition = transitionFor(event);
      if (!transition) return reject('authority_or_sequence_check_failed', { eventType: event.type });

      if (event.detail.eventId) addUnique(state.seenEventIds, event.detail.eventId);
      state.lastEventType = event.type;

      if (transition.activate) {
        state.active = true;
        state.status = 'ACTIVE';
        return result(true, 'activate', { displayedStep: state.step });
      }

      var previousStep = state.step;
      addUnique(state.completedSteps, previousStep);
      state.step = transition.nextStep;
      state.active = true;
      state.status = transition.boundary ? 'BLOCKED_BY_STYLE_LOCK' : 'ACTIVE';
      if (transition.rewardEventId) addUnique(state.rewardEventIds, transition.rewardEventId);
      if (transition.boundary) state.boundaryReached = true;

      return result(true, transition.boundary ? 'reach_style_lock_boundary' : 'advance', {
        completedStep: previousStep,
        displayedStep: state.step,
        blockedByStyleLock: transition.boundary === true,
        rewardEventId: transition.rewardEventId || null
      });
    }

    function skipHint() {
      if (!state.active || state.boundaryReached) return reject('hint_not_available');
      addUnique(state.skippedSteps, state.step);
      return result(true, 'skip_hint', { skippedStep: state.step, advancesJourney: false });
    }

    function replayHint(step) {
      var replayStep = nonEmptyString(step) ? step : state.completedSteps[state.completedSteps.length - 1];
      if (!replayStep || !contains(state.completedSteps, replayStep) || replayStep === 'zone3_arrival') {
        return reject('replay_not_available');
      }
      addUnique(state.replayedSteps, replayStep);
      return result(true, 'replay_hint', {
        replayStep: replayStep,
        advancesJourney: false,
        rewardEventIdsChanged: false
      });
    }

    function getState() {
      return snapshot();
    }

    return Object.freeze({
      accept: accept,
      skipHint: skipHint,
      replayHint: replayHint,
      getState: getState,
      contentVersion: content.version || 'unknown'
    });
  }

  global.GoOdysseyJourneyOnboarding = Object.freeze({
    version: 'W1_03_JOURNEY_ONBOARDING_SPINE_V1',
    create: create
  });
}(typeof window !== 'undefined' ? window : this));
