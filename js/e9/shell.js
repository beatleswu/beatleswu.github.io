/*
 * E9 Adventure Shell — orchestrator.
 *
 * Responsible for: reading flags, toggling legacy vs. E9 visibility,
 * kicking off loadComponent() for each slot, and recovering to legacy on
 * a CRITICAL failure. Per-component DOM logic lives in each component's
 * own init script, wired via the "e9:component-loaded" event.
 *
 * Critical vs non-critical (E9.1A2 contract):
 *   Critical:     shell orchestration itself (this file), World Stage.
 *   Non-critical: Top HUD, Right Cards, Bottom Dock, Left Navigation.
 * A non-critical component failure only renders that component's own
 * fallback (handled inside component_loader.js) and never touches
 * anything else. A critical failure (World Stage fails to load, or this
 * file throws for any reason) triggers full recovery: hide E9, restore
 * Legacy, no reload, no uncaught pageerror.
 *
 * Flag OFF is a complete no-op — no fragment fetches happen at all, and
 * the legacy #skill-map section is left exactly as it was.
 */
(function (global, document) {
  'use strict';

  var CRITICAL_SLOT = {
    flag: 'e9WorldStage', component: 'world_stage', selector: '#e9-world-stage-slot',
    src: '/components/adventure/world_stage.html'
  };

  var NON_CRITICAL_SLOTS = [
    { flag: 'e9TopHud', component: 'top_hud', selector: '#e9-top-hud-slot', src: '/components/adventure/top_hud.html' },
    { flag: 'e9LeftNav', component: 'left_nav', selector: '#e9-left-nav-slot', src: '/components/adventure/left_nav.html' },
    { flag: 'e9RightCards', component: 'right_cards', selector: '#e9-right-cards-slot', src: '/components/adventure/right_cards.html' },
    { flag: 'e9BottomDock', component: 'bottom_dock', selector: '#e9-bottom-dock-slot', src: '/components/adventure/bottom_dock.html' }
  ];

  var LEGACY_SELECTOR = '#skill-map';
  var SHELL_SELECTOR = '#e9-adventure-shell';

  function legacyEl() { return document.querySelector(LEGACY_SELECTOR); }
  function shellEl() { return document.querySelector(SHELL_SELECTOR); }

  function showE9Shell() {
    var shell = shellEl();
    if (shell) {
      shell.hidden = false;
      shell.removeAttribute('aria-hidden');
    }
  }

  function hideE9Shell() {
    var shell = shellEl();
    if (shell) {
      shell.hidden = true;
      shell.setAttribute('aria-hidden', 'true');
    }
  }

  function hideLegacyAdventure() {
    var legacy = legacyEl();
    if (legacy) legacy.hidden = true;
  }

  function showLegacyAdventure() {
    var legacy = legacyEl();
    if (legacy) legacy.hidden = false;
  }

  /**
   * Recovery path for a critical failure. No reload, no further fragment
   * requests, no uncaught error — just fall back to the legacy UI.
   */
  function recoverToLegacy(err) {
    console.error('[E9] critical failure — recovering to legacy Adventure:', err);
    try {
      var statusEl = document.querySelector('#e9-world-stage-slot');
      if (statusEl && global.I18n && typeof global.I18n.t === 'function') {
        // Best-effort: if the shell is still momentarily visible, show a
        // translated notice before we hide it. Not required to succeed.
        statusEl.setAttribute('aria-label', global.I18n.t('e9.shell.critical_error'));
      }
    } catch (labelErr) {
      // ignore — purely cosmetic best-effort
    }
    hideE9Shell();
    showLegacyAdventure();
  }

  function mountSlot(slot) {
    var root = document.querySelector(slot.selector);
    if (!root) return Promise.resolve(false); // slot not present on this page
    if (!global.E9 || typeof global.E9.loadComponent !== 'function') {
      return Promise.resolve(false);
    }
    return global.E9.loadComponent(slot.component, root, slot.src);
  }

  function init() {
    var flags;
    try {
      if (!global.E9 || typeof global.E9.getFlags !== 'function') {
        console.error('[E9] feature_flags.js did not load before shell.js — E9 shell stays off');
        return;
      }
      flags = global.E9.getFlags();
      if (!flags.e9Shell) {
        return; // no-op: legacy stays exactly as-is, zero fragment requests
      }

      hideLegacyAdventure();
      showE9Shell();
    } catch (err) {
      recoverToLegacy(err);
      return;
    }

    // World Stage is critical: await it before mounting anything else, and
    // recover to legacy if it fails.
    var worldStagePromise = flags[CRITICAL_SLOT.flag]
      ? mountSlot(CRITICAL_SLOT)
      : Promise.resolve(true); // flag off for this slot alone isn't a failure

    worldStagePromise.then(function (ok) {
      if (flags[CRITICAL_SLOT.flag] && !ok) {
        recoverToLegacy(new Error('critical component "world_stage" failed to load'));
        return;
      }

      // Non-critical slots mount independently; each isolates its own
      // failure via component_loader.js's fallback rendering.
      NON_CRITICAL_SLOTS.forEach(function (slot) {
        if (flags[slot.flag]) {
          try {
            mountSlot(slot);
          } catch (slotErr) {
            console.error('[E9] non-critical slot threw synchronously (unexpected):', slot.component, slotErr);
          }
        }
      });
    }).catch(function (err) {
      // mountSlot's promise should never reject (component_loader.js
      // catches internally), but guard anyway — a critical-path failure
      // here must still recover to legacy, not surface as pageerror.
      recoverToLegacy(err);
    });
  }

  /**
   * Thin adapter to the existing canonical Adventure Start flow.
   * Never re-implements zone-entry logic — only calls the legacy global
   * function that already exists on this page.
   */
  function startAdventureFromE9(zoneKey) {
    if (typeof global.startAdventureStage !== 'function') {
      var err = new Error('Legacy startAdventureStage() is unavailable');
      console.error('[E9]', err.message);
      throw err;
    }
    global.startAdventureStage(zoneKey);
  }

  global.E9 = global.E9 || {};
  global.E9.startAdventureFromE9 = startAdventureFromE9;
  // Exposed so world_stage.js (the critical component) can trigger full
  // recovery if it successfully mounted its HTML fragment but then fails
  // to load real adventure data — a World Stage that can't show real
  // state is as broken as one whose fragment 404'd.
  global.E9.recoverToLegacy = recoverToLegacy;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window, document);
