/*
 * E9 Adventure State Adapter — single source of truth for World Stage.
 *
 * Canonical source (see docs/planning/e9_1b_real_data_contract.md):
 *   GET /api/adventure/bootstrap -> { zones: [{ key, name, status,
 *     stars, boss: { available }, ... }], ... } -- the SAME endpoint
 *   the legacy Adventure Map uses. No second progression state is ever
 *   created or persisted here.
 */
(function (global) {
  'use strict';

  var VALID_STATUSES = ['locked', 'unlocked', 'completed', 'skipped_by_placement'];
  var cachedSuccess = null;
  var inFlight = null;

  /**
   * Pure normalization: raw zone object -> stable view model, or null if
   * the zone is structurally invalid (missing required fields) -- an
   * invalid zone is dropped, never rendered with fabricated defaults.
   */
  function normalizeZone(raw) {
    if (!raw || typeof raw.key !== 'string' || !raw.key) return null;
    if (typeof raw.name !== 'string' || !raw.name) return null;
    var status = VALID_STATUSES.indexOf(raw.status) !== -1 ? raw.status : null;
    if (!status) return null;

    var stars = 0;
    if (typeof raw.stars === 'number' && !isNaN(raw.stars)) {
      stars = Math.max(0, Math.min(3, Math.round(raw.stars)));
    }

    var bossAvailable = !!(raw.boss && raw.boss.available === true);

    // name_en is optional -- an older API response or a zone missing a
    // translation still normalizes successfully, falling back to `name`
    // (see world_stage.js's zoneDisplayName()), never a raw key.
    var nameEn = (typeof raw.name_en === 'string' && raw.name_en) ? raw.name_en : null;

    // seen/total feed the "{seen}/{total}" progress text (world_stage.js).
    // Same safe-numeric-or-zero normalization as `stars` above -- a
    // missing/non-numeric/negative value must never reach the UI as
    // NaN/undefined/a raw string.
    var seen = (typeof raw.seen === 'number' && !isNaN(raw.seen)) ? Math.max(0, Math.round(raw.seen)) : 0;
    var total = (typeof raw.total === 'number' && !isNaN(raw.total)) ? Math.max(0, Math.round(raw.total)) : 0;

    return {
      key: raw.key,
      name: raw.name,
      nameEn: nameEn,
      status: status,
      locked: status === 'locked',
      cleared: status === 'completed',
      stars: stars,
      bossAvailable: bossAvailable,
      seen: seen,
      total: total,
    };
  }

  /**
   * Pure normalization: raw /api/adventure/bootstrap JSON -> { zones }
   * (array of normalized zones, invalid entries dropped) or throws if
   * the top-level shape itself is invalid.
   */
  function normalizeZones(raw) {
    if (!raw || !Array.isArray(raw.zones)) {
      throw new Error('adventure bootstrap: missing zones array');
    }
    var zones = [];
    for (var i = 0; i < raw.zones.length; i++) {
      var z = normalizeZone(raw.zones[i]);
      if (z) zones.push(z);
    }
    return { zones: zones };
  }

  function classifyHttpError(status) {
    if (status === 401 || status === 403) return 'unauthorized';
    return 'error';
  }

  function invalidateAdventureState() {
    cachedSuccess = null;
    inFlight = null;
  }

  function fetchAdventureState(fetchImpl, options) {
    var opts = options || {};
    var doFetch = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
    if (!doFetch) return Promise.resolve({ ok: false, kind: 'network', status: null });
    if (opts.forceRefresh) invalidateAdventureState();
    if (cachedSuccess) return Promise.resolve(cachedSuccess);
    if (inFlight) return inFlight;

    inFlight = doFetch('/api/adventure/bootstrap', { credentials: 'same-origin' }).then(function (res) {
      if (!res.ok) return { ok: false, kind: classifyHttpError(res.status), status: res.status };
      return res.json().then(function (body) {
        var normalized = { ok: true, data: normalizeZones(body), rawData: body };
        cachedSuccess = normalized;
        return normalized;
      });
    }).catch(function () {
      return { ok: false, kind: 'network', status: null };
    }).then(function (result) {
      if (!result.ok) cachedSuccess = null;
      inFlight = null;
      return result;
    });

    return inFlight;
  }

  var api = {
    normalizeZone: normalizeZone,
    normalizeZones: normalizeZones,
    invalidateAdventureState: invalidateAdventureState,
    fetchAdventureState: fetchAdventureState,
  };

  global.E9 = global.E9 || {};
  global.E9.Adapters = global.E9.Adapters || {};
  global.E9.Adapters.AdventureState = api;
  global.E9AdventureState = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : global);
