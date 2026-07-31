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
    if (!player || !player.parentNode) return;
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

  function setupNavigationShell(root, generation) {
    var registry = window.E9 && window.E9.NavigationRegistry;
    if (!registry || !registry.exactContract()) {
      root.querySelectorAll('[data-e10-vs1f-nav]').forEach(function (node) { node.remove(); });
      return;
    }
    root.setAttribute('data-e10-vs1f-nav', 'utility');
    var utilities = root.querySelector('[data-e10-utility-list]');
    var moreOverlay = root.querySelector('#e10-all-features-overlay');
    var settingsOverlay = root.querySelector('#e10-settings-overlay');
    var moreTrigger = null;
    var lastTrigger = null;
    var previousBodyOverflow = '';

    function makeControl(item, extraClass) {
      var control = document.createElement(item.target ? 'a' : 'button');
      control.className = 'e10-utility-control ' + (extraClass || '');
      control.setAttribute('data-e10-nav-key', item.key);
      control.setAttribute('data-e10-vs1f-nav', item.key);
      if (item.target) control.href = item.target;
      if (!item.target) control.type = 'button';
      if (item.command) {
        control.setAttribute('data-e10-command', item.command);
        control.setAttribute('aria-controls', 'e10-' + item.command + '-overlay');
        control.setAttribute('aria-expanded', 'false');
      }
      control.innerHTML = registry.icon(item.icon, 'e10-utility-icon') + '<span data-i18n="' + item.labelKey + '"></span>';
      return control;
    }

    function focusables(overlay) {
      return Array.prototype.slice.call(overlay.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])'));
    }

    function closeAll(restoreFocus) {
      moreOverlay.hidden = true;
      settingsOverlay.hidden = true;
      if (moreTrigger) moreTrigger.setAttribute('aria-expanded', 'false');
      root.querySelectorAll('[data-e10-command="settings"]').forEach(function (control) { control.setAttribute('aria-expanded', 'false'); });
      document.body.style.overflow = previousBodyOverflow;
      if (restoreFocus && lastTrigger && document.contains(lastTrigger)) lastTrigger.focus();
    }

    function openOverlay(overlay, trigger, returnTrigger) {
      closeAll(false);
      lastTrigger = returnTrigger || trigger;
      previousBodyOverflow = document.body.style.overflow;
      overlay.hidden = false;
      if (trigger && trigger.getAttribute('aria-expanded') !== null) trigger.setAttribute('aria-expanded', 'true');
      document.body.style.overflow = 'hidden';
      var targets = focusables(overlay);
      if (targets.length) targets[0].focus();
    }

    function onDialogKey(event) {
      var overlay = !moreOverlay.hidden ? moreOverlay : (!settingsOverlay.hidden ? settingsOverlay : null);
      if (!overlay) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        closeAll(true);
        return;
      }
      if (event.key !== 'Tab') return;
      var targets = focusables(overlay);
      if (!targets.length) return;
      var first = targets[0];
      var last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }

    registry.itemsFor('utility').forEach(function (item) {
      var control = makeControl(item);
      utilities.appendChild(control);
      if (item.command === 'settings') window.E9.on(control, 'click', function () { openOverlay(settingsOverlay, control); }, null, generation);
    });
    moreTrigger = document.createElement('button');
    moreTrigger.type = 'button';
    moreTrigger.className = 'e10-utility-control e10-more-trigger';
    moreTrigger.setAttribute('data-e10-vs1f-nav', 'more');
    moreTrigger.setAttribute('aria-controls', 'e10-all-features-overlay');
    moreTrigger.setAttribute('aria-expanded', 'false');
    moreTrigger.innerHTML = registry.icon('compass', 'e10-utility-icon') + '<span data-i18n="e10.nav.all_features"></span>';
    utilities.appendChild(moreTrigger);

    registry.itemsFor('more').forEach(function (item) {
      var control = makeControl(item, 'e10-more-item');
      root.querySelector('[data-e10-more-list]').appendChild(control);
      if (item.command === 'settings') window.E9.on(control, 'click', function () { openOverlay(settingsOverlay, control, moreTrigger); }, null, generation);
    });
    window.E9.on(moreTrigger, 'click', function () {
      openOverlay(moreOverlay, moreTrigger);
      moreTrigger.setAttribute('aria-expanded', 'true');
    }, null, generation);
    root.querySelectorAll('[data-e10-dialog-close]').forEach(function (button) {
      window.E9.on(button, 'click', function () { closeAll(true); }, null, generation);
    });
    window.E9.on(document, 'keydown', onDialogKey, null, generation);
    window.E9.on(document, 'e9:adventure-command', function () { closeAll(false); }, null, generation);
    window.E9.registerCleanup(function () { closeAll(false); }, generation);

    var language = root.querySelector('#e10-settings-language');
    if (language && window.I18n && window.I18n.renderSwitcher) window.I18n.renderSwitcher(language);
    var sound = root.querySelector('#e10-settings-sound');
    if (sound && window.SFX) {
      sound.checked = !window.SFX.muted;
      window.E9.on(sound, 'change', function () { window.SFX.muted = !sound.checked; }, null, generation);
    } else if (sound && sound.parentNode) {
      sound.parentNode.hidden = true;
    }
    if (window.I18n && window.I18n.apply) window.I18n.apply();
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');
    applyVs1fBrand(root);
    setupNavigationShell(root, generation);

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
