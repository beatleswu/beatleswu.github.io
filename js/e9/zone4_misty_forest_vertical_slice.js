(function (root, factory) {
  'use strict';

  var api = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.GoOdysseyZone4MistyForestVerticalSlice = api;
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this), function (global) {
  'use strict';

  var CONTRACT_VERSION = 'W2_01_ZONE4_MISTY_FOREST_VERTICAL_SLICE_V1';
  var SUPPORTED_LOCALES = ['zh-TW', 'en-US'];
  var ZONE_KEY = 'k11_15';
  var SHOT_IDS = [];
  for (var shotNumber = 1; shotNumber <= 10; shotNumber += 1) {
    SHOT_IDS.push('Z4_S' + String(shotNumber).padStart(2, '0'));
  }

  function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function asText(value) {
    return typeof value === 'string' ? value : '';
  }

  function selectedLocale(locale) {
    if (SUPPORTED_LOCALES.indexOf(locale) >= 0) return locale;
    return 'zh-TW';
  }

  function validateManifest(manifest) {
    if (!isObject(manifest) || manifest.schemaVersion !== 'w2-01.zone4.misty-forest.vertical-slice.v1') return false;
    if (!isObject(manifest.zone) || manifest.zone.key !== ZONE_KEY) return false;
    if (!isObject(manifest.story) || manifest.story.canonicalShotCount !== 10) return false;
    if (!Array.isArray(manifest.story.shots) || manifest.story.shots.length !== 10) return false;
    for (var i = 0; i < SHOT_IDS.length; i += 1) {
      if (!isObject(manifest.story.shots[i]) || manifest.story.shots[i].id !== SHOT_IDS[i]) return false;
    }
    if (!isObject(manifest.locales) || !isObject(manifest.locales['zh-TW']) || !isObject(manifest.locales['en-US'])) return false;
    if (!isObject(manifest.locales['zh-TW'].dialogue) || !isObject(manifest.locales['en-US'].dialogue)) return false;
    return true;
  }

  function resolveShot(manifest, index) {
    if (!manifest || !manifest.story || !Array.isArray(manifest.story.shots)) return null;
    return manifest.story.shots[index] || null;
  }

  function beatForShot(manifest, shot) {
    var beats = manifest.story.dialogueBeats || [];
    var ids = shot && Array.isArray(shot.dialogueBeatIds) ? shot.dialogueBeatIds : [];
    var selected = [];
    for (var i = 0; i < ids.length; i += 1) {
      for (var j = 0; j < beats.length; j += 1) {
        if (beats[j].beatId === ids[i]) selected.push(beats[j]);
      }
    }
    return selected;
  }

  function uiFor(manifest, locale) {
    var packageForLocale = manifest.locales[locale] || {};
    return packageForLocale.ui || {};
  }

  function formatShotLabel(template, shotNumber, total) {
    return asText(template).replace('{shot}', String(shotNumber)).replace('{total}', String(total));
  }

  function find(root, selector) {
    return root && typeof root.querySelector === 'function' ? root.querySelector(selector) : null;
  }

  function create(options) {
    options = options || {};
    var manifest = options.manifest;
    if (!validateManifest(manifest)) throw new TypeError('Zone 4 vertical-slice manifest is invalid');

    var documentRef = options.document || (global && global.document);
    var mount = options.mount || (documentRef && documentRef.querySelector('[data-zone4-vertical-slice]'));
    if (!mount || typeof mount.querySelector !== 'function') throw new TypeError('Zone 4 vertical-slice mount is required');

    var state = {
      index: 0,
      locale: selectedLocale(options.locale),
      replayCount: 0,
      destroyed: false,
    };

    var image = find(mount, '[data-zone4-image]');
    var empty = find(mount, '[data-zone4-empty]');
    var status = find(mount, '[data-zone4-status]');
    var line = find(mount, '[data-zone4-line]');
    var speaker = find(mount, '[data-zone4-speaker]');
    var assetNote = find(mount, '[data-zone4-asset-note]');
    var handoff = find(mount, '[data-zone4-handoff]');
    var title = find(mount, '[data-zone4-title]');
    var kicker = find(mount, '[data-zone4-kicker]');
    var dialoguePanel = find(mount, '[data-zone4-dialogue-panel]');
    var controls = find(mount, '[data-zone4-controls]');
    var previous = find(mount, '[data-zone4-action="previous"]');
    var next = find(mount, '[data-zone4-action="next"]');
    var replay = find(mount, '[data-zone4-action="replay"]');

    function render() {
      if (state.destroyed) return false;
      var locale = state.locale;
      var ui = uiFor(manifest, locale);
      var shot = resolveShot(manifest, state.index);
      if (!shot) return false;
      var beats = beatForShot(manifest, shot);
      var localeDialogue = manifest.locales[locale].dialogue || {};
      var firstBeat = beats.length ? beats[0] : null;
      var visibleLine = firstBeat ? asText(localeDialogue[firstBeat.i18nKey]) : '';
      var hasLocalizedLine = visibleLine.length > 0;
      var imageData = shot.image || {};
      var canRenderImage = imageData.renderableInBoundedSlice === true && asText(imageData.path).length > 0;

      mount.setAttribute('data-zone4-ready', 'true');
      mount.setAttribute('data-zone4-locale', locale);
      mount.setAttribute('data-zone4-shot', shot.id);
      mount.setAttribute('data-zone4-phase', asText(shot.phase));
      mount.setAttribute('data-zone4-image-status', asText(imageData.status));
      mount.setAttribute('data-zone4-presentation-only', 'true');
      mount.setAttribute('data-zone4-gameplay-mutation', 'false');
      mount.setAttribute('data-zone4-replay-count', String(state.replayCount));

      if (title) title.textContent = asText(manifest.zone.names[locale]);
      if (kicker) kicker.textContent = asText(ui.kicker);
      if (dialoguePanel) dialoguePanel.setAttribute('aria-label', asText(ui.dialogueLabel));
      if (controls) controls.setAttribute('aria-label', asText(ui.controlsLabel));
      if (status) status.textContent = formatShotLabel(ui.shotLabel, shot.number, manifest.story.canonicalShotCount) + ' · ' + asText(ui[shot.phase === 'PRE_PLAY' ? 'prePlay' : (shot.phase === 'POST_CLEAR' ? 'postClear' : 'postClearHook')]);
      if (previous) {
        previous.textContent = asText(ui.previous);
        previous.disabled = state.index === 0;
        previous.setAttribute('aria-label', asText(ui.previous));
      }
      if (next) {
        next.textContent = asText(ui.next);
        next.disabled = state.index >= manifest.story.shots.length - 1;
        next.setAttribute('aria-label', asText(ui.next));
      }
      if (replay) {
        replay.textContent = asText(ui.replay);
        replay.setAttribute('aria-label', asText(ui.replay));
      }
      if (image) {
        image.hidden = !canRenderImage;
        if (canRenderImage) {
          image.src = imageData.path;
          image.alt = imageData.alt && asText(imageData.alt[locale]) ? imageData.alt[locale] : '';
        } else {
          image.removeAttribute('src');
          image.alt = '';
        }
      }
      if (empty) empty.hidden = canRenderImage;
      if (assetNote) assetNote.textContent = canRenderImage ? asText(ui.legacyAsset) : asText(ui.missingAsset);
      if (speaker) speaker.textContent = firstBeat ? asText(firstBeat.character) : '';
      if (line) line.textContent = hasLocalizedLine ? visibleLine : (firstBeat ? asText(ui.subtitlePending) : asText(ui.silent));
      mount.setAttribute('data-zone4-dialogue-state', firstBeat ? (hasLocalizedLine ? 'localized' : 'translation-pending') : 'silent');
      if (handoff) {
        var isHandoff = shot.handoff === 'HANDOFF_TO_GAMEPLAY_AFTER_SHOT';
        var isEnding = shot.handoff === 'END_CINEMATIC_SEQUENCE_AFTER_SHOT';
        handoff.hidden = !isHandoff && !isEnding;
        handoff.textContent = isHandoff ? asText(ui.handoff) : (isEnding ? asText(ui.endingHook) : '');
      }
      return true;
    }

    function nextShot() {
      if (state.destroyed || state.index >= manifest.story.shots.length - 1) return false;
      state.index += 1;
      return render();
    }

    function previousShot() {
      if (state.destroyed || state.index <= 0) return false;
      state.index -= 1;
      return render();
    }

    function replaySlice() {
      if (state.destroyed) return false;
      state.index = 0;
      state.replayCount += 1;
      return render();
    }

    function setLocale(locale) {
      if (state.destroyed) return false;
      state.locale = selectedLocale(locale);
      return render();
    }

    function snapshot() {
      var shot = resolveShot(manifest, state.index);
      return {
        contractVersion: CONTRACT_VERSION,
        zoneKey: ZONE_KEY,
        locale: state.locale,
        shotId: shot ? shot.id : null,
        phase: shot ? shot.phase : null,
        replayCount: state.replayCount,
        presentationOnly: true,
        gameplayMutation: false,
      };
    }

    function destroy() {
      if (state.destroyed) return;
      state.destroyed = true;
      mount.removeAttribute('data-zone4-ready');
      mount.textContent = '';
    }

    if (previous) previous.addEventListener('click', previousShot);
    if (next) next.addEventListener('click', nextShot);
    if (replay) replay.addEventListener('click', replaySlice);
    render();

    return {
      contractVersion: CONTRACT_VERSION,
      render: render,
      next: nextShot,
      previous: previousShot,
      replay: replaySlice,
      setLocale: setLocale,
      snapshot: snapshot,
      destroy: destroy,
    };
  }

  return {
    CONTRACT_VERSION: CONTRACT_VERSION,
    SUPPORTED_LOCALES: SUPPORTED_LOCALES.slice(),
    validateManifest: validateManifest,
    create: create,
  };
});
