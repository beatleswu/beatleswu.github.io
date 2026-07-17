/*
 * E9 Adventure Shell -- orchestrator.
 *
 * Responsible for: reading flags, enforcing exclusive legacy vs. E9
 * shell ownership, kicking off loadComponent() for each slot, and
 * recovering to legacy on a CRITICAL failure.
 *
 * Flag OFF is a complete no-op for E9 runtime work: no fragment fetches,
 * no component init, legacy remains the only visible/interactive shell.
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

  var LEGACY_SELECTORS = [
    '#welcome-state > .guild-hall-hero',
    '#welcome-state > .guild-entry-grid',
    '#skill-map',
    '#welcome-state > .home-left-col',
    '#welcome-state > .home-report'
  ];
  var SHELL_SELECTOR = '#e9-adventure-shell';
  var FOCUSABLE_SELECTOR = [
    'a[href]',
    'area[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    'iframe',
    '[tabindex]',
    '[contenteditable="true"]'
  ].join(',');

  var activeShellState = null;
  var mountStarted = false;

  function shellEl() {
    return document.querySelector(SHELL_SELECTOR);
  }

  function legacyEls() {
    var seen = [];
    LEGACY_SELECTORS.forEach(function (selector) {
      document.querySelectorAll(selector).forEach(function (el) {
        if (seen.indexOf(el) === -1) seen.push(el);
      });
    });
    return seen;
  }

  function focusableEls(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return [];
    return Array.prototype.slice.call(root.querySelectorAll(FOCUSABLE_SELECTOR)).filter(function (el) {
      if (!el || el.hidden || el.getAttribute('aria-hidden') === 'true') return false;
      if (el.tabIndex < 0) return false;
      return true;
    });
  }

  function rootsContainNode(roots, node) {
    if (!node) return false;
    return roots.some(function (root) {
      return root === node || (root && typeof root.contains === 'function' && root.contains(node));
    });
  }

  function suspendTabbing(root) {
    focusableEls(root).forEach(function (el) {
      if (!el.hasAttribute('data-e9-prev-tabindex')) {
        el.setAttribute('data-e9-prev-tabindex', el.getAttribute('tabindex') || '');
      }
      el.setAttribute('tabindex', '-1');
    });
  }

  function restoreTabbing(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return;
    root.querySelectorAll('[data-e9-prev-tabindex]').forEach(function (el) {
      var prev = el.getAttribute('data-e9-prev-tabindex');
      if (prev === '') {
        el.removeAttribute('tabindex');
      } else {
        el.setAttribute('tabindex', prev);
      }
      el.removeAttribute('data-e9-prev-tabindex');
    });
  }

  function setRootState(root, active) {
    if (!root) return;
    root.setAttribute('data-shell-active', active ? 'true' : 'false');
    if (active) {
      root.hidden = false;
      root.removeAttribute('aria-hidden');
      root.removeAttribute('inert');
      root.removeAttribute('data-shell-hidden');
      restoreTabbing(root);
      return;
    }
    suspendTabbing(root);
    root.setAttribute('aria-hidden', 'true');
    root.setAttribute('inert', '');
    root.setAttribute('data-shell-hidden', 'true');
    root.hidden = true;
  }

  function firstFocusableInRoots(roots) {
    for (var i = 0; i < roots.length; i++) {
      var focusables = focusableEls(roots[i]);
      if (focusables.length) return focusables[0];
    }
    return null;
  }

  function resolveRequestedShellMode(flags) {
    if (!flags || !flags.e9Shell) return 'legacy';
    return global.__GO_E9_ACTIVE_SHELL__ === 'e9' ? 'e9' : 'legacy';
  }

  function applyShellState(nextState) {
    var mode = nextState === 'e9' ? 'e9' : 'legacy';
    var legacyRoots = legacyEls();
    var e9Root = shellEl();
    var currentActive = document.activeElement;
    var hidingRoots = mode === 'e9' ? legacyRoots : (e9Root ? [e9Root] : []);
    var focusNeedsMove = rootsContainNode(hidingRoots, currentActive);

    legacyRoots.forEach(function (root) { setRootState(root, mode === 'legacy'); });
    setRootState(e9Root, mode === 'e9');

    document.body.setAttribute('data-adventure-shell-active', mode);
    activeShellState = mode;

    if (focusNeedsMove) {
      var activeRoots = mode === 'e9' ? (e9Root ? [e9Root] : []) : legacyRoots;
      var fallbackTarget = firstFocusableInRoots(activeRoots);
      if (fallbackTarget && typeof fallbackTarget.focus === 'function') {
        try {
          fallbackTarget.focus({ preventScroll: true });
        } catch (focusErr) {
          fallbackTarget.focus();
        }
      } else if (document.body && typeof document.body.focus === 'function') {
        document.body.focus();
      }
    }

    return mode;
  }

  function recoverToLegacy(err) {
    console.error('[E9] critical failure -- recovering to legacy Adventure:', err);
    global.__GO_E9_ACTIVE_SHELL__ = 'legacy';
    try {
      var statusEl = document.querySelector('#e9-world-stage-slot');
      if (statusEl && global.E9 && global.E9.I18nFallback && typeof global.E9.I18nFallback.t === 'function') {
        statusEl.setAttribute('aria-label', global.E9.I18nFallback.t(
          'e9.shell.critical_error', 'A critical error occurred. Returning to Adventure Map.'
        ));
      }
    } catch (labelErr) {
      // cosmetic best-effort only
    }
    applyShellState('legacy');
    var mapReadiness = Promise.resolve(false);
    try {
      if (typeof global.ensureLegacyHomeAmbientState === 'function') {
        global.ensureLegacyHomeAmbientState({ immediate: true, reason: 'e9-critical-fallback' });
      }
    } catch (restoreErr) {
      console.error('[E9] failed to restore legacy ambient ownership after critical fallback:', restoreErr);
    }
    try {
      if (typeof global.ensureLegacyAdventureMapReady === 'function') {
        mapReadiness = Promise.resolve(global.ensureLegacyAdventureMapReady({ reuseE9Adapter: true }));
      }
    } catch (mapRestoreErr) {
      mapReadiness = Promise.reject(mapRestoreErr);
    }
    return mapReadiness.catch(function (mapRestoreErr) {
      console.error('[E9] failed to restore Legacy Adventure Map readiness after critical fallback:', mapRestoreErr);
      return false;
    });
  }

  function mountSlot(slot) {
    var root = document.querySelector(slot.selector);
    if (!root) return Promise.resolve(false);
    if (!global.E9 || typeof global.E9.loadComponent !== 'function') {
      return Promise.resolve(false);
    }
    return global.E9.loadComponent(slot.component, root, slot.src);
  }

  function init() {
    var flags;
    var requestedMode;
    try {
      if (!global.E9 || typeof global.E9.getFlags !== 'function') {
        console.error('[E9] feature_flags.js did not load before shell.js -- E9 shell stays off');
        applyShellState('legacy');
        return;
      }
      flags = global.E9.getFlags();
      requestedMode = resolveRequestedShellMode(flags);
      applyShellState(requestedMode);
      if (requestedMode !== 'e9') {
        return;
      }
    } catch (err) {
      recoverToLegacy(err);
      return;
    }

    if (mountStarted) return;
    mountStarted = true;

    var worldStagePromise = flags[CRITICAL_SLOT.flag]
      ? mountSlot(CRITICAL_SLOT)
      : Promise.resolve(true);

    worldStagePromise.then(function (ok) {
      if (flags[CRITICAL_SLOT.flag] && !ok) {
        recoverToLegacy(new Error('critical component "world_stage" failed to load'));
        return;
      }

      NON_CRITICAL_SLOTS.forEach(function (slot) {
        if (!flags[slot.flag]) return;
        try {
          mountSlot(slot);
        } catch (slotErr) {
          console.error('[E9] non-critical slot threw synchronously:', slot.component, slotErr);
        }
      });
    }).catch(function (err) {
      recoverToLegacy(err);
    });
  }

  function startAdventureFromE9(zoneKey) {
    try {
      if (new URLSearchParams(global.location.search || '').get('e9verify') === 'c3-1-trace') {
        console.info('[E9:C3.1] canonical-entry-owner ' + JSON.stringify({
          zone: zoneKey,
          startAvailable: typeof global.startAdventureStage === 'function',
          path: global.location.pathname,
        }));
      }
    } catch (traceErr) {}
    if (typeof global.startAdventureStage !== 'function') {
      // Keep the existing Adventure route as a governed fail-safe when the
      // legacy inline entry symbol is unavailable during shell handoff.
      global.location.href = '/?zone=' + encodeURIComponent(zoneKey) + '&adventure=1&resume=1';
      return;
    }
    global.startAdventureStage(zoneKey);
  }

  global.E9 = global.E9 || {};
  global.E9.startAdventureFromE9 = startAdventureFromE9;
  global.E9.recoverToLegacy = recoverToLegacy;
  global.E9.applyShellState = applyShellState;
  global.E9.getActiveShell = function () { return activeShellState || 'legacy'; };
  global.E9.resolveRequestedShellMode = resolveRequestedShellMode;
  global.E9.__getLegacyShellRoots = legacyEls;
  global.E9.initShell = init;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window, document);
