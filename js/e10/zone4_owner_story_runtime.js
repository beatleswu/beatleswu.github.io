(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.Zone4OwnerStoryRuntime = factory();
  }
}(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SUPPORTED_LOCALES = ["zh-TW", "en-GB"];

  function clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  function noop() {}

  function safeCall(fn) {
    try {
      return fn();
    } catch (_error) {
      return undefined;
    }
  }

  function create(options) {
    options = options || {};
    var matrix = options.matrix || {};
    var documentRef = options.document || (typeof document !== "undefined" ? document : null);
    var audioFactory = options.audioFactory || function (src) { return new Audio(src); };
    var onStateChange = options.onStateChange || noop;
    var beats = Array.isArray(matrix.beats) ? matrix.beats : [];
    var byId = {};
    beats.forEach(function (beat) { byId[beat.beat_id] = beat; });
    var tracks = matrix.tracks || {};
    var lordMachine = matrix.lord_state_machine || { lord_states: {}, start_state: "challenge_entry" };
    var lordStates = lordMachine.lord_states || {};
    var lordStateIds = Array.isArray(lordMachine.lord_state_ids) ? lordMachine.lord_state_ids : [];
    var stateMachineEnabled = !!matrix.lord_state_machine && lordStateIds.length > 0;
    var mainIds = tracks.main_story && tracks.main_story.beats ? tracks.main_story.beats.slice() : [];

    var state = {
      trackId: "main_story",
      beatId: mainIds[0] || null,
      lordState: null,
      lordPass: false,
      lordFailCount: 0,
      locale: "zh-TW",
      autoPlay: false,
      paused: true,
      status: "READY",
      lastAction: "initial_render",
      narrativeState: "PRACTICE",
      token: 0,
      active: { bgm: null, ambience: null, voice: null, shui: null, sfx: null, transition: null },
      fallbackCount: 0,
      overlapFailureCount: 0,
      replaySignature: null
    };

    function currentBeat() {
      return state.beatId ? (byId[state.beatId] || null) : null;
    }

    function lordRecord(stateKey) {
      return stateKey ? (lordStates[stateKey] || null) : null;
    }

    function isMainBeat(beatId) { return mainIds.indexOf(beatId) !== -1; }
    function isS3Beat(beatId) { return /^Z4_S3_/.test(beatId || ""); }
    function isLordTrack() { return state.trackId === "lord_trial"; }

    function trackBeatIds(trackId) {
      if (trackId === "lord_trial") return lordStateIds.slice();
      return tracks[trackId] && Array.isArray(tracks[trackId].beats) ? tracks[trackId].beats.slice() : [];
    }

    function currentIndex() {
      if (isLordTrack()) return state.lordState ? lordStateIds.indexOf(state.lordState) : -1;
      return trackBeatIds(state.trackId).indexOf(state.beatId);
    }

    function currentNarrativeState() {
      if (isLordTrack()) {
        if (state.lordState === "failure_retraining") return "LORD_FAIL";
        if (state.lordState === "success_background" || state.lordState === "success_portrait") return "LORD_PASS";
        if (state.lordState === "challenge_active") return "LORD_TRIAL_ACTIVE";
        return "LORD_TRIAL_ENTRY";
      }
      if (isS3Beat(state.beatId)) return "POST_LORD_S3";
      return "PRACTICE";
    }

    function activeIdentity(slot) {
      return state.active[slot] ? state.active[slot].identity_key : null;
    }

    function snapshot() {
      var beat = currentBeat();
      return {
        trackId: state.trackId,
        beatId: state.beatId,
        beatIndex: currentIndex(),
        lordState: state.lordState,
        lordPass: state.lordPass,
        lordFailCount: state.lordFailCount,
        narrativeState: state.narrativeState,
        locale: state.locale,
        autoPlay: state.autoPlay,
        paused: state.paused,
        status: state.status,
        lastAction: state.lastAction,
        activeMedia: {
          bgm: activeIdentity("bgm"),
          ambience: activeIdentity("ambience"),
          voice: activeIdentity("voice"),
          shui: activeIdentity("shui"),
          sfx: activeIdentity("sfx"),
          transition: activeIdentity("transition")
        },
        fallbackCount: state.fallbackCount,
        overlapFailureCount: state.overlapFailureCount,
        replaySignature: state.replaySignature,
        currentVisualId: beat && beat.visual ? beat.visual.asset_id : null
      };
    }

    function emit() { onStateChange(snapshot()); }

    function setStatus(status, action) {
      state.status = status;
      if (action) state.lastAction = action;
      state.narrativeState = currentNarrativeState();
      emit();
    }

    function stopHandle(handle) {
      if (!handle || !handle.node) return;
      safeCall(function () { handle.node.pause(); });
      safeCall(function () { handle.node.currentTime = 0; });
      if (handle.removeEnded && handle.node.removeEventListener) {
        safeCall(function () { handle.node.removeEventListener("ended", handle.removeEnded); });
      }
    }

    function stopSlot(slot) {
      stopHandle(state.active[slot]);
      state.active[slot] = null;
    }

    function stopAllMedia() { Object.keys(state.active).forEach(stopSlot); }

    function makeAudio(asset, slot, loop) {
      if (!asset || !asset.path) return null;
      var node;
      try {
        node = audioFactory(asset.path, { asset: asset, slot: slot, loop: !!loop });
      } catch (_error) {
        state.status = "AUDIO_UNAVAILABLE";
        return null;
      }
      if (!node) return null;
      safeCall(function () { node.src = asset.path; });
      safeCall(function () { node.preload = "auto"; });
      safeCall(function () { node.loop = !!loop; });
      safeCall(function () {
        var volumeBySlot = { bgm: 0.18, ambience: 0.28, voice: 1, shui: 0.82, sfx: 0.78, transition: 0.9 };
        if (typeof volumeBySlot[slot] === "number") node.volume = volumeBySlot[slot];
      });
      return { node: node, asset: asset, identity_key: asset.identity_key || asset.asset_id, slot: slot, loop: !!loop };
    }

    function startNode(handle, waitForEnd, token) {
      if (!handle || !handle.node) return Promise.resolve(false);
      var node = handle.node;
      var finished = false;
      var finish = function (ok) {
        if (finished) return;
        finished = true;
        if (handle.removeEnded && node.removeEventListener) safeCall(function () { node.removeEventListener("ended", handle.removeEnded); });
        if (state.active[handle.slot] === handle && !handle.loop) state.active[handle.slot] = null;
        return ok;
      };
      if (waitForEnd && node.addEventListener) {
        handle.removeEnded = function () { finish(true); };
        safeCall(function () { node.addEventListener("ended", handle.removeEnded); });
      }
      var playResult;
      try { playResult = node.play(); } catch (error) { playResult = Promise.reject(error); }
      return Promise.resolve(playResult).then(function () {
        if (!waitForEnd) { finish(true); return true; }
        if (!node.addEventListener) { finish(true); return true; }
        return new Promise(function (resolve) {
          var poll = function () {
            if (finished || token !== state.token || state.paused) { finish(false); resolve(false); return; }
            setTimeout(poll, 25);
          };
          setTimeout(poll, 25);
        });
      }).catch(function () {
        finish(false);
        state.fallbackCount += 1;
        state.status = "AUDIO_FAILED_CLOSED";
        emit();
        return false;
      });
    }

    function startLoop(asset, slot) {
      if (!asset) return Promise.resolve(false);
      var identity = asset.identity_key || asset.asset_id;
      if (state.active[slot] && state.active[slot].identity_key === identity) return Promise.resolve(true);
      stopSlot(slot);
      var handle = makeAudio(asset, slot, true);
      if (!handle) return Promise.resolve(false);
      state.active[slot] = handle;
      return startNode(handle, false, state.token).then(function (ok) {
        if (!ok && state.active[slot] === handle) state.active[slot] = null;
        return ok;
      });
    }

    function startOneShot(asset, slot, token) {
      if (!asset) return Promise.resolve(false);
      stopSlot(slot);
      var handle = makeAudio(asset, slot, false);
      if (!handle) return Promise.resolve(false);
      state.active[slot] = handle;
      return startNode(handle, true, token).then(function (ok) {
        if (!ok && state.active[slot] === handle) state.active[slot] = null;
        return ok;
      });
    }

    function syncBeds(beat) {
      var tasks = [];
      ["bgm", "ambience"].forEach(function (slot) {
        var asset = beat && beat.audio ? beat.audio[slot] : null;
        if (!asset) stopSlot(slot); else tasks.push(startLoop(asset, slot));
      });
      return Promise.all(tasks);
    }

    function render() {
      var beat = currentBeat();
      if (!documentRef || !beat) return;
      var image = documentRef.getElementById("zone4-visual");
      if (image) { image.src = beat.visual.path; image.alt = beat.visual.asset_id + " — " + beat.section; }
      var section = documentRef.getElementById("zone4-section");
      if (section) section.textContent = beat.section + " · " + beat.state_machine_state;
      var beatLabel = documentRef.getElementById("zone4-beat-label");
      if (beatLabel) beatLabel.textContent = isLordTrack() ? "Lord state · " + state.lordState : state.beatId + " · " + (currentIndex() + 1) + "/" + trackBeatIds(state.trackId).length;
      var trackLabel = documentRef.getElementById("zone4-track-label");
      if (trackLabel) trackLabel.textContent = (tracks[state.trackId] && tracks[state.trackId].label) || state.trackId;
      var localeLabel = documentRef.getElementById("zone4-locale-label");
      if (localeLabel) localeLabel.textContent = state.locale;
      var narrative = documentRef.getElementById("zone4-narrative-state");
      if (narrative) narrative.textContent = state.narrativeState + (state.lordPass ? " · LORD PASS RECORDED" : "");
      var subtitles = documentRef.getElementById("zone4-subtitles");
      if (subtitles) {
        subtitles.innerHTML = "";
        (beat.dialogue || []).forEach(function (line) {
          var row = documentRef.createElement("div");
          row.className = "zone4-dialogue-row";
          row.dataset.lineId = line.line_id;
          row.dataset.locale = state.locale;
          var speaker = documentRef.createElement("span"); speaker.className = "zone4-speaker"; speaker.textContent = line.speaker || "";
          var text = documentRef.createElement("span"); text.className = "zone4-line-text"; text.textContent = line.text[state.locale];
          row.appendChild(speaker); row.appendChild(text); subtitles.appendChild(row);
        });
      }
      var cues = documentRef.getElementById("zone4-cues");
      if (cues) {
        cues.innerHTML = "";
        getEventCuesForCurrentBeat().forEach(function (binding) {
          var button = documentRef.createElement("button");
          button.type = "button"; button.className = "zone4-cue-button"; button.dataset.cueId = binding.identity_key;
          button.textContent = "Play cue · " + binding.identity_key;
          button.addEventListener("click", function () { playEventCue(binding.identity_key); });
          cues.appendChild(button);
        });
      }
      var status = documentRef.getElementById("zone4-status"); if (status) status.textContent = state.status + " · " + state.lastAction;
      var auto = documentRef.getElementById("zone4-autoplay"); if (auto) auto.checked = state.autoPlay;
      var selector = documentRef.getElementById("zone4-beat-selector");
      if (selector) {
        selector.innerHTML = "";
        if (isLordTrack()) {
          lordStateIds.forEach(function (stateKey) {
            var record = lordRecord(stateKey); var option = documentRef.createElement("option");
            option.value = stateKey; option.textContent = stateKey + " · " + record.visual_id; option.selected = stateKey === state.lordState;
            selector.appendChild(option);
          });
        } else {
          trackBeatIds(state.trackId).forEach(function (id, index) {
            var option = documentRef.createElement("option"); option.value = id; option.textContent = (index + 1) + ". " + id; option.selected = id === state.beatId;
            selector.appendChild(option);
          });
        }
      }
      var enterButton = documentRef.getElementById("zone4-enter-lord"); if (enterButton) enterButton.disabled = !(state.beatId === "Z4_S2_08" && !isLordTrack());
      var failButton = documentRef.getElementById("zone4-simulate-fail"); if (failButton) failButton.disabled = !(isLordTrack() && state.lordState === "challenge_active");
      var passButton = documentRef.getElementById("zone4-simulate-pass"); if (passButton) passButton.disabled = !(isLordTrack() && state.lordState === "challenge_active");
      emit();
    }

    function playDialogue(token, beat) {
      var chain = Promise.resolve(true);
      (beat.dialogue || []).forEach(function (line) {
        chain = chain.then(function (ok) {
          if (!ok || token !== state.token || state.paused) return false;
          var voice = line.voice_by_locale && line.voice_by_locale[state.locale];
          if (!voice || voice.locale !== state.locale) { state.fallbackCount += 1; state.status = "VOICE_FAIL_CLOSED_SUBTITLE_ONLY"; emit(); return true; }
          return startOneShot(voice, "voice", token).then(function (played) {
            if (!played) { state.status = "VOICE_FAIL_CLOSED_SUBTITLE_ONLY"; emit(); }
            return true;
          });
        });
      });
      return chain;
    }

    function activateCurrent(options) {
      options = options || {};
      var beat = currentBeat(); if (!beat) return Promise.resolve(false);
      var token = ++state.token; var shouldPlay = options.play === true;
      state.paused = !shouldPlay; state.lastAction = options.action || "show_state"; state.narrativeState = currentNarrativeState();
      stopSlot("voice"); stopSlot("shui"); stopSlot("sfx"); stopSlot("transition");
      if (options.restartMedia) { stopSlot("bgm"); stopSlot("ambience"); }
      render();
      if (!shouldPlay) { emit(); return Promise.resolve(true); }
      return syncBeds(beat).then(function () {
        if (token !== state.token || state.paused) return false;
        var tasks = [];
        if (beat.audio && beat.audio.shui) tasks.push(startOneShot(beat.audio.shui, "shui", token));
        if (beat.audio && beat.audio.transition) tasks.push(startOneShot(beat.audio.transition, "transition", token));
        return Promise.all(tasks).then(function () { return playDialogue(token, beat); });
      }).then(function (ok) {
        if (token !== state.token || state.paused || !ok) return ok;
        state.status = "PLAYING"; emit();
        if (state.autoPlay && state.trackId === "main_story") {
          if (stateMachineEnabled && state.beatId === "Z4_S2_08") return enterLordTrial({ play: true, action: "autoplay_enter_lord_trial" });
          var ids = trackBeatIds(state.trackId); var index = ids.indexOf(state.beatId);
          if (index >= 0 && index < ids.length - 1) {
            var nextId = ids[index + 1];
            if (stateMachineEnabled && isS3Beat(nextId) && !state.lordPass) return enterLordTrial({ play: true, action: "autoplay_lord_gate" });
            state.beatId = nextId; return activateCurrent({ play: true, action: "autoplay_next" });
          }
        }
        return true;
      });
    }

    function showMainBeat(beatId, options) {
      options = options || {};
      if (stateMachineEnabled && isS3Beat(beatId) && !state.lordPass) { setStatus("SCENE_LOCKED_LORD_PASS_REQUIRED", "s3_jump_rejected"); return Promise.resolve(false); }
      var targetTrack = options.trackId || "main_story";
      if (trackBeatIds(targetTrack).indexOf(beatId) === -1) return Promise.resolve(false);
      state.trackId = targetTrack; state.beatId = beatId; state.lordState = null;
      if (options.disableAutoPlay) state.autoPlay = false;
      return activateCurrent({ play: options.play === true, restartMedia: options.restartMedia === true, action: options.action || "show_main_beat" });
    }

    function transitionLordState(stateKey, options) {
      options = options || {}; var record = lordRecord(stateKey); if (!record) return Promise.resolve(false);
      state.trackId = "lord_trial"; state.lordState = stateKey; state.beatId = record.beat_id; state.autoPlay = false;
      return activateCurrent({ play: options.play === true, restartMedia: options.restartMedia === true, action: options.action || "lord_state_transition" });
    }

    function enterLordTrial(options) {
      options = options || {};
      if (!stateMachineEnabled) { setStatus("LORD_STATE_BINDING_UNAVAILABLE", "lord_entry_rejected"); return Promise.resolve(false); }
      if (state.lordPass && !options.forceReview) { setStatus("LORD_ALREADY_PASSED", "lord_entry_rejected"); return Promise.resolve(false); }
      return transitionLordState("challenge_entry", { play: options.play === true, restartMedia: options.restartMedia === true, action: options.action || "enter_lord_trial" });
    }

    function simulateFail() {
      if (!isLordTrack() || state.lordState !== "challenge_active") { setStatus("LORD_RESULT_REQUIRES_ACTIVE_STATE", "simulate_fail_rejected"); return Promise.resolve(false); }
      state.lordPass = false; state.lordFailCount += 1;
      return transitionLordState("failure_retraining", { play: !state.paused, action: "simulate_fail" });
    }

    function simulatePass() {
      if (!isLordTrack() || state.lordState !== "challenge_active") { setStatus("LORD_RESULT_REQUIRES_ACTIVE_STATE", "simulate_pass_rejected"); return Promise.resolve(false); }
      state.lordPass = true;
      return transitionLordState("success_background", { play: !state.paused, action: "simulate_pass" });
    }

    function start() { return activateCurrent({ play: true, restartMedia: true, action: "start" }); }

    function pause() {
      state.paused = true; state.token += 1;
      Object.keys(state.active).forEach(function (slot) { var handle = state.active[slot]; if (handle && handle.node) safeCall(function () { handle.node.pause(); }); });
      setStatus("PAUSED", "pause"); return true;
    }

    function next() {
      if (isLordTrack()) {
        var record = lordRecord(state.lordState); if (!record) return Promise.resolve(false);
        if (state.lordState === "challenge_active") { setStatus("WAITING_FOR_LORD_RESULT", "next_waiting_for_simulation"); return Promise.resolve(false); }
        if (state.lordState === "failure_retraining") return showMainBeat("Z4_S2_08", { trackId: "main_story", play: !state.paused, disableAutoPlay: true, action: "return_to_practice" });
        if (state.lordState === "success_portrait") return showMainBeat("Z4_S3_01", { trackId: "main_story", play: !state.paused, disableAutoPlay: true, action: "lord_pass_to_s3" });
        if (record.next_state && lordRecord(record.next_state)) return transitionLordState(record.next_state, { play: !state.paused, action: "next_lord_state" });
        return Promise.resolve(false);
      }
      var ids = trackBeatIds(state.trackId); var index = ids.indexOf(state.beatId);
      if (stateMachineEnabled && state.beatId === "Z4_S2_08") {
        if (state.lordPass) return showMainBeat("Z4_S3_01", { trackId: "main_story", play: !state.paused, action: "passed_gate_to_s3" });
        return enterLordTrial({ play: !state.paused, action: "s2_08_enter_lord_trial" });
      }
      if (index < 0 || index >= ids.length - 1) { setStatus("END_OF_CONTEXT", "next_at_end"); return Promise.resolve(false); }
      var nextId = ids[index + 1];
      if (stateMachineEnabled && isS3Beat(nextId) && !state.lordPass) return enterLordTrial({ play: !state.paused, action: "s3_gate_enter_lord_trial" });
      state.beatId = nextId; return activateCurrent({ play: !state.paused, action: "next" });
    }

    function previous() {
      if (isLordTrack()) {
        var record = lordRecord(state.lordState); if (!record) return Promise.resolve(false);
        if (state.lordState === "challenge_entry") return showMainBeat("Z4_S2_08", { trackId: "main_story", play: !state.paused, disableAutoPlay: true, action: "previous_to_practice_gate" });
        if (record.previous_state && lordRecord(record.previous_state)) return transitionLordState(record.previous_state, { play: !state.paused, action: "previous_lord_state" });
        return Promise.resolve(false);
      }
      var ids = trackBeatIds(state.trackId); var index = ids.indexOf(state.beatId);
      if (index <= 0) {
        if (state.beatId === "Z4_S3_01") return showMainBeat("Z4_S2_08", { trackId: "main_story", play: !state.paused, action: "previous_to_lord_gate" });
        setStatus("START_OF_CONTEXT", "previous_at_start"); return Promise.resolve(false);
      }
      state.beatId = ids[index - 1]; return activateCurrent({ play: !state.paused, action: "previous" });
    }

    function replayCurrent() {
      state.replaySignature = state.lordState
        ? state.lordState + "|" + state.locale + "|" + (state.lordPass ? "PASS" : "NO_PASS")
        : (state.beatId || "") + "|" + state.locale;
      return activateCurrent({ play: !state.paused, action: "replay_current" });
    }

    function setAutoPlay(enabled) {
      state.autoPlay = !!enabled && state.trackId === "main_story" && tracks.main_story && tracks.main_story.autoplay_allowed === true;
      setStatus(state.autoPlay ? "READY" : "AUTO_PLAY_DISABLED_IN_STATE_CONTEXT", "set_autoplay"); return state.autoPlay;
    }

    function setLocale(locale) {
      if (SUPPORTED_LOCALES.indexOf(locale) === -1) { setStatus("LOCALE_REJECTED_FAIL_CLOSED", "set_locale_rejected"); return false; }
      if (locale === state.locale) return true;
      state.locale = locale; state.token += 1; stopSlot("voice"); state.lastAction = "set_locale"; render();
      if (!state.paused) {
        var token = state.token;
        return playDialogue(token, currentBeat()).then(function () { state.status = "PLAYING"; emit(); return true; });
      }
      return true;
    }

    function setTrack(trackId) {
      if (!tracks[trackId]) return false;
      var wasPlaying = !state.paused;
      if (trackId === "lord_trial") return enterLordTrial({ play: wasPlaying, restartMedia: true, action: "set_lord_trial_context", forceReview: true });
      if (trackId === "lord_review" && !stateMachineEnabled) {
        var legacyIds = trackBeatIds(trackId); if (!legacyIds.length) return false;
        state.trackId = trackId; state.lordState = null; state.autoPlay = false;
        return showMainBeat(legacyIds[0], { trackId: trackId, play: wasPlaying, restartMedia: true, action: "set_legacy_lord_review_context" });
      }
      if (tracks[trackId].requires_lord_pass && !state.lordPass) { setStatus("SCENE_LOCKED_LORD_PASS_REQUIRED", "scene_jump_rejected"); return false; }
      var ids = trackBeatIds(trackId); if (!ids.length) return false;
      state.autoPlay = trackId === "main_story" && state.autoPlay;
      return showMainBeat(ids[0], { trackId: trackId, play: wasPlaying, restartMedia: true, action: "set_scene_context" });
    }

    function jumpToBeat(target) {
      if (isLordTrack()) {
        var targetState = lordStates[target] ? target : lordStateIds.filter(function (key) { return lordRecord(key).beat_id === target; })[0];
        if (!targetState) return false;
        if (targetState === "failure_retraining" || targetState === "success_background" || targetState === "success_portrait") { setStatus("STATE_JUMP_REQUIRES_SIMULATION_CONTROL", "state_jump_rejected"); return false; }
        return transitionLordState(targetState, { play: !state.paused, action: "jump_to_lord_state" });
      }
      var ids = trackBeatIds(state.trackId); if (ids.indexOf(target) === -1) return false;
      if (isS3Beat(target) && !state.lordPass) { setStatus("SCENE_LOCKED_LORD_PASS_REQUIRED", "s3_jump_rejected"); return false; }
      return showMainBeat(target, { trackId: state.trackId, play: !state.paused, action: "jump_to_scene_or_beat" });
    }

    function getEventCuesForCurrentBeat() {
      var beat = currentBeat(); if (!beat) return [];
      return (Array.isArray(matrix.event_audio_bindings) ? matrix.event_audio_bindings : []).filter(function (binding) {
        var scope = binding.scene_scope || []; return scope.indexOf(beat.scene_id) !== -1 || scope.indexOf(beat.beat_id) !== -1;
      }).map(clone);
    }

    function playEventCue(identityKey) {
      var binding = (matrix.event_audio_bindings || []).filter(function (candidate) { return candidate.identity_key === identityKey; })[0];
      var beat = currentBeat(); if (!binding || !beat) return Promise.resolve(false);
      var scope = binding.scene_scope || [];
      if (scope.indexOf(beat.scene_id) === -1 && scope.indexOf(beat.beat_id) === -1) { setStatus("CUE_SCOPE_REJECTED", "cue_scope_rejected"); return Promise.resolve(false); }
      var token = ++state.token; var category = binding.asset.category;
      var slot = category === "transition" ? "transition" : (category === "bgm" ? "bgm" : (category === "ambience" ? "ambience" : (category === "shui_vocal" ? "shui" : "sfx")));
      stopSlot(slot); state.paused = false; state.status = "PLAYING"; state.lastAction = "play_event_cue"; emit();
      if (slot === "bgm" || slot === "ambience") return startLoop(binding.asset, slot, token);
      return startOneShot(binding.asset, slot, token);
    }

    render();

    return {
      getSnapshot: snapshot,
      getCurrentBeat: currentBeat,
      getEventCuesForCurrentBeat: getEventCuesForCurrentBeat,
      getLordStateRecord: lordRecord,
      start: start,
      pause: pause,
      next: next,
      previous: previous,
      replayCurrent: replayCurrent,
      setAutoPlay: setAutoPlay,
      setLocale: setLocale,
      setTrack: setTrack,
      jumpToBeat: jumpToBeat,
      enterLordTrial: enterLordTrial,
      simulateFail: simulateFail,
      simulatePass: simulatePass,
      playEventCue: playEventCue,
      stopAllMedia: function () { stopAllMedia(); emit(); },
      render: render,
      supportedLocales: SUPPORTED_LOCALES.slice()
    };
  }

  return { create: create, supportedLocales: SUPPORTED_LOCALES.slice() };
}));
