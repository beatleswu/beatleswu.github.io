/*
 * W1_03_JOURNEY_ZONE3_VERTICAL_SLICE_WIRING_002
 *
 * Thin view adapter. It owns no transport and never starts a Lord Trial or
 * navigation on its own. A user CTA is first accepted as an explicit
 * presentation action, then handed to the existing shell/index bridge.
 */
(function (global, document) {
  'use strict';

  if (!document || !global.GoOdysseyJourneyZone3 || !global.GoOdysseyJourneyZone3Content) return;

  var content = global.GoOdysseyJourneyZone3Content;
  var COMPONENT = 'zone3_vertical_slice';
  var EVENT = 'journey:zone3-event';
  var COMMAND = 'journey:zone3-command';

  var COPY_BY_PHASE = {
    ENTRY_PENDING: 'e9.zone3.entry_pending',
    ENTRY_CINEMATIC: 'e9.zone3.entry_cinematic',
    GAMEPLAY_HANDOFF: 'e9.zone3.gameplay_handoff',
    MAP_BATTLE_TRAINING: 'e9.zone3.map_battle',
    BATTLEFIELD_BOSS_PROGRESS: 'e9.zone3.battlefield_boss',
    LORD_READY: 'e9.zone3.lord_ready',
    LORD_CTA: 'e9.zone3.lord_cta',
    LORD_TRIAL: 'e9.zone3.lord_trial',
    CLEAR_REWARD: 'e9.zone3.clear_reward',
    POST_CLEAR_CINEMATIC: 'e9.zone3.post_clear',
    ZONE4_HOOK: 'e9.zone3.zone4_hook',
    RETURN: 'e9.zone3.return'
  };

  function closestAction(target, root) {
    var node = target;
    while (node && node !== root) {
      if (node.getAttribute && node.getAttribute('data-zone3-action')) return node;
      node = node.parentNode;
    }
    return null;
  }

  function setCopyKey(element, key) {
    if (!element) return;
    if (key) element.setAttribute('data-i18n', key);
    else element.removeAttribute('data-i18n');
  }

  function applyI18n(root) {
    if (global.I18n && typeof global.I18n.apply === 'function') {
      try { global.I18n.apply(root); } catch (error) { console.error('[E9] Zone 3 i18n apply failed:', error); }
    }
  }

  function t(key) {
    if (global.I18n && typeof global.I18n.t === 'function') return global.I18n.t(key);
    return key;
  }

  function emitCommand(action, detail) {
    if (typeof CustomEvent !== 'function') return;
    document.dispatchEvent(new CustomEvent(COMMAND, {
      detail: Object.assign({ action: action, zoneKey: content.zone3Key }, detail || {})
    }));
  }

  function drainQueue(handler) {
    var queue = Array.isArray(global.__GO_ZONE3_JOURNEY_EVENT_QUEUE__)
      ? global.__GO_ZONE3_JOURNEY_EVENT_QUEUE__.slice() : [];
    global.__GO_ZONE3_JOURNEY_EVENT_QUEUE__ = [];
    queue.forEach(handler);
  }

  function consumeLiveQueueItem(detail) {
    // The bridge queues before mount so a non-critical component cannot miss
    // an authenticated bootstrap event. Once mounted, remove the same object
    // after the live dispatch so a later remount cannot replay stale journey
    // history into a fresh presentation controller.
    var queue = global.__GO_ZONE3_JOURNEY_EVENT_QUEUE__;
    if (!Array.isArray(queue) || !detail) return;
    global.__GO_ZONE3_JOURNEY_EVENT_QUEUE__ = queue.filter(function (item) {
      return item !== detail;
    });
  }

  function render(root, controller) {
    var state = controller.getState();
    var copyKey = COPY_BY_PHASE[state.phase] || null;
    var hidden = !state.active || state.phase === 'RETURN' || !copyKey;
    root.hidden = hidden;
    root.setAttribute('aria-hidden', hidden ? 'true' : 'false');
    if (hidden) return;

    root.setAttribute('data-zone3-phase', state.phase);
    var prefix = copyKey;
    setCopyKey(root.querySelector('[data-zone3-kicker]'), prefix + '.kicker');
    setCopyKey(root.querySelector('[data-zone3-title]'), prefix + '.title');
    setCopyKey(root.querySelector('[data-zone3-body]'), prefix + '.body');
    setCopyKey(root.querySelector('[data-zone3-status]'),
      state.phase === 'ENTRY_CINEMATIC' || state.phase === 'POST_CLEAR_CINEMATIC'
        ? 'e9.zone3.pending_assets' : 'e9.zone3.status');
    var cta = root.querySelector('[data-zone3-action="lord-cta"]');
    var back = root.querySelector('[data-zone3-action="return"]');
    if (cta) {
      cta.hidden = state.phase !== 'LORD_READY';
      cta.disabled = state.phase !== 'LORD_READY';
    }
    if (back) {
      back.hidden = state.phase === 'LORD_READY' || state.phase === 'LORD_CTA';
      back.disabled = back.hidden;
    }
    applyI18n(root);
    var status = root.querySelector('[data-zone3-status]');
    if (status && state.phase !== 'ENTRY_CINEMATIC' && state.phase !== 'POST_CLEAR_CINEMATIC') {
      status.textContent = t('e9.zone3.status');
    }
  }

  function bind(target, eventName, handler, generation) {
    if (global.E9 && typeof global.E9.on === 'function') {
      return global.E9.on(target, eventName, handler, null, generation);
    }
    target.addEventListener(eventName, handler);
    return handler;
  }

  function mount(root, generation) {
    if (!root || root.getAttribute('data-e9-zone3-mounted') === 'true') return;
    var controller = global.GoOdysseyJourneyZone3.create({ content: content });

    function renderCurrent() { render(root, controller); }

    function onJourneyEvent(event) {
      var detail = event && event.detail;
      if (!detail || !detail.type) return;
      consumeLiveQueueItem(detail);
      var outcome = controller.accept(detail);
      if (outcome.accepted) renderCurrent();
    }

    function onClick(event) {
      var action = closestAction(event.target, root);
      if (!action) return;
      event.preventDefault();
      var actionName = action.getAttribute('data-zone3-action');
      if (actionName === 'lord-cta') {
        var lordCta = controller.accept({
          type: content.eventTypes.lordCta,
          detail: {
            clicked: true,
            presentationOnly: true,
            source: 'existing_lord_cta',
            autoStart: false
          }
        });
        if (lordCta.accepted) {
          renderCurrent();
          emitCommand('lord-cta', { source: 'zone3_vertical_slice' });
        }
      } else if (actionName === 'return') {
        var returned = controller.accept({
          type: content.eventTypes.returnToMap,
          detail: {
            presentationOnly: true,
            replaySafe: true,
            source: 'canonical_return'
          }
        });
        if (returned.accepted) {
          renderCurrent();
          emitCommand('return', { source: 'zone3_vertical_slice' });
        }
      }
    }

    bind(root, 'click', onClick, generation);
    bind(document, EVENT, onJourneyEvent, generation);
    if (global.E9 && typeof global.E9.registerCleanup === 'function') {
      global.E9.registerCleanup(function () {
        root.removeAttribute('data-e9-zone3-mounted');
        delete root.__goOdysseyJourneyZone3;
      }, generation);
    }
    root.setAttribute('data-e9-zone3-mounted', 'true');
    root.__goOdysseyJourneyZone3 = controller;
    renderCurrent();
    drainQueue(onJourneyEvent);
    renderCurrent();
  }

  document.addEventListener('e9:component-loaded', function (event) {
    var detail = event && event.detail;
    if (!detail || detail.component !== COMPONENT) return;
    mount(detail.root, detail.generation);
  });
}(typeof window !== 'undefined' ? window : this, typeof document !== 'undefined' ? document : null));
