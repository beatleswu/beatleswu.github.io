/*
 * E9 Component Loader — fail-safe fetch + inject + initialize.
 *
 * Contract (fixed order, per Go Odyssey i18n engineering contract):
 *   1. show a lightweight loading skeleton immediately (no blank flash)
 *   2. fetch the fragment (versioned URL), bounded by a timeout so a
 *      permanently-pending request cannot leave the skeleton showing forever
 *      (E9 Phase 1 hardening — see COMPONENT_FETCH_TIMEOUT_MS below)
 *   3. validate response.ok
 *   4. inject into the target root
 *   5. apply the EXISTING window.I18n system to the newly-injected markup
 *      (I18n.apply() is a cheap, idempotent full-document rescan — this
 *      repo has no scoped/subtree i18n API, so re-running the global
 *      apply() after injection is the established pattern, matching what
 *      index.html/hero.html already do after inserting new content)
 *   6. dispatch "e9:component-loaded" with {component, root} so the
 *      component's own init script can wire itself up
 *
 * On any failure at any step (including a timeout): render a safe fallback
 * into the root, log the error, and return — never throw an uncaught error,
 * never let one component's failure touch another component, the rest of
 * the E9 shell, or the legacy page underneath it.
 *
 * Idempotency: each root is marked with data-e9-loaded once settled, so
 * a re-invocation for the same root does not re-fetch, re-inject, or
 * re-dispatch the loaded event.
 */
(function (global) {
  'use strict';

  // Overridable via window.E9.COMPONENT_FETCH_TIMEOUT_MS (read fresh on each
  // call, not captured once) so tests can inject a short value instead of
  // waiting out the real default. 8s gives generous margin for a same-origin
  // fragment fetch under slow/mobile conditions without leaving a user
  // staring at a skeleton for an unreasonable time.
  var DEFAULT_COMPONENT_FETCH_TIMEOUT_MS = 8000;

  function skeletonHtml(component) {
    return '<div class="e9-component-skeleton" data-e9-skeleton="' + component + '" aria-busy="true">' +
      '<span class="e9-visually-hidden">Loading ' + component + '…</span>' +
      '</div>';
  }

  function fallbackHtml(component) {
    return '<div class="e9-component-fallback" data-e9-fallback="' + component + '" role="status">' +
      '<span class="e9-component-fallback__label">' + component + ' unavailable</span>' +
      '</div>';
  }

  function versionedUrl(url) {
    var version = (global.E9 && global.E9.ASSET_VERSION) || '0';
    var sep = url.indexOf('?') === -1 ? '?' : '&';
    return url + sep + 'v=' + encodeURIComponent(version);
  }

  /**
   * @param {string} component  logical component name, e.g. "top_hud"
   * @param {Element} root      container element to inject into
   * @param {string} url        fragment URL (unversioned; version is appended)
   * @returns {Promise<boolean>} resolves true on success, false on fallback
   */
  function loadComponent(component, root, url) {
    if (!root) {
      console.error('[E9] loadComponent: no root element for', component);
      return Promise.resolve(false);
    }
    if (root.getAttribute('data-e9-loaded') === '1' || root.getAttribute('data-e9-loaded') === 'error') {
      // Already settled — do not re-fetch/re-dispatch.
      return Promise.resolve(root.getAttribute('data-e9-loaded') === '1');
    }

    var generation = global.E9 && typeof global.E9.getLifecycleGeneration === 'function'
      ? global.E9.getLifecycleGeneration() : null;
    function current() {
      return !global.E9 || typeof global.E9.isLifecycleCurrent !== 'function' ||
        global.E9.isLifecycleCurrent(generation);
    }

    try {
      root.innerHTML = skeletonHtml(component);
    } catch (skeletonErr) {
      console.error('[E9] skeleton render failed:', component, skeletonErr);
    }

    var timeoutMs = (global.E9 && typeof global.E9.COMPONENT_FETCH_TIMEOUT_MS === 'number')
      ? global.E9.COMPONENT_FETCH_TIMEOUT_MS : DEFAULT_COMPONENT_FETCH_TIMEOUT_MS;
    var controller = new AbortController();
    // abort() call site #1: our own bounded timeout. This is one of exactly
    // two call sites that can abort this fetch (the other is the lifecycle
    // cleanup below) — the .catch() below's reasoning about which one fired
    // depends on there being exactly these two; if a third cancellation
    // source (e.g. a manual retry button) is ever added, that reasoning must
    // be re-examined, not silently inherited.
    var timeoutHandle = setTimeout(function () { controller.abort(); }, timeoutMs);
    if (global.E9 && typeof global.E9.registerCleanup === 'function') {
      // abort() call site #2: destroy-triggered cleanup, reusing the exact
      // same generation-scoped mechanism shell.js's on() already uses for
      // event listeners (registerCleanup/lifecycleCleanups) rather than
      // inventing a parallel cleanup path. destroyLifecycle() always
      // advances lifecycleGeneration before running cleanups, so by the time
      // this fires, current() is already false for this generation.
      global.E9.registerCleanup(function () {
        clearTimeout(timeoutHandle);
        controller.abort();
      }, generation);
    }

    return fetch(versionedUrl(url), { credentials: 'same-origin', signal: controller.signal })
      .then(function (res) {
        clearTimeout(timeoutHandle);
        if (!res.ok) {
          throw new Error('HTTP ' + res.status + ' loading ' + url);
        }
        return res.text();
      })
      .then(function (html) {
        if (!current()) return false;
        root.innerHTML = html;
        try {
          if (global.I18n && typeof global.I18n.apply === 'function') {
            global.I18n.apply();
          }
        } catch (i18nErr) {
          // Never let an i18n failure block the component from mounting —
          // untranslated text is degraded, not broken.
          console.error('[E9] I18n.apply() failed after injecting', component, i18nErr);
        }
        root.setAttribute('data-e9-loaded', '1');
        root.dispatchEvent(new CustomEvent('e9:component-loaded', {
          bubbles: true,
          detail: { component: component, root: root, generation: generation }
        }));
        return true;
      })
      .catch(function (err) {
        clearTimeout(timeoutHandle);
        if (!current()) return false;
        // Reaching here with current() still true and an AbortError can only
        // mean OUR OWN timeout fired (see the two-call-site note above) — a
        // destroy-triggered abort always makes current() false first. Render
        // the identical fallback as any other failure; no new visual state
        // or separate "timedOut" bookkeeping is needed.
        console.error('[E9] component load failed:', component, err);
        try {
          root.innerHTML = fallbackHtml(component);
          root.setAttribute('data-e9-loaded', 'error');
        } catch (renderErr) {
          console.error('[E9] fallback render also failed:', component, renderErr);
        }
        return false;
      });
  }

  global.E9 = global.E9 || {};
  global.E9.loadComponent = loadComponent;
  global.E9.COMPONENT_FETCH_TIMEOUT_MS = DEFAULT_COMPONENT_FETCH_TIMEOUT_MS;
})(window);
