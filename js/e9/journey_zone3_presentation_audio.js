(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory(typeof globalThis !== 'undefined' ? globalThis : null);
    } else {
        root.GoOdysseyZone3PresentationAudio = factory(root);
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (globalRoot) {
    'use strict';

    /*
     * Zone 3 presentation-only audio bridge.
     *
     * The committed presentation manifest is the only source of cue paths.
     * This module owns short-lived HTMLMediaElement resources and phase/shot
     * routing. It has no gameplay, progression, reward, or locale authority.
     */
    const VERSION = 'w1-zone3-presentation-audio-010';
    const ZONE = 3;
    const MANIFEST_PATH = '/assets/e10/audio/zone3/zone3-presentation-audio-manifest.json';
    const PHASE_BGM = Object.freeze({
        FIRST_ENTRY: 'Z3_BGM_DISCOVERY',
        BOSS_READY: 'Z3_BGM_ESCALATION',
        POST_CLEAR: 'Z3_BGM_RECOVERY',
    });
    const SHOT_AUDIO = Object.freeze({
        SHOT01: Object.freeze({
            ambience: Object.freeze(['Z3_CAVE_ROOM_TONE']),
            events: Object.freeze(['Z3_REFUGEE_FOOTSTEPS', 'Z3_BELONGINGS_MOVEMENT']),
        }),
        SHOT02: Object.freeze({
            ambience: Object.freeze(['Z3_FAMILY_ACTIVITY']),
            events: Object.freeze([]),
        }),
        SHOT03: Object.freeze({
            ambience: Object.freeze(['Z3_FAMILY_ACTIVITY']),
            events: Object.freeze([]),
        }),
        SHOT04: Object.freeze({
            ambience: Object.freeze(['Z3_FAMILY_ACTIVITY']),
            events: Object.freeze([]),
        }),
        SHOT05: Object.freeze({
            ambience: Object.freeze(['Z3_DISTANT_CAVE_WIND']),
            events: Object.freeze(['Z3_WATER_DRIP', 'Z3_ROCKFALL', 'Z3_BLOCKED_WATER_FLOW']),
        }),
        SHOT06: Object.freeze({
            ambience: Object.freeze(['Z3_TRIAL_TENSION']),
            events: Object.freeze(['Z3_CENTURION_ARMOR']),
        }),
        SHOT07: Object.freeze({
            ambience: Object.freeze(['Z3_TRIAL_TENSION']),
            events: Object.freeze(['Z3_CENTURION_SPEAR_PLANT']),
        }),
        SHOT08: Object.freeze({
            ambience: Object.freeze(['Z3_FRAGILE_TRUCE']),
            events: Object.freeze([]),
        }),
        SHOT09: Object.freeze({
            ambience: Object.freeze(['Z3_FRAGILE_TRUCE']),
            events: Object.freeze(['Z3_SHUI_REACTION', 'Z3_STONE_PHYSICAL_HANDOFF']),
        }),
        SHOT10: Object.freeze({
            ambience: Object.freeze(['Z3_FRAGILE_TRUCE']),
            events: Object.freeze(['Z3_MISTY_FOREST_WIND_TRANSITION']),
        }),
    });
    const CATEGORY_COUNTS = Object.freeze({
        ambience: 5,
        event_sfx: 7,
        transition: 1,
        reusable_sfx: 2,
        bgm: 3,
        total: 18,
    });

    function asString(value) {
        return typeof value === 'string' ? value : '';
    }

    function runtimeUrl(path) {
        const value = asString(path);
        if (!value) return '';
        return value.charAt(0) === '/' ? value : `/${value}`;
    }

    function validateManifest(value) {
        const source = value && typeof value === 'object' ? value : {};
        const entries = Array.isArray(source.entries)
            ? source.entries
            : (Array.isArray(source.CUES) ? source.CUES : []);
        const ids = new Set();
        const errors = [];
        if (Number(source.ZONE) !== ZONE) errors.push('zone');
        entries.forEach((entry, index) => {
            const id = asString(entry?.CUE_ID);
            if (!id) errors.push(`missing_cue_id_${index}`);
            if (ids.has(id)) errors.push(`duplicate_cue_id_${id}`);
            ids.add(id);
            if (!asString(entry?.OUTPUT_PATH) && !asString(entry?.SOURCE_ASSET_OR_PIPELINE)) {
                errors.push(`missing_path_${id || index}`);
            }
        });
        const counts = entries.reduce((out, entry) => {
            const category = asString(entry?.CATEGORY);
            out[category] = (out[category] || 0) + 1;
            return out;
        }, {});
        Object.keys(CATEGORY_COUNTS).forEach((key) => {
            if (key !== 'total' && Number(counts[key] || 0) !== CATEGORY_COUNTS[key]) {
                errors.push(`category_count_${key}`);
            }
        });
        if (entries.length !== CATEGORY_COUNTS.total) errors.push('total_count');
        return {
            ok: errors.length === 0,
            errors,
            manifest: source,
            entries,
            counts,
        };
    }

    function create(options) {
        const config = options && typeof options === 'object' ? options : {};
        const windowImpl = config.window || globalRoot || null;
        const documentImpl = config.document || windowImpl?.document || null;
        const fetchImpl = config.fetch || windowImpl?.fetch || null;
        const audioFactory = config.audioFactory || null;
        const active = new Map();
        let manifest = null;
        let cueById = new Map();
        let loadPromise = null;
        let currentPhase = null;
        let currentShot = null;
        let commandSerial = 0;
        let destroyed = false;
        let mutedOverride = null;
        let muteListenerAttached = false;

        function isMuted() {
            if (mutedOverride !== null) return mutedOverride;
            if (typeof config.isMuted === 'function') {
                try { return Boolean(config.isMuted()); } catch (error) {}
            }
            try { return Boolean(windowImpl?.SFX?.muted); } catch (error) { return false; }
        }

        function applyMute() {
            const muted = isMuted();
            active.forEach((record) => {
                try { record.audio.muted = muted; } catch (error) {}
            });
            return muted;
        }

        function buildAudioElement() {
            try {
                if (typeof audioFactory === 'function') return audioFactory();
                if (documentImpl?.createElement) return documentImpl.createElement('audio');
                if (typeof windowImpl?.Audio === 'function') return new windowImpl.Audio();
            } catch (error) {}
            return null;
        }

        function stopRecord(record) {
            if (!record || !active.has(record.key)) return false;
            active.delete(record.key);
            const audio = record.audio;
            try {
                audio.onended = null;
                audio.onerror = null;
                audio.pause?.();
                audio.currentTime = 0;
                audio.removeAttribute?.('src');
                audio.load?.();
            } catch (error) {}
            return true;
        }

        function stopRole(role) {
            Array.from(active.values())
                .filter((record) => record.role === role)
                .forEach(stopRecord);
        }

        function playCue(cueId, optionsForCue) {
            const cue = cueById.get(cueId);
            if (!cue || destroyed) return { ok: false, reason: 'presentation_audio_unavailable', cueId };
            const request = optionsForCue && typeof optionsForCue === 'object' ? optionsForCue : {};
            const category = asString(cue.CATEGORY);
            const role = request.role || (
                category === 'bgm' ? 'bgm' :
                    category === 'ambience' ? 'ambience' : 'transient'
            );
            if (role === 'bgm') stopRole('bgm');
            if (role === 'ambience') stopRole('ambience');
            const key = role + ':' + cueId;
            stopRecord(active.get(key));
            const audio = buildAudioElement();
            if (!audio) return { ok: false, reason: 'audio_element_unavailable', cueId };
            const record = { key, cueId, role, category, audio };
            active.set(key, record);
            try {
                audio.preload = 'auto';
                audio.playsInline = true;
                audio.src = runtimeUrl(cue.OUTPUT_PATH || cue.SOURCE_ASSET_OR_PIPELINE);
                audio.loop = Boolean(cue.LOOPABLE);
                audio.muted = isMuted();
                audio.volume = Number.isFinite(Number(request.volume))
                    ? Number(request.volume)
                    : (role === 'bgm' ? 0.35 : role === 'ambience' ? 0.22 : 0.8);
                audio.onended = audio.loop ? null : () => stopRecord(record);
                audio.onerror = () => stopRecord(record);
                const playResult = audio.play?.();
                Promise.resolve(playResult).catch(() => stopRecord(record));
                return { ok: true, cueId, role, muted: Boolean(audio.muted), path: audio.src };
            } catch (error) {
                stopRecord(record);
                return { ok: false, reason: 'presentation_audio_failure', cueId };
            }
        }

        function setManifest(nextManifest) {
            const checked = validateManifest(nextManifest);
            if (!checked.ok) {
                throw new Error('Zone 3 presentation audio manifest invalid: ' + checked.errors.join(','));
            }
            manifest = checked.manifest;
            cueById = new Map(checked.entries.map((entry) => [entry.CUE_ID, entry]));
            return {
                ok: true,
                cueCount: checked.entries.length,
                categoryCounts: checked.counts,
            };
        }

        function load() {
            if (manifest) return Promise.resolve({ ok: true, manifest });
            if (loadPromise) return loadPromise;
            if (config.manifest) {
                try {
                    setManifest(config.manifest);
                    return Promise.resolve({ ok: true, manifest });
                } catch (error) {
                    return Promise.reject(error);
                }
            }
            if (typeof fetchImpl !== 'function') {
                return Promise.reject(new Error('Zone 3 presentation audio fetch unavailable'));
            }
            loadPromise = Promise.resolve(fetchImpl(config.manifestUrl || MANIFEST_PATH))
                .then((response) => {
                    if (response && response.ok === false) throw new Error(`audio_manifest_http_${response.status}`);
                    return response?.json ? response.json() : response;
                })
                .then((value) => {
                    setManifest(value);
                    return { ok: true, manifest };
                })
                .catch((error) => {
                    loadPromise = null;
                    throw error;
                });
            return loadPromise;
        }

        function beginPhase(phase) {
            const normalized = asString(phase).toUpperCase();
            const cueId = PHASE_BGM[normalized];
            if (!cueId) return { ok: false, reason: 'unknown_phase', phase: normalized };
            if (currentPhase === normalized && Array.from(active.values()).some((record) => record.role === 'bgm')) {
                return { ok: true, phase: normalized, cueId, reused: true };
            }
            stopRole('bgm');
            stopRole('ambience');
            currentPhase = normalized;
            const result = playCue(cueId, { role: 'bgm', volume: 0.35 });
            return { ...result, phase: normalized };
        }

        function enterShot(shotId, optionsForShot) {
            const request = optionsForShot && typeof optionsForShot === 'object' ? optionsForShot : {};
            const id = asString(shotId).toUpperCase();
            const token = commandSerial;
            return load().then(() => {
                if (destroyed || token !== commandSerial) return { ok: false, reason: 'stale_presentation_request' };
                const binding = SHOT_AUDIO[id];
                if (!binding) return { ok: false, reason: 'unknown_shot', shotId: id };
                const phase = asString(request.phase).toUpperCase() || (
                    Number(id.slice(-2)) <= 5 ? 'FIRST_ENTRY' : Number(id.slice(-2)) <= 7 ? 'BOSS_READY' : 'POST_CLEAR'
                );
                const phaseResult = beginPhase(phase);
                stopRole('ambience');
                const ambienceResult = binding.ambience[0]
                    ? playCue(binding.ambience[0], { role: 'ambience', volume: 0.22 })
                    : { ok: true };
                const eventResults = binding.events.map((cueId) => playCue(cueId, { role: 'transient', volume: 0.8 }));
                currentShot = id;
                applyMute();
                return {
                    ok: phaseResult.ok !== false && ambienceResult.ok !== false && eventResults.every((result) => result.ok !== false),
                    shotId: id,
                    phase,
                    phaseResult,
                    ambienceResult,
                    eventResults,
                };
            }).catch((error) => ({ ok: false, reason: 'presentation_audio_failure', error: String(error), shotId: id }));
        }

        function stopAll(optionsForStop) {
            const request = optionsForStop && typeof optionsForStop === 'object' ? optionsForStop : {};
            if (request.invalidate !== false) commandSerial += 1;
            Array.from(active.values()).forEach(stopRecord);
            currentPhase = null;
            currentShot = null;
            return { ok: true };
        }

        function reset() {
            return stopAll();
        }

        function syncMute() {
            return { ok: true, muted: applyMute() };
        }

        function setMuted(value) {
            mutedOverride = Boolean(value);
            return syncMute();
        }

        function getResourceStats() {
            let bgm = 0;
            let ambience = 0;
            let transient = 0;
            active.forEach((record) => {
                if (record.role === 'bgm') bgm += 1;
                else if (record.role === 'ambience') ambience += 1;
                else transient += 1;
            });
            return {
                activeAudioCount: active.size,
                activeBgmCount: bgm,
                activeAmbienceCount: ambience,
                activeTransientCount: transient,
                timerCount: 0,
                animationFrameCount: 0,
                listenerCount: muteListenerAttached ? 1 : 0,
                currentPhase,
                currentShot,
                muted: isMuted(),
            };
        }

        function getActiveAudioState() {
            return Array.from(active.values()).map((record) => ({
                key: record.key,
                cueId: record.cueId,
                role: record.role,
                muted: Boolean(record.audio.muted),
                src: asString(record.audio.src),
            }));
        }

        function getContract() {
            return {
                version: VERSION,
                zone: ZONE,
                manifestPath: config.manifestUrl || MANIFEST_PATH,
                categoryCounts: CATEGORY_COUNTS,
                phaseBgm: PHASE_BGM,
                shotAudio: SHOT_AUDIO,
                maxSimultaneousBgmStreams: 1,
                replaySharedSource: true,
                routeExitStopsAudio: true,
                globalMute: true,
                newVolumeControlUi: false,
                presentationOnly: true,
            };
        }

        function onMuteChanged() { syncMute(); }
        if (documentImpl?.addEventListener) {
            try {
                documentImpl.addEventListener('go-odyssey-audio-mute-changed', onMuteChanged);
                muteListenerAttached = true;
            } catch (error) {}
        }

        function destroy() {
            if (destroyed) return { ok: true };
            destroyed = true;
            stopAll({ invalidate: true });
            if (muteListenerAttached) {
                try { documentImpl.removeEventListener('go-odyssey-audio-mute-changed', onMuteChanged); } catch (error) {}
                muteListenerAttached = false;
            }
            return { ok: true };
        }

        if (config.manifest) {
            try { setManifest(config.manifest); } catch (error) { loadPromise = Promise.reject(error); }
        }

        return Object.freeze({
            VERSION,
            MANIFEST_PATH,
            CATEGORY_COUNTS,
            SHOT_AUDIO,
            load,
            whenReady: load,
            setManifest,
            beginPhase,
            enterShot,
            playCue,
            syncMute,
            setMuted,
            stopAll,
            reset,
            getResourceStats,
            getActiveAudioState,
            getContract,
            getManifest: () => manifest,
            destroy,
        });
    }

    return Object.freeze({
        VERSION,
        MANIFEST_PATH,
        CATEGORY_COUNTS,
        PHASE_BGM,
        SHOT_AUDIO,
        validateManifest,
        create,
    });
}));
