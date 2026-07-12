/*
 * E9 Right Cards — component init (non-critical).
 * Operates only on its own root. Each card fetches independently and
 * fails independently — one card erroring never blocks the others.
 * Real data sources only (no new API, no fabricated numbers):
 *   GET /api/daily-challenge/today
 *   GET /api/adventure/bootstrap  -> zones[] (boss progress summary)
 *   GET /api/srs/due              -> {due:[], count}
 *   GET /api/mistakes/stats       -> {total, corrected, worst5}
 */
(function (document) {
  'use strict';

  function t(key, fallback) {
    if (window.I18n && typeof window.I18n.t === 'function') {
      var val = window.I18n.t(key);
      return val || fallback;
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

  function loadDailyChallenge(root) {
    fetch('/api/daily-challenge/today', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function () {
        setBody(root, 'daily_challenge', t('index.ws.bounty_desk', 'Daily Challenge available'));
      })
      .catch(function (err) {
        console.error('[E9] right_cards daily_challenge fetch failed (non-critical):', err);
        setBody(root, 'daily_challenge', t('e9.right_cards.empty', 'No data yet'));
      });
  }

  function loadBossProgress(root) {
    fetch('/api/adventure/bootstrap', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        var zones = (data && data.zones) || [];
        if (!zones.length) {
          setBody(root, 'boss_progress', t('e9.right_cards.empty', 'No data yet'));
          return;
        }
        var cleared = zones.filter(function (z) { return z.status === 'completed'; }).length;
        setBody(root, 'boss_progress', t('index.adv.summary', '{n} / {t} areas cleared')
          .replace('{n}', cleared).replace('{t}', zones.length));
      })
      .catch(function (err) {
        console.error('[E9] right_cards boss_progress fetch failed (non-critical):', err);
        setBody(root, 'boss_progress', t('e9.right_cards.error', 'Unavailable'));
      });
  }

  function loadSrsDue(root) {
    fetch('/api/srs/due', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        var count = (data && typeof data.count === 'number') ? data.count : 0;
        setBody(root, 'srs_due', count > 0 ? String(count) : t('e9.right_cards.empty', 'No data yet'));
      })
      .catch(function (err) {
        console.error('[E9] right_cards srs_due fetch failed (non-critical):', err);
        setBody(root, 'srs_due', t('e9.right_cards.error', 'Unavailable'));
      });
  }

  function loadWeakness(root) {
    fetch('/api/mistakes/stats', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        var total = (data && typeof data.total === 'number') ? data.total : 0;
        setBody(root, 'weakness', total > 0 ? String(total) : t('e9.right_cards.empty', 'No data yet'));
      })
      .catch(function (err) {
        console.error('[E9] right_cards weakness fetch failed (non-critical):', err);
        setBody(root, 'weakness', t('e9.right_cards.error', 'Unavailable'));
      });
  }

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');

    loadDailyChallenge(root);
    loadBossProgress(root);
    loadSrsDue(root);
    loadWeakness(root);
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'right_cards') {
      init(e.detail.root);
    }
  });
})(document);
