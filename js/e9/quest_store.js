(function (global) {
  'use strict';

  function createStore(generation) {
    var destroyed = false;
    var inFlight = null;
    var snapshot = null;
    var previous = {};
    var initialized = false;

    function current() {
      return !destroyed && (!global.E9 || typeof global.E9.isLifecycleCurrent !== 'function' || global.E9.isLifecycleCurrent(generation));
    }

    function emptySnapshot() {
      return {
        // maxStars is the Zone-star authority used by quest evaluation.  A
        // separate visible projection may retain a grandfathered legacy Boss
        // star, but that projection must not complete a future star quest.
        adventure: {
          maxStars: null,
          authoritativeMaxStars: null,
          visibleMaxStars: null,
          completedZoneCount: null
        },
        dailyChallenge: { userSubmitted: null },
        fetchedAt: Date.now()
      };
    }

    function load() {
      if (!current()) return Promise.resolve({ ok: false, stale: true, snapshot: snapshot });
      if (inFlight) return inFlight;
      var adapters = global.E9 && global.E9.Adapters;
      var adventure = adapters && adapters.AdventureState;
      var activity = adapters && adapters.ActivityState;
      var adventurePromise = adventure && typeof adventure.fetchAdventureState === 'function'
        ? adventure.fetchAdventureState()
        : Promise.resolve({ ok: false, kind: 'unavailable' });
      var dailyPromise = activity && typeof activity.fetchDailyChallenge === 'function'
        ? activity.fetchDailyChallenge()
        : Promise.resolve({ ok: false, kind: 'unavailable' });
      inFlight = Promise.all([adventurePromise, dailyPromise]).then(function (results) {
        inFlight = null;
        if (!current()) return { ok: false, stale: true, snapshot: snapshot };
        var a = results[0];
        var d = results[1];
        var next = emptySnapshot();
        var errors = [];
        if (a && a.ok && a.data && Array.isArray(a.data.zones)) {
          next.adventure.maxStars = a.data.zones.reduce(function (max, zone) {
            return Math.max(max, typeof zone.stars === 'number' ? zone.stars : 0);
          }, 0);
          next.adventure.visibleMaxStars = a.data.zones.reduce(function (max, zone) {
            return Math.max(max, typeof zone.stars === 'number' ? zone.stars : 0);
          }, 0);
          next.adventure.authoritativeMaxStars = a.data.zones.reduce(function (max, zone) {
            var authority = typeof zone.zone_authority_stars === 'number'
              ? zone.zone_authority_stars
              : (typeof zone.stars === 'number' ? zone.stars : 0);
            return Math.max(max, authority);
          }, 0);
          next.adventure.completedZoneCount = a.data.zones.reduce(function (count, zone) {
            return count + (zone && zone.cleared === true ? 1 : 0);
          }, 0);
        } else errors.push('adventure');
        if (d && d.ok && d.data && typeof d.data.submitted === 'boolean') {
          next.dailyChallenge.userSubmitted = d.data.submitted;
        } else errors.push('dailyChallenge');
        snapshot = next;
        return { ok: errors.length === 0, partial: errors.length > 0 && errors.length < 2, errors: errors, snapshot: next };
      }).catch(function () {
        inFlight = null;
        if (!current()) return { ok: false, stale: true, snapshot: snapshot };
        snapshot = emptySnapshot();
        return { ok: false, errors: ['adventure', 'dailyChallenge'], snapshot: snapshot };
      });
      return inFlight;
    }

    function evaluate(catalog, evaluator) {
      var results = (catalog || []).map(function (definition) {
        var value = evaluator.evaluateQuest(definition, snapshot || emptySnapshot());
        var was = previous[definition.id];
        if (initialized && was && was.completed !== true && value.completed === true) value.justCompleted = true;
        previous[definition.id] = value;
        return value;
      });
      initialized = true;
      return results;
    }

    function isCriticalFallbackCleanup() {
      // recoverToLegacy() marks the pending ownership handoff to legacy
      // before it destroys the E9 lifecycle.  Normal destroyShell() performs
      // the same cleanup first and only marks the shell legacy afterwards.
      // Preserve the shared AdventureState cache only for that narrow,
      // observable handoff while the active lifecycle is still E9.
      var e9 = global.E9;
      return global.__GO_E9_ACTIVE_SHELL__ === 'legacy'
        && e9
        && typeof e9.getActiveShell === 'function'
        && e9.getActiveShell() === 'e9';
    }

    function prepareLegacyFallbackCache(result) {
      // Legacy Adventure Map consumes the older `unlocked`/`completed` field
      // names.  When the shared successful result came from a minimal or
      // older payload without those aliases, project the adapter's already
      // normalized read-only values onto the cached raw result.  This is a
      // presentation compatibility bridge only; it does not create or alter
      // server-owned progression.
      if (!result || result.ok !== true || !result.data || !Array.isArray(result.data.zones)) return;
      var rawData = result.rawData && typeof result.rawData === 'object'
        ? result.rawData
        : {};
      var rawZones = Array.isArray(rawData.zones) ? rawData.zones : [];
      var normalizedByKey = {};
      result.data.zones.forEach(function (zone) {
        if (zone && typeof zone.key === 'string') normalizedByKey[zone.key] = zone;
      });
      var sourceZones = rawZones.length ? rawZones : result.data.zones;
      rawData.zones = sourceZones.map(function (rawZone) {
        var source = rawZone && typeof rawZone === 'object' ? rawZone : {};
        var key = typeof source.key === 'string' ? source.key : null;
        var normalized = key ? normalizedByKey[key] : null;
        if (!normalized) return source;
        var next = source;
        var hasEnterability = typeof source.unlocked === 'boolean'
          || typeof source.can_enter === 'boolean'
          || (source.stage && typeof source.stage.can_enter === 'boolean');
        if (!hasEnterability || (typeof source.completed !== 'boolean' && typeof source.cleared !== 'boolean')) {
          next = Object.assign({}, source);
        }
        if (!hasEnterability) next.unlocked = normalized.locked !== true;
        if (typeof next.completed !== 'boolean' && typeof next.cleared !== 'boolean') {
          next.cleared = normalized.cleared === true;
        }
        if (!source.name && normalized.name) next.name = normalized.name;
        if (!source.name_en && normalized.nameEn) next.name_en = normalized.nameEn;
        if (typeof source.stars !== 'number' && typeof normalized.stars === 'number') next.stars = normalized.stars;
        if (typeof source.seen !== 'number' && typeof normalized.seen === 'number') next.seen = normalized.seen;
        if (typeof source.total !== 'number' && typeof normalized.total === 'number') next.total = normalized.total;
        return next;
      });
      result.rawData = rawData;
    }

    function destroy() {
      destroyed = true;
      inFlight = null;
      snapshot = null;
      previous = {};
      initialized = false;
      var adapters = global.E9 && global.E9.Adapters;
      if (isCriticalFallbackCleanup()
          && adapters && adapters.AdventureState
          && typeof adapters.AdventureState.fetchAdventureState === 'function') {
        adapters.AdventureState.fetchAdventureState().then(prepareLegacyFallbackCache, function () {});
      } else if (adapters && adapters.AdventureState
          && typeof adapters.AdventureState.invalidateAdventureState === 'function') {
        adapters.AdventureState.invalidateAdventureState();
      }
      if (adapters && adapters.ActivityState && typeof adapters.ActivityState.invalidateActivityState === 'function') adapters.ActivityState.invalidateActivityState();
    }

    return { load: load, evaluate: evaluate, destroy: destroy, isCurrent: current, getSnapshot: function () { return snapshot; } };
  }

  global.E9 = global.E9 || {};
  global.E9.createQuestStore = createStore;
  if (typeof module !== 'undefined' && module.exports) module.exports = { createQuestStore: createStore };
})(typeof window !== 'undefined' ? window : global);
