/*
 * E9 Right Cards — component init (non-critical).
 * Operates only on its own root. Each card fetches independently via
 * js/e9/adapters/activity_state.js and fails independently -- one card
 * erroring never blocks the others. Real data sources only (no new API,
 * no fabricated numbers):
 *   GET /api/daily-challenge/today
 *   GET /api/adventure/bootstrap  -> zones[] (boss progress summary)
 *   GET /api/srs/due              -> {due:[], count}
 *   GET /api/mistakes/stats       -> {total, corrected, worst5}
 */
(function (document) {
  'use strict';

  function t(key, fallback) {
    if (window.E9 && window.E9.I18nFallback && typeof window.E9.I18nFallback.t === 'function') {
      return window.E9.I18nFallback.t(key, fallback);
    }
    return fallback;
  }

  function setBody(root, cardKey, text) {
    var el = root.querySelector('[data-e9-card-body="' + cardKey + '"]');
    if (!el) return;
    el.textContent = text;
    // Each card body starts with a static data-i18n="e9.right_cards.loading"
    // placeholder. Remove it once real content/empty/error text is set, so
    // a later, unrelated I18n.apply() elsewhere on the page cannot silently
    // revert it back to "Loading…" (see js/e9/top_hud.js for the same fix
    // and the live-verified regression this addresses).
    el.removeAttribute('data-i18n');
  }

  function formatCompactProgress(cleared, total) {
    return t('e10.world_stage.progress_compact', '')
      .replace('{n}', cleared || 0).replace('{t}', total || 0);
  }

  function setCompactProgress(root, cleared, total) {
    root.__e9CompactProgress = { cleared: cleared, total: total };
    var compact = formatCompactProgress(cleared, total);
    var toggle = root.querySelector('#e9-right-drawer-toggle');
    var mobileSummary = root.querySelector('#e9-right-drawer-mobile-summary');
    if (toggle) {
      toggle.textContent = compact + ' ▾';
      toggle.setAttribute('aria-label', compact);
      toggle.removeAttribute('data-i18n');
    }
    if (mobileSummary) {
      mobileSummary.textContent = compact;
      mobileSummary.removeAttribute('data-i18n');
    }
  }

  function setCompactProgressLoading(root) {
    root.__e9CompactProgress = null;
    var loading = t('e9.right_cards.loading', 'Loading…');
    var toggle = root.querySelector('#e9-right-drawer-toggle');
    var mobileSummary = root.querySelector('#e9-right-drawer-mobile-summary');
    if (toggle) {
      toggle.textContent = loading;
      toggle.setAttribute('aria-label', loading);
      toggle.removeAttribute('data-i18n');
    }
    if (mobileSummary) {
      mobileSummary.textContent = loading;
      mobileSummary.removeAttribute('data-i18n');
    }
  }

  function syncDrawerLandmark(root) {
    var landmark = root.querySelector('#e10-drawer-zone-landmark');
    var toggle = root.querySelector('#e9-right-drawer-toggle');
    var desktopSurface = window.matchMedia && window.matchMedia(
      '(min-width: 768px) and (orientation: landscape), (min-width: 1280px)'
    ).matches;
    var source = root.__e10SelectedLandmarkSrc;
    if (!landmark) return;
    if (desktopSurface && toggle && toggle.getAttribute('aria-expanded') === 'true' && source) {
      if (landmark.getAttribute('src') !== source) landmark.setAttribute('src', source);
      landmark.hidden = false;
    } else {
      landmark.hidden = true;
      landmark.removeAttribute('src');
    }
  }

  function updateDrawerZoneSummary(root, detail) {
    if (!detail) return;
    var kicker = root.querySelector('.e10-drawer-zone-summary__kicker');
    var title = root.querySelector('#e10-drawer-zone-title');
    var state = root.querySelector('#e10-drawer-zone-state');
    var body = root.querySelector('#e10-drawer-zone-body');
    var number = root.querySelector('[data-e10-zone-number]');
    var stars = root.querySelector('[data-e10-zone-stars]');
    var questValue = root.querySelector('[data-e10-zone-quest-value]');
    var questBar = root.querySelector('[data-e10-zone-quest-bar]');
    var regionValue = root.querySelector('[data-e10-zone-region-value]');
    var regionBar = root.querySelector('[data-e10-zone-region-bar]');
    var cta = root.querySelector('[data-e10-zone-cta]');
    var secondaryCta = root.querySelector('[data-e10-zone-secondary-cta]');
    var replay = root.querySelector('[data-e10-zone-replay]');
    root.__e10SelectedLandmarkSrc = detail.landmarkSrc || '';
    root.__e10SelectedZoneKey = detail.zoneKey || '';
    root.__e10ChallengeTargetZoneKey = detail.challengeTargetZoneKey || '';
    root.__e10ChallengeTargetEnabled = detail.ctaEnabled === true;
    root.__e10ChallengeTargetKind = detail.ctaKind || null;
    root.__e10SecondaryTargetZoneKey = detail.zoneKey || '';
    root.__e10SecondaryTargetEnabled = detail.secondaryCtaEnabled === true;
    root.__e10SecondaryTargetKind = detail.secondaryCtaKind || null;
    syncDrawerLandmark(root);
    if (kicker) {
      kicker.textContent = detail.headingText || t(detail.headingKey, 'Selected Zone');
      kicker.setAttribute('data-zone-heading', detail.isCurrentPlayerZone ? 'current' : 'selected');
      kicker.removeAttribute('data-i18n');
    }
    if (title) {
      title.textContent = (detail.zoneNumber ? 'Zone ' + detail.zoneNumber + ' · ' : '') + (detail.name || detail.zoneKey || '');
      title.removeAttribute('data-i18n');
    }
    if (state) state.textContent = detail.statusText || '';
    if (number) number.textContent = String(detail.zoneNumber || '');
    if (stars) {
      var earnedStars = Math.max(0, Math.min(3, detail.stars || 0));
      stars.textContent = '';
      stars.setAttribute('aria-label', t('index.adv.stars_label', 'Stars') + ': ' + earnedStars + ' / 3');
      for (var starIndex = 0; starIndex < 3; starIndex += 1) {
        var star = document.createElement('i');
        star.className = 'e10-art-star' + (starIndex < earnedStars ? ' is-earned' : ' is-empty');
        star.setAttribute('aria-hidden', 'true');
        stars.appendChild(star);
      }
    }
    var questPercent = detail.total ? Math.max(0, Math.min(100, detail.seen / detail.total * 100)) : 0;
    var regionPercent = detail.zoneNumber ? Math.max(0, Math.min(100, detail.zoneNumber / 10 * 100)) : 0;
    if (questValue) questValue.textContent = (detail.seen || 0) + ' / ' + (detail.total || 0);
    if (questBar) questBar.style.width = questPercent + '%';
    if (regionValue) regionValue.textContent = (detail.zoneNumber || 0) + ' / 10';
    if (regionBar) regionBar.style.width = regionPercent + '%';
    if (cta) {
      cta.hidden = false;
      cta.disabled = detail.ctaEnabled !== true;
      cta.setAttribute('aria-disabled', detail.ctaEnabled === true ? 'false' : 'true');
      cta.setAttribute('data-challenge-target-zone', detail.challengeTargetZoneKey || '');
      cta.textContent = detail.ctaLabel || t('e10.world_stage.state_locked', 'Locked');
      cta.removeAttribute('data-i18n');
    }
    if (secondaryCta) {
      secondaryCta.hidden = detail.secondaryCtaEnabled !== true;
      secondaryCta.disabled = detail.secondaryCtaEnabled !== true;
      secondaryCta.setAttribute('aria-disabled', detail.secondaryCtaEnabled === true ? 'false' : 'true');
      secondaryCta.setAttribute('data-challenge-target-zone', detail.zoneKey || '');
      secondaryCta.textContent = detail.secondaryCtaLabel || t('e10.world_stage.replenish_stars', 'Replenish Stars');
      secondaryCta.removeAttribute('data-i18n');
    }
    if (replay) {
      // E10_REPLAY_STORY_CROSS_SURFACE_IPAD_HOTFIX_002: ask the one shared
      // availability authority (world_stage.js), never a zone-key allowlist.
      // This used to read `detail.zoneKey === 'k26_30'`, which both showed a
      // button the dispatcher would refuse (Zone 1, dead tap on iPad
      // landscape) and hid a legitimate one (Zone 2, which declares
      // replayable segments). Visibility and dispatch now answer to the same
      // predicate, so this surface cannot render a dead button again.
      var replayEnabled = !!(window.E9
        && typeof window.E9.zoneReplayStoryAvailable === 'function'
        && window.E9.zoneReplayStoryAvailable(detail.zoneKey, detail));
      replay.hidden = !replayEnabled;
      replay.disabled = !replayEnabled;
      replay.setAttribute('aria-hidden', replayEnabled ? 'false' : 'true');
      if (replayEnabled) {
        replay.textContent = t('e10.world_stage.replay_story', 'Replay Story');
        replay.removeAttribute('data-i18n');
      }
    }
    if (body) {
      body.textContent = [detail.summary, detail.progress].filter(Boolean).join(' · ');
      body.removeAttribute('data-i18n');
    }
  }

  function errorTextFor(cardKey, result) {
    if (result.kind === 'unauthorized') return t('e9.right_cards.unauthorized', 'Please log in again');
    return t('e9.right_cards.error', 'Unavailable');
  }

  function loadDailyChallenge(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'daily_challenge', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchDailyChallenge().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'daily_challenge', errorTextFor('daily_challenge', result));
        return;
      }
      var text = result.data.submitted
        ? t('e9.right_cards.daily_challenge_done', 'Completed today')
        : t('e9.right_cards.daily_challenge_available', 'Available now');
      setBody(root, 'daily_challenge', text);
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards daily_challenge fetch failed (non-critical):', err);
      setBody(root, 'daily_challenge', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function loadBossProgress(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'boss_progress', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchBossProgress().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'boss_progress', errorTextFor('boss_progress', result));
        return;
      }
      var d = result.data;
      setCompactProgress(root, d.cleared, d.total);
      if (!d.total) {
        setBody(root, 'boss_progress', t('e9.right_cards.empty', 'No data yet'));
        return;
      }
      setBody(root, 'boss_progress', t('index.adv.summary', '{n} / {t} areas cleared')
        .replace('{n}', d.cleared).replace('{t}', d.total));
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards boss_progress fetch failed (non-critical):', err);
      setBody(root, 'boss_progress', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function loadSrsDue(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'srs_due', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchSrsDue().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'srs_due', errorTextFor('srs_due', result));
        return;
      }
      var count = result.data.count;
      setBody(root, 'srs_due', count !== null && count > 0 ? String(count) : t('e9.right_cards.empty', 'No data yet'));
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards srs_due fetch failed (non-critical):', err);
      setBody(root, 'srs_due', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function loadWeakness(root, current) {
    var adapter = window.E9 && window.E9.Adapters && window.E9.Adapters.ActivityState;
    if (!adapter) return setBody(root, 'weakness', t('e9.right_cards.error', 'Unavailable'));
    adapter.fetchMistakes().then(function (result) {
      if (!current()) return;
      if (!result.ok) {
        setBody(root, 'weakness', errorTextFor('weakness', result));
        return;
      }
      var total = result.data.total;
      setBody(root, 'weakness', total !== null && total > 0 ? String(total) : t('e9.right_cards.empty', 'No data yet'));
    }).catch(function (err) {
      if (!current()) return;
      console.error('[E9] right_cards weakness fetch failed (non-critical):', err);
      setBody(root, 'weakness', t('e9.right_cards.error', 'Unavailable'));
    });
  }

  function init(root, generation) {
    if (root.getAttribute('data-e9-inited') === '1') return;
    root.setAttribute('data-e9-inited', '1');
    setCompactProgress(root, 0, 0);
    var toggle = root.querySelector('#e9-right-drawer-toggle');
    var panel = root.querySelector('#e9-right-drawer-panel');
    var closeButton = root.querySelector('#e10-right-drawer-close');
    var slot = root.parentElement;
    var shell = document.querySelector('.e9-body');
    var registry = window.E9 && window.E9.NavigationRegistry;
    var exactVs1f = !!(registry && registry.exactContract && registry.exactContract());
    var backdrop = null;
    if (exactVs1f && slot) {
      if (closeButton) closeButton.innerHTML = registry.icon('close', 'e10-close-icon');
      var zoneSummary = root.querySelector('.e10-drawer-zone-summary');
      if (zoneSummary) {
        var kicker = zoneSummary.querySelector('.e10-drawer-zone-summary__kicker');
        if (kicker) kicker.setAttribute('data-i18n', 'e10.world_stage.current_zone');
        var state = zoneSummary.querySelector('#e10-drawer-zone-state');
        var body = zoneSummary.querySelector('#e10-drawer-zone-body');
        var information = document.createElement('div');
        information.className = 'e10-zone-panel-information';
        information.setAttribute('data-e10-zone-information', '');
        information.innerHTML = '<span class="e10-zone-panel-runtime__number" data-e10-zone-number></span>'
          + '<div class="e10-zone-panel-information__copy"></div>';
        var informationCopy = information.querySelector('.e10-zone-panel-information__copy');
        if (informationCopy) {
          if (state) informationCopy.appendChild(state);
          if (body) informationCopy.appendChild(body);
        }
        zoneSummary.appendChild(information);
        var presentation = document.createElement('div');
        presentation.className = 'e10-zone-panel-runtime';
        presentation.setAttribute('data-e10-vs1f-zone-panel', '');
        presentation.innerHTML = '<span class="e10-zone-panel-runtime__stars" data-e10-zone-stars></span>'
          + '<div class="e10-zone-panel-runtime__metric"><span data-i18n="e10.world_stage.task_progress"></span><strong data-e10-zone-quest-value></strong><i><b data-e10-zone-quest-bar></b></i></div>'
          + '<div class="e10-zone-panel-runtime__metric"><span data-i18n="e10.world_stage.region_progress"></span><strong data-e10-zone-region-value></strong><i><b data-e10-zone-region-bar></b></i></div>'
          + '<button type="button" class="e10-zone-panel-runtime__cta" data-e10-zone-cta data-i18n="e10.world_stage.continue_adventure"></button>'
          + '<button type="button" class="e10-zone-panel-runtime__cta e10-zone-panel-runtime__cta--secondary" data-e10-zone-secondary-cta hidden></button>';
        zoneSummary.appendChild(presentation);
        var zoneCta = presentation.querySelector('[data-e10-zone-cta]');
        if (zoneCta) {
          window.E9.on(zoneCta, 'click', function () {
            // Route through the same shared dispatcher world_stage.js's own
            // CTAs use -- a 'challenge_lord' target must enter the existing
            // canonical Lord flow, never the ordinary startAdventureFromE9()
            // handoff this panel used to call unconditionally.
            if (window.E9 && typeof window.E9.dispatchAdventureAction === 'function') {
              window.E9.dispatchAdventureAction({
                enabled: root.__e10ChallengeTargetEnabled,
                targetZoneKey: root.__e10ChallengeTargetZoneKey,
                kind: root.__e10ChallengeTargetKind,
              });
            }
          }, null, generation);
        }
        var secondaryCta = presentation.querySelector('[data-e10-zone-secondary-cta]');
        if (secondaryCta) {
          window.E9.on(secondaryCta, 'click', function () {
            if (window.E9 && typeof window.E9.dispatchAdventureAction === 'function') {
              window.E9.dispatchAdventureAction({
                enabled: root.__e10SecondaryTargetEnabled,
                targetZoneKey: root.__e10SecondaryTargetZoneKey,
                kind: root.__e10SecondaryTargetKind,
              });
            }
          }, null, generation);
        }
        var replayButton = zoneSummary.querySelector('[data-e10-zone-replay]');
        if (replayButton) {
          window.E9.on(replayButton, 'click', function (event) {
            if (event) event.stopPropagation();
            if (window.E9 && typeof window.E9.replayAdventureIntro === 'function') {
              window.E9.replayAdventureIntro(root.__e10SelectedZoneKey);
            }
          }, null, generation);
        }
        if (window.I18n && window.I18n.apply) window.I18n.apply(zoneSummary);
      }
      backdrop = document.createElement('button');
      backdrop.type = 'button';
      backdrop.className = 'e10-drawer-backdrop';
      backdrop.hidden = true;
      backdrop.tabIndex = -1;
      backdrop.setAttribute('aria-hidden', 'true');
      slot.insertAdjacentElement('beforebegin', backdrop);
    } else if (closeButton) {
      closeButton.remove();
      closeButton = null;
    }
    var current = function () {
      return !window.E9 || typeof window.E9.isLifecycleCurrent !== 'function' || window.E9.isLifecycleCurrent(generation);
    };
    var onAdventureStateUpdated = function () {
      if (!current()) return;
      // Boss settlement invalidates the shared Adventure adapter. Clear the
      // compact value before re-reading it so a drawer opened immediately
      // after settlement cannot show the pre-clear progress snapshot.
      setCompactProgressLoading(root);
      setBody(root, 'boss_progress', t('e9.right_cards.loading', 'Loading…'));
      loadBossProgress(root, current);
    };
    var setOpen = function (open, restoreFocus) {
      if (!toggle || !panel) return;
      // On stacked portrait surfaces the lower Zone Card owns the detail
      // interaction. A late zone-card event must not reopen the desktop
      // drawer/backdrop after ownership has already moved to that card.
      if (root.getAttribute('data-e10-detail-owner') === 'lower-card') open = false;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      panel.hidden = !open;
      root.classList.toggle('is-drawer-open', open);
      if (slot) slot.classList.toggle('is-drawer-open', open);
      if (shell) shell.classList.toggle('is-right-drawer-open', open);
      if (backdrop) {
        backdrop.hidden = !open;
        backdrop.style.display = open ? '' : 'none';
        backdrop.style.pointerEvents = open ? '' : 'none';
        backdrop.setAttribute('aria-hidden', open ? 'false' : 'true');
      }
      syncDrawerLandmark(root);
      if (!open && restoreFocus && root.__e9DrawerTrigger) {
        root.__e9DrawerTrigger.focus();
      }
    };
    var stackedDetailSurface = window.matchMedia && window.matchMedia(
      '(max-width: 1279px) and (orientation: portrait), (max-width: 767px)'
    );
    var portraitLowerCardSurface = window.matchMedia && window.matchMedia(
      '(min-width: 768px) and (max-width: 1279px) and (orientation: portrait)'
    );
    var syncDetailSurfaceOwnership = function () {
      var lowerCardOwnsDetails = !!(stackedDetailSurface && stackedDetailSurface.matches);
      var adventureShell = document.querySelector('#e9-adventure-shell');
      var immersiveShell = !!(adventureShell && adventureShell.getAttribute('data-e10-visual-skin') === 'immersive-rpg');
      var lowerCard = adventureShell && adventureShell.querySelector('#e9-world-stage-details');
      if (lowerCardOwnsDetails) setOpen(false, false);
      root.hidden = lowerCardOwnsDetails;
      root.inert = lowerCardOwnsDetails;
      root.setAttribute('aria-hidden', lowerCardOwnsDetails ? 'true' : 'false');
      root.setAttribute('data-e10-detail-owner', lowerCardOwnsDetails ? 'lower-card' : 'side-panel');
      if (toggle) {
        if (lowerCardOwnsDetails) toggle.tabIndex = -1;
        else toggle.removeAttribute('tabindex');
      }
      if (backdrop && lowerCardOwnsDetails) backdrop.hidden = true;
      if (immersiveShell && lowerCard) {
        lowerCard.hidden = !(portraitLowerCardSurface && portraitLowerCardSurface.matches);
      }
    };
    if (toggle && panel) {
      var onToggle = function () {
        root.__e9DrawerTrigger = toggle;
        setOpen(toggle.getAttribute('aria-expanded') !== 'true', false);
      };
      var onKey = function (evt) {
        if (evt.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') setOpen(false, true);
      };
      var onAdventure = function () { setOpen(false, false); };
      var onZoneSelected = function (evt) {
        updateDrawerZoneSummary(root, evt.detail);
        // Side-panel surfaces have no lower Zone Card to own the selected
        // zone's replay action. Open the already-rendered drawer only when
        // the shared replay predicate made that action genuinely available;
        // portrait/mobile ownership remains unchanged.
        var replay = root.querySelector('[data-e10-zone-replay]');
        var lowerOwner = root.getAttribute('data-e10-detail-owner') === 'lower-card';
        if (!lowerOwner && replay && !replay.hidden && !replay.disabled) {
          setOpen(true, false);
        }
      };
      var onZoneCardRequested = function () {
        if (window.E9 && window.E9.latestZoneSelection) {
          updateDrawerZoneSummary(root, window.E9.latestZoneSelection);
        }
        setOpen(true, false);
      };
      var onI18nChanged = function () {
        if (!current()) return;
        var progress = root.__e9CompactProgress;
        if (progress) setCompactProgress(root, progress.cleared, progress.total);
        if (window.E9 && window.E9.latestZoneSelection) {
          updateDrawerZoneSummary(root, window.E9.latestZoneSelection);
        }
      };
      setOpen(false, false);
      syncDetailSurfaceOwnership();
      if (window.E9 && window.E9.latestZoneSelection) {
        updateDrawerZoneSummary(root, window.E9.latestZoneSelection);
      }
      if (window.E9 && typeof window.E9.on === 'function') {
        window.E9.on(toggle, 'click', onToggle, null, generation);
        if (closeButton) window.E9.on(closeButton, 'click', function () { setOpen(false, true); }, null, generation);
        if (backdrop) window.E9.on(backdrop, 'click', function () { setOpen(false, true); }, null, generation);
        window.E9.on(document, 'keydown', onKey, null, generation);
        window.E9.on(document, 'e9:zone-selected', onZoneSelected, null, generation);
        window.E9.on(document, 'e9:zone-card-requested', onZoneCardRequested, null, generation);
        window.E9.on(document, 'e9:i18n-changed', onI18nChanged, null, generation);
        window.E9.on(document, 'e9:adventure-command', onAdventure, null, generation);
        window.E9.on(document, 'e10:adventure-state-updated', onAdventureStateUpdated, null, generation);
        if (stackedDetailSurface) window.E9.on(stackedDetailSurface, 'change', syncDetailSurfaceOwnership, null, generation);
        if (portraitLowerCardSurface) window.E9.on(portraitLowerCardSurface, 'change', syncDetailSurfaceOwnership, null, generation);
      } else {
        toggle.addEventListener('click', onToggle);
        if (closeButton) closeButton.addEventListener('click', function () { setOpen(false, true); });
        if (backdrop) backdrop.addEventListener('click', function () { setOpen(false, true); });
        document.addEventListener('keydown', onKey);
        document.addEventListener('e9:zone-selected', onZoneSelected);
        document.addEventListener('e9:zone-card-requested', onZoneCardRequested);
        document.addEventListener('e9:adventure-command', onAdventure);
        document.addEventListener('e9:i18n-changed', onI18nChanged);
        document.addEventListener('e10:adventure-state-updated', onAdventureStateUpdated);
        if (stackedDetailSurface && stackedDetailSurface.addEventListener) {
          stackedDetailSurface.addEventListener('change', syncDetailSurfaceOwnership);
        }
        if (portraitLowerCardSurface && portraitLowerCardSurface.addEventListener) {
          portraitLowerCardSurface.addEventListener('change', syncDetailSurfaceOwnership);
        }
      }
    }

    if (window.E9 && typeof window.E9.registerCleanup === 'function') {
      window.E9.registerCleanup(function () {
        delete root.__e9CompactProgress;
        delete root.__e10SelectedLandmarkSrc;
        delete root.__e10SelectedZoneKey;
        delete root.__e10ChallengeTargetZoneKey;
        delete root.__e10ChallengeTargetEnabled;
        delete root.__e10SecondaryTargetZoneKey;
        delete root.__e10SecondaryTargetEnabled;
        delete root.__e10SecondaryTargetKind;
        if (backdrop) backdrop.remove();
        if (slot) slot.classList.remove('is-drawer-open');
        root.hidden = false;
        root.inert = false;
        root.removeAttribute('aria-hidden');
        root.removeAttribute('data-e10-detail-owner');
        if (toggle) toggle.removeAttribute('tabindex');
        if (shell) shell.classList.remove('is-right-drawer-open');
      }, generation);
    }
    loadDailyChallenge(root, current);
    loadBossProgress(root, current);
    loadSrsDue(root, current);
    loadWeakness(root, current);
  }

  document.addEventListener('e9:component-loaded', function (e) {
    if (e.detail && e.detail.component === 'right_cards') {
      init(e.detail.root, e.detail.generation);
    }
  });
})(document);
