/*
 * E9 Player State Adapter — single source of truth for Top HUD.
 *
 * Canonical sources (see docs/planning/e9_1b_real_data_contract.md):
 *   GET /api/skills/profile -> { display_name, rank_level: 'LV<n>', ... }
 *   GET /api/user/coins     -> { coins, challenge_wins, ... }
 *   GET /api/player/appearance -> { character_key, ... }
 *
 * Responsibility: fetch, validate, normalize into a stable view model.
 * Never persists a second copy of canonical state (no localStorage, no
 * module-level cache surviving across page loads) -- every call re-reads
 * the canonical source.
 */
(function (global) {
  'use strict';

  var CHARACTER_ROOT = '/assets/hero/characters/';
  var FALLBACK_AVATAR = CHARACTER_ROOT + 'chibi_reference_normalized.webp';
  var CHARACTER_ASSETS = {
    apprentice: 'chibi_apprentice_normalized.webp',
    apprentice_girl: 'chibi_apprentice_girl_normalized.webp',
    swordsman: 'chibi_swordsman_normalized.webp',
    rogue: 'chibi_rogue_normalized.webp',
    ranger: 'chibi_ranger_normalized.webp',
    berserker: 'chibi_berserker_normalized.webp',
    guardian: 'chibi_guardian_normalized.webp',
    paladin: 'chibi_paladin_normalized.webp',
    mage: 'chibi_mage_normalized.webp',
    sage: 'chibi_sage_normalized.webp',
  };

  function normalizeAppearance(raw) {
    var key = raw && typeof raw.character_key === 'string' ? raw.character_key.trim() : '';
    var filename = CHARACTER_ASSETS[key];
    return {
      avatarSrc: filename ? CHARACTER_ROOT + filename : FALLBACK_AVATAR,
      avatarFallbackSrc: FALLBACK_AVATAR,
    };
  }

  /**
   * Pure normalization: raw /api/skills/profile JSON -> { name, level } or
   * throws on a structurally invalid response (missing required field).
   * rank_level is a string like 'LV12' -- extracts the numeric level so
   * callers can render it next to their own "Lv." label without a
   * duplicated "Lv. LV12" (a real bug in the pre-adapter top_hud.js).
   */
  function normalizeProfile(raw) {
    if (!raw || typeof raw !== 'object') {
      throw new Error('profile: response is not an object');
    }
    var name = typeof raw.display_name === 'string' && raw.display_name.trim() ? raw.display_name : null;
    var level = null;
    if (typeof raw.rank_level === 'string') {
      var m = raw.rank_level.match(/(\d+)/);
      if (m) level = parseInt(m[1], 10);
    } else if (typeof raw.rank_level === 'number' && !isNaN(raw.rank_level)) {
      level = raw.rank_level;
    }
    if (level !== null && (isNaN(level) || level < 0)) {
      level = null; // malformed/negative -- unavailable, not fabricated
    }
    return { name: name, level: level };
  }

  /**
   * Pure normalization: raw /api/user/coins JSON -> { coins } or throws.
   * 0 is valid data; missing/non-numeric/negative is unavailable (null),
   * never silently coerced to 0 -- callers must be able to tell "player
   * has zero coins" apart from "coins could not be read".
   */
  function normalizeCoins(raw) {
    if (!raw || typeof raw !== 'object') {
      throw new Error('coins: response is not an object');
    }
    var coins = null;
    if (typeof raw.coins === 'number' && !isNaN(raw.coins) && raw.coins >= 0) {
      coins = raw.coins;
    }
    return { coins: coins };
  }

  function classifyHttpError(status) {
    if (status === 401) return 'unauthorized';
    if (status === 403) return 'unauthorized';
    return 'error';
  }

  /**
   * fetchImpl is injectable so this file can be unit-tested under Node
   * without a real network/browser (see tests/e9_node_tests/).
   * Returns a Promise resolving to either:
   *   { ok: true, data: { name, level, coins, avatarSrc, avatarFallbackSrc } }
   *   { ok: false, kind: 'unauthorized'|'error'|'network', status }
   */
  function fetchPlayerState(fetchImpl) {
    var doFetch = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
    if (!doFetch) return Promise.resolve({ ok: false, kind: 'network', status: null });

    return Promise.all([
      doFetch('/api/skills/profile', { credentials: 'same-origin' }),
      doFetch('/api/user/coins', { credentials: 'same-origin' }),
      doFetch('/api/player/appearance', { credentials: 'same-origin' }).then(function (response) {
        if (!response.ok) return normalizeAppearance(null);
        return response.json().then(normalizeAppearance, function () { return normalizeAppearance(null); });
      }, function () { return normalizeAppearance(null); }),
    ]).then(function (responses) {
      var profileRes = responses[0];
      var coinsRes = responses[1];
      if (!profileRes.ok) return { ok: false, kind: classifyHttpError(profileRes.status), status: profileRes.status };
      if (!coinsRes.ok) return { ok: false, kind: classifyHttpError(coinsRes.status), status: coinsRes.status };
      return Promise.all([profileRes.json(), coinsRes.json()]).then(function (bodies) {
        var profile = normalizeProfile(bodies[0]);
        var coins = normalizeCoins(bodies[1]);
        var appearance = responses[2];
        return { ok: true, data: {
          name: profile.name,
          level: profile.level,
          coins: coins.coins,
          avatarSrc: appearance.avatarSrc,
          avatarFallbackSrc: appearance.avatarFallbackSrc,
        } };
      });
    }).catch(function () {
      return { ok: false, kind: 'network', status: null };
    });
  }

  var api = {
    normalizeProfile: normalizeProfile,
    normalizeCoins: normalizeCoins,
    normalizeAppearance: normalizeAppearance,
    fetchPlayerState: fetchPlayerState,
  };

  global.E9 = global.E9 || {};
  global.E9.Adapters = global.E9.Adapters || {};
  global.E9.Adapters.PlayerState = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : global);
