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

  var VS1F_STATIC_CONTRACT = 'e10-vs1f-integrated-world-map';

  function applyVs1fBrand(root) {
    var marker = document.querySelector('meta[name="go-odyssey-static-contract"]');
    if (!marker || marker.getAttribute('content') !== VS1F_STATIC_CONTRACT) return;
    var player = root.querySelector('.e9-hud__player');
    var avatar = root.querySelector('#top-hud-avatar');
    if (!player || !player.parentNode) return;
    if (avatar) avatar.remove();
    var brand = document.createElement('div');
    brand.className = 'e10-hud-brand';
    brand.setAttribute('data-e10-vs1f-brand', '');
    brand.innerHTML = '<svg class="e10-hud-brand__crest" viewBox="0 0 48 56" aria-hidden="true" focusable="false">'
      + '<path d="M24 2 44 10v15c0 13-8 23-20 29C12 48 4 38 4 25V10Z"/>'
      + '<circle cx="19" cy="25" r="8"/><circle cx="29" cy="31" r="8"/></svg>'
      + '<span class="e10-hud-brand__copy"><strong data-i18n="common.brand">Go Odyssey</strong>'
      + '<span data-i18n="e10.rpg.world_stage_label">World Stage</span></span>';
    player.parentNode.insertBefore(brand, player);
    if (window.I18n && typeof window.I18n.apply === 'function') window.I18n.apply(brand);
  }

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
    if (window.E9 && window.E9.I18nFallback && typeof window.E9.I18nFallback.t === 'function') {
      return window.E9.I18nFallback.t(key, fallback);
    }
    return fallback;
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');
    applyVs1fBrand(root);

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

    var current = function () {
      return !window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation);
    };
    adapter.fetchPlayerState().then(function (result) {
      if (!current()) return;
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
          var formattedCoins = data.coins.toLocaleString();
          coinsEl.textContent = formattedCoins;
          coinsEl.setAttribute(
            'aria-label',
            t('e10.rpg.coins_label', '{n} coins').replace('{n}', formattedCoins)
          );
          coinsEl.hidden = false;
        }
      }
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] top_hud data fetch failed (non-critical):', err);
      applyText(nameEl, t('e9.top_hud.error', 'Player status unavailable'));
    });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'top_hud') {
      init(e.detail.root, e.detail.generation);
    }
  });
})(document);
