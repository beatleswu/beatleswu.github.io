/*
 * E9 Feature Flags — single source of truth for the Adventure Shell rollout.
 *
 * Rollout stages (see docs/planning/e9_1a1_component_foundation.md):
 *   Stage A: standalone spike/demo page only, no production wiring.
 *   Stage B: integrated into index.html but PRODUCTION_FLAGS.e9Shell stays
 *            false — every real player still sees the legacy Adventure Map.
 *   Stage C: PRODUCTION_FLAGS.e9Shell flips to true in a real release,
 *            after E9 UI/RWD/Avatar/Monster/regression work is done.
 *
 * There is deliberately no production gray rollout and no player-triggered
 * URL toggle. Query-param overrides only ever take effect in a debug
 * environment (see isDebugEnvironment) AND only when ?E9_DEBUG=1 is present.
 * A bare query param can never flip a flag in production by itself.
 */
(function (global) {
  'use strict';

  // Bump alongside sw.js VERSION whenever E9 JS/CSS changes ship, so the
  // cache-first strategy in sw.js for *.js/*.css does not strand users on
  // a stale bundle. Also appended as ?v= on every component fragment URL.
  var ASSET_VERSION = 'e9-1d2-1';

  var PRODUCTION_FLAGS = {
    e9Shell: false,
    e9TopHud: false,
    e9LeftNav: false,
    e9RightCards: false,
    e9BottomDock: false,
    e9WorldStage: false
  };

  // Debug environment = localhost/dev-style hostname, NOT the production
  // hostname. This is a coarse, client-side check (not a security boundary)
  // meant only to keep query-param overrides out of real players' hands;
  // it must be combined with the explicit ?E9_DEBUG=1 opt-in below.
  var DEBUG_HOSTNAMES = new RegExp(
    '^(localhost|127\\.0\\.0\\.1|\\[::1\\]|.*\\.local|.*\\.test)$', 'i'
  );

  function isDebugEnvironment() {
    var host = (global.location && global.location.hostname) || '';
    return DEBUG_HOSTNAMES.test(host);
  }

  function resolveFlags() {
    if (global.__GO_E9_FLAGS__ && typeof global.__GO_E9_FLAGS__ === 'object') {
      return Object.assign({}, global.__GO_E9_FLAGS__);
    }
    var base = Object.assign({}, PRODUCTION_FLAGS, global.GO_ODYSSEY_FEATURES || {});
    var params = new URLSearchParams(global.location ? global.location.search : '');

    var debugOptIn = params.get('E9_DEBUG') === '1';
    global.__GO_E9_FLAGS__ = Object.assign({}, base);
    if (!debugOptIn || !isDebugEnvironment()) {
      return base;
    }

    // Debug mode: allow any PRODUCTION_FLAGS key to be overridden via query,
    // e.g. ?E9_DEBUG=1&e9RightCards=0 — only reachable on a debug hostname.
    Object.keys(base).forEach(function (key) {
      if (params.has(key)) {
        var raw = params.get(key);
        base[key] = raw !== '0' && raw !== 'false';
      }
    });
    global.__GO_E9_FLAGS__ = Object.assign({}, base);
    return base;
  }

  global.E9 = global.E9 || {};
  global.E9.ASSET_VERSION = ASSET_VERSION;
  global.E9.PRODUCTION_FLAGS = PRODUCTION_FLAGS;
  global.E9.isDebugEnvironment = isDebugEnvironment;
  global.E9.getFlags = resolveFlags;
})(window);
