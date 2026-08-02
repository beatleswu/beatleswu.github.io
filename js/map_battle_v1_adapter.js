/*
 * Shared Map Battle v1 client adapter.
 *
 * Legacy Adventure and E10 World Map intentionally expose only these thin
 * adapters.  They submit the same request contract and consume only the
 * authoritative HP/revision returned by the server.  This module has no
 * legacy SRS fallback and never creates a grade, damage value, or nonce.
 */
(function (global) {
  'use strict';

  var ENDPOINT = '/api/adventure/map-battles/v1/answers';
  var RUNTIME_SERVICE_ID = 'map-battle-v1-runtime';
  var UPGRADE_MESSAGE = '遊戲已更新，請重新整理後繼續';

  function requiredText(value, name) {
    if (typeof value !== 'string' || !value.trim()) throw new Error(name + ' is required');
    return value.trim();
  }

  function buildRequest(state, moves) {
    state = state || {};
    if (!Array.isArray(moves)) throw new Error('moves must be an array');
    return {
      battle_id: requiredText(state.battleId || state.battle_id, 'battle_id'),
      attempt_id: requiredText(state.attemptId || state.attempt_id, 'attempt_id'),
      submission_nonce: requiredText(state.submissionNonce || state.submission_nonce, 'submission_nonce'),
      battle_revision: Number.isInteger(state.battleRevision != null ? state.battleRevision : state.battle_revision)
        ? (state.battleRevision != null ? state.battleRevision : state.battle_revision) : 0,
      question_revision: requiredText(state.questionRevision || state.question_revision, 'question_revision'),
      player_color: requiredText(state.playerColor || state.player_color, 'player_color'),
      transform_id: requiredText(state.transformId || state.transform_id, 'transform_id'),
      transform_version: requiredText(state.transformVersion || state.transform_version, 'transform_version'),
      moves: moves
    };
  }

  function applyAuthoritativeState(state, response) {
    if (!state || !response || typeof response !== 'object') throw new Error('authoritative response is required');
    if (Number.isFinite(response.player_hp_after)) state.playerHp = response.player_hp_after;
    if (Number.isFinite(response.monster_hp_after)) state.monsterHp = response.monster_hp_after;
    if (Number.isFinite(response.battle_revision)) state.battleRevision = response.battle_revision;
    state.monsterDefeated = response.monster_defeated === true;
    state.playerDefeated = response.player_defeated === true;
    return {
      duplicate: response.duplicate === true,
      replayDamageAnimation: response.duplicate !== true,
      nextAction: response.next_action || 'continue',
      runtimeService: response.runtime_service || RUNTIME_SERVICE_ID
    };
  }

  async function submit(state, moves, fetchImpl) {
    var fetcher = fetchImpl || global.fetch;
    if (typeof fetcher !== 'function') throw new Error('fetch is unavailable');
    var response = await fetcher(ENDPOINT, {
      credentials: 'include',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Map-Battle-Client-Protocol': 'v1'
      },
      body: JSON.stringify(buildRequest(state, moves))
    });
    var data = await response.json();
    if (response.status === 426 || data.code === 'upgrade_required') {
      var upgrade = new Error(UPGRADE_MESSAGE);
      upgrade.code = 'upgrade_required';
      upgrade.status = 426;
      throw upgrade;
    }
    if (!response.ok) {
      var failure = new Error(data.message || data.error || ('HTTP ' + response.status));
      failure.code = data.code || data.error || 'map_battle_request_failed';
      failure.status = response.status;
      throw failure;
    }
    if (data && data.runtime_service && data.runtime_service !== RUNTIME_SERVICE_ID) {
      throw new Error('unexpected battle runtime service');
    }
    return data;
  }

  function makeAdapter(surface) {
    return {
      surface: surface,
      runtimeService: RUNTIME_SERVICE_ID,
      endpoint: ENDPOINT,
      buildRequest: buildRequest,
      submit: submit,
      applyAuthoritativeState: applyAuthoritativeState,
      upgradeMessage: UPGRADE_MESSAGE
    };
  }

  var shared = {
    runtimeService: RUNTIME_SERVICE_ID,
    endpoint: ENDPOINT,
    buildRequest: buildRequest,
    submit: submit,
    applyAuthoritativeState: applyAuthoritativeState,
    legacy: makeAdapter('legacy-adventure-map'),
    e10: makeAdapter('e10-world-map')
  };
  global.MapBattleV1 = shared;
  global.E9 = global.E9 || {};
  global.E9.Adapters = global.E9.Adapters || {};
  global.E9.Adapters.MapBattleV1 = shared.e10;
}(window));
