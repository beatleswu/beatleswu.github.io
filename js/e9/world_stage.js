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
 * Zone selection dispatches "e9:zone-selected" (bubbles) and updates the
 * ephemeral detail selection. Only the detail CTA invokes the adapter, so
 * selecting a card never starts an encounter or changes progression state.
 */
(function (document) {
  'use strict';

  function t(key, fallback) {
    if (window.E9 && window.E9.I18nFallback && typeof window.E9.I18nFallback.t === 'function') {
      return window.E9.I18nFallback.t(key, fallback);
    }
    return fallback;
  }

  // Same locale check the legacy Adventure Map's own _zoneEn()/_zoneName()
  // already use (index.html) -- zone names are plain strings, not i18n.js
  // dictionary keys, so this picks between the two API-provided fields
  // directly rather than going through t()/I18nFallback. Falls back to
  // `name` (the Chinese source string) whenever English isn't selected OR
  // a zone's `nameEn` is missing -- never a blank label or a raw key.
  function isEnglishLocale() {
    return typeof window.I18n !== 'undefined' && typeof window.I18n.getLang === 'function' && window.I18n.getLang() === 'en';
  }
  function zoneDisplayName(zone) {
    if (!zone) return '';
    if (isEnglishLocale() && zone.nameEn) return zone.nameEn;
    return zone.name;
  }

  function renderBeginnerVillageMainline(root, zone) {
    var panel = root.querySelector('#e9-newbie-mainline');
    if (!panel || !zone || zone.key !== 'k26_30') return;

    var setText = function (selector, key, fallback) {
      var el = panel.querySelector(selector);
      if (el) el.textContent = t(key, fallback);
    };
    setText('#e9-newbie-mainline-kicker', 'adventure.newbie.first_stop', 'First Stop');
    setText('#e9-newbie-mainline-title', 'adventure.newbie.first_stop_title', 'First Stop: Beginner Village');
    setText('#e9-newbie-mainline-summary', 'adventure.newbie.summary', 'Defeat the village monsters, complete your training, and challenge the Village Examiner.');
    setText(
      '#e9-newbie-mainline-boss',
      zone.bossAvailable ? 'adventure.newbie.boss_ready' : 'adventure.newbie.objective',
      zone.bossAvailable ? 'Village Examiner: prepare for your challenge.' : 'Keep training to challenge the Village Examiner.'
    );
    setText('#e9-newbie-mainline-goal', 'adventure.newbie.first_star_hint', 'Defeat the boss to earn your first star.');

    var steps = panel.querySelector('#e9-newbie-mainline-steps');
    if (steps) {
      steps.innerHTML = '';
      [
        ['adventure.newbie.step_battle', 'Solve and battle'],
        ['adventure.newbie.step_progress', 'Build progress'],
        ['adventure.newbie.step_boss', 'Challenge the boss'],
      ].forEach(function (item) {
        var li = document.createElement('li');
        li.textContent = t(item[0], item[1]);
        steps.appendChild(li);
      });
    }

    var cta = panel.querySelector('#e9-newbie-mainline-cta');
    if (cta) {
      var ctaKey = zone.bossAvailable
        ? 'adventure.newbie.cta_boss'
        : (zone.cleared || zone.stars > 0
          ? 'adventure.newbie.cta_continue'
          : 'adventure.newbie.cta_begin');
      cta.textContent = t(ctaKey, 'Begin the Beginner Village Adventure');
      if (cta.__e9AdventureHandler) {
        cta.removeEventListener('click', cta.__e9AdventureHandler);
      }
      cta.__e9AdventureHandler = function () {
        if (window.E9 && typeof window.E9.startAdventureFromE9 === 'function') {
          window.E9.startAdventureFromE9(zone.key);
        }
      };
      if (window.E9 && typeof window.E9.on === 'function') {
        window.E9.on(cta, 'click', cta.__e9AdventureHandler);
      } else {
        cta.addEventListener('click', cta.__e9AdventureHandler);
      }
    }
    panel.hidden = false;
  }

  function renderSelectedZone(root, zones, zoneKey, focusDetails) {
    var state = root.__e9WorldStageState;
    var zone = zones.filter(function (item) { return item.key === zoneKey; })[0];
    var details = root.querySelector('#e9-world-stage-details');
    var label = root.querySelector('#e9-world-stage-details-label');
    var summary = root.querySelector('#e9-world-stage-details-summary');
    var newbie = root.querySelector('#e9-newbie-mainline');
    if (!zone || zone.locked) return;

    state.selectedZoneKey = zone.key;
    root.querySelectorAll('[data-zone]').forEach(function (tile) {
      var selected = tile.getAttribute('data-zone') === zone.key;
      tile.setAttribute('aria-pressed', selected ? 'true' : 'false');
      tile.classList.toggle('is-selected', selected);
    });
    if (details) details.hidden = false;
    if (label) label.textContent = zoneDisplayName(zone) || zone.key;
    if (summary) summary.textContent = zone.bossAvailable
      ? t('index.adv.boss_ready', 'Boss challenge ready')
      : (zone.cleared ? t('index.adv.boss_cleared', 'Area cleared') : t('index.adv.panel_ready', 'Adventure is ready'));
    renderBeginnerVillageMainline(root, zone);
    if (newbie && zone.key !== 'k26_30') newbie.hidden = true;
    if (focusDetails && details) {
      var focusTarget = zone.key === 'k26_30' && newbie && !newbie.hidden ? newbie : details;
      try { focusTarget.focus({ preventScroll: true }); } catch (err) { focusTarget.focus(); }
      if (typeof focusTarget.scrollIntoView === 'function' && window.matchMedia && window.matchMedia('(max-width: 900px)').matches) {
        focusTarget.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }

  function renderZones(root, zones) {
    var statusEl = root.querySelector('#e9-world-stage-status');
    var zonesEl = root.querySelector('#e9-world-stage-zones');
    if (!zonesEl) return;

    var state = root.__e9WorldStageState || (root.__e9WorldStageState = { zones: zones, selectedZoneKey: null });
    state.zones = zones;
    zonesEl.innerHTML = '';
    zones.forEach(function (zone) {
      var tile = document.createElement('div');
      tile.className = 'e9-zone e9-zone--' + (zone.status || 'locked');
      tile.setAttribute('role', 'listitem');
      tile.setAttribute('data-zone', zone.key);

      if (!zone.locked) {
        tile.setAttribute('aria-pressed', 'false');
        tile.tabIndex = 0;
        tile.setAttribute('role', 'button');
      } else {
        tile.setAttribute('aria-disabled', 'true');
        tile.title = t('index.adv.zone_locked', 'This area is still sealed by mist.');
      }

      // Zone display name: English locale prefers zone.nameEn (from the
      // API's name_en field), falling back to zone.name (Chinese) if
      // English isn't selected or nameEn is missing -- same precedence
      // the legacy Adventure Map's own _zoneName() already uses.
      var label = document.createElement('span');
      label.className = 'e9-zone__name';
      label.textContent = zoneDisplayName(zone);
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
          renderSelectedZone(root, zones, zone.key, true);
        };
        var keyActivate = function (evt) {
          if (evt.key === 'Enter' || evt.key === ' ') {
            evt.preventDefault();
            activate();
          }
        };
        if (window.E9 && typeof window.E9.on === 'function') {
          window.E9.on(tile, 'click', activate);
          window.E9.on(tile, 'keydown', keyActivate);
        } else {
          tile.addEventListener('click', activate);
          tile.addEventListener('keydown', keyActivate);
        }
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
    var selected = state.selectedZoneKey && zones.filter(function (zone) { return zone.key === state.selectedZoneKey; })[0];
    if (selected && !selected.locked) renderSelectedZone(root, zones, selected.key, false);
  }

  function recoverToLegacy(reason) {
    console.error('[E9] world_stage CRITICAL: adventure data unavailable, recovering to legacy:', reason);
    if (window.E9 && typeof window.E9.recoverToLegacy === 'function') {
      window.E9.recoverToLegacy(reason);
    }
  }

  function load(root, isRetry, generation) {
    var current = function () {
      return !window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' ||
        window.E9.isLifecycleCurrent(generation);
    };
    if (!current()) return;
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.AdventureState;
    if (!adapter) {
      recoverToLegacy(new Error('AdventureState adapter not loaded'));
      return;
    }

    adapter.fetchAdventureState().then(function (result) {
      if (!current()) return;
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
          load(root, true, generation);
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
      if (!current()) return;
      recoverToLegacy(err);
    });
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');
    root.__e9WorldStageState = { zones: [], selectedZoneKey: null };
    var onChanged = function () {
      var state = root.__e9WorldStageState;
      if ((!window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation)) && state && state.zones && state.zones.length) renderZones(root, state.zones);
    };
    var onReady = function () {
      var state = root.__e9WorldStageState;
      if ((!window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation)) && state && state.zones && state.zones.length) renderZones(root, state.zones);
    };
    if (window.E9 && typeof window.E9.on === 'function') {
      window.E9.on(document, 'e9:i18n-changed', onChanged, null, generation);
      window.E9.on(document, 'e9:i18n-ready', onReady, null, generation);
    } else {
      document.addEventListener('e9:i18n-changed', onChanged);
      document.addEventListener('e9:i18n-ready', onReady);
    }
    load(root, false, generation);
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'world_stage') {
      init(e.detail.root, e.detail.generation);
    }
  });
})(document);
