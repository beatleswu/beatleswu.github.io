/*
 * E9 World Stage — component init (CRITICAL).
 * Operates only on its own root. Real data source only:
 *   GET /api/adventure/bootstrap -> zones[] (same endpoint the legacy
 *   Adventure Map uses; no new API, no fabricated zone data).
 * Zone-state text reuses the EXISTING index.adv.* i18n keys — no second
 * translation dictionary for adventure semantics.
 * If the data fetch fails, this is treated as a CRITICAL failure (a
 * World Stage that can't show real state is non-functional) and
 * triggers full shell recovery to the legacy Adventure Map via
 * window.E9.recoverToLegacy(), NOT just a local error message.
 * Adventure Start uses the thin adapter window.E9.startAdventureFromE9()
 * (defined in shell.js), which calls the existing legacy
 * startAdventureStage() global — no gameplay logic is duplicated here.
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

      var isLocked = zone.status === 'locked';
      if (!isLocked) {
        tile.tabIndex = 0;
        tile.setAttribute('role', 'button');
      } else {
        tile.setAttribute('aria-disabled', 'true');
        tile.title = t('index.adv.zone_locked', 'This area is still sealed by mist.');
      }

      // Zone display name comes straight from the API (zone.name), same
      // as the legacy map — there is no separate English zone-name field
      // to translate against.
      var label = document.createElement('span');
      label.className = 'e9-zone__name';
      label.textContent = zone.name || zone.key;
      tile.appendChild(label);

      var stars = Math.max(0, Math.min(3, Number(zone.stars) || 0));
      if (zone.status === 'completed' || stars > 0) {
        var starsEl = document.createElement('span');
        starsEl.className = 'e9-zone__stars';
        starsEl.textContent = '★'.repeat(stars) + '☆'.repeat(3 - stars);
        tile.appendChild(starsEl);
      }

      if (zone.boss && zone.boss.available) {
        var bossEl = document.createElement('span');
        bossEl.className = 'e9-zone__boss-ready';
        bossEl.textContent = t('index.adv.boss_ready', 'Seal broken').split(':')[0];
        tile.appendChild(bossEl);
      }

      if (!isLocked) {
        tile.addEventListener('click', function () {
          try {
            window.E9.startAdventureFromE9(zone.key);
          } catch (err) {
            // Interaction-time failure — logged, not a critical-recovery
            // trigger (the shell itself is still healthy and displayed).
            console.error('[E9] world_stage: failed to start adventure for', zone.key, err);
          }
        });
        tile.addEventListener('keydown', function (evt) {
          if (evt.key === 'Enter' || evt.key === ' ') {
            evt.preventDefault();
            tile.click();
          }
        });
      }

      zonesEl.appendChild(tile);
    });

    zonesEl.hidden = false;
    if (statusEl) {
      var clearedCount = zones.filter(function (z) { return z.status === 'completed'; }).length;
      statusEl.textContent = t('index.adv.summary', '{n} / {t} areas cleared')
        .replace('{n}', clearedCount).replace('{t}', zones.length);
    }
  }

  function init(root) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');

    fetch('/api/adventure/bootstrap', { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        var zones = (data && data.zones) || [];
        renderZones(root, zones);
      })
      .catch(function (err) {
        console.error('[E9] world_stage CRITICAL: adventure data fetch failed, recovering to legacy:', err);
        if (window.E9 && typeof window.E9.recoverToLegacy === 'function') {
          window.E9.recoverToLegacy(err);
        }
      });
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'world_stage') {
      init(e.detail.root);
    }
  });
})(document);
