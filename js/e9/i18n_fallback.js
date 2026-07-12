/*
 * E9 i18n fallback helper — single hardened wrapper around window.I18n.t()
 * for all E9 components (see docs/planning/release_fix_b_e9_i18n_fallback.md).
 *
 * window.I18n.t(key) returns the key itself when the key is missing from
 * the dictionary (see i18n.js) -- a bare `I18n.t(key) || fallback` never
 * reaches `fallback` because the returned key string is truthy. This
 * helper checks "did a real translation actually come back" instead of
 * relying on truthiness, so a missing key, an empty result, an
 * unavailable I18n object, or a thrown error all fall through to the
 * caller's fallback text -- never a raw dictionary key rendered to a
 * player or a screen reader.
 *
 * Does not add a params/interpolation argument: the real I18n.t() takes
 * only `key`. Every existing call site (legacy index.html and E9 alike)
 * does its own `.replace('{n}', value)` chaining on the returned string,
 * and this helper preserves that contract unchanged.
 */
(function (global) {
  'use strict';

  function translate(key, fallback) {
    var i18n = global.I18n;
    if (!i18n || typeof i18n.t !== 'function') return fallback;

    var val;
    try {
      val = i18n.t(key);
    } catch (err) {
      return fallback;
    }

    if (val === null || val === undefined || val === '' || val === key) {
      return fallback;
    }
    return val;
  }

  var api = { t: translate };

  global.E9 = global.E9 || {};
  global.E9.I18nFallback = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : global);
