/*
 * E9 World Stage — component init (CRITICAL).
 * Reads canonical adventure state via js/e9/adapters/adventure_state.js
 * (single source of truth -- no second progression state is created or
 * persisted here). Real data source only:
 *   GET /api/adventure/bootstrap -> zones[] (same endpoint the legacy
 *   Adventure Map uses; no new API, no fabricated zone data).
 * Progression summaries reuse the EXISTING index.adv.* i18n keys; compact
 * presentation labels use the shared i18n.js registry. No component-local
 * translation dictionary or progression mapping is created.
 * If the data fetch fails (or the session is unauthorized), this is
 * treated as a CRITICAL failure (a World Stage that can't show real
 * state is non-functional) and triggers full shell recovery to the
 * legacy Adventure Map via window.E9.recoverToLegacy(), NOT just a local
 * error message. A single retry is offered first for a recoverable
 * (non-auth) error, dispatching "e9:refresh-requested" before falling
 * back to recovery if the retry also fails.
 * Adventure Start uses the thin adapter window.E9.startAdventureFromE9()
 * (defined in shell.js), which calls the existing canonical in-page
 * question entry -- no gameplay logic is duplicated here.
 * Zone selection dispatches "e9:zone-selected" (bubbles) and updates the
 * ephemeral detail selection. Only the detail CTA invokes the adapter, so
 * selecting a card never starts an encounter or changes progression state.
 */
(function (document) {
  'use strict';

  // Static/runtime compatibility bridge. This value is intentionally read
  // once from an exact marker baked into the static index. Query parameters,
  // hostname, browser storage and mutable window globals are not inputs.
  var VS1E_STATIC_CONTRACT = 'e10-vs1f-integrated-world-map';
  var staticContractMarker = document.querySelector(
    'meta[name="go-odyssey-static-contract"]'
  );
  var VS1E_STATIC_CONTRACT_ACTIVE = !!staticContractMarker
    && staticContractMarker.getAttribute('content') === VS1E_STATIC_CONTRACT;

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

  // VS1D-1 canonical map-stage-local coordinates, normalized against the
  // 900 x 506 SVG frame. The same values position L5 nodes, reserved L6
  // boss anchors, and the L7 current-player marker; never viewport pixels.
  var ZONE_ANCHORS = {
    k26_30: { x: 26.0, y: 69.6 }, k21_25: { x: 36.3, y: 48.6 },
    k16_20: { x: 33.1, y: 29.4 }, k11_15: { x: 46.0, y: 26.3 },
    k6_10: { x: 57.6, y: 32.6 }, k1_5: { x: 71.4, y: 31.4 },
    d1_2: { x: 80.0, y: 44.7 }, d3_4: { x: 70.3, y: 65.0 },
    d5_6: { x: 56.0, y: 74.3 }, d7_plus: { x: 84.8, y: 23.1 }
  };
  var VS1F_ZONE_ANCHORS = {
    k26_30: { x: 14.5, y: 77.0 }, k21_25: { x: 28.0, y: 67.5 },
    k16_20: { x: 16.5, y: 39.1 }, k11_15: { x: 36.0, y: 53.4 },
    k6_10: { x: 62.0, y: 53.4 }, k1_5: { x: 75.0, y: 38.3 },
    d1_2: { x: 87.0, y: 51.5 }, d3_4: { x: 75.0, y: 76.5 },
    d5_6: { x: 53.0, y: 39.1 }, d7_plus: { x: 43.0, y: 18.5 }
  };
  var BOSS_ANCHORS = {
    k26_30: { x: 19.1, y: 65.8 }, k21_25: { x: 42.3, y: 56.9 },
    k16_20: { x: 28.0, y: 23.9 }, k11_15: { x: 51.1, y: 22.3 },
    k6_10: { x: 64.0, y: 27.1 }, k1_5: { x: 76.3, y: 36.8 },
    d1_2: { x: 75.1, y: 50.4 }, d3_4: { x: 77.6, y: 68.8 },
    d5_6: { x: 50.8, y: 68.8 }, d7_plus: { x: 79.1, y: 17.6 }
  };
  var ZONE_PLAQUE_SIDES = {
    k26_30: 'right', k21_25: 'left', k16_20: 'left', k11_15: 'top',
    k6_10: 'bottom', k1_5: 'left', d1_2: 'left', d3_4: 'right',
    d5_6: 'left', d7_plus: 'left'
  };
  var ZONE_LANDMARKS = {
    k26_30: '/assets/maps/e10-vs1f-landmarks/zone-01-beginner-village.webp',
    k21_25: '/assets/maps/e10-vs1f-landmarks/zone-02-slime-plains.webp',
    k16_20: '/assets/maps/e10-vs1f-landmarks/zone-03-goblin-cave.webp',
    k11_15: '/assets/maps/e10-vs1f-landmarks/zone-04-twilight-forest.webp',
    k6_10: '/assets/maps/e10-vs1f-landmarks/zone-05-sky-tower.webp',
    k1_5: '/assets/maps/e10-vs1f-landmarks/zone-06-royal-castle.webp',
    d1_2: '/assets/maps/e10-vs1f-landmarks/zone-07-star-sea-passage.webp',
    d3_4: '/assets/maps/e10-vs1f-landmarks/zone-08-abyssal-forge.webp',
    d5_6: '/assets/maps/e10-vs1f-landmarks/zone-09-eternal-night-shrine.webp',
    d7_plus: '/assets/maps/e10-vs1f-landmarks/zone-10-ancient-doom-temple.webp'
  };

  function applyAnchor(el, anchor) {
    if (!el || !anchor) return;
    el.style.setProperty('--anchor-x', anchor.x + '%');
    el.style.setProperty('--anchor-y', anchor.y + '%');
  }

  function resolvePlayerLocation(zones) {
    // The normalized API status is progression state; selectedZoneKey is
    // ephemeral inspection state and is deliberately not an input. The first
    // canonical unlocked frontier is the current location. If the progression
    // response exposes no unlocked frontier, fail closed with no hero marker.
    return zones.filter(function (zone) {
      return !zone.locked && zone.status === 'unlocked';
    })[0] || null;
  }

  function findZone(zones, zoneKey) {
    return zones.filter(function (zone) { return zone.key === zoneKey; })[0] || null;
  }

  function resolveChallengeTargetZoneKey(zone) {
    return zone && !zone.locked && zone.canEnter !== false ? zone.key : null;
  }

  function syncInteractionState(state, zones) {
    var current = resolvePlayerLocation(zones);
    var selected = findZone(zones, state.selectedZoneKey) || current || zones[0] || null;
    state.currentPlayerZoneKey = current ? current.key : null;
    state.selectedZoneKey = selected ? selected.key : null;
    state.challengeTargetZoneKey = resolveChallengeTargetZoneKey(selected);
    return { current: current, selected: selected };
  }

  function ctaContract(zone, state) {
    var target = resolveChallengeTargetZoneKey(zone);
    if (!target) {
      return { enabled: false, targetZoneKey: null, label: t('e10.world_stage.state_locked', 'Locked') };
    }
    if (zone.status === 'completed') {
      return { enabled: true, targetZoneKey: target, label: t('index.adv.quest_replay_training', 'Star training') };
    }
    if (zone.status === 'skipped_by_placement') {
      return { enabled: true, targetZoneKey: target, label: t('index.adv.skipped_replay', 'Star training available') };
    }
    return {
      enabled: true,
      targetZoneKey: target,
      label: target === state.currentPlayerZoneKey
        ? t('e10.world_stage.continue_adventure', 'Continue Adventure')
        : t('index.adv.start_challenge', 'Start Challenge'),
    };
  }

  function usesLandmarkCards() {
    return !!(window.matchMedia && window.matchMedia('(max-width: 767px)').matches);
  }

  function updateRouteProgress(root, zones) {
    if (!VS1E_STATIC_CONTRACT_ACTIVE || !zones.length) return;
    var completed = zones.filter(function (zone) {
      return zone.cleared || zone.status === 'completed';
    }).length;
    var progressValue = root.querySelector('[data-e10-adventure-progress-value]');
    var progressBar = root.querySelector('[data-e10-adventure-progress-bar]');
    if (progressValue) progressValue.textContent = completed + ' / ' + zones.length;
    if (progressBar) progressBar.style.width = Math.max(0, Math.min(100, completed / zones.length * 100)) + '%';
  }

  function enableImmersiveRpgSkin(root, generation) {
    var shell = root && root.closest ? root.closest('#e9-adventure-shell') : null;
    if (!shell) return;
    if (!VS1E_STATIC_CONTRACT_ACTIVE) {
      shell.removeAttribute('data-e10-visual-skin');
      document.body.removeAttribute('data-e10-visual-skin');
      return;
    }
    shell.setAttribute('data-e10-visual-skin', 'immersive-rpg');
    shell.setAttribute('data-e10-art-kit', 'runtime-v1');
    document.body.setAttribute('data-e10-visual-skin', 'immersive-rpg');
    document.body.setAttribute('data-e10-art-kit', 'runtime-v1');
    var mapStage = root.querySelector('#e9-map-stage');
    if (mapStage && !mapStage.querySelector('[data-e10-adventure-progress]')) {
      var progress = document.createElement('section');
      progress.className = 'e10-adventure-progress';
      progress.setAttribute('data-e10-adventure-progress', '');
      progress.setAttribute('aria-label', t('e10.world_stage.adventure_progress', 'Adventure progress'));
      var registry = window.E9 && window.E9.NavigationRegistry;
      progress.innerHTML = (registry ? registry.icon('compass', 'e10-adventure-progress__icon') : '')
        + '<span class="e10-adventure-progress__copy"><strong data-i18n="e10.world_stage.adventure_progress"></strong>'
        + '<span data-e10-adventure-progress-value>0 / 10</span></span>'
        + '<span class="e10-adventure-progress__track" aria-hidden="true"><span data-e10-adventure-progress-bar></span></span>';
      mapStage.appendChild(progress);
      if (window.I18n && window.I18n.apply) window.I18n.apply(progress);
    }
    if (window.E9 && typeof window.E9.registerCleanup === 'function') {
      window.E9.registerCleanup(function () {
        shell.removeAttribute('data-e10-visual-skin');
        shell.removeAttribute('data-e10-art-kit');
        document.body.removeAttribute('data-e10-visual-skin');
        document.body.removeAttribute('data-e10-art-kit');
        if (window.E9) delete window.E9.latestZoneSelection;
      }, generation);
    }
  }

  function prepareVs1dDom(root) {
    if (VS1E_STATIC_CONTRACT_ACTIVE) return;
    root.querySelectorAll('[data-e10-vs1f-route-layer]').forEach(function (path) { path.remove(); });
    var ground = root.querySelector('.e9-route__ground');
    var ascension = root.querySelector('.e9-route__ascension');
    if (ground) {
      ground.setAttribute('class', 'e9-route__ground');
      ground.removeAttribute('pathLength');
    }
    if (ascension) {
      ascension.setAttribute('class', 'e9-route__ascension');
      ascension.removeAttribute('pathLength');
    }
    root.querySelectorAll('[data-player-location]').forEach(function (tile) {
      tile.removeAttribute('data-player-location');
      tile.classList.remove('is-current');
    });
    root.querySelectorAll('.e10-current-hero, .e10-zone-landmark').forEach(function (element) {
      element.remove();
    });
    var mapStage = root.querySelector('#e9-map-stage');
    var status = root.querySelector('#e9-world-stage-status');
    if (mapStage && status && status.parentNode === mapStage) {
      mapStage.parentNode.insertBefore(status, mapStage);
    }
    [
      '#e9-world-stage-primary-cta',
      '.e9-zone-details__kicker',
      '#e9-world-stage-details-state',
      '#e9-world-stage-details-progress',
    ].forEach(function (selector) {
      var element = root.querySelector(selector);
      if (element) element.hidden = true;
    });
  }

  function configureBaseMap(root) {
    var base = root.querySelector('.e9-map-stage__base');
    if (!base) return;
    if (VS1E_STATIC_CONTRACT_ACTIVE) {
      base.src = '/assets/maps/e10_world_stage_v2_clean.webp';
      base.width = 2048;
      base.height = 1152;
      base.setAttribute('data-e10-vs1f-clean-map', 'v2');
      return;
    }
    base.src = base.getAttribute('data-vs1d-src') || '/assets/maps/e10_world_stage_v1_base.webp';
    base.width = 1672;
    base.height = 941;
    base.removeAttribute('data-e10-vs1f-clean-map');
  }

  function ensureVs1fRouteLayers(root, zones) {
    if (!VS1E_STATIC_CONTRACT_ACTIVE) return;
    var route = root.querySelector('.e9-map-stage__route');
    var ground = route && route.querySelector('.e9-route__ground');
    var ascension = route && route.querySelector('.e9-route__ascension');
    if (!route || !ground || !ascension) return;
    route.setAttribute('viewBox', '0 0 1000 562');
    route.querySelectorAll('[data-e10-vs1f-route-layer]').forEach(function (path) { path.remove(); });
    zones.forEach(function (zone, index) {
      var next = zones[index + 1];
      var from = VS1F_ZONE_ANCHORS[zone.key];
      var to = next && VS1F_ZONE_ANCHORS[next.key];
      if (!next || !from || !to) return;
      var x1 = from.x * 10;
      var y1 = from.y * 5.62;
      var x2 = to.x * 10;
      var y2 = to.y * 5.62;
      var bend = index % 2 === 0 ? -18 : 18;
      var pathData = 'M' + x1 + ' ' + y1
        + ' C' + (x1 + (x2 - x1) * 0.34) + ' ' + (y1 + bend)
        + ' ' + (x1 + (x2 - x1) * 0.66) + ' ' + (y2 - bend)
        + ' ' + x2 + ' ' + y2;
      var state = (zone.status === 'completed' || next.status === 'completed')
        ? 'completed'
        : (next.locked ? 'locked' : 'available');
      var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('class', 'e9-route__material e9-route__material--' + state);
      path.setAttribute('d', pathData);
      path.setAttribute('data-e10-route-from', zone.key);
      path.setAttribute('data-e10-route-to', next.key);
      path.setAttribute('data-e10-route-state', state);
      path.setAttribute('data-e10-vs1f-route-layer', '');
      route.appendChild(path);
    });
  }

  function syncPlayerMarkerPortrait(root, explicitSource) {
    if (!VS1E_STATIC_CONTRACT_ACTIVE) return;
    var hudAvatar = document.querySelector('#top-hud-avatar-image');
    var source = explicitSource || (hudAvatar && hudAvatar.getAttribute('src')) || '';
    if (!source) return;
    var mobileCards = window.matchMedia && window.matchMedia('(max-width: 767px)').matches;
    var hosts = Array.prototype.slice.call(root.querySelectorAll(
      mobileCards ? '.e10-current-hero' : '#e9-world-stage-player'
    ));
    root.querySelectorAll('.e10-player-marker-portrait').forEach(function (portrait) {
      if (hosts.indexOf(portrait.parentNode) === -1) portrait.remove();
    });
    hosts.forEach(function (host) {
      var portrait = host.querySelector('.e10-player-marker-portrait');
      if (!portrait) {
        portrait = document.createElement('img');
        portrait.className = 'e10-player-marker-portrait';
        portrait.alt = '';
        portrait.width = 64;
        portrait.height = 64;
        portrait.decoding = 'async';
        portrait.draggable = false;
        portrait.setAttribute('aria-hidden', 'true');
        host.appendChild(portrait);
      }
      if (portrait.getAttribute('src') !== source) portrait.setAttribute('src', source);
    });
  }

  function updatePlayerMarker(root, zone) {
    var marker = root.querySelector('#e9-world-stage-player');
    var anchor = zone && (VS1E_STATIC_CONTRACT_ACTIVE ? VS1F_ZONE_ANCHORS : ZONE_ANCHORS)[zone.key];
    var mapStage = root.querySelector('#e9-map-stage');
    root.querySelectorAll('.e10-current-hero').forEach(function (hero) { hero.remove(); });
    if (!marker) return;
    if (!zone || !anchor) {
      marker.hidden = true;
      return;
    }
    if (usesLandmarkCards()) {
      marker.hidden = true;
      var currentTile = root.querySelector('[data-zone="' + zone.key + '"]');
      if (currentTile) {
        var mobileHero = document.createElement('span');
        mobileHero.className = 'e10-current-hero';
        mobileHero.setAttribute('aria-hidden', 'true');
        currentTile.appendChild(mobileHero);
        syncPlayerMarkerPortrait(root);
      }
      return;
    }
    applyAnchor(marker, anchor);
    if (mapStage) {
      mapStage.style.setProperty('--focus-x', anchor.x + '%');
      mapStage.style.setProperty('--focus-y', anchor.y + '%');
    }
    marker.hidden = false;
    syncPlayerMarkerPortrait(root);
  }

  function newbieCtaText(zone) {
    var ctaKey = zone && zone.bossAvailable
      ? 'adventure.newbie.cta_boss'
      : (zone && (zone.cleared || zone.stars > 0)
        ? 'adventure.newbie.cta_continue'
        : 'adventure.newbie.cta_begin');
    return t(ctaKey, 'Begin the Beginner Village Adventure');
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
      cta.textContent = newbieCtaText(zone);
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

  // Progression summaries reuse existing index.adv.* keys (see
  // world_stage.html's header comment), while compact state labels resolve
  // through the shared i18n registry. index.adv.boss_ready is a template
  // ('Seal broken: {seen}/{total}' / '封印解除：{seen}/{total} 題'); callers
  // MUST substitute both placeholders themselves (I18nFallback.t() only
  // returns the raw string -- same contract as legacy's own I18n.t()
  // callers, e.g. index.html's node_title `.replace('{seen}',...)` chain).
  function bossReadyText(zone) {
    return t('index.adv.boss_ready', 'Seal broken: {seen}/{total}')
      .replace('{seen}', String(zone.seen))
      .replace('{total}', String(zone.total));
  }

  // index.adv.boss_cleared is likewise a template ('Defeated {stars}' /
  // '已擊破 {stars}') -- same substitution contract as bossReadyText above.
  function clearedText(zone) {
    return t('index.adv.boss_cleared', 'Defeated {stars}')
      .replace('{stars}', String(zone.stars));
  }

  function zoneStateText(zone) {
    if (zone.locked) return t('e10.world_stage.state_locked', 'Locked');
    if (zone.cleared || zone.status === 'completed') {
      return t('e10.world_stage.state_completed', 'Completed');
    }
    if (zone.status === 'skipped_by_placement') {
      return t('index.adv.status_skipped_by_placement', 'Star training available');
    }
    if (zone.__e10PlayerLocation) {
      return t('e10.world_stage.state_current', 'Current location');
    }
    return t('e10.world_stage.state_available', 'Available');
  }

  function zoneSummaryText(zone) {
    if (zone.status === 'skipped_by_placement') {
      return t('index.adv.skipped_help', 'Use this area to earn stars and strengthen your basics.');
    }
    if (zone.locked) return t('index.adv.zone_locked', 'This area is still sealed by mist.');
    return zone.bossAvailable
      ? bossReadyText(zone)
      : (zone.cleared ? clearedText(zone) : t('index.adv.panel_ready', 'Adventure is ready'));
  }

  function zoneProgressText(zone) {
    return t('e10.world_stage.zone_progress', 'Quest progress {seen}/{total}')
      .replace('{seen}', String(zone.seen || 0))
      .replace('{total}', String(zone.total || 0));
  }

  function setSelectedTileState(root, zoneKey) {
    root.querySelectorAll('[data-zone]').forEach(function (tile) {
      var selected = tile.getAttribute('data-zone') === zoneKey;
      if (tile.getAttribute('aria-disabled') !== 'true') {
        tile.setAttribute('aria-pressed', selected ? 'true' : 'false');
      }
      tile.classList.toggle('is-selected', selected);
    });
  }

  function configureAdventureButton(button, zone, contract) {
    if (!button || !zone || !contract) {
      if (button) button.hidden = true;
      return;
    }
    button.hidden = false;
    button.disabled = !contract.enabled;
    button.setAttribute('aria-disabled', contract.enabled ? 'false' : 'true');
    button.setAttribute('data-challenge-target-zone', contract.targetZoneKey || '');
    button.textContent = contract.label;
    if (button.__e9AdventureHandler) {
      button.removeEventListener('click', button.__e9AdventureHandler);
    }
    button.__e9AdventureHandler = function () {
      if (contract.enabled && contract.targetZoneKey && window.E9 && typeof window.E9.startAdventureFromE9 === 'function') {
        window.E9.startAdventureFromE9(contract.targetZoneKey);
      }
    };
    if (window.E9 && typeof window.E9.on === 'function') {
      window.E9.on(button, 'click', button.__e9AdventureHandler);
    } else {
      button.addEventListener('click', button.__e9AdventureHandler);
    }
  }

  function configurePrimaryCta(root, zone, state) {
    var primary = root.querySelector('#e9-world-stage-primary-cta');
    if (!VS1E_STATIC_CONTRACT_ACTIVE) {
      if (primary) primary.hidden = true;
      return;
    }
    var contract = zone && ctaContract(zone, state);
    var label = contract ? contract.label : '';
    configureAdventureButton(primary, zone, contract);
    if (primary && zone && !primary.hidden) {
      var registry = window.E9 && window.E9.NavigationRegistry;
      primary.innerHTML = (registry ? registry.icon('compass', 'e10-map-primary-cta__icon') : '')
        + '<span class="e10-map-primary-cta__copy"><strong>' + label + '</strong>'
        + '<span>' + (zoneDisplayName(zone) || zone.key) + '</span></span>';
      primary.setAttribute('aria-label', label + ': ' + (zoneDisplayName(zone) || zone.key));
    }
  }

  function updateSelectedZoneCopy(root, zone) {
    var landmark = root.querySelector('#e9-world-stage-details-landmark');
    var number = root.querySelector('#e9-world-stage-details-number');
    var stars = root.querySelector('#e9-world-stage-details-stars');
    var label = root.querySelector('#e9-world-stage-details-label');
    var stateText = root.querySelector('#e9-world-stage-details-state');
    var summary = root.querySelector('#e9-world-stage-details-summary');
    var progress = root.querySelector('#e9-world-stage-details-progress');
    var regionProgress = root.querySelector('#e9-world-stage-details-region-progress');
    if (number) number.textContent = 'Zone ' + (zone.__e10Index || 0);
    if (stars) stars.textContent = '\u2605 ' + String(zone.stars || 0);
    if (label) label.textContent = zoneDisplayName(zone) || zone.key;
    if (stateText) {
      stateText.hidden = !VS1E_STATIC_CONTRACT_ACTIVE;
      if (VS1E_STATIC_CONTRACT_ACTIVE) stateText.textContent = zoneStateText(zone);
    }
    if (summary) summary.textContent = zoneSummaryText(zone);
    if (progress) {
      progress.hidden = !VS1E_STATIC_CONTRACT_ACTIVE;
      if (VS1E_STATIC_CONTRACT_ACTIVE) progress.textContent = (zone.seen || 0) + ' / ' + (zone.total || 0);
    }
    if (regionProgress) regionProgress.textContent = (zone.__e10Index || 0) + ' / 10';
    var portraitSurface = window.matchMedia && window.matchMedia(
      '(min-width: 768px) and (max-width: 1279px) and (orientation: portrait)'
    ).matches;
    if (landmark) {
      if (portraitSurface && ZONE_LANDMARKS[zone.key]) {
        if (landmark.getAttribute('src') !== ZONE_LANDMARKS[zone.key]) {
          landmark.setAttribute('src', ZONE_LANDMARKS[zone.key]);
        }
        landmark.hidden = false;
      } else {
        landmark.hidden = true;
        landmark.removeAttribute('src');
      }
    }
  }

  function zoneSelectionDetail(zone, state) {
    var contract = ctaContract(zone, state);
    var isCurrent = zone.key === state.currentPlayerZoneKey;
    return {
      zoneKey: zone.key,
      currentPlayerZoneKey: state.currentPlayerZoneKey,
      selectedZoneKey: state.selectedZoneKey,
      challengeTargetZoneKey: contract.targetZoneKey,
      isCurrentPlayerZone: isCurrent,
      headingKey: isCurrent ? 'e10.world_stage.current_zone' : 'e10.world_stage.selected_zone',
      headingText: isCurrent
        ? t('e10.world_stage.current_zone', 'Current Zone')
        : t('e10.world_stage.selected_zone', 'Selected Zone'),
      status: zone.status,
      name: zoneDisplayName(zone) || zone.key,
      statusText: zoneStateText(zone),
      summary: zoneSummaryText(zone),
      progress: zoneProgressText(zone),
      landmarkSrc: ZONE_LANDMARKS[zone.key] || '',
      zoneNumber: zone.__e10Index || 0,
      stars: zone.stars || 0,
      seen: zone.seen || 0,
      total: zone.total || 0,
      locked: !!zone.locked,
      ctaEnabled: contract.enabled,
      ctaLabel: contract.label,
    };
  }

  function dispatchZoneSelection(root, zone, state) {
    var detail = zoneSelectionDetail(zone, state);
    if (window.E9) window.E9.latestZoneSelection = detail;
    root.dispatchEvent(new CustomEvent('e9:zone-selected', { bubbles: true, detail: detail }));
  }

  // The small zone-tile badge only ever shows index.adv.boss_ready's
  // short lead-in ("Seal broken" / "封印解除") -- it never substitutes
  // {seen}/{total} at all (see bossReadyText(zone) above for the full,
  // substituted summary-panel text). Truncating on the current
  // dictionary values' colon (ASCII ':' or full-width '：') is NOT
  // sufficient on its own: a future translation could carry the same
  // {seen}/{total} placeholders with no colon at all (e.g. "Seal broken
  // {seen}/{total}"), which a colon-only split would pass through
  // unchanged. This drops everything from the first colon onward first
  // (current values), THEN independently drops everything from the
  // first literal "{seen}" or "{total}" token onward (any future,
  // delimiter-free value) -- so neither placeholder can survive the
  // badge regardless of what punctuation (if any) a translation uses.
  function bossReadyBadgeText() {
    var text = t('index.adv.boss_ready', 'Seal broken: {seen}/{total}');
    return text
      .split(/[:：]/)[0]
      .split(/\{seen\}|\{total\}/)[0]
      .trim();
  }

  function renderSelectedZone(root, zones, zoneKey, focusDetails) {
    var state = root.__e9WorldStageState;
    var zone = zones.filter(function (item) { return item.key === zoneKey; })[0];
    var details = root.querySelector('#e9-world-stage-details');
    var summary = root.querySelector('#e9-world-stage-details-summary');
    var cta = root.querySelector('#e9-world-stage-details-cta');
    var newbie = root.querySelector('#e9-newbie-mainline');
    if (!zone) {
      if (cta) cta.hidden = true;
      return;
    }

    state.selectedZoneKey = zone.key;
    state.challengeTargetZoneKey = resolveChallengeTargetZoneKey(zone);
    setSelectedTileState(root, zone.key);
    if (!VS1E_STATIC_CONTRACT_ACTIVE) updatePlayerMarker(root, zone);
    var isMobile = window.matchMedia && window.matchMedia('(max-width: 767px)').matches;
    var isPortraitTablet = window.matchMedia && window.matchMedia(
      '(min-width: 768px) and (max-width: 1279px) and (orientation: portrait)'
    ).matches;
    if (details) details.hidden = VS1E_STATIC_CONTRACT_ACTIVE ? !isPortraitTablet : isMobile;
    updateSelectedZoneCopy(root, zone);
    if (summary) summary.textContent = zone.bossAvailable
      ? bossReadyText(zone)
      : (zone.cleared ? clearedText(zone) : t('index.adv.panel_ready', 'Adventure is ready'));
    configurePrimaryCta(root, zone, state);

    if (cta) {
      if (!VS1E_STATIC_CONTRACT_ACTIVE && zone.key === 'k26_30') {
        // Beginner Village owns its own tutorial CTA below
        // (renderBeginnerVillageMainline's #e9-newbie-mainline-cta) --
        // never show a second, duplicate "start" button for it here.
        cta.hidden = true;
      } else {
        configureAdventureButton(cta, zone, ctaContract(zone, state));
      }
    }

    root.querySelectorAll('.e9-zone__inline-details').forEach(function (panel) { panel.remove(); });
    if (isMobile) {
      var inlineIsNewbie = !!(cta && cta.hidden);
      var selectedTile = root.querySelector('[data-zone="' + zone.key + '"]');
      if (selectedTile) {
        var inline = document.createElement('div');
        inline.className = 'e9-zone__inline-details';
        var inlineSummary = document.createElement('p');
        inlineSummary.textContent = summary ? summary.textContent : '';
        inline.appendChild(inlineSummary);
        if (VS1E_STATIC_CONTRACT_ACTIVE || !inlineIsNewbie) {
          var inlineCta = document.createElement('button');
          inlineCta.type = 'button';
          inlineCta.className = 'e9-zone__inline-cta e9-adventure-cta';
          var inlineContract = ctaContract(zone, state);
          inlineCta.textContent = inlineContract.label;
          inlineCta.disabled = !inlineContract.enabled;
          inlineCta.setAttribute('aria-disabled', inlineContract.enabled ? 'false' : 'true');
          inlineCta.setAttribute('data-challenge-target-zone', inlineContract.targetZoneKey || '');
          inlineCta.addEventListener('click', function (evt) {
            evt.stopPropagation();
            if (inlineContract.enabled && inlineContract.targetZoneKey && window.E9 && typeof window.E9.startAdventureFromE9 === 'function') {
              window.E9.startAdventureFromE9(inlineContract.targetZoneKey);
            }
          });
          inline.appendChild(inlineCta);
        }
        selectedTile.appendChild(inline);
      }
    }

    renderBeginnerVillageMainline(root, zone);
    if (newbie && (
      (VS1E_STATIC_CONTRACT_ACTIVE && (isMobile || zone.key !== 'k26_30'))
      || (!VS1E_STATIC_CONTRACT_ACTIVE && zone.key !== 'k26_30')
    )) newbie.hidden = true;
    if (focusDetails && details) {
      var focusTarget = zone.key === 'k26_30' && newbie && !newbie.hidden ? newbie : details;
      try { focusTarget.focus({ preventScroll: true }); } catch (err) { focusTarget.focus(); }
      if (typeof focusTarget.scrollIntoView === 'function' && window.matchMedia && window.matchMedia('(max-width: 900px)').matches) {
        // Preserve the selected detail's keyboard focus, but pan the visual
        // viewport to the selected-zone action on mobile. Centering the real
        // CTA keeps it above the fixed navigation instead of leaving the
        // bottom half of an expanded Zone card underneath that dock.
        var mobileFocus = isMobile
          ? (root.querySelector('[data-zone="' + zone.key + '"] .e9-zone__inline-cta') || root.querySelector('[data-zone="' + zone.key + '"]'))
          : (root.querySelector('#e9-map-stage') || focusTarget);
        var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (isMobile || reduced) {
          mobileFocus.scrollIntoView({ behavior: 'auto', block: isMobile ? 'center' : 'start' });
        } else {
          mobileFocus.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }
    }
  }

  function renderZones(root, zones) {
    var statusEl = root.querySelector('#e9-world-stage-status');
    var zonesEl = root.querySelector('#e9-world-stage-zones');
    var mapStage = root.querySelector('#e9-map-stage');
    var bossAnchorsEl = root.querySelector('#e9-world-stage-boss-anchors');
    if (!zonesEl || !mapStage || !bossAnchorsEl) return;

    var state = root.__e9WorldStageState || (root.__e9WorldStageState = {
      zones: zones,
      currentPlayerZoneKey: null,
      selectedZoneKey: null,
      challengeTargetZoneKey: null,
    });
    state.zones = zones;
    var identities = VS1E_STATIC_CONTRACT_ACTIVE
      ? syncInteractionState(state, zones)
      : { current: null, selected: null };
    var playerLocation = identities.current;
    zones.forEach(function (zone) {
      zone.__e10PlayerLocation = !!(VS1E_STATIC_CONTRACT_ACTIVE && playerLocation && zone.key === playerLocation.key);
    });
    ensureVs1fRouteLayers(root, zones);
    updateRouteProgress(root, zones);
    zonesEl.innerHTML = '';
    bossAnchorsEl.innerHTML = '';
    zones.forEach(function (zone, index) {
      zone.__e10Index = index + 1;
      var anchor = (VS1E_STATIC_CONTRACT_ACTIVE ? VS1F_ZONE_ANCHORS : ZONE_ANCHORS)[zone.key];
      var bossAnchor = BOSS_ANCHORS[zone.key];
      if (!anchor || !bossAnchor) return; // unknown API data never receives fabricated coordinates
      var tile = document.createElement('button');
      tile.type = 'button';
      tile.className = 'e9-zone e9-zone--' + (zone.status || 'locked');
      tile.setAttribute('data-zone', zone.key);
      if (VS1E_STATIC_CONTRACT_ACTIVE) {
        tile.setAttribute('data-plaque-side', ZONE_PLAQUE_SIDES[zone.key] || 'right');
      }
      if (VS1E_STATIC_CONTRACT_ACTIVE && usesLandmarkCards()) {
        var landmark = document.createElement('img');
        landmark.className = 'e10-zone-landmark';
        landmark.src = ZONE_LANDMARKS[zone.key];
        landmark.alt = '';
        landmark.width = 320;
        landmark.height = 320;
        landmark.loading = 'lazy';
        landmark.decoding = 'async';
        landmark.draggable = false;
        landmark.setAttribute('aria-hidden', 'true');
        tile.appendChild(landmark);
      }
      tile.setAttribute('data-normalized-anchor', anchor.x + ',' + anchor.y);
      tile.setAttribute('aria-label', zoneDisplayName(zone) + ': ' + zoneStateText(zone));
      applyAnchor(tile, anchor);
      if (VS1E_STATIC_CONTRACT_ACTIVE && playerLocation && zone.key === playerLocation.key) {
        tile.classList.add('is-current');
        tile.setAttribute('data-player-location', 'true');
      } else if (!VS1E_STATIC_CONTRACT_ACTIVE && (
        zone.current || zone.selected || (!zone.locked && zone.status === 'unlocked')
      )) {
        tile.classList.add('is-current');
      }

      var number = document.createElement('span');
      number.className = 'e9-zone__number';
      number.textContent = String(index + 1);
      number.setAttribute('aria-hidden', 'true');
      tile.appendChild(number);

      var stateBadge = document.createElement('span');
      stateBadge.className = 'e9-zone__state';
      stateBadge.setAttribute('aria-hidden', 'true');
      var isCompleted = zone.cleared || zone.status === 'completed';
      stateBadge.setAttribute(
        'data-zone-state',
        zone.locked ? 'locked' : (isCompleted ? 'completed' : (
          playerLocation && zone.key === playerLocation.key ? 'current' : 'available'
        ))
      );
      stateBadge.textContent = isCompleted ? '\u2713' : '';
      tile.appendChild(stateBadge);

      tile.setAttribute('aria-pressed', 'false');
      if (zone.locked) {
        tile.setAttribute('data-zone-locked', 'true');
        tile.title = t('index.adv.zone_locked', 'This area is still sealed by mist.');
      }

      // Zone display name: English locale prefers zone.nameEn (from the
      // API's name_en field), falling back to zone.name (Chinese) if
      // English isn't selected or nameEn is missing -- same precedence
      // the legacy Adventure Map's own _zoneName() already uses.
      var label = document.createElement('span');
      label.className = 'e9-zone__name';
      label.textContent = zoneDisplayName(zone);
      if (VS1E_STATIC_CONTRACT_ACTIVE) {
        var plaque = document.createElement('span');
        plaque.className = 'e9-zone__plaque';
        plaque.appendChild(label);
        var compactState = document.createElement('span');
        compactState.className = 'e9-zone__status-text';
        compactState.textContent = zoneStateText(zone);
        plaque.appendChild(compactState);
        tile.appendChild(plaque);
      } else {
        tile.appendChild(label);
      }

      if (zone.cleared || zone.stars > 0) {
        var starsEl = document.createElement('span');
        starsEl.className = 'e9-zone__stars';
        starsEl.setAttribute('aria-label', t('index.adv.stars_label', 'Stars') + ': ' + zone.stars + ' / 3');
        for (var starIndex = 0; starIndex < 3; starIndex += 1) {
          var star = document.createElement('i');
          star.className = 'e10-art-star' + (starIndex < zone.stars ? ' is-earned' : ' is-empty');
          star.setAttribute('aria-hidden', 'true');
          starsEl.appendChild(star);
        }
        tile.appendChild(starsEl);
      }

      if (zone.bossAvailable) {
        var bossEl = document.createElement('span');
        bossEl.className = 'e9-zone__boss-ready';
        bossEl.textContent = bossReadyBadgeText();
        tile.appendChild(bossEl);
      }

      var activate = function () {
          renderSelectedZone(root, zones, zone.key, true);
          var selectionDetail = VS1E_STATIC_CONTRACT_ACTIVE
            ? zoneSelectionDetail(zone, state)
            : { zoneKey: zone.key, status: zone.status };
          if (VS1E_STATIC_CONTRACT_ACTIVE && window.E9) {
            window.E9.latestZoneSelection = selectionDetail;
          }
          tile.dispatchEvent(new CustomEvent('e9:zone-selected', {
            bubbles: true,
            detail: selectionDetail,
          }));
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

      zonesEl.appendChild(tile);

      // L6 contract: preserve each canonical safe-box coordinate without
      // displaying a false Boss asset in this sprint.
      var reserved = document.createElement('span');
      reserved.setAttribute('data-zone-boss-anchor', zone.key);
      reserved.setAttribute('data-normalized-anchor', bossAnchor.x + ',' + bossAnchor.y);
      applyAnchor(reserved, bossAnchor);
      bossAnchorsEl.appendChild(reserved);
    });

    mapStage.hidden = false;
    zonesEl.hidden = false;
    if (VS1E_STATIC_CONTRACT_ACTIVE) updatePlayerMarker(root, playerLocation);
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
    if (selected) {
      renderSelectedZone(root, zones, selected.key, false);
      if (VS1E_STATIC_CONTRACT_ACTIVE) dispatchZoneSelection(root, selected, state);
    } else if (VS1E_STATIC_CONTRACT_ACTIVE) {
      var recommended = playerLocation || zones.filter(function (zone) { return !zone.locked; })[0];
      if (recommended) {
        state.selectedZoneKey = recommended.key;
        setSelectedTileState(root, recommended.key);
        updateSelectedZoneCopy(root, recommended);
        state.challengeTargetZoneKey = resolveChallengeTargetZoneKey(recommended);
        configurePrimaryCta(root, recommended, state);
        dispatchZoneSelection(root, recommended, state);
        var portraitDetails = root.querySelector('#e9-world-stage-details');
        var portraitTablet = window.matchMedia && window.matchMedia(
          '(min-width: 768px) and (max-width: 1279px) and (orientation: portrait)'
        ).matches;
        if (portraitDetails) portraitDetails.hidden = !portraitTablet;
      }
    }
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
      enableImmersiveRpgSkin(root, generation);
    }).catch(function (err) {
      if (!current()) return;
      recoverToLegacy(err);
    });
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return; // no duplicate binding
    root.setAttribute('data-e9-inited', '1');
    configureBaseMap(root);
    prepareVs1dDom(root);
    root.__e9WorldStageState = {
      zones: [],
      currentPlayerZoneKey: null,
      selectedZoneKey: null,
      challengeTargetZoneKey: null,
    };
    var onChanged = function () {
      var state = root.__e9WorldStageState;
      if ((!window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation)) && state && state.zones && state.zones.length) renderZones(root, state.zones);
    };
    var onReady = function () {
      var state = root.__e9WorldStageState;
      if ((!window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation)) && state && state.zones && state.zones.length) renderZones(root, state.zones);
    };
    var onAvatar = function (event) {
      var source = event && event.detail && event.detail.source;
      syncPlayerMarkerPortrait(root, source);
    };
    if (window.E9 && typeof window.E9.on === 'function') {
      window.E9.on(document, 'e9:i18n-changed', onChanged, null, generation);
      window.E9.on(document, 'e9:i18n-ready', onReady, null, generation);
      window.E9.on(document, 'e9:player-avatar-updated', onAvatar, null, generation);
    } else {
      document.addEventListener('e9:i18n-changed', onChanged);
      document.addEventListener('e9:i18n-ready', onReady);
      document.addEventListener('e9:player-avatar-updated', onAvatar);
    }
    load(root, false, generation);
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'world_stage') {
      init(e.detail.root, e.detail.generation);
    }
  });
})(document);
