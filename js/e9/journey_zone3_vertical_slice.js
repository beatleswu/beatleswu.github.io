/*
 * W1_03_JOURNEY_ZONE3_CINEMATIC_ASSET_SLOT_AND_RESPONSIVE_BINDING_005
 *
 * Pure presentation-state adapter for the Zone 3 journey.  Existing server
 * adapters and index.html own transport, review, settlement, reward, and
 * unlock authority.  This module only accepts already-authoritative facts,
 * sequences contextual UI phases, and remembers reward presentation IDs in
 * page memory so a replay cannot repeat a reward card. Image slots and
 * localized dialogue are presentation-only; the server remains the
 * authority for entry, clear, reward, Lord eligibility, and unlock state.
 */
(function (global) {
  'use strict';

  var FALLBACK_CONTENT = {
    version: 'fallback',
    zone3Key: 'k16_20',
    zone4Key: 'k11_15',
    phases: [
      'IDLE', 'ENTRY_PENDING', 'ENTRY_CINEMATIC', 'GAMEPLAY_HANDOFF',
      'MAP_BATTLE_TRAINING', 'BATTLEFIELD_BOSS_PROGRESS', 'LORD_READY',
      'LORD_CTA', 'LORD_TRIAL', 'CLEAR_REWARD', 'POST_CLEAR_CINEMATIC',
      'ZONE4_HOOK', 'RETURN'
    ],
    eventTypes: {
      zoneSelected: 'journey:zone3-zone-selected',
      entry: 'journey:zone3-entry',
      firstEntryCinematic: 'journey:zone3-first-entry-cinematic',
      gameplayHandoff: 'journey:zone3-gameplay-handoff',
      mapBattle: 'journey:zone3-map-battle',
      battlefieldBossProgress: 'journey:zone3-battlefield-boss-progress',
      lordReady: 'journey:zone3-lord-ready',
      lordCta: 'journey:zone3-lord-cta',
      lordTrialStarted: 'journey:zone3-lord-trial-started',
      lordTrialProgress: 'journey:zone3-lord-trial-progress',
      lordClear: 'journey:zone3-lord-clear',
      reward: 'journey:zone3-reward',
      postClear: 'journey:zone3-post-clear',
      zone4Hook: 'journey:zone4-hook',
      returnToMap: 'journey:zone3-return'
    },
    assetSlots: {
      zone3Entry: { slotId: 'zone3_entry_cinematic', status: 'PENDING_FINAL_ASSETS' },
      zone3PostClear: { slotId: 'zone3_post_clear_cinematic', status: 'PENDING_FINAL_ASSETS' }
    },
    styleLock: { status: 'BLOCKED_BY_STYLE_LOCK' }
  };

  function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function isArray(value) { return Array.isArray(value); }

  function hasOwn(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function clone(value) {
    if (isArray(value)) return value.map(clone);
    if (!isObject(value)) return value;
    var result = {};
    Object.keys(value).forEach(function (key) { result[key] = clone(value[key]); });
    return result;
  }

  function nonEmptyString(value) {
    return typeof value === 'string' && value.trim() !== '';
  }

  function firstDefined(object, keys) {
    for (var index = 0; index < keys.length; index += 1) {
      if (hasOwn(object, keys[index])
          && object[keys[index]] !== null
          && object[keys[index]] !== undefined) return object[keys[index]];
    }
    return undefined;
  }

  function normalized(value) {
    return typeof value === 'string' ? value.trim() : '';
  }

  function upper(value) {
    return typeof value === 'string' ? value.toUpperCase() : '';
  }

  function finiteNumber(value) {
    return typeof value === 'number' && isFinite(value);
  }

  function contains(values, value) { return values.indexOf(value) !== -1; }

  function addUnique(values, value) {
    if (!contains(values, value)) values.push(value);
  }

  function eventFrom(input) {
    if (!isObject(input)) return null;
    var detail = isObject(input.detail) ? input.detail : input;
    var type = input.type || input.eventType || detail.type;
    if (!nonEmptyString(type)) return null;
    return { type: type, detail: detail };
  }

  function zoneKey(zone) {
    return normalized(firstDefined(zone || {}, ['key', 'zoneKey', 'zone_key']));
  }

  function zonesFrom(detail) {
    if (isArray(detail.zones)) return detail.zones;
    if (isArray(detail.serverZones)) return detail.serverZones;
    return [];
  }

  function findZone(zones, key) {
    for (var index = 0; index < zones.length; index += 1) {
      if (zoneKey(zones[index]) === key) return zones[index];
    }
    return null;
  }

  function zoneCanEnter(zone) {
    if (!isObject(zone) || zone.locked === true || zone.status === 'locked') return false;
    if (zone.canEnter === true || zone.can_enter === true) return true;
    return zone.status === 'unlocked' || zone.status === 'completed';
  }

  function zoneCleared(zone) {
    return !!(isObject(zone) && (zone.cleared === true || zone.completed === true
      || zone.status === 'completed'));
  }

  function zoneBossReady(zone) {
    return !!(isObject(zone) && (zone.bossAvailable === true
      || zone.boss_available === true
      || zone.boss_ready === true
      || (isObject(zone.boss) && zone.boss.available === true)));
  }

  function serverCurrentZoneKey(detail) {
    return normalized(firstDefined(detail, ['currentZoneKey', 'current_zone_key']));
  }

  function serverZoneFor(detail, key) {
    var zone = firstDefined(detail, ['zone3', 'serverZone', 'zone']);
    if (zoneKey(zone) === key) return zone;
    return findZone(zonesFrom(detail), key);
  }

  function primaryActionIsLord(detail) {
    var action = firstDefined(detail, ['primaryAction', 'primary_action']);
    if (!isObject(action)) return false;
    var kind = normalized(firstDefined(action, ['kind', 'type', 'action']));
    var actionZone = normalized(firstDefined(action, ['zoneKey', 'zone_key']));
    return (kind === 'challenge_lord' || kind === 'replay_completed')
      && actionZone === 'k16_20';
  }

  function create(options) {
    options = isObject(options) ? options : {};
    var content = options.content || global.GoOdysseyJourneyZone3Content || FALLBACK_CONTENT;
    var events = isObject(content.eventTypes) ? content.eventTypes : FALLBACK_CONTENT.eventTypes;
    var zone3Key = normalized(content.zone3Key) || FALLBACK_CONTENT.zone3Key;
    var zone4Key = normalized(content.zone4Key) || FALLBACK_CONTENT.zone4Key;
    var entrySlot = content.assetSlots && content.assetSlots.zone3Entry
      ? content.assetSlots.zone3Entry : FALLBACK_CONTENT.assetSlots.zone3Entry;
    var postClearSlot = content.assetSlots && content.assetSlots.zone3PostClear
      ? content.assetSlots.zone3PostClear : FALLBACK_CONTENT.assetSlots.zone3PostClear;

    var state = {
      active: false,
      status: 'INACTIVE',
      phase: 'IDLE',
      selectedZoneKey: null,
      progressionZoneKey: null,
      replay: false,
      authoritativeClear: false,
      rewardSettled: false,
      zone4HookReady: false,
      safeAssetStatus: entrySlot.status || 'PENDING_FINAL_ASSETS',
      completedPhases: [],
      seenEventIds: [],
      rewardEventIds: [],
      lastEventType: null,
      lastBattleResult: null,
      lastServerMonster: null,
      lastRewardStatus: null,
      lordAttemptId: null
    };

    function snapshot() {
      return clone({
        active: state.active,
        status: state.status,
        phase: state.phase,
        selectedZoneKey: state.selectedZoneKey,
        progressionZoneKey: state.progressionZoneKey,
        replay: state.replay,
        authoritativeClear: state.authoritativeClear,
        rewardSettled: state.rewardSettled,
        zone4HookReady: state.zone4HookReady,
        safeAssetStatus: state.safeAssetStatus,
        completedPhases: state.completedPhases,
        rewardEventIds: state.rewardEventIds,
        lastEventType: state.lastEventType,
        lastBattleResult: state.lastBattleResult,
        lastServerMonster: state.lastServerMonster,
        lastRewardStatus: state.lastRewardStatus,
        lordAttemptId: state.lordAttemptId,
        styleLock: state.phase === 'ENTRY_CINEMATIC' || state.phase === 'POST_CLEAR_CINEMATIC'
          ? ((content.styleLock && content.styleLock.status) || 'BLOCKED_BY_STYLE_LOCK') : null,
        assetSlots: {
          zone3Entry: entrySlot.slotId || null,
          zone3PostClear: postClearSlot.slotId || null
        }
      });
    }

    function result(accepted, action, extra) {
      var output = {
        accepted: accepted,
        action: action,
        presentationOnly: action === 'observe' || action === 'show_safe_fallback'
          || action === 'show_cinematic'
          || action === 'show_lord_cta' || action === 'return_safe',
        state: snapshot()
      };
      if (isObject(extra)) Object.keys(extra).forEach(function (key) {
        output[key] = clone(extra[key]);
      });
      return output;
    }

    function reject(reason, extra) {
      var details = { reason: reason };
      if (isObject(extra)) Object.keys(extra).forEach(function (key) {
        details[key] = extra[key];
      });
      return result(false, 'ignored', details);
    }

    function baseServerFact(detail, source) {
      return detail.authoritative === true && detail.source === source;
    }

    function validZone3Snapshot(detail) {
      var selected = normalized(firstDefined(detail, ['selectedZoneKey', 'selected_zone_key', 'zoneKey', 'zone_key']));
      var zone = serverZoneFor(detail, zone3Key);
      return selected === zone3Key && zoneCanEnter(zone) && zoneKey(zone) === zone3Key;
    }

    function validZoneSelected(detail) {
      return baseServerFact(detail, 'adventure_bootstrap') && validZone3Snapshot(detail);
    }

    function validEntry(detail) {
      return baseServerFact(detail, 'adventure_bootstrap')
        && normalized(firstDefined(detail, ['zoneKey', 'zone_key'])) === zone3Key
        && zoneCanEnter(serverZoneFor(detail, zone3Key));
    }

    function validFirstEntryCinematic(detail) {
      var slotMatches = normalized(detail.assetSlot) === normalized(entrySlot.slotId);
      var common = detail.authoritative === true
        && detail.completed === true
        && detail.presentationOnly === true
        && slotMatches;
      var manifestPresentation = detail.source === 'world_manifest'
        && detail.safeFallback !== true
        && normalized(detail.assetStatus) === 'READY';
      var safeFallback = detail.source === 'manifest_safe_fallback'
        && detail.safeFallback === true
        && normalized(detail.assetStatus) === 'PENDING_FINAL_ASSETS';
      return common && (manifestPresentation || safeFallback);
    }

    function validGameplayHandoff(detail) {
      return baseServerFact(detail, 'canonical_adventure_entry')
        && detail.started === true
        && detail.serverBound === true
        && normalized(firstDefined(detail, ['zoneKey', 'zone_key'])) === zone3Key
        && nonEmptyString(firstDefined(detail, ['attemptId', 'attempt_id']))
        && nonEmptyString(firstDefined(detail, ['questionId', 'question_id']));
    }

    function validMapBattle(detail) {
      var mapZone = normalized(firstDefined(detail, ['zoneKey', 'zone_key']));
      var attemptId = firstDefined(detail, ['attemptId', 'attempt_id']);
      var questionId = firstDefined(detail, ['questionId', 'question_id']);
      var resultName = upper(firstDefined(detail, ['result', 'battleResult', 'battle_result']));
      return baseServerFact(detail, 'map_battle_v1')
        && detail.serverBound === true
        && mapZone === zone3Key
        && nonEmptyString(attemptId)
        && (finiteNumber(questionId) || nonEmptyString(questionId))
        && (detail.boardReady === true || resultName === 'CORRECT' || resultName === 'INCORRECT');
    }

    function validLordReady(detail) {
      var zone = serverZoneFor(detail, zone3Key);
      return baseServerFact(detail, 'adventure_bootstrap')
        && detail.autoStart !== true
        && detail.lordReady === true
        && zoneCanEnter(zone)
        && (zoneBossReady(zone) || primaryActionIsLord(detail));
    }

    function validLordCta(detail) {
      return detail.clicked === true
        && detail.presentationOnly === true
        && detail.source === 'existing_lord_cta'
        && detail.autoStart !== true
        && !hasOwn(detail, 'attemptId')
        && !hasOwn(detail, 'attempt_id');
    }

    function validLordTrialStarted(detail) {
      return baseServerFact(detail, 'adventure_boss_start')
        && detail.serverBound === true
        && normalized(firstDefined(detail, ['zoneKey', 'zone_key'])) === zone3Key
        && nonEmptyString(firstDefined(detail, ['attemptId', 'attempt_id']))
        && typeof detail.replay === 'boolean';
    }

    function validLordTrialProgress(detail) {
      var attemptId = firstDefined(detail, ['attemptId', 'attempt_id']);
      return baseServerFact(detail, 'adventure_boss_review')
        && detail.committed === true
        && detail.serverBound === true
        && normalized(firstDefined(detail, ['zoneKey', 'zone_key'])) === zone3Key
        && nonEmptyString(attemptId)
        && (!state.lordAttemptId || String(attemptId) === String(state.lordAttemptId))
        && (finiteNumber(detail.questionId) || nonEmptyString(detail.questionId));
    }

    function validLordClear(detail) {
      var zone = serverZoneFor(detail, zone3Key);
      var attemptId = firstDefined(detail, ['attemptId', 'attempt_id']);
      return baseServerFact(detail, 'adventure_boss_finish')
        && detail.passed === true
        && detail.zoneCleared === true
        && nonEmptyString(attemptId)
        && (!state.lordAttemptId || String(attemptId) === String(state.lordAttemptId))
        && typeof detail.replay === 'boolean'
        && typeof detail.firstClear === 'boolean'
        && (detail.replay ? detail.firstClear === false : detail.firstClear === true)
        && zoneCleared(zone)
        && zoneKey(zone) === zone3Key;
    }

    function validReward(detail) {
      var replay = detail.replay === true || detail.attemptMode === 'replay' || detail.attempt_mode === 'replay';
      var status = upper(firstDefined(detail, ['rewardStatus', 'reward_status']));
      var payload = isObject(detail.reward);
      return baseServerFact(detail, 'battlefield_reward_consumer')
        && detail.rewardProjection === true
        && detail.firstClear === true
        && detail.entitlementConsumed === true
        && replay !== true
        && nonEmptyString(firstDefined(detail, ['rewardEventId', 'reward_event_id']))
        && (payload || status === 'GRANTED' || status === 'ALREADY_OWNED')
        && detail.rewardZoneKey === zone3Key;
    }

    function validPostClear(detail) {
      var replay = detail.replay === true;
      var common = detail.authoritativeClear === true
        && detail.presentationOnly === true
        && normalized(detail.assetSlot) === normalized(postClearSlot.slotId);
      var manifestPresentation = detail.source === 'world_manifest'
        && detail.safeFallback !== true
        && normalized(detail.assetStatus) === 'READY';
      var safeFallback = detail.source === 'manifest_safe_fallback'
        && detail.safeFallback === true
        && normalized(detail.assetStatus) === 'PENDING_FINAL_ASSETS';
      return common && (manifestPresentation || safeFallback)
        && (replay || state.rewardSettled === true);
    }

    function validZone4Hook(detail) {
      var zone3 = serverZoneFor(detail, zone3Key);
      var zone4 = serverZoneFor(detail, zone4Key);
      return baseServerFact(detail, 'adventure_bootstrap')
        && detail.zone3Cleared === true
        && detail.hookOnly === true
        && detail.autoNavigate !== true
        && zoneCleared(zone3)
        && zoneCanEnter(zone4)
        && normalized(firstDefined(detail, ['zone4Key', 'zone4_key', 'targetZoneKey', 'target_zone_key'])) === zone4Key;
    }

    function validReturn(detail) {
      return detail.presentationOnly === true
        && detail.replaySafe === true
        && detail.source === 'canonical_return';
    }

    function transitionFor(event) {
      var detail = event.detail;
      var phase = state.phase;
      if (phase === 'IDLE' && event.type === events.zoneSelected && validZoneSelected(detail)) {
        return { nextPhase: 'ENTRY_PENDING', action: 'show_entry_target' };
      }
      if (phase === 'ENTRY_PENDING' && event.type === events.entry && validEntry(detail)) {
        return { nextPhase: 'ENTRY_CINEMATIC', action: 'show_safe_fallback' };
      }
      if (phase === 'ENTRY_CINEMATIC' && event.type === events.firstEntryCinematic
          && validFirstEntryCinematic(detail)) {
        return { nextPhase: 'GAMEPLAY_HANDOFF', action: 'show_cinematic' };
      }
      if (phase === 'GAMEPLAY_HANDOFF' && event.type === events.gameplayHandoff
          && validGameplayHandoff(detail)) {
        return { nextPhase: 'MAP_BATTLE_TRAINING', action: 'handoff' };
      }
      if ((phase === 'MAP_BATTLE_TRAINING' || phase === 'BATTLEFIELD_BOSS_PROGRESS')
          && event.type === events.mapBattle && validMapBattle(detail)) {
        var defeated = detail.monsterDefeated === true || detail.monster_defeated === true;
        return {
          nextPhase: defeated ? 'BATTLEFIELD_BOSS_PROGRESS' : 'MAP_BATTLE_TRAINING',
          action: 'observe'
        };
      }
      if ((phase === 'MAP_BATTLE_TRAINING' || phase === 'BATTLEFIELD_BOSS_PROGRESS')
          && event.type === events.battlefieldBossProgress && validMapBattle(detail)) {
        return { nextPhase: 'BATTLEFIELD_BOSS_PROGRESS', action: 'observe' };
      }
      if ((phase === 'ENTRY_PENDING' || phase === 'ENTRY_CINEMATIC'
          || phase === 'MAP_BATTLE_TRAINING' || phase === 'BATTLEFIELD_BOSS_PROGRESS')
          && event.type === events.lordReady && validLordReady(detail)) {
        return { nextPhase: 'LORD_READY', action: 'show_lord_cta' };
      }
      if (phase === 'LORD_READY' && event.type === events.lordCta && validLordCta(detail)) {
        return { nextPhase: 'LORD_CTA', action: 'show_lord_cta' };
      }
      if (phase === 'LORD_CTA' && event.type === events.lordTrialStarted
          && validLordTrialStarted(detail)) {
        return { nextPhase: 'LORD_TRIAL', action: 'handoff' };
      }
      if (phase === 'LORD_TRIAL' && event.type === events.lordTrialProgress
          && validLordTrialProgress(detail)) {
        return { nextPhase: 'LORD_TRIAL', action: 'observe' };
      }
      if (phase === 'LORD_TRIAL' && event.type === events.lordClear && validLordClear(detail)) {
        return { nextPhase: 'CLEAR_REWARD', action: 'clear' };
      }
      if (phase === 'CLEAR_REWARD' && event.type === events.reward && validReward(detail)) {
        return { nextPhase: 'CLEAR_REWARD', action: 'reward' };
      }
      if (phase === 'CLEAR_REWARD' && event.type === events.postClear && validPostClear(detail)) {
        return { nextPhase: 'POST_CLEAR_CINEMATIC', action: 'show_cinematic' };
      }
      if (phase === 'POST_CLEAR_CINEMATIC' && event.type === events.zone4Hook
          && validZone4Hook(detail)) {
        return { nextPhase: 'ZONE4_HOOK', action: 'show_zone4_hook' };
      }
      if (phase !== 'IDLE' && event.type === events.returnToMap && validReturn(detail)) {
        return { nextPhase: 'RETURN', action: 'return_safe' };
      }
      return null;
    }

    function updateServerFacts(detail) {
      var current = serverCurrentZoneKey(detail);
      // This is intentionally the only assignment to progressionZoneKey. A
      // selected tile is presentation state and can never move the player.
      if (current) state.progressionZoneKey = current;
      if (isObject(detail.adventureMonster)) state.lastServerMonster = clone(detail.adventureMonster);
      var battleResult = firstDefined(detail, ['result', 'battleResult', 'battle_result']);
      if (battleResult !== undefined) state.lastBattleResult = battleResult;
      var rewardStatus = firstDefined(detail, ['rewardStatus', 'reward_status']);
      if (rewardStatus !== undefined) state.lastRewardStatus = rewardStatus;
    }

    function accept(input) {
      var event = eventFrom(input);
      if (!event) return reject('invalid_event');
      var detail = event.detail;
      var eventId = firstDefined(detail, ['eventId', 'event_id']);
      var rewardEventId = firstDefined(detail, ['rewardEventId', 'reward_event_id']);
      if (eventId && contains(state.seenEventIds, eventId)) {
        return reject('duplicate_event', { eventId: eventId });
      }
      if (event.type === events.reward && rewardEventId && contains(state.rewardEventIds, rewardEventId)) {
        return reject('duplicate_reward_event', { rewardEventId: rewardEventId });
      }
      var transition = transitionFor(event);
      if (!transition) return reject('authority_or_sequence_check_failed', { eventType: event.type });

      if (eventId) addUnique(state.seenEventIds, eventId);
      state.lastEventType = event.type;
      updateServerFacts(detail);

      if (event.type === events.zoneSelected) {
        state.selectedZoneKey = zone3Key;
      }
      if (event.type === events.lordClear) {
        state.replay = detail.replay === true;
        state.authoritativeClear = true;
      }
      if (event.type === events.lordTrialStarted) {
        state.lordAttemptId = firstDefined(detail, ['attemptId', 'attempt_id']);
      }
      if (event.type === events.reward) {
        state.rewardSettled = true;
        addUnique(state.rewardEventIds, rewardEventId);
      }
      if (event.type === events.zone4Hook) state.zone4HookReady = true;

      var previousPhase = state.phase;
      if (transition.nextPhase !== previousPhase) addUnique(state.completedPhases, previousPhase);
      state.phase = transition.nextPhase;
      state.active = true;
      state.status = 'ACTIVE';
      return result(true, transition.action, {
        previousPhase: previousPhase,
        displayedPhase: state.phase,
        replay: state.replay,
        rewardEventId: rewardEventId || null,
        noClientUnlock: true
      });
    }

    function reset() {
      state.active = false;
      state.status = 'INACTIVE';
      state.phase = 'IDLE';
      state.selectedZoneKey = null;
      state.progressionZoneKey = null;
      state.replay = false;
      state.authoritativeClear = false;
      state.rewardSettled = false;
      state.zone4HookReady = false;
      state.completedPhases = [];
      state.seenEventIds = [];
      state.rewardEventIds = [];
      state.lastEventType = null;
      state.lastBattleResult = null;
      state.lastServerMonster = null;
      state.lastRewardStatus = null;
      state.lordAttemptId = null;
      return snapshot();
    }

    return Object.freeze({
      accept: accept,
      reset: reset,
      getState: snapshot,
      contentVersion: content.version || 'unknown'
    });
  }

  global.GoOdysseyJourneyZone3 = Object.freeze({
    version: 'W1_03_JOURNEY_ZONE3_VERTICAL_SLICE_WIRING_V1',
    create: create
  });
}(typeof window !== 'undefined' ? window : this));
