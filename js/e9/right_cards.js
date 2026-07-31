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
    var title = root.querySelector('#e10-drawer-zone-title');
    var state = root.querySelector('#e10-drawer-zone-state');
    var body = root.querySelector('#e10-drawer-zone-body');
    root.__e10SelectedLandmarkSrc = detail.landmarkSrc || '';
    syncDrawerLandmark(root);
    if (title) {
      title.textContent = detail.name || detail.zoneKey || '';
      title.removeAttribute('data-i18n');
    }
    if (state) state.textContent = detail.statusText || '';
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
    var setOpen = function (open, restoreFocus) {
      if (!toggle || !panel) return;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      panel.hidden = !open;
      root.classList.toggle('is-drawer-open', open);
      if (slot) slot.classList.toggle('is-drawer-open', open);
      if (shell) shell.classList.toggle('is-right-drawer-open', open);
      if (backdrop) backdrop.hidden = !open;
      syncDrawerLandmark(root);
      if (!open && restoreFocus && root.__e9DrawerTrigger) {
        root.__e9DrawerTrigger.focus();
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
      var onZoneSelected = function (evt) { updateDrawerZoneSummary(root, evt.detail); };
      var onI18nChanged = function () {
        if (!current()) return;
        var progress = root.__e9CompactProgress;
        if (progress) setCompactProgress(root, progress.cleared, progress.total);
        if (window.E9 && window.E9.latestZoneSelection) {
          updateDrawerZoneSummary(root, window.E9.latestZoneSelection);
        }
      };
      setOpen(false, false);
      if (window.E9 && window.E9.latestZoneSelection) {
        updateDrawerZoneSummary(root, window.E9.latestZoneSelection);
      }
      if (window.E9 && typeof window.E9.on === 'function') {
        window.E9.on(toggle, 'click', onToggle, null, generation);
        if (closeButton) window.E9.on(closeButton, 'click', function () { setOpen(false, true); }, null, generation);
        if (backdrop) window.E9.on(backdrop, 'click', function () { setOpen(false, true); }, null, generation);
        window.E9.on(document, 'keydown', onKey, null, generation);
        window.E9.on(document, 'e9:zone-selected', onZoneSelected, null, generation);
        window.E9.on(document, 'e9:i18n-changed', onI18nChanged, null, generation);
        window.E9.on(document, 'e9:adventure-command', onAdventure, null, generation);
      } else {
        toggle.addEventListener('click', onToggle);
        if (closeButton) closeButton.addEventListener('click', function () { setOpen(false, true); });
        if (backdrop) backdrop.addEventListener('click', function () { setOpen(false, true); });
        document.addEventListener('keydown', onKey);
        document.addEventListener('e9:zone-selected', onZoneSelected);
        document.addEventListener('e9:adventure-command', onAdventure);
        document.addEventListener('e9:i18n-changed', onI18nChanged);
      }
    }

    if (window.E9 && typeof window.E9.registerCleanup === 'function') {
      window.E9.registerCleanup(function () {
        delete root.__e9CompactProgress;
        delete root.__e10SelectedLandmarkSrc;
        if (backdrop) backdrop.remove();
        if (slot) slot.classList.remove('is-drawer-open');
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
