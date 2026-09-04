/*
 * W1_03_JOURNEY_ONBOARDING_SPINE_001
 *
 * Thin E9 adapter for the pure onboarding spine. It only renders inside the
 * journey component root and consumes bridge events from existing surfaces.
 * The separately governed shell pass is responsible for loading this file,
 * adding the slot, and emitting the bridge events.
 */
(function (global, document) {
  'use strict';

  if (!document || !global.GoOdysseyJourneyOnboarding || !global.GoOdysseyJourneyOnboardingContent) return;

  var content = global.GoOdysseyJourneyOnboardingContent;
  var COMPONENT = 'journey_onboarding';
  var EVENT = 'journey:onboarding-event';

  function closestAction(target, root) {
    var node = target;
    while (node && node !== root) {
      if (node.getAttribute && node.getAttribute('data-journey-action')) return node;
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
      try { global.I18n.apply(root); } catch (error) { console.error('[E9] journey i18n apply failed:', error); }
    }
  }

  function consumeLiveQueueItem(detail) {
    // Bridge events are queued only to cover the gap before this non-critical
    // fragment mounts. Remove a live-dispatched object so a later remount does
    // not replay stale first-session history.
    var queue = global.__GO_JOURNEY_ONBOARDING_EVENT_QUEUE__;
    if (!Array.isArray(queue) || !detail) return;
    global.__GO_JOURNEY_ONBOARDING_EVENT_QUEUE__ = queue.filter(function (item) {
      return item !== detail;
    });
  }

  function render(root, controller, overrideStep) {
    var state = controller.getState();
    var step = overrideStep || state.step;
    var contract = content.stepContracts[step];
    var hidden = !state.active || state.boundaryReached || !contract || !contract.copyKey;
    root.hidden = hidden;
    root.setAttribute('aria-hidden', hidden ? 'true' : 'false');
    if (hidden) return;

    root.setAttribute('data-journey-step', step);
    var prefix = contract.copyKey;
    setCopyKey(root.querySelector('[data-journey-kicker]'), prefix + '.kicker');
    setCopyKey(root.querySelector('[data-journey-title]'), prefix + '.title');
    setCopyKey(root.querySelector('[data-journey-body]'), prefix + '.body');
    setCopyKey(root.querySelector('[data-journey-skip]'), content.controlCopyKeys.skip);
    setCopyKey(root.querySelector('[data-journey-replay]'), content.controlCopyKeys.replay);

    var replay = root.querySelector('[data-journey-replay]');
    if (replay) replay.hidden = state.completedSteps.length === 0;
    applyI18n(root);
  }

  function bind(target, eventName, handler, generation) {
    if (global.E9 && typeof global.E9.on === 'function') {
      return global.E9.on(target, eventName, handler, null, generation);
    }
    target.addEventListener(eventName, handler);
    return handler;
  }

  function mount(root, generation) {
    if (!root || root.getAttribute('data-e9-journey-mounted') === 'true') return;
    var controller = global.GoOdysseyJourneyOnboarding.create({ content: content });
    var overrideStep = null;

    function renderCurrent() {
      render(root, controller, overrideStep);
    }

    function onClick(event) {
      var action = closestAction(event.target, root);
      if (!action) return;
      event.preventDefault();
      if (action.getAttribute('data-journey-action') === 'skip') {
        overrideStep = null;
        controller.skipHint();
        renderCurrent();
      } else if (action.getAttribute('data-journey-action') === 'replay') {
        var replayResult = controller.replayHint();
        if (replayResult.accepted) {
          overrideStep = replayResult.replayStep;
          renderCurrent();
        }
      }
    }

    function onJourneyEvent(event) {
      var detail = event && event.detail;
      if (!detail || !detail.type) return;
      consumeLiveQueueItem(detail);
      overrideStep = null;
      var outcome = controller.accept(detail);
      if (outcome.accepted) renderCurrent();
    }

    bind(root, 'click', onClick, generation);
    bind(document, EVENT, onJourneyEvent, generation);
    if (global.E9 && typeof global.E9.registerCleanup === 'function') {
      global.E9.registerCleanup(function () {
        root.removeAttribute('data-e9-journey-mounted');
        delete root.__goOdysseyJourneyOnboarding;
      }, generation);
    }
    root.setAttribute('data-e9-journey-mounted', 'true');
    root.__goOdysseyJourneyOnboarding = controller;
    renderCurrent();
    // The authenticated legacy bootstrap can finish before a non-critical
    // fragment arrives. Replay only the page-memory bridge events that were
    // queued before this component mounted; the queue carries no authority
    // or persistence and is cleared after this mount consumes it.
    var queued = Array.isArray(global.__GO_JOURNEY_ONBOARDING_EVENT_QUEUE__)
      ? global.__GO_JOURNEY_ONBOARDING_EVENT_QUEUE__.slice() : [];
    global.__GO_JOURNEY_ONBOARDING_EVENT_QUEUE__ = [];
    queued.forEach(function (payload) {
      onJourneyEvent({ detail: payload });
    });
  }

  document.addEventListener('e9:component-loaded', function (event) {
    var detail = event && event.detail;
    if (!detail || detail.component !== COMPONENT) return;
    mount(detail.root, detail.generation);
  });
}(typeof window !== 'undefined' ? window : this, typeof document !== 'undefined' ? document : null));
