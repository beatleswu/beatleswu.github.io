/*
 * E9 Top HUD — component init (non-critical).
 * Reads canonical player state via js/e9/adapters/player_state.js (single
 * source of truth -- no second copy of name/level/coins is ever stored
 * here). Real data sources only:
 *   GET /api/skills/profile -> display_name, rank_level
 *   GET /api/user/coins     -> coins
 * No Stars/HP/SP here by design (see components/adventure/top_hud.html).
 * A fetch failure shows a translated error/unauthorized state, never a
 * fabricated number, and never affects any other component.
 */
(function (document) {
  'use strict';

  function applyText(el, text) {
    if (!el) return;
    el.textContent = text;
    // This element (e.g. #top-hud-name) starts with a static data-i18n
    // loading placeholder. Once JS has set its real content (player name
    // or a translated error), the attribute must go -- otherwise any LATER,
    // unrelated I18n.apply() call elsewhere on the page (site-nav.js,
    // a language switch, etc.) would silently re-rescan the whole document
    // and revert this element back to "Loading…" forever, since
    // data-e9-inited already blocks re-fetching. Live-verified regression
    // during E9.1A2 Rev2 browser verification.
    el.removeAttribute('data-i18n');
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

    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.PlayerState;
    if (!adapter) {
      console.error('[E9] top_hud: PlayerState adapter not loaded');
      applyText(nameEl, t('e9.top_hud.error', 'Player status unavailable'));
      return;
    }

    adapter.fetchPlayerState().then(function (result) {
      if (!result.ok) {
        if (result.kind === 'unauthorized') {
          applyText(nameEl, t('e9.top_hud.unauthorized', 'Please log in again'));
        } else {
          applyText(nameEl, t('e9.top_hud.error', 'Player status unavailable'));
        }
        return;
      }

      var data = result.data;
      applyText(nameEl, data.name || t('e9.top_hud.error', 'Player status unavailable'));

      // level is a plain number (adapter already stripped the 'LV' prefix
      // from rank_level) -- rendered next to the existing "Lv." label, so
      // this never produces a doubled "Lv. LV12".
      if (data.level !== null) {
        if (levelValueEl) levelValueEl.textContent = String(data.level);
        if (levelWrap) levelWrap.hidden = false;
      }

      if (data.coins !== null) {
        if (coinsEl) {
          coinsEl.textContent = '🪙 ' + data.coins.toLocaleString();
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
