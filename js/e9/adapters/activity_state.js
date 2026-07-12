/*
 * E9 Activity State Adapter — single source of truth for Right Cards.
 *
 * Canonical sources (see docs/planning/e9_1b_real_data_contract.md):
 *   GET /api/daily-challenge/today -> { user_submitted, user_correct, ... }
 *   GET /api/adventure/bootstrap   -> { zones: [...] } (boss progress summary)
 *   GET /api/srs/due                -> { due: [...], count }
 *   GET /api/mistakes/stats         -> { total, corrected, worst5 }
 *
 * Each card fetches/normalizes independently -- one failing never blocks
 * the others (see js/e9/right_cards.js, which calls these functions
 * separately per card).
 */
(function (global) {
  'use strict';

  function classifyHttpError(status) {
    if (status === 401 || status === 403) return 'unauthorized';
    return 'error';
  }

  /** raw daily-challenge/today JSON -> { submitted, correct } */
  function normalizeDailyChallenge(raw) {
    if (!raw || typeof raw !== 'object') throw new Error('daily-challenge: response is not an object');
    var submitted = raw.user_submitted === true;
    var correct = submitted && typeof raw.user_correct === 'boolean' ? raw.user_correct : null;
    return { submitted: submitted, correct: correct };
  }

  /** raw adventure/bootstrap JSON -> { cleared, total } (boss progress summary) */
  function normalizeBossProgress(raw) {
    if (!raw || !Array.isArray(raw.zones)) throw new Error('adventure bootstrap: missing zones array');
    var total = raw.zones.length;
    var cleared = 0;
    for (var i = 0; i < raw.zones.length; i++) {
      if (raw.zones[i] && raw.zones[i].status === 'completed') cleared++;
    }
    return { cleared: cleared, total: total };
  }

  /** raw srs/due JSON -> { count } */
  function normalizeSrsDue(raw) {
    if (!raw || typeof raw !== 'object') throw new Error('srs/due: response is not an object');
    var count = typeof raw.count === 'number' && !isNaN(raw.count) && raw.count >= 0 ? raw.count : null;
    return { count: count };
  }

  /** raw mistakes/stats JSON -> { total } */
  function normalizeMistakes(raw) {
    if (!raw || typeof raw !== 'object') throw new Error('mistakes/stats: response is not an object');
    var total = typeof raw.total === 'number' && !isNaN(raw.total) && raw.total >= 0 ? raw.total : null;
    return { total: total };
  }

  function fetchOne(url, normalize, fetchImpl) {
    var doFetch = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
    if (!doFetch) return Promise.resolve({ ok: false, kind: 'network', status: null });
    return doFetch(url, { credentials: 'same-origin' }).then(function (res) {
      if (!res.ok) return { ok: false, kind: classifyHttpError(res.status), status: res.status };
      return res.json().then(function (body) {
        return { ok: true, data: normalize(body) };
      });
    }).catch(function () {
      return { ok: false, kind: 'network', status: null };
    });
  }

  function fetchDailyChallenge(fetchImpl) {
    return fetchOne('/api/daily-challenge/today', normalizeDailyChallenge, fetchImpl);
  }
  function fetchBossProgress(fetchImpl) {
    return fetchOne('/api/adventure/bootstrap', normalizeBossProgress, fetchImpl);
  }
  function fetchSrsDue(fetchImpl) {
    return fetchOne('/api/srs/due', normalizeSrsDue, fetchImpl);
  }
  function fetchMistakes(fetchImpl) {
    return fetchOne('/api/mistakes/stats', normalizeMistakes, fetchImpl);
  }

  var api = {
    normalizeDailyChallenge: normalizeDailyChallenge,
    normalizeBossProgress: normalizeBossProgress,
    normalizeSrsDue: normalizeSrsDue,
    normalizeMistakes: normalizeMistakes,
    fetchDailyChallenge: fetchDailyChallenge,
    fetchBossProgress: fetchBossProgress,
    fetchSrsDue: fetchSrsDue,
    fetchMistakes: fetchMistakes,
  };

  global.E9 = global.E9 || {};
  global.E9.Adapters = global.E9.Adapters || {};
  global.E9.Adapters.ActivityState = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : global);
