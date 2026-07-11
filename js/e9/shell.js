/*
 * E9 Adventure Shell — orchestrator.
 *
 * Responsible only for: reading flags, toggling legacy vs. E9 visibility,
 * and kicking off loadComponent() for each slot. Contains no per-component
 * DOM logic — that lives in each component's own init script, wired via
 * the "e9:component-loaded" event dispatched by component_loader.js.
 *
 * Runs once on DOMContentLoaded. If E9.getFlags().e9Shell is false, this
 * is a complete no-op — nothing on the host page is touched. This is what
 * makes the flag a true, low-risk rollback switch once this is wired into
 * a real page (E9.1A2); on a standalone demo page with no legacy section,
 * hideLegacyAdventure() simply finds nothing and does nothing.
 */
(function (global, document) {
  'use strict';

  var SLOTS = [
    { flag: 'e9TopHud', component: 'top_hud', selector: '#e9-top-hud-slot', src: '/components/adventure/top_hud.html' },
    { flag: 'e9LeftNav', component: 'left_nav', selector: '#e9-left-nav-slot', src: '/components/adventure/left_nav.html' },
    { flag: 'e9WorldStage', component: 'world_stage', selector: '#e9-world-stage-slot', src: '/components/adventure/world_stage.html' },
    { flag: 'e9RightCards', component: 'right_cards', selector: '#e9-right-cards-slot', src: '/components/adventure/right_cards.html' },
    { flag: 'e9BottomDock', component: 'bottom_dock', selector: '#e9-bottom-dock-slot', src: '/components/adventure/bottom_dock.html' }
  ];

  var LEGACY_SELECTOR = '#skill-map';
  var SHELL_SELECTOR = '#e9-adventure-shell';

  function showE9Shell() {
    var shell = document.querySelector(SHELL_SELECTOR);
    if (shell) shell.hidden = false;
  }

  function hideLegacyAdventure() {
    var legacy = document.querySelector(LEGACY_SELECTOR);
    if (legacy) legacy.hidden = true;
  }

  function mountSlot(slot) {
    var root = document.querySelector(slot.selector);
    if (!root) {
      // Slot markup not present on this page — not an error, just means
      // this page hasn't adopted the E9 shell block. Skip quietly.
      return;
    }
    if (!global.E9 || typeof global.E9.loadComponent !== 'function') {
      console.error('[E9] component_loader.js did not load before shell.js — skipping', slot.component);
      return;
    }
    global.E9.loadComponent(slot.component, root, slot.src);
  }

  function init() {
    try {
      if (!global.E9 || typeof global.E9.getFlags !== 'function') {
        console.error('[E9] feature_flags.js did not load before shell.js — E9 shell stays off');
        return;
      }
      var flags = global.E9.getFlags();
      if (!flags.e9Shell) {
        return; // no-op: legacy stays exactly as-is
      }

      hideLegacyAdventure();
      showE9Shell();

      SLOTS.forEach(function (slot) {
        if (flags[slot.flag]) {
          mountSlot(slot);
        }
      });
    } catch (err) {
      // Never let a shell-init failure surface as an uncaught pageerror or
      // take down the rest of the page (Practice / Adventure Start etc.).
      console.error('[E9] shell init failed, leaving legacy Adventure Map active:', err);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window, document);
