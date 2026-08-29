/*
 * A040 legacy Hero cache boundary.
 *
 * This helper is deliberately storage-only. It never knows ownership,
 * equipped state, slots, effects, or combat values. Once a server-owned
 * character/equipment snapshot exists, callers can retain only the legacy
 * character compatibility hint and discard every old equipment key.
 */
(function (global) {
  'use strict';

  const FUNCTIONAL_CACHE_FIELDS = Object.freeze([
    'armor', 'cape', 'weapon', 'offhand', 'hat', 'pet', 'aura', 'acc',
  ]);

  function parse(raw) {
    if (typeof raw !== 'string' || !raw.trim()) return {};
    try {
      const value = JSON.parse(raw);
      return value && typeof value === 'object' && !Array.isArray(value)
        ? value
        : {};
    } catch (_) {
      return {};
    }
  }

  function characterOnly(raw, validCharacters, fallback = 'apprentice') {
    const value = parse(raw);
    const valid = validCharacters instanceof Set
      ? validCharacters
      : new Set(Array.isArray(validCharacters) ? validCharacters : []);
    const candidate = typeof value.character === 'string' ? value.character.trim() : '';
    return valid.has(candidate) ? candidate : fallback;
  }

  function discardFunctionalEquipment(storage, key, serverCharacter, validCharacters, fallback = 'apprentice') {
    const character = characterOnly(
      JSON.stringify({ character: serverCharacter }),
      validCharacters,
      fallback,
    );
    try {
      if (storage && typeof storage.setItem === 'function') {
        storage.setItem(key, JSON.stringify({ character }));
      }
    } catch (_) {
      // Storage can be unavailable in privacy mode; the in-memory server
      // projection remains authoritative and the cache is simply ignored.
    }
    return { character, discardedFields: FUNCTIONAL_CACHE_FIELDS.slice() };
  }

  global.GoOdysseyLegacyHeroCache = Object.freeze({
    FUNCTIONAL_CACHE_FIELDS,
    parse,
    characterOnly,
    discardFunctionalEquipment,
  });
})(typeof window !== 'undefined' ? window : globalThis);
