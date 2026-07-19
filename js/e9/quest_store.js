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
        adventure: { maxStars: null, completedZoneCount: null },
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

    function destroy() {
      destroyed = true;
      inFlight = null;
      snapshot = null;
      previous = {};
      initialized = false;
      var adapters = global.E9 && global.E9.Adapters;
      if (adapters && adapters.AdventureState && typeof adapters.AdventureState.invalidateAdventureState === 'function') adapters.AdventureState.invalidateAdventureState();
      if (adapters && adapters.ActivityState && typeof adapters.ActivityState.invalidateActivityState === 'function') adapters.ActivityState.invalidateActivityState();
    }

    return { load: load, evaluate: evaluate, destroy: destroy, isCurrent: current, getSnapshot: function () { return snapshot; } };
  }

  global.E9 = global.E9 || {};
  global.E9.createQuestStore = createStore;
  if (typeof module !== 'undefined' && module.exports) module.exports = { createQuestStore: createStore };
})(typeof window !== 'undefined' ? window : global);
