/*
 * Legacy Adventure bridge for the shared Map Battle v1 runtime.
 *
 * This file owns transport and authoritative-state parsing only.  It never
 * derives settlement authority in the browser and it keeps retry identity in
 * the in-memory state object so a retry can reuse the issued nonce.
 */
(function (global) {
  'use strict';

  var ANSWER_ENDPOINT = '/api/adventure/map-battles/v1/answers';
  var ATTEMPT_ENDPOINT = '/api/adventure/map-battles/v1/attempts';
  var RUNTIME_SERVICE_ID = 'map-battle-v1-runtime';
  var UPGRADE_MESSAGE = 'Game updated; refresh and continue';

  function requiredText(value, name) {
    if (typeof value !== 'string' || !value.trim()) {
      throw new Error(name + ' is required');
    }
    return value.trim();
  }

  function responseError(response, data) {
    if (response.status === 426 || data.code === 'upgrade_required') {
      var upgrade = new Error(UPGRADE_MESSAGE);
      upgrade.code = 'upgrade_required';
      upgrade.status = 426;
      return upgrade;
    }
    var failure = new Error(data.message || data.error || ('HTTP ' + response.status));
    failure.code = data.code || data.error || 'map_battle_request_failed';
    failure.status = response.status;
    failure.retryable = data.retryable === true;
    return failure;
  }

  async function request(fetcher, url, options) {
    var response = await fetcher(url, options);
    var data = await response.json();
    if (!response.ok) throw responseError(response, data || {});
    if (data && data.runtime_service && data.runtime_service !== RUNTIME_SERVICE_ID) {
      throw new Error('unexpected battle runtime service');
    }
    return data || {};
  }

  function headers() {
    return {
      'Content-Type': 'application/json',
      'X-Map-Battle-Client-Protocol': 'v1'
    };
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
    if (!state || !response || typeof response !== 'object') {
      throw new Error('authoritative response is required');
    }
    var battle = response.battle && typeof response.battle === 'object'
      ? response.battle : response;
    if (Number.isFinite(battle.player_hp)) state.playerHp = Number(battle.player_hp);
    if (Number.isFinite(battle.player_hp_max)) state.playerHpMax = Number(battle.player_hp_max);
    if (Number.isFinite(battle.monster_hp)) state.monsterHp = Number(battle.monster_hp);
    if (Number.isFinite(battle.monster_hp_max)) state.monsterHpMax = Number(battle.monster_hp_max);
    if (Number.isFinite(battle.battle_revision)) state.battleRevision = Number(battle.battle_revision);
    if (Number.isFinite(response.player_hp_after)) state.playerHp = Number(response.player_hp_after);
    if (Number.isFinite(response.monster_hp_after)) state.monsterHp = Number(response.monster_hp_after);
    if (Number.isFinite(response.battle_revision)) state.battleRevision = Number(response.battle_revision);
    if (battle.battle_id) state.battleId = String(battle.battle_id);
    if (battle.zone_key) state.zoneKey = String(battle.zone_key);
    state.monsterDefeated = response.monster_defeated === true || Number(state.monsterHp) === 0;
    state.playerDefeated = response.player_defeated === true || Number(state.playerHp) === 0;
    state.lastResult = response.result || state.lastResult || null;
    state.lastDuplicate = response.duplicate === true;
    state.lastResponse = {
      result: response.result || null,
      duplicate: response.duplicate === true,
      accepted: response.accepted === true,
      damageToMonster: Number(response.damage_to_monster || 0),
      damageToPlayer: Number(response.damage_to_player || 0),
      battleRevision: Number.isFinite(response.battle_revision)
        ? Number(response.battle_revision) : state.battleRevision
    };
    return state;
  }

  async function prepare(context, fetchImpl) {
    var fetcher = fetchImpl || global.fetch;
    if (typeof fetcher !== 'function') throw new Error('fetch is unavailable');
    context = context || {};
    var data = await request(fetcher, ATTEMPT_ENDPOINT, {
      credentials: 'include',
      method: 'POST',
      headers: headers(),
      body: JSON.stringify({
        zone_key: requiredText(context.zoneKey || context.zone_key, 'zone_key'),
        question_id: Number(context.questionId != null ? context.questionId : context.question_id)
      })
    });
    var attempt = data.attempt || {};
    var state = {
      active: true,
      battleId: String(data.battle_id || attempt.battle_id),
      attemptId: String(data.attempt_id || attempt.attempt_id),
      submissionNonce: requiredText(data.submission_nonce, 'submission_nonce'),
      questionId: Number(data.question_id || attempt.question_id),
      questionRevision: String(data.question_revision || attempt.question_revision),
      playerColor: String(data.player_color || attempt.player_color || 'B'),
      transformId: String(data.transform_id || attempt.transform_id),
      transformVersion: String(data.transform_version || attempt.transform_version),
      issuedAt: data.issued_at || attempt.issued_at,
      expiresAt: data.expires_at || attempt.expires_at,
      moves: []
    };
    applyAuthoritativeState(state, data.battle || data);
    return state;
  }

  async function refreshBattle(state, fetchImpl) {
    var fetcher = fetchImpl || global.fetch;
    if (typeof fetcher !== 'function') throw new Error('fetch is unavailable');
    state = state || {};
    var battleId = requiredText(state.battleId || state.battle_id, 'battle_id');
    var data = await request(fetcher, '/api/adventure/map-battles/v1/battles/' + encodeURIComponent(battleId), {
      credentials: 'include',
      method: 'GET',
      headers: { 'X-Map-Battle-Client-Protocol': 'v1' }
    });
    applyAuthoritativeState(state, data.battle || data);
    return state;
  }

  async function submit(state, moves, fetchImpl) {
    var fetcher = fetchImpl || global.fetch;
    if (typeof fetcher !== 'function') throw new Error('fetch is unavailable');
    var data = await request(fetcher, ANSWER_ENDPOINT, {
      credentials: 'include',
      method: 'POST',
      headers: headers(),
      body: JSON.stringify(buildRequest(state, moves))
    });
    applyAuthoritativeState(state, data);
    return data;
  }

  function retry(state, moves, fetchImpl) {
    return submit(state, moves, fetchImpl);
  }

  var legacy = {
    surface: 'legacy-adventure-map',
    runtimeService: RUNTIME_SERVICE_ID,
    endpoint: ANSWER_ENDPOINT,
    attemptEndpoint: ATTEMPT_ENDPOINT,
    buildRequest: buildRequest,
    prepare: prepare,
    refreshBattle: refreshBattle,
    submit: submit,
    retry: retry,
    applyAuthoritativeState: applyAuthoritativeState,
    upgradeMessage: UPGRADE_MESSAGE
  };
  var shared = {
    runtimeService: RUNTIME_SERVICE_ID,
    endpoint: ANSWER_ENDPOINT,
    attemptEndpoint: ATTEMPT_ENDPOINT,
    buildRequest: buildRequest,
    prepare: prepare,
    refreshBattle: refreshBattle,
    submit: submit,
    retry: retry,
    applyAuthoritativeState: applyAuthoritativeState,
    legacy: legacy
  };
  global.MapBattleV1 = shared;
}(window));
