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
  var DEFAULT_CHARACTER_KEY = 'apprentice';
  var CHARACTER_PRESENTATIONS = {
    apprentice: { id: 'apprentice', asset: CHARACTER_ROOT + 'chibi_apprentice_normalized.webp' },
    apprentice_girl: { id: 'apprentice_girl', asset: CHARACTER_ROOT + 'chibi_apprentice_girl_normalized.webp' },
    swordsman: { id: 'swordsman', asset: CHARACTER_ROOT + 'chibi_swordsman_normalized.webp' },
    rogue: { id: 'rogue', asset: CHARACTER_ROOT + 'chibi_rogue_normalized.webp' },
    ranger: { id: 'ranger', asset: CHARACTER_ROOT + 'chibi_ranger_normalized.webp' },
    berserker: { id: 'berserker', asset: CHARACTER_ROOT + 'chibi_berserker_normalized.webp' },
    guardian: { id: 'guardian', asset: CHARACTER_ROOT + 'chibi_guardian_normalized.webp' },
    paladin: { id: 'paladin', asset: CHARACTER_ROOT + 'chibi_paladin_normalized.webp' },
    mage: { id: 'mage', asset: CHARACTER_ROOT + 'chibi_mage_normalized.webp' },
    sage: { id: 'sage', asset: CHARACTER_ROOT + 'chibi_sage_normalized.webp' },
  };
  var DERIVED84_RUNTIME_MANIFEST_URL = '/assets/world-map-identity/runtime_manifest.json';
  var derived84ManifestPromise = null;

  function isFuture30Appearance(raw) {
    return !!(raw && raw.character_runtime
      && typeof raw.character_runtime.visual_model_id === 'string'
      && raw.character_runtime.visual_model_id.trim());
  }

  function safeDerived84Path(value) {
    if (typeof value !== 'string' || !value.startsWith('assets/world-map-identity/')
      || value.includes('..') || value.includes('\\')) return '';
    return '/' + value;
  }

  function validateDerived84Manifest(manifest) {
    if (!manifest || typeof manifest !== 'object'
      || manifest.manifest_version !== 'G009_DERIVED84_RUNTIME_MANIFEST_V1'
      || manifest.derived_84_asset_visual_authority !== 'LOCKED'
      || manifest.owner_acceptance_complete !== true
      || manifest.runtime_consumed !== true
      || manifest.derived_84_total !== 84
      || manifest.owner_accepted_authority_rows !== 84
      || !Array.isArray(manifest.entries) || manifest.entries.length !== 84) {
      throw new Error('derived84_manifest_authority_mismatch');
    }
    var counts = { AVATAR: 0, STANDING: 0, COMPANION: 0 };
    var avatarByVisual = Object.create(null);
    var standingByVisual = Object.create(null);
    manifest.entries.forEach(function (entry) {
      if (!entry || entry.owner_decision !== 'PASS'
        || !Object.prototype.hasOwnProperty.call(counts, entry.asset_role)
        || typeof entry.expected_runtime_sha256 !== 'string'
        || !/^[a-f0-9]{64}$/i.test(entry.expected_runtime_sha256)) {
        throw new Error('derived84_manifest_entry_invalid');
      }
      var path = safeDerived84Path(entry.target_runtime_path);
      if (!path) throw new Error('derived84_manifest_path_invalid');
      counts[entry.asset_role] += 1;
      if (entry.asset_role === 'AVATAR' || entry.asset_role === 'STANDING') {
        if (typeof entry.visual_model_id !== 'string' || !entry.visual_model_id.trim()) {
          throw new Error('derived84_visual_identity_missing');
        }
        var byVisual = entry.asset_role === 'AVATAR' ? avatarByVisual : standingByVisual;
        if (byVisual[entry.visual_model_id]) throw new Error('derived84_visual_identity_duplicate');
        byVisual[entry.visual_model_id] = { path: path, sha256: entry.expected_runtime_sha256 };
      }
    });
    if (counts.AVATAR !== 33 || counts.STANDING !== 33 || counts.COMPANION !== 18) {
      throw new Error('derived84_manifest_role_count_mismatch');
    }
    return { avatarByVisual: avatarByVisual, standingByVisual: standingByVisual };
  }

  function loadDerived84Manifest(doFetch) {
    if (derived84ManifestPromise) return derived84ManifestPromise;
    derived84ManifestPromise = doFetch(DERIVED84_RUNTIME_MANIFEST_URL, {
      credentials: 'same-origin',
      cache: 'no-store',
    }).then(function (response) {
      if (!response.ok) throw new Error('derived84_manifest_http_' + response.status);
      return response.json();
    }).then(validateDerived84Manifest).catch(function (error) {
      derived84ManifestPromise = null;
      throw error;
    });
    return derived84ManifestPromise;
  }

  function resolveFuture30AvatarPresentation(raw, manifestIndex) {
    var runtime = raw.character_runtime;
    var visualModelId = runtime.visual_model_id;
    var avatar = manifestIndex.avatarByVisual[visualModelId];
    var standing = manifestIndex.standingByVisual[visualModelId];
    if (!avatar || !standing) throw new Error('derived84_visual_identity_unmapped');
    return {
      id: raw.character_key || visualModelId,
      asset: avatar.path,
      avatarAsset: avatar.path,
      standingAsset: standing.path,
      fallbackAsset: '',
      presentationType: 'future30-derived84',
      characterKey: raw.character_key || null,
      visualModelId: visualModelId,
    };
  }

  function resolveAppearanceAsync(raw, doFetch) {
    if (!isFuture30Appearance(raw)) return Promise.resolve(normalizeAppearance(raw));
    return loadDerived84Manifest(doFetch).then(function (manifestIndex) {
      var presentation = resolveFuture30AvatarPresentation(raw, manifestIndex);
      return {
        avatarSrc: presentation.avatarAsset,
        avatarFallbackSrc: '',
        avatarPresentation: presentation,
      };
    });
  }

  /*
   * Narrow boundary for consumers that need the player's map presentation.
   * The catalog and its asset ownership stay private to this adapter. A
   * future character compositor can replace this provider while the World
   * Map continues to consume this resolved shape.
   */
  function resolveCurrentPlayerAvatarPresentation(raw) {
    var key = raw && typeof raw.character_key === 'string' ? raw.character_key.trim() : '';
    var resolved = CHARACTER_PRESENTATIONS[key] || CHARACTER_PRESENTATIONS[DEFAULT_CHARACTER_KEY];
    var fallback = CHARACTER_PRESENTATIONS[DEFAULT_CHARACTER_KEY];
    return {
      id: resolved.id,
      asset: resolved.asset,
      fallbackAsset: fallback.asset,
      presentationType: 'full-body-character',
    };
  }

  function normalizeAppearance(raw) {
    if (isFuture30Appearance(raw)) {
      return {
        avatarSrc: '',
        avatarFallbackSrc: '',
        avatarPresentation: {
          id: raw.character_key || raw.character_runtime.visual_model_id,
          asset: '',
          avatarAsset: '',
          standingAsset: '',
          fallbackAsset: '',
          presentationType: 'future30-derived84-unresolved',
        },
      };
    }
    var presentation = resolveCurrentPlayerAvatarPresentation(raw);
    return {
      avatarSrc: presentation.asset,
      avatarFallbackSrc: presentation.fallbackAsset,
      avatarPresentation: presentation,
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

  function defaultAvatarPresentationResult(kind, status) {
    return {
      ok: true,
      data: resolveCurrentPlayerAvatarPresentation({ character_key: DEFAULT_CHARACTER_KEY }),
      fallback: true,
      kind: kind || null,
      status: status || null,
    };
  }

  /**
   * Read only the committed appearance endpoint for consumers such as the
   * World Map. Preview/local-loadout state is deliberately not an input.
   * Missing or invalid committed character data resolves through the same
   * canonical default used by Character Appearance (apprentice).
   */
  function fetchAvatarPresentation(fetchImpl) {
    var doFetch = fetchImpl || (typeof fetch !== 'undefined' ? fetch : null);
    if (!doFetch) return Promise.resolve(defaultAvatarPresentationResult('network', null));

    return doFetch('/api/player/appearance', { credentials: 'same-origin' }).then(function (response) {
      if (!response.ok) return defaultAvatarPresentationResult(classifyHttpError(response.status), response.status);
      return response.json().then(function (raw) {
        if (!isFuture30Appearance(raw)) {
          return { ok: true, data: resolveCurrentPlayerAvatarPresentation(raw), fallback: false };
        }
        return loadDerived84Manifest(doFetch).then(function (manifestIndex) {
          return { ok: true, data: resolveFuture30AvatarPresentation(raw, manifestIndex), fallback: false };
        });
      }, function () {
        return defaultAvatarPresentationResult('error', response.status);
      });
    }, function () {
      return defaultAvatarPresentationResult('network', null);
    }).catch(function () {
      return { ok: false, kind: 'error', status: null };
    });
  }

  /**
   * fetchImpl is injectable so this file can be unit-tested under Node
   * without a real network/browser (see tests/e9_node_tests/).
   * Returns a Promise resolving to either:
   *   { ok: true, data: { name, level, coins, avatarSrc, avatarFallbackSrc, avatarPresentation } }
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
        return response.json().then(function (raw) {
          return resolveAppearanceAsync(raw, doFetch);
        }, function () { return normalizeAppearance(null); });
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
          avatarPresentation: appearance.avatarPresentation,
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
    resolveCurrentPlayerAvatarPresentation: resolveCurrentPlayerAvatarPresentation,
    fetchAvatarPresentation: fetchAvatarPresentation,
    fetchPlayerState: fetchPlayerState,
  };

  global.E9 = global.E9 || {};
  global.E9.Adapters = global.E9.Adapters || {};
  global.E9.Adapters.PlayerState = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : global);
