/*
 * E9 Right Cards — component init (non-critical).
 * Operates only on its own root. Each card fetches independently via
 * js/e9/adapters/activity_state.js and fails independently -- one card
 * erroring never blocks the others. Real data sources only (no new API,
 * no fabricated numbers):
 *   GET /api/daily-challenge/today
 *   GET /api/adventure/bootstrap  -> zones[] (boss progress summary)
 *   GET /api/srs/due              -> {due:[], count}
 *   GET /api/mistakes/stats       -> {total, corrected, worst5}
 */
(function (document) {
  'use strict';

  function t(key, fallback) {
    if (window.E9 && window.E9.I18nFallback && typeof window.E9.I18nFallback.t === 'function') {
      return window.E9.I18nFallback.t(key, fallback);
    }
    return fallback;
  }

  function setBody(root, cardKey, text) {
    var el = root.querySelector('[data-e9-card-body="' + cardKey + '"]');
    if (!el) return;
    el.textContent = text;
    // Each card body starts with a static data-i18n="e9.right_cards.loading"
    // placeholder. Remove it once real content/empty/error text is set, so
    // a later, unrelated I18n.apply() elsewhere on the page cannot silently
    // revert it back to "Loading…" (see js/e9/top_hud.js for the same fix
    // and the live-verified regression this addresses).
    el.removeAttribute('data-i18n');
  }

  function errorTextFor(cardKey, result) {
    if (result.kind === 'unauthorized') return t('e9.right_cards.unauthorized', 'Please log in again');
    return t('e9.right_cards.error', 'Unavailable');
  }

  function loadDailyChallenge(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'daily_challenge', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchDailyChallenge().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'daily_challenge', errorTextFor('daily_challenge', result));
        return;
      }
      var text = result.data.submitted
        ? t('e9.right_cards.daily_challenge_done', 'Completed today')
        : t('e9.right_cards.daily_challenge_available', 'Available now');
      setBody(root, 'daily_challenge', text);
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards daily_challenge fetch failed (non-critical):', err);
      setBody(root, 'daily_challenge', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function loadBossProgress(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'boss_progress', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchBossProgress().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'boss_progress', errorTextFor('boss_progress', result));
        return;
      }
      var d = result.data;
      if (!d.total) {
        setBody(root, 'boss_progress', t('e9.right_cards.empty', 'No data yet'));
        return;
      }
      setBody(root, 'boss_progress', t('index.adv.summary', '{n} / {t} areas cleared')
        .replace('{n}', d.cleared).replace('{t}', d.total));
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards boss_progress fetch failed (non-critical):', err);
      setBody(root, 'boss_progress', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function loadSrsDue(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'srs_due', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchSrsDue().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'srs_due', errorTextFor('srs_due', result));
        return;
      }
      var count = result.data.count;
      setBody(root, 'srs_due', count !== null && count > 0 ? String(count) : t('e9.right_cards.empty', 'No data yet'));
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards srs_due fetch failed (non-critical):', err);
      setBody(root, 'srs_due', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function loadWeakness(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'weakness', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchMistakes().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'weakness', errorTextFor('weakness', result));
        return;
      }
      var total = result.data.total;
      setBody(root, 'weakness', total !== null && total > 0 ? String(total) : t('e9.right_cards.empty', 'No data yet'));
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards weakness fetch failed (non-critical):', err);
      setBody(root, 'weakness', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');

    var current = function () {
      return !window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation);
    };
    loadDailyChallenge(root, current);
    loadBossProgress(root, current);
    loadSrsDue(root, current);
    loadWeakness(root, current);
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'right_cards') {
      init(e.detail.root, e.detail.generation);
    }
  });
})(document);
