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
  var E10_CINEMATIC_KEYS = [
    'e10_zone1_intro_v1', 'e10_zone2_intro_v1', 'e10_zone3_intro_v1',
    'e10_zone4_intro_v1', 'e10_zone5_intro_v1', 'e10_zone6_intro_v1',
    'e10_zone7_intro_v1', 'e10_zone8_intro_v1', 'e10_zone9_intro_v1',
    'e10_zone10_intro_v1',
  ];
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
      canEnter: raw.can_enter === true && status !== 'locked',
      skippedByPlacement: status === 'skipped_by_placement' || raw.skipped_by_placement === true,
      recommended: raw.recommended === true,
      selected: raw.selected === true,
      stars: stars,
      bossAvailable: bossAvailable,
      seen: seen,
      total: total,
      // Boss availability is copied only from the authoritative nested
      // payload; displayed seen/total values never promote a boss to ready.
      bossKey: (raw.boss && typeof raw.boss.key === 'string') ? raw.boss.key : null,
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
    var currentZoneKey = null;
    if (typeof raw.current_zone_key === 'string' && raw.current_zone_key) {
      for (var j = 0; j < zones.length; j++) {
        if (zones[j].key === raw.current_zone_key && !zones[j].locked && zones[j].canEnter === true) {
          currentZoneKey = raw.current_zone_key;
          break;
        }
      }
    }
    var primaryAction = null;
    var rawAction = raw.primary_action;
    var validActionKinds = ['challenge_lord', 'normal_progression', 'replenish_stars', 'replay_completed'];
    if (rawAction && typeof rawAction.kind === 'string' && validActionKinds.indexOf(rawAction.kind) !== -1) {
      for (var k = 0; k < zones.length; k++) {
        if (zones[k].key === rawAction.zone_key && !zones[k].locked && zones[k].canEnter === true) {
          primaryAction = {
            kind: rawAction.kind,
            zoneKey: rawAction.zone_key,
            bossKey: typeof rawAction.boss_key === 'string' ? rawAction.boss_key : null,
          };
          break;
        }
      }
    }
    var rawCinematics = raw.cinematics && typeof raw.cinematics === 'object'
      ? raw.cinematics
      : {};
    var cinematics = {};
    E10_CINEMATIC_KEYS.forEach(function (key) {
      var entry = rawCinematics[key];
      cinematics[key] = {
        // The server is authoritative. Missing/invalid records are unseen;
        // browser storage is intentionally not consulted here.
        seen: !!(entry && entry.seen === true),
        seenAt: entry && typeof entry.seen_at === 'string' ? entry.seen_at : null,
      };
    });
    return {
      zones: zones,
      cinematics: cinematics,
      placement: raw.placement || null,
      recommended: raw.recommended || null,
      selected: raw.selected || null,
      currentZoneKey: currentZoneKey,
      primaryAction: primaryAction,
    };
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

    var requestInit = { credentials: 'same-origin' };
    if (opts.forceRefresh) requestInit.cache = 'no-store';
    inFlight = doFetch('/api/adventure/bootstrap', requestInit).then(function (res) {
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

  function refreshAdventureState(fetchImpl) {
    return fetchAdventureState(fetchImpl, { forceRefresh: true });
  }

  var api = {
    normalizeZone: normalizeZone,
    normalizeZones: normalizeZones,
    invalidateAdventureState: invalidateAdventureState,
    fetchAdventureState: fetchAdventureState,
    refreshAdventureState: refreshAdventureState,
  };

  global.E9 = global.E9 || {};
  global.E9.Adapters = global.E9.Adapters || {};
  global.E9.Adapters.AdventureState = api;
  global.E9AdventureState = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : global);
