/*
 * E9 World Stage — component init (CRITICAL).
 * Reads canonical adventure state via js/e9/adapters/adventure_state.js
 * (single source of truth -- no second progression state is created or
 * persisted here). Real data source only:
 *   GET /api/adventure/bootstrap -> zones[] (same endpoint the legacy
 *   Adventure Map uses; no new API, no fabricated zone data).
 * Zone-state text reuses the EXISTING index.adv.* i18n keys -- no second
 * translation dictionary for adventure semantics.
 * If the data fetch fails (or the session is unauthorized), this is
 * treated as a CRITICAL failure (a World Stage that can't show real
 * state is non-functional) and triggers full shell recovery to the
 * legacy Adventure Map via window.E9.recoverToLegacy(), NOT just a local
 * error message. A single retry is offered first for a recoverable
 * (non-auth) error, dispatching "e9:refresh-requested" before falling
 * back to recovery if the retry also fails.
 * Adventure Start uses the thin adapter window.E9.startAdventureFromE9()
 * (defined in shell.js), which calls the existing legacy
 * startAdventureStage() global -- no gameplay logic is duplicated here.
 * Zone selection dispatches "e9:zone-selected" (bubbles) before invoking
 * the adapter, so other code can observe the interaction without the
 * adapter itself becoming a second event bus for progression state.
 */
(function (document) {
  'use strict';

  function t(key, fallback) {
    if (window.I18n && typeof window.I18n.t === 'function') {
      var val = window.I18n.t(key);
      return val || fallback;
    }
    return fallback;
  }

  function renderZones(root, zones) {
    var statusEl = root.querySelector('#e9-world-stage-status');
    var zonesEl = root.querySelector('#e9-world-stage-zones');
    if (!zonesEl) return;

    zonesEl.innerHTML = '';
    zones.forEach(function (zone) {
      var tile = document.createElement('div');
      tile.className = 'e9-zone e9-zone--' + (zone.status || 'locked');
      tile.setAttribute('role', 'listitem');
      tile.setAttribute('data-zone', zone.key);

      if (!zone.locked) {
        tile.tabIndex = 0;
        tile.setAttribute('role', 'button');
      } else {
        tile.setAttribute('aria-disabled', 'true');
        tile.title = t('index.adv.zone_locked', 'This area is still sealed by mist.');
      }

      // Zone display name comes straight from the API (zone.name), same
      // as the legacy map -- there is no separate English zone-name field
      // to translate against.
      var label = document.createElement('span');
      label.className = 'e9-zone__name';
      label.textContent = zone.name;
      tile.appendChild(label);

      if (zone.cleared || zone.stars > 0) {
        var starsEl = document.createElement('span');
        starsEl.className = 'e9-zone__stars';
        starsEl.textContent = '★'.repeat(zone.stars) + '☆'.repeat(3 - zone.stars);
        tile.appendChild(starsEl);
      }

      if (zone.bossAvailable) {
        var bossEl = document.createElement('span');
        bossEl.className = 'e9-zone__boss-ready';
        bossEl.textContent = t('index.adv.boss_ready', 'Seal broken').split(':')[0];
        tile.appendChild(bossEl);
      }

      if (!zone.locked) {
        var activate = function () {
          tile.dispatchEvent(new CustomEvent('e9:zone-selected', {
            bubbles: true,
            detail: { zoneKey: zone.key, status: zone.status },
          }));
          try {
            window.E9.startAdventureFromE9(zone.key);
          } catch (err) {
            // Interaction-time failure -- logged, not a critical-recovery
            // trigger (the shell itself is still healthy and displayed).
            console.error('[E9] world_stage: failed to start adventure for', zone.key, err);
          }
        };
        tile.addEventListener('click', activate);
        tile.addEventListener('keydown', function (evt) {
          if (evt.key === 'Enter' || evt.key === ' ') {
            evt.preventDefault();
            activate();
          }
        });
      }

      zonesEl.appendChild(tile);
    });

    zonesEl.hidden = false;
    if (statusEl) {
      var clearedCount = zones.filter(function (z) { return z.cleared; }).length;
      statusEl.textContent = t('index.adv.summary', '{n} / {t} areas cleared')
        .replace('{n}', clearedCount).replace('{t}', zones.length);
      // #e9-world-stage-status starts with a static data-i18n="e9.world_stage.loading"
      // placeholder; remove it once real summary text is set so a later,
      // unrelated I18n.apply() elsewhere on the page cannot silently revert
      // it back to "Loading…" (same class of bug fixed in top_hud.js /
      // right_cards.js, live-verified during E9.1A2 Rev2).
      statusEl.removeAttribute('data-i18n');
    }
  }

  function recoverToLegacy(reason) {
    console.error('[E9] world_stage CRITICAL: adventure data unavailable, recovering to legacy:', reason);
    if (window.E9 && typeof window.E9.recoverToLegacy === 'function') {
      window.E9.recoverToLegacy(reason);
    }
  }

  function load(root, isRetry) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.AdventureState;
    if (!adapter) {
      recoverToLegacy(new Error('AdventureState adapter not loaded'));
      return;
    }

    adapter.fetchAdventureState().then(function (result) {
      if (!result.ok) {
        if (result.kind === 'unauthorized') {
          recoverToLegacy(new Error('unauthorized (status ' + result.status + ')'));
          return;
        }
        if (!isRetry) {
          // One retry for a recoverable (network/5xx) failure before
          // giving up and falling back to legacy.
          root.dispatchEvent(new CustomEvent('e9:refresh-requested', {
            bubbles: true,
            detail: { component: 'world_stage', reason: result.kind },
          }));
          load(root, true);
          return;
        }
        recoverToLegacy(new Error('adventure data fetch failed: ' + result.kind + ' (status ' + result.status + ')'));
        return;
      }
      if (!result.data.zones.length) {
        // Structurally valid response but zero usable zones -- still a
        // critical condition (World Stage has nothing real to show), not
        // rendered as a fabricated empty board.
        recoverToLegacy(new Error('adventure data returned zero valid zones'));
        return;
      }
      renderZones(root, result.data.zones);
    }).catch(function (err) {
      recoverToLegacy(err);
    });
  }

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');
    load(root, false);
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'world_stage') {
      init(e.detail.root);
    }
  });
})(document);
