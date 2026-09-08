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

  function stepPresentationState(state, step, displayStep) {
    if (displayStep === step) return 'current';
    if (state.skippedSteps && state.skippedSteps.indexOf(step) !== -1) return 'skipped';
    if (state.completedSteps && state.completedSteps.indexOf(step) !== -1) return 'completed';
    return 'upcoming';
  }

  function renderProgress(root, state, displayStep) {
    var progress = root.querySelector('[data-journey-progress]');
    if (!progress || typeof document.createElement !== 'function') return;
    progress.replaceChildren();
    (content.stepOrder || []).forEach(function (step) {
      var contract = content.stepContracts[step];
      // zone3_arrival remains a style-lock boundary and has no user copy yet.
      if (!contract || !contract.copyKey) return;
      var item = document.createElement('li');
      var label = document.createElement('span');
      var stateName = stepPresentationState(state, step, displayStep);
      item.setAttribute('data-journey-progress-step', step);
      item.setAttribute('data-journey-progress-state', stateName);
      if (stateName === 'current') item.setAttribute('aria-current', 'step');
      label.setAttribute('data-i18n', contract.copyKey + '.title');
      label.textContent = step.replace(/_/g, ' ');
      item.appendChild(label);
      progress.appendChild(item);
    });
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
    var suppressed = root.getAttribute('data-journey-presentation-suppressed') === 'true';
    var hidden = suppressed || !state.active || state.boundaryReached || !contract || !contract.copyKey;
    root.hidden = hidden;
    root.setAttribute('aria-hidden', hidden ? 'true' : 'false');
    if (hidden) {
      if (suppressed) root.setAttribute('data-journey-visibility', 'suppressed');
      else root.removeAttribute('data-journey-visibility');
      return;
    }

    root.removeAttribute('data-journey-visibility');
    root.setAttribute('data-journey-step', step);
    root.setAttribute('data-journey-presentation-state', overrideStep ? 'replay' : 'live');
    var prefix = contract.copyKey;
    setCopyKey(root.querySelector('[data-journey-kicker]'), prefix + '.kicker');
    setCopyKey(root.querySelector('[data-journey-title]'), prefix + '.title');
    setCopyKey(root.querySelector('[data-journey-body]'), prefix + '.body');
    setCopyKey(root.querySelector('[data-journey-skip]'), content.controlCopyKeys.skip);
    setCopyKey(root.querySelector('[data-journey-replay]'), content.controlCopyKeys.replay);
    renderProgress(root, state, step);

    var replay = root.querySelector('[data-journey-replay]');
    if (replay) replay.hidden = state.completedSteps.length === 0;
    applyI18n(root);

    var status = root.querySelector('[data-journey-status]');
    var title = root.querySelector('[data-journey-title]');
    var body = root.querySelector('[data-journey-body]');
    if (status) {
      status.textContent = [title && title.textContent, body && body.textContent]
        .filter(Boolean).join('. ') || step.replace(/_/g, ' ');
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
        var skipResult = controller.skipHint();
        overrideStep = null;
        if (skipResult.accepted) root.setAttribute('data-journey-presentation-suppressed', 'true');
        renderCurrent();
      } else if (action.getAttribute('data-journey-action') === 'replay') {
        var replayResult = controller.replayHint();
        if (replayResult.accepted) {
          root.removeAttribute('data-journey-presentation-suppressed');
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
      if (outcome.accepted) {
        root.removeAttribute('data-journey-presentation-suppressed');
        renderCurrent();
      }
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
    root.removeAttribute('data-journey-presentation-suppressed');
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
