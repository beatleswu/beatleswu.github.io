/*
 * E9 Top HUD — component init (non-critical).
 * Operates only on its own root. Real data sources only:
 *   GET /api/skills/profile -> display_name, rank_level
 *   GET /api/user/coins     -> coins
 * No Stars/HP/SP here by design (see components/adventure/top_hud.html).
 * A fetch failure shows a translated error state, never a fabricated
 * number, and never affects any other component.
 */
(function (document) {
  'use strict';

  function applyText(el, text) {
    if (el) el.textContent = text;
  }

  function t(key, fallback) {
    if (window.I18n && typeof window.I18n.t === 'function') {
      var val = window.I18n.t(key);
      return val || fallback;
    }
    return fallback;
  }

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');

    var nameEl = root.querySelector('#top-hud-name');
    var levelWrap = root.querySelector('#top-hud-level');
    var levelValueEl = root.querySelector('#top-hud-level-value');
    var coinsEl = root.querySelector('#top-hud-coins');

    Promise.all([
      fetch('/api/skills/profile', { credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) throw new Error('profile HTTP ' + r.status);
        return r.json();
      }),
      fetch('/api/user/coins', { credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) throw new Error('coins HTTP ' + r.status);
        return r.json();
      })
    ]).then(function (results) {
      var profile = results[0] || {};
      var coinsRes = results[1] || {};

      applyText(nameEl, profile.display_name || t('e9.top_hud.error', 'Player status unavailable'));

      if (profile.rank_level) {
        if (levelValueEl) levelValueEl.textContent = profile.rank_level;
        if (levelWrap) levelWrap.hidden = false;
      }

      if (typeof coinsRes.coins === 'number') {
        if (coinsEl) {
          coinsEl.textContent = '🪙 ' + coinsRes.coins.toLocaleString();
          coinsEl.hidden = false;
        }
      }
    }).catch(function (err) {
      console.error('[E9] top_hud data fetch failed (non-critical):', err);
      applyText(nameEl, t('e9.top_hud.error', 'Player status unavailable'));
    });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'top_hud') {
      init(e.detail.root);
    }
  });
})(document);
