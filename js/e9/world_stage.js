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
 * treated as a CRITICAL failure unless it is the recoverable cinematic
 * state read-error boundary. A single retry is offered first for a
 * recoverable (non-auth) error, dispatching "e9:refresh-requested".
 * After that retry, a cinematic-state read error stays inside E10 and
 * uses a conservative Zone 1 first-entry fallback; unrelated critical
 * failures still recover the full shell to the legacy Adventure Map via
 * window.E9.recoverToLegacy().
 * Adventure Start uses the thin adapter window.E9.startAdventureFromE9()
 * (defined in shell.js), which calls the existing canonical in-page
 * question entry -- no gameplay logic is duplicated here.
 * Zone selection dispatches "e9:zone-selected" (bubbles) and updates the
 * ephemeral detail selection. Zone 1's node selection additionally invokes
 * the canonical first-entry cinematic when the server says it is unseen;
 * every Zone Card CTA remains an ordinary training handoff.
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
    var currentZoneKey = arguments.length > 1 ? arguments[1] : null;
    // current_zone_key is server authority.  selectedZoneKey, recommended
    // display state, URL state, and a client-derived frontier are never inputs.
    // The old selectedZoneKey / zone.status === 'unlocked' frontier contract
    // is intentionally documented here as rejected input, not an authority.
    if (typeof currentZoneKey !== 'string' || !currentZoneKey) return null;
    return findZone(zones, currentZoneKey);
  }

  function findZone(zones, zoneKey) {
    return zones.filter(function (zone) { return zone.key === zoneKey; })[0] || null;
  }

  // A cinematic-state read failure must not hand the player to the Legacy
  // shell, but the E10 World Stage still needs an actionable Zone 1 node if
  // the initial bootstrap failed before any authoritative zones were drawn.
  // Use previously rendered authoritative zones when available. On a cold
  // failure, use only static zone identity/coordinates already declared by
  // the page and conservatively enable Zone 1; no progression values are
  // inferred or persisted by this fallback, and Zones 2-10 stay disabled.
  function readErrorFallbackZones(root) {
    var previous = root && root.__e9WorldStageState && root.__e9WorldStageState.zones;
    if (Array.isArray(previous) && previous.length) return previous;
    if (typeof ADVENTURE_ZONES === 'undefined' || !Array.isArray(ADVENTURE_ZONES)) return [];
    return ADVENTURE_ZONES.map(function (source, index) {
      var zone1 = index === 0;
      return {
        key: source.key,
        name: source.name,
        nameEn: source.nameEn || null,
        status: zone1 ? 'unlocked' : 'locked',
        locked: !zone1,
        canEnter: zone1,
        cleared: false,
        skippedByPlacement: false,
        recommended: zone1,
        selected: zone1,
        stars: 0,
        bossAvailable: false,
        bossKey: null,
        seen: 0,
        total: 0,
      };
    });
  }

  // Zone 1 remains the legacy constant consumed by the existing read-error
  // harness. Zone 2 joins the same server-backed first-entry/replay contract
  // without changing Zone 1's key or seen-state semantics.
  var ACTIVE_INTRO_ZONE_KEY = 'k26_30';
  var ACTIVE_INTRO_CINEMATIC_KEY = 'e10_zone1_intro_v1';

  function resolveChallengeTargetZoneKey(zone) {
    return zone && !zone.locked && zone.canEnter !== false ? zone.key : null;
  }

  function activeMandatoryEncounterAction(state, explicitZoneKey) {
    var lifecycle = window.__GO_E10_BATTLE_LIFECYCLE__;
    if (!lifecycle || lifecycle.mode !== 'active' || lifecycle.hasNonce !== true
        || lifecycle.attemptState !== 'ISSUED') return null;
    var targetZoneKey = lifecycle.zoneKey || null;
    if (!targetZoneKey) return null;
    if (explicitZoneKey && String(targetZoneKey) !== String(explicitZoneKey)) return null;
    if (lifecycle.expiresAt && Date.parse(lifecycle.expiresAt) <= Date.now()) return null;
    return { kind: 'resume_encounter', zoneKey: targetZoneKey };
  }

  function actionLabel(action, state) {
    if (!action) return '';
    if (action.kind === 'resume_encounter') return t('e10.world_stage.resume_encounter', 'Resume Encounter');
    if (action.kind === 'challenge_lord') return t('e10.world_stage.challenge_lord', 'Challenge Lord');
    if (action.kind === 'replenish_stars') return t('e10.world_stage.replenish_stars', 'Replenish Stars');
    if (action.kind === 'replay_completed') return t('index.adv.quest_rechallenge_boss', 'Challenge Lord again');
    return action.zoneKey === state.currentPlayerZoneKey
      ? t('e10.world_stage.continue_adventure', 'Continue Adventure')
      : t('index.adv.start_challenge', 'Start Challenge');
  }

  function resolvePrimaryCta(state, zones) {
    var resume = activeMandatoryEncounterAction(state);
    if (resume && findZone(zones, resume.zoneKey)) return resume;

    // Prefer the server's arbitration.  The fallback is deliberately based
    // only on normalized authoritative boss/progression fields, never seen/total.
    var serverAction = state.primaryAction;
    if (serverAction && findZone(zones, serverAction.zoneKey)) return serverAction;

    var lord = zones.filter(function (zone) {
      return zone.bossAvailable === true && !zone.cleared && zone.canEnter !== false && !zone.locked;
    })[0];
    if (lord) return { kind: 'challenge_lord', zoneKey: lord.key };

    var current = findZone(zones, state.currentPlayerZoneKey);
    if (current && !current.cleared && resolveChallengeTargetZoneKey(current)) {
      return { kind: 'normal_progression', zoneKey: current.key };
    }
    var refill = zones.filter(function (zone) {
      return !zone.locked && zone.canEnter !== false && zone.stars < 3;
    })[0];
    if (refill) return { kind: 'replenish_stars', zoneKey: refill.key };
    var completed = zones.filter(function (zone) { return zone.cleared && resolveChallengeTargetZoneKey(zone); });
    return completed.length ? { kind: 'replay_completed', zoneKey: completed[completed.length - 1].key } : null;
  }

  function syncInteractionState(state, zones, currentZoneKey, primaryAction) {
    var current = resolvePlayerLocation(zones, currentZoneKey);
    var selected = findZone(zones, state.selectedZoneKey) || current || zones[0] || null;
    state.currentPlayerZoneKey = current ? current.key : null;
    state.authoritativeCurrentZoneKey = state.currentPlayerZoneKey;
    state.primaryAction = primaryAction || null;
    state.selectedZoneKey = selected ? selected.key : null;
    // Selection and authoritative player location are separate identities.
    // The selected card owns the next challenge target. A proven issued
    // encounter changes only the action label when it belongs to this same
    // zone; cross-zone lifecycle state never overwrites explicit selection.
    var mandatory = activeMandatoryEncounterAction(state, selected && selected.key);
    state.challengeTargetZoneKey = mandatory && mandatory.zoneKey
      ? mandatory.zoneKey
      : resolveChallengeTargetZoneKey(selected);
    return { current: current, selected: selected };
  }

  function ctaContract(zone, state) {
    // A same-zone issued encounter may resume. Cross-zone lifecycle state is
    // deliberately ignored so every CTA surface keeps explicit selection.
    var mandatory = activeMandatoryEncounterAction(state, zone && zone.key);
    var mandatoryZone = mandatory && findZone(state.zones || [], mandatory.zoneKey);
    if (mandatoryZone) {
      return {
        enabled: true,
        targetZoneKey: mandatoryZone.key,
        label: actionLabel(mandatory, state),
        kind: mandatory.kind,
      };
    }
    var target = resolveChallengeTargetZoneKey(zone);
    if (!target) {
      return { enabled: false, targetZoneKey: null, label: t('e10.world_stage.state_locked', 'Locked') };
    }
    // A cleared, enterable zone always keeps Lord replay as its primary card
    // action.  Star completion is independent from the server-owned clear
    // bit, so 1/2-star cleared zones must not fall through to training here.
    if (zone.cleared === true || zone.status === 'completed') {
      return {
        enabled: true,
        targetZoneKey: target,
        label: actionLabel({ kind: 'replay_completed', zoneKey: zone.key }, state),
        kind: 'replay_completed',
      };
    }
    // The root-level arbitration (state.primaryAction / the client-computed
    // fallback in resolvePrimaryCta) names exactly ONE zone. A per-zone card
    // may only inherit that decision when it IS the named zone -- otherwise
    // this card must fall through to ITS OWN authoritative fields below.
    // This is the fix for CTA_SCOPE_DEFECT: previously any unlocked zone's
    // card unconditionally inherited the single global pick.
    var primary = resolvePrimaryCta(state, state.zones || []);
    if (primary && primary.zoneKey === zone.key && primary.kind !== 'replay_completed') {
      var primaryLabel = primary.kind === 'normal_progression'
        ? (primary.zoneKey === state.currentPlayerZoneKey
          ? t('e10.world_stage.continue_adventure', 'Continue Adventure')
          : t('index.adv.start_challenge', 'Start Challenge'))
        : actionLabel(primary, state);
      return { enabled: true, targetZoneKey: primary.zoneKey, label: primaryLabel, kind: primary.kind };
    }
    // Backstop: even when this zone isn't the single globally-arbitrated
    // pick, its OWN authoritative boss.available must still win over
    // completed/skipped/normal -- never inferred from seen/total, only the
    // server-provided bossAvailable flag already normalized onto the zone.
    if (zone.bossAvailable === true && !zone.cleared) {
      return {
        enabled: true,
        targetZoneKey: target,
        label: actionLabel({ kind: 'challenge_lord', zoneKey: zone.key }, state),
        kind: 'challenge_lord',
      };
    }
    if (zone.status === 'skipped_by_placement') {
      return { enabled: true, targetZoneKey: target, label: t('index.adv.skipped_replay', 'Star training available'), kind: 'replenish_stars' };
    }
    return {
      enabled: true,
      targetZoneKey: target,
      label: target === state.currentPlayerZoneKey
        ? t('e10.world_stage.continue_adventure', 'Continue Adventure')
        : t('index.adv.start_challenge', 'Start Challenge'),
      kind: 'normal_progression',
    };
  }

  function secondaryCtaContract(zone, state) {
    if (!zone || zone.locked || zone.canEnter === false) return null;
    var secondary = state && state.secondaryAction;
    if (secondary && secondary.zoneKey === zone.key && secondary.kind === 'replenish_stars') {
      return {
        enabled: true,
        targetZoneKey: zone.key,
        label: actionLabel(secondary, state),
        kind: secondary.kind,
      };
    }
    // The cleared-zone card is allowed to retain its own server-normalized
    // star count as the secondary training surface; the replay eligibility
    // itself remains the server-owned cleared bit above and in the Lord start
    // contract.
    if (zone.cleared === true && Number(zone.stars || 0) < 3) {
      return {
        enabled: true,
        targetZoneKey: zone.key,
        label: actionLabel({ kind: 'replenish_stars', zoneKey: zone.key }, state),
        kind: 'replenish_stars',
      };
    }
    return null;
  }

  function usesLandmarkCards() {
    return !!(window.matchMedia && window.matchMedia('(max-width: 767px)').matches);
  }

  function usesInlinePlayerMarkerSurface() {
    if (!window.matchMedia) return false;
    var mobile = window.matchMedia('(max-width: 767px)').matches;
    var tablet = window.matchMedia(
      '(min-width: 768px) and (max-width: 1279px)'
    ).matches;
    var tabletPortrait = window.matchMedia(
      '(min-width: 768px) and (max-width: 1279px) and (orientation: portrait)'
    ).matches;
    var touchSurface = window.matchMedia('(pointer: coarse)').matches
      || (typeof navigator !== 'undefined' && navigator.maxTouchPoints > 0);
    var appleTouchSurface = typeof navigator !== 'undefined'
      && touchSurface
      && navigator.maxTouchPoints > 0
      && /iPad|Macintosh/.test(navigator.userAgent || '');
    var tabletPortraitViewport = tabletPortrait
      && typeof window.innerHeight === 'number'
      && window.innerHeight >= 960;
    return mobile || (tablet && (tabletPortraitViewport || appleTouchSurface));
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

  function syncPlayerMarkerPresentation(root, presentation) {
    if (!VS1E_STATIC_CONTRACT_ACTIVE) return;
    var mobileCards = window.matchMedia && window.matchMedia('(max-width: 767px)').matches;
    // Keep this selector split as a compatibility hook for the two existing
    // responsive surfaces, while the runtime now moves one marker host
    // between them instead of creating desktop/mobile duplicates.
    var markerSelector = mobileCards ? '.e10-current-hero' : '#e9-world-stage-player';
    var hosts = Array.prototype.slice.call(root.querySelectorAll(markerSelector));
    var marker = root.querySelector('#e9-world-stage-player') || hosts[0] || null;
    if (!marker || !presentation || typeof presentation.asset !== 'string' || !presentation.asset) {
      if (marker) marker.querySelectorAll('.e10-player-marker-avatar').forEach(function (avatar) { avatar.remove(); });
      return;
    }

    var avatar = marker.querySelector('.e10-player-marker-avatar');
    if (!avatar) {
      avatar = document.createElement('img');
      avatar.className = 'e10-player-marker-avatar';
      avatar.alt = '';
      avatar.width = 96;
      avatar.height = 128;
      avatar.decoding = 'async';
      avatar.draggable = false;
      avatar.setAttribute('aria-hidden', 'true');
      marker.appendChild(avatar);
    }
    var fallbackAsset = typeof presentation.fallbackAsset === 'string'
      ? presentation.fallbackAsset
      : '';
    avatar.onerror = function () {
      if (avatar.getAttribute('data-e10-avatar-fallback') === '1') {
        avatar.hidden = true;
        return;
      }
      if (fallbackAsset && avatar.getAttribute('src') !== fallbackAsset) {
        avatar.setAttribute('data-e10-avatar-fallback', '1');
        avatar.hidden = false;
        avatar.setAttribute('src', fallbackAsset);
        return;
      }
      avatar.hidden = true;
    };
    avatar.hidden = false;
    avatar.removeAttribute('data-e10-avatar-fallback');
    if (avatar.getAttribute('src') !== presentation.asset) avatar.setAttribute('src', presentation.asset);
    marker.setAttribute('data-player-avatar-id', presentation.id || '');
    marker.setAttribute('data-player-avatar-presentation', presentation.presentationType || 'resolved-avatar');
  }

  function restorePlayerMarkerHost(root, mapStage) {
    if (!root || !mapStage) return;
    var marker = root.querySelector('#e9-world-stage-player');
    if (!marker) return;
    marker.classList.remove('e10-current-hero');
    if (marker.parentNode !== mapStage) mapStage.appendChild(marker);
  }

  function reconcilePlayerNodeMarker(root, zone, generation) {
    var generationKey = String(generation || '');
    var stageState = root.__e9WorldStageState || {};
    var presentation = stageState.avatarPresentation || null;
    var markerHosts = Array.prototype.slice.call(root.querySelectorAll('#e9-world-stage-player'));
    var marker = markerHosts[0] || null;
    markerHosts.slice(1).forEach(function (duplicate) { duplicate.remove(); });
    // A component shell can be replaced while the old layout is still in the
    // document.  Keep only the current shell's existing marker scaffold.
    document.querySelectorAll('#e9-world-stage-player').forEach(function (host) {
      if (!root.contains(host)) host.remove();
    });
    document.querySelectorAll('.e10-current-hero').forEach(function (hero) {
      var belongsToRoot = root.contains(hero);
      var sameGeneration = hero.getAttribute('data-e10-shell-generation') === generationKey;
      if (!belongsToRoot || !sameGeneration) hero.remove();
    });
    if (marker) marker.classList.remove('e10-current-hero');
    root.querySelectorAll('.e10-current-hero').forEach(function (hero) { hero.remove(); });
    var anchor = zone && (VS1E_STATIC_CONTRACT_ACTIVE ? VS1F_ZONE_ANCHORS : ZONE_ANCHORS)[zone.key];
    var mapStage = root.querySelector('#e9-map-stage');
    if (!marker) return;
    restorePlayerMarkerHost(root, mapStage);
    marker.style.pointerEvents = 'none';
    marker.setAttribute('data-e10-shell-generation', generationKey);
    if (!zone || !anchor) {
      marker.hidden = true;
      syncPlayerMarkerPresentation(root, null);
      return;
    }
    if (usesInlinePlayerMarkerSurface()) {
      marker.hidden = false;
      var currentTile = root.querySelector('[data-zone="' + zone.key + '"]');
      if (currentTile) {
        var mobileHero = marker;
        mobileHero.classList.add('e10-current-hero');
        mobileHero.setAttribute('aria-hidden', 'true');
        mobileHero.setAttribute('data-e10-shell-generation', generationKey);
        mobileHero.style.pointerEvents = 'none';
        currentTile.appendChild(mobileHero);
        syncPlayerMarkerPresentation(root, presentation);
      } else {
        marker.hidden = true;
      }
      return;
    }
    applyAnchor(marker, anchor);
    if (mapStage) {
      mapStage.style.setProperty('--focus-x', anchor.x + '%');
      mapStage.style.setProperty('--focus-y', anchor.y + '%');
    }
    marker.hidden = false;
    syncPlayerMarkerPresentation(root, presentation);
  }

  function newbieCtaText(zone) {
    var ctaKey = zone && zone.bossAvailable
      ? 'adventure.newbie.cta_boss'
      : (zone && (zone.cleared || zone.stars > 0)
        ? 'adventure.newbie.cta_continue'
        : 'adventure.newbie.cta_begin');
    return t(ctaKey, 'Begin the Beginner Village Adventure');
  }

  function renderBeginnerVillageMainline(root, zone, state) {
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
      // Label stays tutorial-flavored (newbieCtaText) -- only the routing
      // decision comes from the same authoritative ctaContract()/
      // dispatchAdventureAction() every other CTA surface uses. This CTA
      // must never re-derive challenge_lord readiness itself (e.g. from
      // zone.bossAvailable directly): a fourth, independent routing branch
      // is exactly the defect class already fixed for the other three
      // surfaces.
      cta.textContent = newbieCtaText(zone);
      if (cta.__e9AdventureHandler) {
        cta.removeEventListener('click', cta.__e9AdventureHandler);
      }
      var contract = ctaContract(zone, state);
      cta.__e9AdventureHandler = function () {
        dispatchAdventureAction(contract);
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

  function zoneBossProgressText(zone) {
    if (zone.bossAvailable) return bossReadyText(zone);
    if (zone.cleared) return clearedText(zone);
    return t('index.adv.boss_intro_progress', 'Progress: {completed} / {total}')
      .replace('{completed}', String(zone.seen || 0))
      .replace('{total}', String(zone.total || 0));
  }

  function setSelectedTileState(root, zoneKey, preservePressedState) {
    root.querySelectorAll('[data-zone]').forEach(function (tile) {
      var selected = tile.getAttribute('data-zone') === zoneKey;
      if (!preservePressedState && tile.getAttribute('aria-disabled') !== 'true') {
        tile.setAttribute('aria-pressed', selected ? 'true' : 'false');
      }
      tile.classList.toggle('is-selected', selected);
    });
  }

  // CTA_ACTION_ROUTING_DEFECT fix: a 'challenge_lord' contract must invoke
  // the existing, canonical Lord entry point (openAdventureBossFromQuestCard
  // -> showBossCinematic -> confirmBossBattle -> the existing boss-challenge
  // finish contract, index.html-owned), never the generic
  // startAdventureFromE9() ordinary-question handoff. E9's own JS never
  // calls the boss challenge API routes directly -- it always defers to
  // this one shared, legacy-owned entry point.
  // openAdventureBossFromQuestCard() reads the legacy _adventureProgress
  // cache for live boss/cleared state; that cache is never populated while
  // the E9 shell owns the page (ensureLegacyAdventureMapReady() is skipped
  // at page init whenever the E9 shell is active). Reuse the E9 adapter's
  // already-fetched bootstrap data (no duplicate network call) to populate
  // it before handing off -- this is the existing, reviewed shell-to-legacy
  // bridge (window.ensureLegacyAdventureMapReady), not a new one.
  function dispatchAdventureAction(contract) {
    if (!contract || !contract.enabled || !contract.targetZoneKey) return;
    if (contract.kind === 'challenge_lord' || contract.kind === 'replay_completed') {
      var enter = function () {
        if (typeof window.openAdventureBossFromQuestCard === 'function') {
          window.openAdventureBossFromQuestCard(contract.targetZoneKey);
        }
      };
      if (typeof window.ensureLegacyAdventureMapReady === 'function') {
        window.ensureLegacyAdventureMapReady({ reuseE9Adapter: true }).then(enter, enter);
      } else {
        enter();
      }
      return;
    }
    // normal_progression is the Zone Card's main training CTA, including
    // Zone 1. First-entry cinematic routing is intentionally handled by the
    // map-node selection path below so the cinematic can end at the card.
    if (window.E9 && typeof window.E9.startAdventureFromE9 === 'function') {
      window.E9.startAdventureFromE9(contract.targetZoneKey);
    }
  }

  function cinematicSeen(state, cinematicKey) {
    if (state && state.cinematicReadError && cinematicKey === ACTIVE_INTRO_CINEMATIC_KEY) {
      // Read-error degraded mode is a per-invocation UI decision only. It is
      // deliberately not a persisted unseen record or a browser cache.
      return false;
    }
    var entry = state && state.cinematics && state.cinematics[cinematicKey];
    return !!(entry && entry.seen === true);
  }

  function introCinematicKeyForZone(zoneKey) {
    if (zoneKey === ACTIVE_INTRO_ZONE_KEY) return ACTIVE_INTRO_CINEMATIC_KEY;
    if (zoneKey === 'k21_25') return 'e10_zone2_intro_v1';
    return null;
  }

  function introEntryInFlightKey(zoneKey) {
    return zoneKey === ACTIVE_INTRO_ZONE_KEY ? 'zone1EntryInFlight' : 'zone2EntryInFlight';
  }

  function withLegacyAdventureReady(callback) {
    if (typeof window.ensureLegacyAdventureMapReady !== 'function') {
      callback();
      return;
    }
    try {
      window.ensureLegacyAdventureMapReady({ reuseE9Adapter: true }).then(callback, callback);
    } catch (error) {
      callback();
    }
  }

  function withCinematicHost(callback, state) {
    if (state && state.cinematicReadError) {
      // The E10 shell already owns the cinematic host. Do not restore the
      // Legacy Adventure Map merely because account cinematic state failed
      // to load.
      callback();
      return;
    }
    withLegacyAdventureReady(callback);
  }

  function worldStageRoot() {
    // component_loader mounts world_stage on the slot; #adventure-stage is
    // the injected child markup, not the state-owning root.
    return document.querySelector('#e9-world-stage-slot')
      || document.querySelector('#adventure-stage');
  }

  function dispatchZone1Entry(root, zone, state) {
    var cinematicKey = introCinematicKeyForZone(zone && zone.key);
    if (!zone || !cinematicKey || zone.locked) return;
    // The bootstrap snapshot is server-authoritative. Missing state means
    // unseen, so a fresh account cannot be silently promoted by browser data.
    if (cinematicSeen(state, cinematicKey)) return;
    var inFlightKey = introEntryInFlightKey(zone.key);
    if (state[inFlightKey]) return;
    state[inFlightKey] = true;
    var start = function () {
      if (typeof window.startAdventureStage !== 'function') {
        state[inFlightKey] = false;
        console.error('[E10] Zone entry cinematic host is unavailable');
        return;
      }
      try {
        var options = { mode: 'first_entry' };
        if (state.cinematicReadError) options.readErrorDegraded = true;
        window.startAdventureStage(zone.key, options);
      } catch (error) {
        state[inFlightKey] = false;
        console.error('[E10] Zone first-entry cinematic failed to start:', error);
      }
    };
    withCinematicHost(start, state);
  }

  function replayAdventureIntro(zoneKey) {
    if (zoneKey !== ACTIVE_INTRO_ZONE_KEY && zoneKey !== 'k21_25') return false;
    if (!introCinematicKeyForZone(zoneKey)) return false;
    var root = worldStageRoot();
    var state = root && root.__e9WorldStageState;
    withCinematicHost(function () {
      if (typeof window.startAdventureStage === 'function') {
        var options = { mode: 'manual_replay' };
        if (state && state.cinematicReadError) options.readErrorDegraded = true;
        window.startAdventureStage(zoneKey, options);
      }
    }, state);
    return true;
  }

  function updateAdventureCinematicState(cinematics) {
    var root = worldStageRoot();
    var state = root && root.__e9WorldStageState;
    if (!state || !cinematics || typeof cinematics !== 'object') return;
    state.cinematics = cinematics;
    state.cinematicReadError = false;
  }

  function showAdventureZoneCard(zoneKey) {
    var root = worldStageRoot();
    var state = root && root.__e9WorldStageState;
    var zone = state && findZone(state.zones || [], zoneKey);
    if (!root || !state || !zone) return false;
    state.zone1EntryInFlight = false;
    state.zone2EntryInFlight = false;
    renderSelectedZone(root, state.zones, zone.key, false);
    dispatchZoneSelection(root, zone, state);
    document.dispatchEvent(new CustomEvent('e9:zone-card-requested', {
      bubbles: true,
      detail: { zoneKey: zone.key },
    }));
    return true;
  }

  function configureStoryReplayButton(button, zone) {
    if (!button || !zone) return;
    var enabled = !!introCinematicKeyForZone(zone.key);
    button.hidden = !enabled;
    button.disabled = !enabled;
    button.setAttribute('aria-hidden', enabled ? 'false' : 'true');
    if (!enabled) return;
    button.textContent = t('e10.world_stage.replay_story', 'Replay Story');
    button.removeAttribute('data-i18n');
    if (button.__e9StoryReplayHandler) {
      button.removeEventListener('click', button.__e9StoryReplayHandler);
    }
    button.__e9StoryReplayHandler = function (event) {
      if (event) event.stopPropagation();
      replayAdventureIntro(zone.key);
    };
    if (window.E9 && typeof window.E9.on === 'function') {
      window.E9.on(button, 'click', button.__e9StoryReplayHandler);
    } else {
      button.addEventListener('click', button.__e9StoryReplayHandler);
    }
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
      dispatchAdventureAction(contract);
    };
    if (window.E9 && typeof window.E9.on === 'function') {
      window.E9.on(button, 'click', button.__e9AdventureHandler);
    } else {
      button.addEventListener('click', button.__e9AdventureHandler);
    }
  }

  function configureSecondaryAdventureButton(button, zone, contract) {
    if (!button) return;
    if (!zone || !contract || !contract.enabled) {
      button.hidden = true;
      button.disabled = true;
      button.removeAttribute('data-challenge-target-zone');
      return;
    }
    button.hidden = false;
    button.disabled = false;
    button.setAttribute('aria-disabled', 'false');
    button.setAttribute('data-challenge-target-zone', contract.targetZoneKey || '');
    button.textContent = contract.label;
    if (button.__e9SecondaryAdventureHandler) {
      button.removeEventListener('click', button.__e9SecondaryAdventureHandler);
    }
    button.__e9SecondaryAdventureHandler = function () {
      dispatchAdventureAction(contract);
    };
    if (window.E9 && typeof window.E9.on === 'function') {
      window.E9.on(button, 'click', button.__e9SecondaryAdventureHandler);
    } else {
      button.addEventListener('click', button.__e9SecondaryAdventureHandler);
    }
  }

  function configurePrimaryCta(root, zone, state) {
    var primary = root.querySelector('#e9-world-stage-primary-cta');
    if (!VS1E_STATIC_CONTRACT_ACTIVE) {
      if (primary) primary.hidden = true;
      return;
    }
    // The map-level CTA is rendered beside the selected-zone details, so its
    // action identity must be that selected zone. Same-zone resume is decided
    // by ctaContract and then revalidated by the server at gameplay bootstrap.
    var targetZone = zone;
    var contract = targetZone && ctaContract(targetZone, state);
    var label = contract ? contract.label : '';
    configureAdventureButton(primary, targetZone, contract);
    if (primary && targetZone && !primary.hidden) {
      var registry = window.E9 && window.E9.NavigationRegistry;
      primary.innerHTML = (registry ? registry.icon('compass', 'e10-map-primary-cta__icon') : '')
        + '<span class="e10-map-primary-cta__copy"><strong>' + label + '</strong>'
        + '<span>' + (zoneDisplayName(targetZone) || targetZone.key) + '</span></span>';
      primary.setAttribute('aria-label', label + ': ' + (zoneDisplayName(targetZone) || targetZone.key));
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
    var bossProgress = root.querySelector('#e9-world-stage-details-boss-progress');
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
    if (bossProgress) bossProgress.textContent = zoneBossProgressText(zone);
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
    var secondary = secondaryCtaContract(zone, state);
    var isCurrent = zone.key === state.currentPlayerZoneKey;
    return {
      zoneKey: zone.key,
      currentPlayerZoneKey: state.currentPlayerZoneKey,
      selectedZoneKey: state.selectedZoneKey,
      challengeTargetZoneKey: contract.targetZoneKey,
      currentZoneKey: state.currentPlayerZoneKey,
      ctaKind: contract.kind || null,
      primaryActionKind: state.primaryAction && state.primaryAction.kind || null,
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
      secondaryCtaKind: secondary && secondary.kind || null,
      secondaryCtaEnabled: !!(secondary && secondary.enabled),
      secondaryCtaLabel: secondary && secondary.label || '',
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
    var secondaryCta = root.querySelector('#e9-world-stage-details-secondary-cta');
    var replay = root.querySelector('#e9-world-stage-details-replay');
    var newbie = root.querySelector('#e9-newbie-mainline');
    if (!zone) {
      if (cta) cta.hidden = true;
      return;
    }

    state.selectedZoneKey = zone.key;
    state.challengeTargetZoneKey = ctaContract(zone, state).targetZoneKey;
    // Keep the prior aria-pressed target while a locked zone is inspected;
    // the locked tile receives the visual/state selection class and its
    // details, but it must not become an actionable selection in the
    // canonical keyboard/assistive-technology contract.
    setSelectedTileState(root, zone.key, !!zone.locked);
    // if (!VS1E_STATIC_CONTRACT_ACTIVE) updatePlayerMarker(root, zone);
    // Selection-only renders must not move the authoritative player marker.
    var isMobile = window.matchMedia && window.matchMedia('(max-width: 767px)').matches;
    var isPortraitTablet = window.matchMedia && window.matchMedia(
      '(min-width: 768px) and (max-width: 1279px) and (orientation: portrait)'
    ).matches;
    if (details) details.hidden = VS1E_STATIC_CONTRACT_ACTIVE ? !isPortraitTablet : isMobile;
    updateSelectedZoneCopy(root, zone);
    configureStoryReplayButton(replay, zone);
    if (summary) summary.textContent = zone.bossAvailable
      ? bossReadyText(zone)
      : (zone.cleared ? clearedText(zone) : t('index.adv.panel_ready', 'Adventure is ready'));
    configurePrimaryCta(root, zone, state);

    if (cta) {
      // Portrait tablets use this lower detail card as their only actionable
      // Zone CTA.  It must always receive the freshly-derived selected-zone
      // contract, including completed Zone 1 replay semantics.  The separate
      // Beginner Village tutorial panel is hidden on this responsive surface;
      // suppressing this button for k26_30 left its prior zone's label/action
      // attached while landscape continued to use the correctly configured
      // map/panel CTA.
      configureAdventureButton(cta, zone, ctaContract(zone, state));
    }
    if (secondaryCta) {
      configureSecondaryAdventureButton(secondaryCta, zone, secondaryCtaContract(zone, state));
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
            dispatchAdventureAction(inlineContract);
          });
          inline.appendChild(inlineCta);
          var inlineSecondary = secondaryCtaContract(zone, state);
          if (inlineSecondary && inlineSecondary.enabled) {
            var inlineSecondaryCta = document.createElement('button');
            inlineSecondaryCta.type = 'button';
            inlineSecondaryCta.className = 'e9-zone__inline-cta e9-zone__inline-cta--secondary e9-adventure-cta';
            inlineSecondaryCta.textContent = inlineSecondary.label;
            inlineSecondaryCta.setAttribute('aria-disabled', 'false');
            inlineSecondaryCta.setAttribute('data-challenge-target-zone', inlineSecondary.targetZoneKey || '');
            inlineSecondaryCta.addEventListener('click', function (evt) {
              evt.stopPropagation();
              dispatchAdventureAction(inlineSecondary);
            });
            inline.appendChild(inlineSecondaryCta);
          }
        }
        selectedTile.appendChild(inline);
      }
    }

    renderBeginnerVillageMainline(root, zone, state);
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
        // Mobile stacked details are intentionally user-scrollable. Calling
        // scrollIntoView on a nested tile can scroll the outer document and
        // clip the shell above the viewport; focus remains on the selected
        // card without forcing that page-level jump.
        if (isMobile) return;
        var scrollOptions = {
          behavior: isMobile || reduced ? 'auto' : 'smooth',
          // Preserve the established centered focus contract for tablet and
          // desktop detail surfaces; mobile exits above before this scroll.
          block: isMobile ? 'center' : 'start'
        };
        if (scrollOptions.behavior === 'smooth') {
          mobileFocus.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
          mobileFocus.scrollIntoView(scrollOptions);
        }
      }
    }
  }

  function renderZones(root, zones, authority) {
    authority = authority || {};
    var statusEl = root.querySelector('#e9-world-stage-status');
    var zonesEl = root.querySelector('#e9-world-stage-zones');
    var mapStage = root.querySelector('#e9-map-stage');
    var bossAnchorsEl = root.querySelector('#e9-world-stage-boss-anchors');
    if (!zonesEl || !mapStage || !bossAnchorsEl) return;

    var state = root.__e9WorldStageState || (root.__e9WorldStageState = {
      zones: zones,
      currentPlayerZoneKey: null,
      authoritativeCurrentZoneKey: null,
      selectedZoneKey: null,
      challengeTargetZoneKey: null,
      primaryAction: null,
      secondaryAction: null,
      avatarPresentation: null,
      cinematics: {},
      generation: null,
    });
    if (!state.selectedZoneKey && authority.selected && typeof authority.selected.zone_key === 'string') {
      state.selectedZoneKey = authority.selected.zone_key;
    }
    if (authority.generation) state.generation = authority.generation;
    var authoritativeCurrentZoneKey = Object.prototype.hasOwnProperty.call(authority, 'currentZoneKey')
      ? authority.currentZoneKey
      : state.authoritativeCurrentZoneKey;
    var primaryAction = Object.prototype.hasOwnProperty.call(authority, 'primaryAction')
      ? authority.primaryAction
      : state.primaryAction;
    var secondaryAction = Object.prototype.hasOwnProperty.call(authority, 'secondaryAction')
      ? authority.secondaryAction
      : state.secondaryAction;
    state.zones = zones;
    state.secondaryAction = secondaryAction || null;
    if (Object.prototype.hasOwnProperty.call(authority, 'cinematics')) {
      state.cinematics = authority.cinematics || {};
    }
    if (Object.prototype.hasOwnProperty.call(authority, 'cinematicReadError')) {
      state.cinematicReadError = authority.cinematicReadError === true;
    }
    var identities = VS1E_STATIC_CONTRACT_ACTIVE
      ? syncInteractionState(state, zones, authoritativeCurrentZoneKey, primaryAction)
      : { current: null, selected: null };
    var playerLocation = identities.current;
    zones.forEach(function (zone) {
      zone.__e10PlayerLocation = !!(VS1E_STATIC_CONTRACT_ACTIVE && playerLocation && zone.key === playerLocation.key);
    });
    ensureVs1fRouteLayers(root, zones);
    updateRouteProgress(root, zones);
    // A mobile marker is temporarily nested inside its current Zone tile.
    // Move that same host back to the map frame before replacing tile DOM so
    // the next render cannot orphan or duplicate the player marker.
    restorePlayerMarkerHost(root, mapStage);
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
        // Locked zones remain inspectable so their details explain the
        // progression boundary, but they are never an actionable challenge
        // target.  aria-disabled also keeps the selected/pressed contract
        // from advertising a locked tile as the active target.
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
          dispatchZone1Entry(root, zone, state);
      };
      var keyActivate = function (evt) {
          if (evt.key === 'Enter' || evt.key === ' ') {
            evt.preventDefault();
            if (zone.locked) return;
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
    // Existing lifecycle contract name retained in this note while the one
    // idempotent implementation is reconcilePlayerNodeMarker().
    // updatePlayerMarker(root, playerLocation)
    if (VS1E_STATIC_CONTRACT_ACTIVE) reconcilePlayerNodeMarker(root, playerLocation, state.generation);
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
        state.challengeTargetZoneKey = ctaContract(recommended, state).targetZoneKey;
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

  function renderReadErrorDegradedState(root, generation, reason) {
    var zones = readErrorFallbackZones(root);
    if (!zones.length) {
      console.error('[E10] cinematic-state read error has no E10 zone fallback:', reason);
      return false;
    }
    var stageState = root.__e9WorldStageState || (root.__e9WorldStageState = {});
    stageState.cinematicReadError = true;
    stageState.cinematics = {};
    renderZones(root, zones, {
      generation: generation,
      currentZoneKey: null,
      primaryAction: null,
      secondaryAction: null,
      cinematics: {},
      cinematicReadError: true,
    });
    enableImmersiveRpgSkin(root, generation);
    console.warn('[E10] cinematic-state read unavailable; keeping E10 shell with conservative Zone 1 entry:', reason);
    return true;
  }

  function loadAvatarPresentation(root, generation) {
    var current = function () {
      return !window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' ||
        window.E9.isLifecycleCurrent(generation);
    };
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.PlayerState;
    if (!adapter || typeof adapter.fetchAvatarPresentation !== 'function') {
      console.error('[E10] world_stage: resolved avatar presentation provider unavailable');
      return;
    }
    adapter.fetchAvatarPresentation().then(function (result) {
      if (!current()) return;
      var state = root.__e9WorldStageState;
      if (!state) return;
      state.avatarPresentation = result && result.ok ? result.data : null;
      if (state.zones && state.zones.length) {
        renderZones(root, state.zones, {
          currentZoneKey: state.authoritativeCurrentZoneKey,
          primaryAction: state.primaryAction,
          secondaryAction: state.secondaryAction,
          generation: state.generation,
        });
      }
    }).catch(function (err) {
      if (current()) console.error('[E10] world_stage avatar presentation fetch failed:', err);
    });
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

    var stateRequest = typeof adapter.refreshAdventureState === 'function'
      ? adapter.refreshAdventureState()
      : adapter.fetchAdventureState(null, { forceRefresh: true });
    stateRequest.then(function (result) {
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
        renderReadErrorDegradedState(
          root,
          generation,
          new Error('adventure data fetch failed: ' + result.kind + ' (status ' + result.status + ')')
        );
        return;
      }
      if (!result.data.zones.length) {
        // Structurally valid response but zero usable zones -- still a
        // critical condition (World Stage has nothing real to show), not
        // rendered as a fabricated empty board.
        recoverToLegacy(new Error('adventure data returned zero valid zones'));
        return;
      }
      var authority = result.data;
      authority.generation = generation;
      var stageState = root.__e9WorldStageState;
      if (stageState) {
        stageState.authoritativeCurrentZoneKey = authority.currentZoneKey;
        stageState.primaryAction = authority.primaryAction;
        stageState.generation = generation;
        if (!stageState.selectedZoneKey && authority.selected && typeof authority.selected.zone_key === 'string') {
          stageState.selectedZoneKey = authority.selected.zone_key;
        }
      }
      // Pass the complete fresh authority snapshot into the render boundary.
      // Keeping current_zone_key and primary_action explicit here prevents a
      // re-entry render from relying on the previous in-memory stage state.
      renderZones(root, result.data.zones, authority);
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
      authoritativeCurrentZoneKey: null,
      selectedZoneKey: null,
      challengeTargetZoneKey: null,
      primaryAction: null,
      secondaryAction: null,
      avatarPresentation: null,
      cinematics: {},
      generation: generation,
    };
    var onChanged = function () {
      var state = root.__e9WorldStageState;
      if ((!window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation)) && state && state.zones && state.zones.length) renderZones(root, state.zones, {
        currentZoneKey: state.authoritativeCurrentZoneKey,
        primaryAction: state.primaryAction,
        secondaryAction: state.secondaryAction,
        generation: state.generation,
      });
    };
    var onReady = function () {
      var state = root.__e9WorldStageState;
      if ((!window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation)) && state && state.zones && state.zones.length) renderZones(root, state.zones, {
        currentZoneKey: state.authoritativeCurrentZoneKey,
        primaryAction: state.primaryAction,
        secondaryAction: state.secondaryAction,
        generation: state.generation,
      });
    };
    var onAvatar = function (event) {
      // The event is a refresh hint only. Never trust the HUD DOM/source or a
      // preview event as appearance authority; re-read the committed provider.
      loadAvatarPresentation(root, generation);
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
    loadAvatarPresentation(root, generation);
    load(root, false, generation);
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'world_stage') {
      init(e.detail.root, e.detail.generation);
    }
  });

  // Shared with other E9 components (right_cards.js's own zone-detail CTA)
  // that dispatch the same {enabled, targetZoneKey, kind} contract this
  // module already produces via ctaContract()/zoneSelectionDetail() -- a
  // second, independent copy of this routing decision is exactly how the
  // CTA_ACTION_ROUTING_DEFECT regression reached a third surface unnoticed.
  window.E9 = window.E9 || {};
  window.E9.dispatchAdventureAction = dispatchAdventureAction;
  window.E9.replayAdventureIntro = replayAdventureIntro;
  window.E9.showAdventureZoneCard = showAdventureZoneCard;
  window.E9.updateAdventureCinematicState = updateAdventureCinematicState;
})(document);
