import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

class FakeNode {
  constructor(tagName = 'div') {
    this.tagName = String(tagName).toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.parentNode = null;
    this.listeners = new Map();
    this.hidden = false;
    this.textContent = '';
  }

  setAttribute(name, value) {
    this.attributes.set(String(name), String(value));
  }

  getAttribute(name) {
    const key = String(name);
    return this.attributes.has(key) ? this.attributes.get(key) : null;
  }

  removeAttribute(name) {
    this.attributes.delete(String(name));
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  replaceChildren(...children) {
    this.children = [];
    children.forEach((child) => this.appendChild(child));
  }

  addEventListener(name, handler) {
    const handlers = this.listeners.get(name) || [];
    handlers.push(handler);
    this.listeners.set(name, handlers);
  }

  dispatchEvent(event) {
    if (!event.target) event.target = this;
    if (typeof event.preventDefault !== 'function') event.preventDefault = () => {};
    event.currentTarget = this;
    (this.listeners.get(event.type) || []).slice().forEach((handler) => handler(event));
    return true;
  }

  querySelector(selector) {
    for (const child of this.children) {
      if (matchesSelector(child, selector)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }

  querySelectorAll(selector) {
    const matches = [];
    const visit = (node) => {
      node.children.forEach((child) => {
        if (matchesSelector(child, selector)) matches.push(child);
        visit(child);
      });
    };
    visit(this);
    return matches;
  }
}

class FakeDocument extends FakeNode {
  constructor() {
    super('#document');
  }

  createElement(tagName) {
    return new FakeNode(tagName);
  }
}

function matchesSelector(node, selector) {
  const exactAttribute = selector.match(/^\[([^=\]]+)="([^"]*)"\]$/);
  if (exactAttribute) return node.getAttribute(exactAttribute[1]) === exactAttribute[2];
  const attribute = selector.match(/^\[([^\]]+)\]$/);
  return Boolean(attribute && node.getAttribute(attribute[1]) !== null);
}

function loadScript(context, relativePath) {
  vm.runInContext(fs.readFileSync(path.join(repositoryRoot, relativePath), 'utf8'), context, {
    filename: relativePath,
  });
}

function makeRoot() {
  const root = new FakeNode('aside');
  root.setAttribute('data-e9-component', 'journey_onboarding');
  root.setAttribute('data-i18n-aria-label', 'e9.journey.aria_label');
  root.setAttribute('aria-labelledby', 'journey-onboarding-title');
  root.setAttribute('aria-describedby', 'journey-onboarding-body');
  root.hidden = true;
  root.setAttribute('aria-hidden', 'true');

  const card = root.appendChild(new FakeNode('div'));
  card.setAttribute('data-journey-card', '');
  const kicker = card.appendChild(new FakeNode('p'));
  kicker.setAttribute('data-journey-kicker', '');
  const title = card.appendChild(new FakeNode('h2'));
  title.setAttribute('data-journey-title', '');
  const body = card.appendChild(new FakeNode('p'));
  body.setAttribute('data-journey-body', '');
  const progress = card.appendChild(new FakeNode('ol'));
  progress.setAttribute('data-journey-progress', '');
  const status = card.appendChild(new FakeNode('p'));
  status.setAttribute('data-journey-status', '');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const actions = card.appendChild(new FakeNode('div'));
  const skip = actions.appendChild(new FakeNode('button'));
  skip.setAttribute('type', 'button');
  skip.setAttribute('data-journey-action', 'skip');
  skip.setAttribute('data-journey-skip', '');
  const replay = actions.appendChild(new FakeNode('button'));
  replay.setAttribute('type', 'button');
  replay.setAttribute('data-journey-action', 'replay');
  replay.setAttribute('data-journey-replay', '');
  replay.hidden = true;
  return root;
}

const document = new FakeDocument();
const context = { console, document };
context.window = context;
context.E9 = {
  on(target, eventName, handler) {
    target.addEventListener(eventName, handler);
    return handler;
  },
  registerCleanup() {},
};
context.I18n = {
  apply(root) {
    root.querySelectorAll('[data-i18n]').forEach((node) => {
      node.textContent = node.getAttribute('data-i18n');
    });
  },
};
vm.createContext(context);

loadScript(context, 'js/e9/journey_onboarding_content.js');
loadScript(context, 'js/e9/journey_onboarding_spine.js');
loadScript(context, 'js/e9/journey_onboarding_view.js');

const content = context.GoOdysseyJourneyOnboardingContent;
assert.ok(content, 'canonical onboarding content must load');
assert.ok(context.GoOdysseyJourneyOnboarding, 'canonical onboarding spine must load');

let checks = 0;
function check(condition, message) {
  checks += 1;
  assert.ok(condition, message);
}

function emit(root, type, detail, eventId) {
  const payload = { type, detail: { ...detail, ...(eventId ? { eventId } : {}) } };
  document.dispatchEvent({ type: 'journey:onboarding-event', detail: payload });
  return root.__goOdysseyJourneyOnboarding.getState();
}

function mount(root, generation) {
  document.dispatchEvent({
    type: 'e9:component-loaded',
    detail: { component: 'journey_onboarding', root, generation },
  });
}

const root = makeRoot();
mount(root, 1);
const controller = root.__goOdysseyJourneyOnboarding;
check(root.hidden === true, 'the rail remains hidden before the first-session event');
check(controller.getState().active === false, 'the view is backed by the canonical inactive state');

emit(root, content.eventTypes.openingReady, {
  authenticated: true,
  firstSession: true,
  authoritySource: 'existing_onboarding',
}, 'session-1');
check(root.hidden === false, 'the first-session rail mounts after the existing opening event');
check(root.getAttribute('data-journey-step') === 'opening', 'opening is the first displayed step');
check(root.getAttribute('data-journey-presentation-state') === 'live', 'canonical events render as live guidance');
check(root.querySelector('[data-journey-progress]').children.length > 0, 'ordered progress context is rendered');
check(root.querySelector('[data-journey-progress-step="opening"]').getAttribute('aria-current') === 'step', 'the current step is announced in the progress rail');
check(root.querySelector('[data-journey-status]').getAttribute('aria-live') === 'polite', 'step changes have a live status region');
check(root.querySelector('[data-journey-status]').textContent.length > 0, 'the live status region receives the current guidance copy');
check(root.getAttribute('aria-labelledby') === 'journey-onboarding-title', 'the rail has a labelled region');
check(root.querySelector('[data-journey-action="skip"]').tagName === 'BUTTON', 'skip is keyboard-focusable native button markup');
check(root.querySelector('[data-journey-action="skip"]').getAttribute('type') === 'button', 'skip cannot submit a surrounding form');

emit(root, content.eventTypes.openingReady, {
  authenticated: true,
  firstSession: true,
  authoritySource: 'existing_onboarding',
}, 'session-1');
check(root.getAttribute('data-journey-step') === 'opening', 'duplicate or stale events do not move the rail');

emit(root, content.eventTypes.worldRevealed, {
  visible: true,
  presentationState: 'legacy',
  authoritySource: 'existing_shell',
}, 'shell-1');
check(root.getAttribute('data-journey-step') === 'world_reveal', 'world context follows the opening event');

const skip = root.querySelector('[data-journey-action="skip"]');
root.dispatchEvent({ type: 'click', target: skip });
check(root.hidden === true, 'skip suppresses the visible presentation rail');
check(root.getAttribute('data-journey-visibility') === 'suppressed', 'skip is exposed as presentation suppression');
check(controller.getState().skippedSteps.includes('world_reveal'), 'skip is recorded only in the presentation spine state');
check(controller.getState().step === 'world_reveal', 'skip does not advance canonical onboarding state');

emit(root, content.eventTypes.heroCompanionIntroduced, {
  heroReady: true,
  companionReady: true,
  authoritySource: 'existing_profile',
}, 'profile-1');
check(root.hidden === false, 'a later canonical event resumes a skipped presentation');
check(root.getAttribute('data-journey-step') === 'hero_companion', 'resume follows the existing event order');
check(root.getAttribute('data-journey-visibility') === null, 'resuming removes presentation suppression');

emit(root, content.eventTypes.adventureStarted, {
  started: true,
  authoritative: true,
  zoneKey: content.zoneKeys.zone1,
  source: 'canonical_adventure',
}, 'adventure-1');
check(root.getAttribute('data-journey-step') === 'first_adventure', 'Adventure entry is explained by the canonical event');

emit(root, content.eventTypes.questionReady, {
  authoritative: true,
  boardReady: true,
  questionId: 'question-1',
  zoneKey: content.zoneKeys.zone1,
  source: 'canonical_question_runtime',
}, 'question-1');
check(root.getAttribute('data-journey-step') === 'first_question', 'board interaction and question guidance render in order');

emit(root, content.eventTypes.reviewCommitted, {
  committed: true,
  authoritative: true,
  questionId: 'question-1',
  grade: 3,
  source: 'canonical_srs_review',
}, 'review-1');
check(root.getAttribute('data-journey-step') === 'answer_feedback', 'the answer result follows the question event');

emit(root, content.eventTypes.attackResolved, {
  authoritative: true,
  result: 'CORRECT',
  damage_to_monster: 1,
  source: 'map_battle_v1',
}, 'battle-hit-1');
check(root.getAttribute('data-journey-step') === 'attack_hit', 'question-to-attack guidance renders without a second battle state machine');

emit(root, content.eventTypes.encounterVictory, {
  authoritative: true,
  monster_defeated: true,
  source: 'map_battle_v1',
}, 'battle-win-1');
check(root.getAttribute('data-journey-step') === 'first_victory', 'Monster defeat guidance renders from the existing victory event');

emit(root, content.eventTypes.rewardRevealed, {
  authoritative: true,
  rewardProjection: true,
  rewardEventId: 'reward-1',
  rewardStatus: 'GRANTED',
  replay: false,
  source: 'battlefield_reward_consumer',
}, 'reward-1');
check(root.getAttribute('data-journey-step') === 'reward_reveal', 'reward guidance renders from the authoritative reward projection');

emit(root, content.eventTypes.growthFeedback, {
  authoritative: true,
  xpProjection: true,
  xpGain: 25,
  source: 'committed_review_presentation',
}, 'growth-1');
check(root.getAttribute('data-journey-step') === 'growth_feedback', 'growth feedback follows reward presentation');

emit(root, content.eventTypes.nextAction, {
  authoritative: true,
  nextAction: { kind: 'return_to_adventure_map' },
  source: 'adventure_bootstrap',
}, 'next-1');
check(root.getAttribute('data-journey-step') === 'next_action', 'the next action is rendered from existing bootstrap state');

emit(root, content.eventTypes.zoneProgressed, {
  authoritative: true,
  zones: [
    { key: content.zoneKeys.zone1, status: 'completed' },
    { key: content.zoneKeys.zone2, status: 'unlocked', canEnter: true },
  ],
  source: 'adventure_bootstrap',
}, 'progress-1');
check(root.getAttribute('data-journey-step') === 'zone_progression', 'zone progression guidance is rendered for the Zone 1 to Zone 2 boundary');
check(root.querySelector('[data-journey-action="replay"]').hidden === false, 'completed presentation steps expose replay');

const replay = root.querySelector('[data-journey-action="replay"]');
root.dispatchEvent({ type: 'click', target: replay });
const replayStep = root.getAttribute('data-journey-step');
check(root.hidden === false, 'replay restores a completed presentation step');
check(root.getAttribute('data-journey-presentation-state') === 'replay', 'replay is marked as presentation-only');
check(controller.getState().completedSteps.includes(replayStep), 'replay can only show an already completed step');
check(controller.getState().step === 'zone_progression', 'replay does not alter canonical progression');

emit(root, content.eventTypes.rewardRevealed, {
  authoritative: true,
  rewardProjection: true,
  rewardEventId: 'reward-stale',
  rewardStatus: 'GRANTED',
  replay: false,
  source: 'battlefield_reward_consumer',
}, 'reward-stale');
check(controller.getState().step === 'zone_progression', 'stale out-of-order events fail safely');

const returningRoot = makeRoot();
mount(returningRoot, 2);
emit(returningRoot, content.eventTypes.openingReady, {
  authenticated: true,
  firstSession: false,
  authoritySource: 'existing_onboarding',
}, 'returning-session');
check(returningRoot.hidden === true, 'returning players are not forced through the first-session rail');
check(returningRoot.__goOdysseyJourneyOnboarding.getState().active === false, 'returning-player presentation remains inactive');

console.log(JSON.stringify({
  status: 'PASS',
  checks,
  failures: 0,
  finalStep: controller.getState().step,
  replayStep,
  returningPlayerHidden: returningRoot.hidden,
}));
