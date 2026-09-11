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

  setAttribute(name, value) { this.attributes.set(String(name), String(value)); }
  getAttribute(name) { return this.attributes.has(String(name)) ? this.attributes.get(String(name)) : null; }
  removeAttribute(name) { this.attributes.delete(String(name)); }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...children) { this.children = []; children.forEach((child) => this.appendChild(child)); }
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
  constructor() { super('#document'); }
  createElement(tagName) { return new FakeNode(tagName); }
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
  root.setAttribute('aria-labelledby', 'journey-onboarding-title');
  root.setAttribute('aria-describedby', 'journey-onboarding-body');
  root.hidden = true;
  root.setAttribute('aria-hidden', 'true');
  const card = root.appendChild(new FakeNode('div'));
  card.setAttribute('data-journey-card', '');
  card.appendChild(new FakeNode('p')).setAttribute('data-journey-kicker', '');
  card.appendChild(new FakeNode('h2')).setAttribute('data-journey-title', '');
  card.appendChild(new FakeNode('p')).setAttribute('data-journey-body', '');
  card.appendChild(new FakeNode('ol')).setAttribute('data-journey-progress', '');
  const status = card.appendChild(new FakeNode('p'));
  status.setAttribute('data-journey-status', '');
  status.setAttribute('role', 'status');
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
  on(target, eventName, handler) { target.addEventListener(eventName, handler); return handler; },
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
assert.ok(content, 'presentation content must load');

let checks = 0;
function check(condition, message) { checks += 1; assert.ok(condition, message); }

function mount(root, generation) {
  document.dispatchEvent({
    type: 'e9:component-loaded',
    detail: { component: 'journey_onboarding', root, generation },
  });
}

function emitProjection(projection) {
  document.dispatchEvent({
    type: 'journey:onboarding-v2-projection',
    detail: projection,
  });
}

const root = makeRoot();
mount(root, 1);
const controller = root.__goOdysseyJourneyOnboarding;
check(root.hidden === true, 'V2 remains dormant without an explicit projection enablement');
check(root.__goOdysseyJourneyOnboardingV2.getProjection() === null, 'no projection is exposed before the server event');

emitProjection({
  enabled: true,
  source: 'browser',
  projection: { state: { state_version: 1, status: 'IN_PROGRESS', current_step: 'first_context' } },
});
check(root.hidden === true, 'unlabelled browser input cannot activate the bridge');
check(controller.getState().active === false, 'browser input does not activate the presentation spine');

emitProjection({ enabled: false, source: 'server_onboarding_v2' });
check(root.hidden === true, 'explicitly disabled server projection stays dormant');

emitProjection({
  enabled: true,
  source: 'server_onboarding_v2',
  projection: { state: { state_version: 4, status: 'IN_PROGRESS', current_step: 'first_context' } },
});
check(root.hidden === false, 'an enabled server projection renders the dormant rail');
check(root.getAttribute('data-journey-v2-enabled') === 'true', 'server enablement is explicit in the DOM contract');
check(root.getAttribute('data-journey-v2-state-version') === '4', 'state version is rendered as projection metadata');
check(root.getAttribute('data-journey-v2-status') === 'IN_PROGRESS', 'server status is rendered without local persistence');
check(root.getAttribute('data-journey-v2-step') === 'first_context', 'canonical V2 step is retained separately from UI step');
check(root.getAttribute('data-journey-step') === 'first_adventure', 'V2 step maps to existing presentation copy');
check(root.getAttribute('data-journey-presentation-state') === 'server_projection', 'projection rendering is marked presentation-only');
check(root.getAttribute('data-journey-v2-readonly') === 'true', 'the bridge declares its read-only boundary');
check(controller.getState().active === false, 'rendering a projection never advances the client controller');

const skip = root.querySelector('[data-journey-action="skip"]');
root.dispatchEvent({ type: 'click', target: skip });
check(controller.getState().skippedSteps.length === 0, 'V2 DOM clicks cannot mutate presentation or server progression');

emitProjection({
  enabled: true,
  source: 'server_onboarding_v2',
  projection: { state: { state_version: 5, status: 'COMPLETED', current_step: 'next_action' } },
});
check(root.hidden === true, 'completed V2 projection hides active onboarding guidance');
check(root.getAttribute('data-journey-v2-status') === 'COMPLETED', 'terminal status remains inspectable for shell logic');
check(root.__goOdysseyJourneyOnboardingV2.getProjection().state_version === 5, 'the bridge exposes only the latest server projection snapshot');

console.log(JSON.stringify({
  status: 'PASS',
  checks,
  failures: 0,
  controllerActive: controller.getState().active,
  terminalStatus: root.getAttribute('data-journey-v2-status'),
}));
