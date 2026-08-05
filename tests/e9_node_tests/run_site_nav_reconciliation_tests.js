'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const SITE_NAV_JS = path.join(REPO_ROOT, 'site-nav.js');

class FakeElement {
  constructor(tagName, document) {
    this.tagName = tagName.toUpperCase();
    this.document = document;
    this.attrs = {};
    this.dataset = {};
    this.listeners = {};
    this.children = [];
    this.className = '';
    this.hasLinks = false;
    this.innerHTML = '';
  }

  setAttribute(name, value) {
    this.attrs[name] = String(value);
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
  }

  removeAttribute(name) {
    delete this.attrs[name];
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  addEventListener(name, handler) {
    (this.listeners[name] || (this.listeners[name] = [])).push(handler);
  }

  querySelector(selector) {
    if (selector === '.cg-nav-links') {
      return this.hasLinks ? { remove: () => { this.hasLinks = false; } } : null;
    }
    if (selector === '[id^="lang-switcher-"]') return null;
    if (selector === '.cg-nav-lang') return { appendChild: (child) => child };
    if (selector === '.cg-nav-logout') return { addEventListener: () => {} };
    if (selector === '.cg-nav-actions') return { insertAdjacentHTML: () => { this.hasLinks = true; } };
    return null;
  }

  replaceWith(next) {
    this.document.header = next;
  }

  set innerHTML(value) {
    this.html = String(value);
    this.hasLinks = this.html.includes('class="cg-nav-links"');
  }

  get innerHTML() {
    return this.html || '';
  }
}

function createHarness({ staticContract = 'e10-vs1f-integrated-world-map' } = {}) {
  const doc = {
    readyState: 'complete',
    listeners: {},
    body: null,
    head: { appendChild: () => {} },
    meta: { getAttribute: (name) => name === 'content' ? staticContract : null },
    header: null,
    addEventListener(name, handler) {
      (this.listeners[name] || (this.listeners[name] = [])).push(handler);
    },
    dispatchEvent(event) {
      (this.listeners[event.type] || []).slice().forEach((handler) => handler(event));
      return true;
    },
    createElement(tagName) {
      return new FakeElement(tagName, this);
    },
    querySelector(selector) {
      if (selector === 'meta[name="go-odyssey-static-contract"]') return this.meta;
      if (selector === 'header.cg-nav') {
        return this.header && this.header.className === 'cg-nav' ? this.header : null;
      }
      if (selector === 'header:not(.hero)') return this.header;
      return null;
    },
    querySelectorAll(selector) {
      if (selector === 'header.cg-nav') {
        return this.header && this.header.className === 'cg-nav' ? [this.header] : [];
      }
      return [];
    },
    getElementById: () => null,
  };
  doc.body = new FakeElement('body', doc);
  doc.header = new FakeElement('header', doc);
  doc.header.className = 'placeholder';

  const win = {
    document: doc,
    location: { pathname: '/', origin: 'https://example.test' },
    __GO_E9_ACTIVE_SHELL__: undefined,
    __GO_ADVENTURE_SHELL_OWNER__: undefined,
    localStorage: { getItem: () => null },
    setTimeout: () => 0,
    clearTimeout: () => {},
    fetch: () => Promise.resolve({ json: () => Promise.resolve({ logged_in: false }) }),
    listeners: {},
    addEventListener(name, handler) {
      (this.listeners[name] || (this.listeners[name] = [])).push(handler);
    },
    dispatchEvent(event) {
      (this.listeners[event.type] || []).slice().forEach((handler) => handler(event));
      return true;
    },
    CustomEvent: function CustomEvent(name, init) {
      this.type = name;
      this.detail = init && init.detail;
    },
  };

  const context = {
    window: win,
    document: doc,
    location: win.location,
    URL,
    CustomEvent: win.CustomEvent,
    Promise,
    console,
  };
  vm.runInNewContext(fs.readFileSync(SITE_NAV_JS, 'utf8'), context, { filename: 'site-nav.js' });
  return { doc, win };
}

function setShell(harness, mode) {
  harness.win.__GO_E9_ACTIVE_SHELL__ = mode;
  harness.doc.body.setAttribute('data-adventure-shell-active', mode);
  harness.doc.dispatchEvent(new harness.win.CustomEvent('e9:shell-state-changed', {
    detail: { activeShell: mode },
  }));
}

function setE10BattleOwner(harness, active, { bodyOnly = false } = {}) {
  const owner = active ? 'e10-battle' : null;
  harness.win.__GO_ADVENTURE_SHELL_OWNER__ = bodyOnly ? undefined : owner;
  if (owner) harness.doc.body.setAttribute('data-adventure-shell-owner', owner);
  else harness.doc.body.removeAttribute('data-adventure-shell-owner');
  harness.doc.dispatchEvent(new harness.win.CustomEvent('e10:adventure-shell-owner-changed', {
    detail: { owner },
  }));
}

async function main() {
  const h = createHarness();
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, true, 'initial unresolved shell keeps the shared nav');
  assert.strictEqual(h.doc.listeners['e9:shell-state-changed'].length, 1);
  assert.strictEqual(h.doc.listeners['e10:adventure-shell-owner-changed'].length, 1);

  setShell(h, 'e9');
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, false, 'E10 shell strips global links after auth');
  assert.strictEqual(h.doc.header.dataset.e10SessionStrip, '1');

  setShell(h, 'legacy');
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, true, 'Legacy shell restores global links');
  assert.strictEqual(h.doc.header.dataset.e10SessionStrip, undefined);

  setE10BattleOwner(h, true);
  assert.strictEqual(h.doc.header.hasLinks, false, 'authoritative E10 Battle owner strips links even with Legacy renderer');

  setE10BattleOwner(h, false);
  assert.strictEqual(h.doc.header.hasLinks, true, 'clearing E10 Battle ownership restores Legacy links');

  setE10BattleOwner(h, true, { bodyOnly: true });
  assert.strictEqual(h.doc.header.hasLinks, false, 'body owner marker also covers delayed bootstrap reconciliation');

  setE10BattleOwner(h, false);
  assert.strictEqual(h.doc.header.hasLinks, true, 'cleared body owner marker restores Legacy links');

  const generic = createHarness({ staticContract: 'generic-page' });
  setE10BattleOwner(generic, true);
  assert.strictEqual(generic.doc.header.hasLinks, true, 'generic pages ignore the E10 Battle marker');

  setShell(h, 'e9');
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, false, 'Legacy to E10 transition strips links again');

  await Promise.resolve();
  console.log('site-nav reconciliation tests passed (10 assertions)');
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
