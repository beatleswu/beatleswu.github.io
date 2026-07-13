'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const SHELL_JS = path.join(REPO_ROOT, 'js', 'e9', 'shell.js');
const FOCUSABLE_SELECTOR = [
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

let passCount = 0;
let failures = [];

function test(name, fn) {
  Promise.resolve()
    .then(fn)
    .then(() => { passCount++; })
    .catch((err) => {
      failures.push({ name, error: err && err.stack ? err.stack : String(err) });
    });
}

class FakeNode {
  constructor(name, doc) {
    this.name = name;
    this.doc = doc;
    this.attrs = {};
    this.hidden = false;
    this.tabIndex = 0;
    this.children = [];
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name === 'tabindex') this.tabIndex = Number(value);
  }
  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
  }
  hasAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attrs, name);
  }
  removeAttribute(name) {
    delete this.attrs[name];
    if (name === 'tabindex') this.tabIndex = 0;
  }
  querySelectorAll(selector) {
    if (selector === FOCUSABLE_SELECTOR) return this.children.slice();
    if (selector === '[data-e9-prev-tabindex]') {
      return this.children.filter((child) => child.hasAttribute('data-e9-prev-tabindex'));
    }
    return [];
  }
  contains(node) {
    return this === node || this.children.indexOf(node) !== -1;
  }
  focus() {
    this.doc.activeElement = this;
  }
  dispatchEvent() {}
}

function createHarness(opts) {
  const doc = {
    readyState: 'complete',
    activeElement: null,
    listeners: {},
    addEventListener(name, fn) {
      this.listeners[name] = fn;
    },
  };
  doc.body = new FakeNode('body', doc);
  doc.body.focus = function () { doc.activeElement = doc.body; };

  const legacyRoots = [
    new FakeNode('guild-hall-hero', doc),
    new FakeNode('guild-entry-grid', doc),
    new FakeNode('skill-map', doc),
    new FakeNode('home-left-col', doc),
    new FakeNode('home-report', doc),
  ];
  const e9Root = new FakeNode('e9-shell', doc);
  const e9Button = new FakeNode('e9-button', doc);
  const legacyButton = new FakeNode('legacy-button', doc);
  legacyRoots[2].children.push(legacyButton);
  e9Root.children.push(e9Button);

  const slots = {
    '#e9-world-stage-slot': new FakeNode('world-stage-slot', doc),
    '#e9-top-hud-slot': new FakeNode('top-hud-slot', doc),
    '#e9-left-nav-slot': new FakeNode('left-nav-slot', doc),
    '#e9-right-cards-slot': new FakeNode('right-cards-slot', doc),
    '#e9-bottom-dock-slot': new FakeNode('bottom-dock-slot', doc),
  };

  doc.querySelector = function (selector) {
    if (selector === '#e9-adventure-shell') return e9Root;
    return slots[selector] || null;
  };
  doc.querySelectorAll = function (selector) {
    const mapping = {
      '#welcome-state > .guild-hall-hero': [legacyRoots[0]],
      '#welcome-state > .guild-entry-grid': [legacyRoots[1]],
      '#skill-map': [legacyRoots[2]],
      '#welcome-state > .home-left-col': [legacyRoots[3]],
      '#welcome-state > .home-report': [legacyRoots[4]],
    };
    return mapping[selector] ? mapping[selector].slice() : [];
  };

  const flags = Object.assign({
    e9Shell: false,
    e9TopHud: false,
    e9LeftNav: false,
    e9RightCards: false,
    e9BottomDock: false,
    e9WorldStage: false,
  }, opts.flags || {});

  let loadCalls = [];
  const win = {
    location: { hostname: opts.hostname || '127.0.0.1', search: opts.search || '' },
    document: doc,
    __GO_E9_ACTIVE_SHELL__: opts.activeShell || 'legacy',
    console: console,
    startAdventureStage: function () {},
    E9: {
      getFlags: function () { return Object.assign({}, flags); },
      loadComponent: function (component, root) {
        loadCalls.push(component);
        root.setAttribute('data-e9-loaded', '1');
        return Promise.resolve(true);
      },
      I18nFallback: { t: function (_key, fallback) { return fallback; } },
    },
    CustomEvent: function CustomEvent(name, init) {
      this.type = name;
      this.detail = init && init.detail;
    }
  };

  const context = {
    window: win,
    document: doc,
    console: console,
    CustomEvent: win.CustomEvent,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    Promise: Promise,
  };
  context.global = win;

  vm.runInNewContext(fs.readFileSync(SHELL_JS, 'utf8'), context, { filename: 'shell.js' });

  return {
    doc,
    win,
    legacyRoots,
    legacyButton,
    e9Root,
    e9Button,
    loadCalls,
    flush: () => new Promise((resolve) => setImmediate(resolve)),
  };
}

test('flag off keeps legacy active and mounts nothing', async () => {
  const h = createHarness({ flags: {} });
  await h.flush();
  assert.strictEqual(h.win.E9.getActiveShell(), 'legacy');
  assert.strictEqual(h.e9Root.hidden, true);
  assert.strictEqual(h.e9Root.getAttribute('aria-hidden'), 'true');
  assert.strictEqual(h.legacyRoots[0].hidden, false);
  assert.strictEqual(h.loadCalls.length, 0);
  assert.strictEqual(h.legacyButton.tabIndex, 0);
});

test('flag on activates only e9 shell and suppresses legacy focusability', async () => {
  const h = createHarness({
    activeShell: 'e9',
    flags: {
      e9Shell: true,
      e9TopHud: true,
      e9LeftNav: true,
      e9RightCards: true,
      e9BottomDock: true,
      e9WorldStage: true,
    }
  });
  await h.flush();
  assert.strictEqual(h.win.E9.getActiveShell(), 'e9');
  h.legacyRoots.forEach((root) => {
    assert.strictEqual(root.hidden, true);
    assert.strictEqual(root.getAttribute('aria-hidden'), 'true');
    assert.strictEqual(root.getAttribute('inert'), '');
  });
  assert.strictEqual(h.legacyButton.tabIndex, -1);
  assert.strictEqual(h.e9Root.hidden, false);
  assert.strictEqual(h.e9Root.getAttribute('aria-hidden'), null);
  assert.strictEqual(h.loadCalls.length, 5);
});

test('focus moves out of legacy when switching to e9', async () => {
  const h = createHarness({
    activeShell: 'e9',
    flags: {
      e9Shell: true,
      e9TopHud: true,
      e9LeftNav: true,
      e9RightCards: true,
      e9BottomDock: true,
      e9WorldStage: true,
    }
  });
  h.doc.activeElement = h.legacyButton;
  h.win.E9.initShell();
  await h.flush();
  assert.strictEqual(h.doc.activeElement, h.e9Button);
});

test('switching back to legacy restores tab order and focus', async () => {
  const h = createHarness({
    activeShell: 'e9',
    flags: {
      e9Shell: true,
      e9TopHud: true,
      e9LeftNav: true,
      e9RightCards: true,
      e9BottomDock: true,
      e9WorldStage: true,
    }
  });
  await h.flush();
  h.doc.activeElement = h.e9Button;
  h.win.E9.applyShellState('legacy');
  assert.strictEqual(h.doc.activeElement, h.legacyButton);
  assert.strictEqual(h.legacyButton.tabIndex, 0);
  assert.strictEqual(h.e9Button.tabIndex, -1);
});

test('initShell is idempotent for fragment mounts', async () => {
  const h = createHarness({
    activeShell: 'e9',
    flags: {
      e9Shell: true,
      e9TopHud: true,
      e9LeftNav: true,
      e9RightCards: true,
      e9BottomDock: true,
      e9WorldStage: true,
    }
  });
  await h.flush();
  const firstCount = h.loadCalls.length;
  h.win.E9.initShell();
  await h.flush();
  assert.strictEqual(h.loadCalls.length, firstCount);
});

setImmediate(() => {
  setImmediate(() => {
    if (failures.length) {
      console.error('Shell exclusivity tests failed:');
      failures.forEach((f) => {
        console.error('- ' + f.name + ': ' + f.error);
      });
      process.exit(1);
    }
    console.log(passCount + ' passed');
  });
});
