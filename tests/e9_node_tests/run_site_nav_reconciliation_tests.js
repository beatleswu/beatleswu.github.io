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

function createHarness() {
  const doc = {
    readyState: 'complete',
    listeners: {},
    body: null,
    head: { appendChild: () => {} },
    meta: { getAttribute: (name) => name === 'content' ? 'e10-vs1f-integrated-world-map' : null },
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

async function main() {
  const h = createHarness();
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, true, 'initial unresolved shell keeps the shared nav');
  assert.strictEqual(h.doc.listeners['e9:shell-state-changed'].length, 1);

  setShell(h, 'e9');
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, false, 'E10 shell strips global links after auth');
  assert.strictEqual(h.doc.header.dataset.e10SessionStrip, '1');

  setShell(h, 'legacy');
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, true, 'Legacy shell restores global links');
  assert.strictEqual(h.doc.header.dataset.e10SessionStrip, undefined);

  setShell(h, 'e9');
  assert.strictEqual(h.doc.querySelectorAll('header.cg-nav').length, 1);
  assert.strictEqual(h.doc.header.hasLinks, false, 'Legacy to E10 transition strips links again');

  await Promise.resolve();
  console.log('site-nav reconciliation tests passed (4 assertions)');
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
