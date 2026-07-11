/*
 * E9 Component Loader — fail-safe fetch + inject + initialize.
 *
 * Contract:
 *   1. show a lightweight loading skeleton immediately (no blank flash)
 *   2. fetch the fragment (versioned URL)
 *   3. validate response.ok
 *   4. inject into the target root
 *   5. dispatch "e9:component-loaded" with {component, root} so the
 *      component's own init script can wire itself up
 *
 * On any failure at any step: render a safe fallback into the root,
 * log the error, and return — never throw an uncaught error, never let
 * one component's failure touch another component, the rest of the E9
 * shell, or the legacy page underneath it.
 *
 * Idempotency: each root is marked with data-e9-loaded once settled, so
 * a re-invocation for the same root does not re-fetch, re-inject, or
 * re-dispatch the loaded event.
 */
(function (global) {
  'use strict';

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

    try {
      root.innerHTML = skeletonHtml(component);
    } catch (skeletonErr) {
      console.error('[E9] skeleton render failed:', component, skeletonErr);
    }

    return fetch(versionedUrl(url), { credentials: 'same-origin' })
      .then(function (res) {
        if (!res.ok) {
          throw new Error('HTTP ' + res.status + ' loading ' + url);
        }
        return res.text();
      })
      .then(function (html) {
        root.innerHTML = html;
        root.setAttribute('data-e9-loaded', '1');
        root.dispatchEvent(new CustomEvent('e9:component-loaded', {
          bubbles: true,
          detail: { component: component, root: root }
        }));
        return true;
      })
      .catch(function (err) {
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
})(window);
