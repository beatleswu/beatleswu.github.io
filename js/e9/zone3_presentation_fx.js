(function (root, factory) {
    'use strict';
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.GoOdysseyZone3PresentationFX = factory();
    }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    /*
     * Standalone Zone 3 presentation package.
     *
     * The module owns only short-lived visual resources attached to a caller-
     * supplied stage.  It has no application-data dependency and never
     * decides a game result.  A failed effect is deliberately disposable so
     * the surrounding presentation can continue without it.
     */

    const VERSION = 'w1-zone3-presentation-fx-009';
    const ZONE_KEY = 'k16_20';
    const ZONE_NAME_ZH = '哥布林洞穴';
    const ZONE_NAME_EN = 'Goblin Cave';
    const PARALLAX_IMPLEMENTED = false;
    const PARALLAX_RECOMMENDED_CLASSIFICATION =
        'INTENTIONALLY_DIFFERENT_NOT_REQUIRED_FOR_ZONE3_V1';

    const LIMITS = Object.freeze({
        PARTICLE_COUNT: 18,
        EFFECT_ANIMATION_DURATION_MS: 2800,
        CAMERA_ANIMATION_DURATION_MS: 8000,
        SIMULTANEOUS_EFFECT_COUNT: 12,
    });

    const EFFECT_IDS = Object.freeze([
        'Z3_L01',
        'Z3_V01',
        'Z3_V02',
        'Z3_V03',
        'Z3_V04',
        'Z3_V05',
        'Z3_V06',
        'Z3_V07',
        'Z3_V08',
        'Z3_V09',
        'Z3_V10',
        'Z3_T01_VISUAL',
    ]);

    const SHOT_IDS = Object.freeze([
        'SHOT01', 'SHOT02', 'SHOT03', 'SHOT04', 'SHOT05',
        'SHOT06', 'SHOT07', 'SHOT08', 'SHOT09', 'SHOT10',
    ]);

    const SHOT_EFFECTS = Object.freeze({
        SHOT01: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT02: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT03: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_V03']),
        SHOT04: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT05: Object.freeze([
            'Z3_L01', 'Z3_V01', 'Z3_V02', 'Z3_V03',
            'Z3_V05', 'Z3_V06', 'Z3_V07',
        ]),
        SHOT06: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT07: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_V08', 'Z3_V09']),
        SHOT08: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_V03', 'Z3_V10']),
        SHOT09: Object.freeze(['Z3_L01', 'Z3_V01']),
        SHOT10: Object.freeze(['Z3_L01', 'Z3_V01', 'Z3_T01_VISUAL']),
    });

    const SHOT_OPTIONAL_EFFECTS = Object.freeze({
        SHOT03: Object.freeze(['Z3_V04']),
        SHOT05: Object.freeze(['Z3_V04']),
        SHOT08: Object.freeze(['Z3_V04']),
    });

    const EFFECT_DEFINITIONS = Object.freeze({
        Z3_L01: Object.freeze({
            cueId: 'Z3_L01',
            name: 'SUBTLE_WARM_LIGHT_FLICKER',
            kind: 'light',
            loop: true,
            required: true,
            particleCount: 0,
            durationMs: 0,
        }),
        Z3_V01: Object.freeze({
            cueId: 'Z3_V01',
            name: 'CAVE_DUST_MOTES',
            kind: 'particles',
            loop: true,
            required: true,
            particleCount: 12,
            durationMs: 0,
        }),
        Z3_V02: Object.freeze({
            cueId: 'Z3_V02',
            name: 'WATER_REFLECTION_SHIMMER',
            kind: 'water',
            loop: true,
            required: true,
            particleCount: 0,
            durationMs: 0,
        }),
        Z3_V03: Object.freeze({
            cueId: 'Z3_V03',
            name: 'SHUI_WATER_PARTICLES',
            kind: 'particles',
            loop: true,
            required: true,
            particleCount: 8,
            durationMs: 0,
        }),
        Z3_V04: Object.freeze({
            cueId: 'Z3_V04',
            name: 'SHUI_TRANSLUCENT_PULSE',
            kind: 'pulse',
            loop: false,
            required: false,
            particleCount: 0,
            durationMs: 900,
        }),
        Z3_V05: Object.freeze({
            cueId: 'Z3_V05',
            name: 'ROCK_DUST_FALL',
            kind: 'burst',
            loop: false,
            required: true,
            particleCount: 7,
            durationMs: 1250,
        }),
        Z3_V06: Object.freeze({
            cueId: 'Z3_V06',
            name: 'SMALL_ROCK_DEBRIS',
            kind: 'debris',
            loop: false,
            required: true,
            particleCount: 4,
            durationMs: 900,
        }),
        Z3_V07: Object.freeze({
            cueId: 'Z3_V07',
            name: 'BLOCKED_WATER_MIST',
            kind: 'mist',
            loop: true,
            required: true,
            particleCount: 0,
            durationMs: 0,
        }),
        Z3_V08: Object.freeze({
            cueId: 'Z3_V08',
            name: 'CENTURION_SPEAR_DUST_IMPULSE',
            kind: 'burst',
            loop: false,
            required: true,
            particleCount: 5,
            durationMs: 800,
        }),
        Z3_V09: Object.freeze({
            cueId: 'Z3_V09',
            name: 'TRIAL_SUBTLE_ENVIRONMENT_TENSION',
            kind: 'tension',
            loop: true,
            required: true,
            particleCount: 0,
            durationMs: 0,
        }),
        Z3_V10: Object.freeze({
            cueId: 'Z3_V10',
            name: 'TRUCE_ENVIRONMENT_CALMING',
            kind: 'settle',
            loop: false,
            required: true,
            particleCount: 0,
            durationMs: 1000,
        }),
        Z3_T01_VISUAL: Object.freeze({
            cueId: 'Z3_T01',
            name: 'MISTY_FOREST_FOG_TRANSITION',
            kind: 'transition',
            loop: false,
            required: true,
            particleCount: 0,
            durationMs: 2200,
        }),
    });

    const CAMERA_CUES = Object.freeze({
        SHOT01: Object.freeze({
            mode: 'slow_push', durationMs: 7000,
            scaleFrom: 1, scaleTo: 1.012, x: 50, y: 50,
        }),
        SHOT02: Object.freeze({
            mode: 'slow_drift', durationMs: 6500,
            dxPct: -0.4, dyPct: 0.2, x: 51, y: 50,
        }),
        SHOT03: Object.freeze({
            mode: 'slow_push', durationMs: 7000,
            scaleFrom: 1, scaleTo: 1.008, x: 50, y: 50,
        }),
        SHOT04: Object.freeze({
            mode: 'static_hold', durationMs: 0,
            scaleFrom: 1, scaleTo: 1, x: 50, y: 50,
        }),
        SHOT05: Object.freeze({
            mode: 'bounded_impact_impulse', durationMs: 260,
            amplitudePx: 4, repetitions: 1, x: 50, y: 50,
        }),
        SHOT06: Object.freeze({
            mode: 'slow_push', durationMs: 6500,
            scaleFrom: 1, scaleTo: 1.01, x: 50, y: 50,
        }),
        SHOT07: Object.freeze({
            mode: 'bounded_impact_impulse', durationMs: 220,
            amplitudePx: 3, repetitions: 1, x: 50, y: 50,
        }),
        SHOT08: Object.freeze({
            mode: 'slow_pull', durationMs: 7000,
            scaleFrom: 1.01, scaleTo: 1, x: 50, y: 50,
        }),
        SHOT09: Object.freeze({
            mode: 'static_hold', durationMs: 0,
            scaleFrom: 1, scaleTo: 1, x: 50, y: 50,
        }),
        SHOT10: Object.freeze({
            mode: 'slow_drift', durationMs: 6500,
            dxPct: 0.35, dyPct: -0.1, x: 49, y: 50,
        }),
    });

    const CAMERA_MODES = Object.freeze([
        'slow_push',
        'slow_drift',
        'static_hold',
        'bounded_impact_impulse',
        'slow_pull',
    ]);

    const EFFECT_CLASS_NAMES = Object.freeze(EFFECT_IDS.map((id) =>
        `z3-effect-${slug(id)}`));

    function slug(value) {
        return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-');
    }

    function finiteOr(value, fallback) {
        const number = Number(value);
        return Number.isFinite(number) ? number : fallback;
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function validShot(shotId) {
        return SHOT_IDS.includes(String(shotId || ''));
    }

    function hashSeed(value) {
        let hash = 2166136261;
        for (const character of String(value || '')) {
            hash ^= character.charCodeAt(0);
            hash = Math.imul(hash, 16777619);
        }
        return hash >>> 0;
    }

    function fixedParticlePosition(seed, index) {
        const value = (seed + Math.imul(index + 1, 2654435761)) >>> 0;
        return {
            x: 8 + (value % 84),
            y: 8 + ((value >>> 8) % 80),
            delay: (value % 700) / 1000,
            duration: 1.5 + ((value >>> 16) % 12) / 10,
            size: 2 + ((value >>> 24) % 3),
        };
    }

    // A particle pool is still deterministic and bounded, but priority cues
    // need to land on the story action rather than at arbitrary full-frame
    // coordinates.  These are presentation coordinates only; they do not
    // inspect or alter gameplay state.  The fallbacks preserve the original
    // sparse full-frame depth treatment for every other shot/effect pair.
    function storyParticlePosition(effectId, shotId, index) {
        const bounds = {
            'SHOT05:Z3_V03': { x: [18, 38], y: [36, 82] },
            'SHOT05:Z3_V05': { x: [43, 77], y: [38, 78] },
            'SHOT05:Z3_V06': { x: [48, 79], y: [50, 84] },
            'SHOT07:Z3_V08': { x: [43, 56], y: [68, 88] },
        }[`${shotId || ''}:${effectId}`];
        const position = fixedParticlePosition(
            hashSeed(`${shotId || ''}:${effectId}`),
            index,
        );
        if (!bounds) return position;
        const span = (range) => range[0] + ((position.x / 100) * (range[1] - range[0]));
        const ySpan = (range) => range[0] + ((position.y / 100) * (range[1] - range[0]));
        return {
            ...position,
            x: span(bounds.x),
            y: ySpan(bounds.y),
        };
    }

    function safeLog(logger, error) {
        if (typeof logger !== 'function') return;
        try { logger(error); } catch (ignored) { /* diagnostics only */ }
    }

    function create(options) {
        const config = options && typeof options === 'object' ? options : {};
        const windowImpl = config.window
            || (typeof globalThis !== 'undefined' ? globalThis : null);
        const documentImpl = config.document || windowImpl?.document || null;
        const host = config.root && typeof config.root.appendChild === 'function'
            ? config.root
            : null;
        const logger = config.logger;
        const setTimer = config.setTimeout
            || windowImpl?.setTimeout?.bind(windowImpl)
            || (typeof setTimeout === 'function' ? setTimeout : null);
        const clearTimer = config.clearTimeout
            || windowImpl?.clearTimeout?.bind(windowImpl)
            || (typeof clearTimeout === 'function' ? clearTimeout : null);
        const requestFrame = config.requestAnimationFrame
            || windowImpl?.requestAnimationFrame?.bind(windowImpl)
            || null;
        const cancelFrame = config.cancelAnimationFrame
            || windowImpl?.cancelAnimationFrame?.bind(windowImpl)
            || null;

        const activeEffects = new Map();
        const activeTimers = new Set();
        const activeRafs = new Set();
        const activeListeners = new Set();
        let cameraState = null;
        let destroyed = false;

        function result(ok, extra) {
            return Object.freeze({ ok: Boolean(ok), ...(extra || {}) });
        }

        function prefersReducedMotion(request) {
            if (request && typeof request.reducedMotion === 'boolean') {
                return request.reducedMotion;
            }
            try {
                return Boolean(windowImpl?.matchMedia?.(
                    '(prefers-reduced-motion: reduce)')?.matches);
            } catch (error) {
                safeLog(logger, error);
                return false;
            }
        }

        function setClass(target, className, enabled) {
            if (!target?.classList) return;
            try {
                target.classList.toggle(className, Boolean(enabled));
            } catch (error) {
                safeLog(logger, error);
            }
        }

        function setAttribute(target, name, value) {
            try {
                if (target?.setAttribute) target.setAttribute(name, value);
            } catch (error) {
                safeLog(logger, error);
            }
        }

        function removeNode(node) {
            try {
                if (node?.parentNode) node.parentNode.removeChild(node);
            } catch (error) {
                safeLog(logger, error);
            }
        }

        function cancelTrackedTimer(handle, scope) {
            if (handle === undefined || handle === null) return;
            try { clearTimer?.(handle); } catch (error) { safeLog(logger, error); }
            activeTimers.delete(handle);
            scope?.timers?.delete(handle);
        }

        function cancelTrackedRaf(handle, scope) {
            if (handle === undefined || handle === null) return;
            try { cancelFrame?.(handle); } catch (error) { safeLog(logger, error); }
            activeRafs.delete(handle);
            scope?.rafs?.delete(handle);
        }

        function scheduleTimer(scope, callback, delay) {
            if (typeof setTimer !== 'function') return null;
            let handle = null;
            try {
                handle = setTimer(() => {
                    activeTimers.delete(handle);
                    scope.timers.delete(handle);
                    if (destroyed || !scopeIsCurrent(scope)) return;
                    try { callback(); } catch (error) { safeLog(logger, error); }
                }, Math.max(0, Math.round(delay)));
                scope.timers.add(handle);
                activeTimers.add(handle);
                return handle;
            } catch (error) {
                safeLog(logger, error);
                return null;
            }
        }

        function scheduleRaf(scope, callback) {
            if (typeof requestFrame !== 'function') return null;
            let handle = null;
            try {
                handle = requestFrame((timestamp) => {
                    activeRafs.delete(handle);
                    scope.rafs.delete(handle);
                    if (destroyed || !scopeIsCurrent(scope)) return;
                    try { callback(timestamp); } catch (error) { safeLog(logger, error); }
                });
                scope.rafs.add(handle);
                activeRafs.add(handle);
                return handle;
            } catch (error) {
                safeLog(logger, error);
                return null;
            }
        }

        function trackAbort(scope, signal) {
            if (!signal || typeof signal.addEventListener !== 'function') return;
            const listener = () => stop(scope.effectId);
            try {
                signal.addEventListener('abort', listener, { once: true });
                const record = { target: signal, type: 'abort', listener };
                scope.listeners.add(record);
                activeListeners.add(record);
            } catch (error) {
                safeLog(logger, error);
            }
        }

        function removeTrackedListeners(scope) {
            for (const record of scope.listeners) {
                try { record.target.removeEventListener(record.type, record.listener); }
                catch (error) { safeLog(logger, error); }
                activeListeners.delete(record);
            }
            scope.listeners.clear();
        }

        function scopeIsCurrent(scope) {
            if (scope.effectId) return activeEffects.get(scope.effectId) === scope;
            return cameraState === scope;
        }

        function cleanupScope(scope) {
            for (const handle of Array.from(scope.timers)) {
                cancelTrackedTimer(handle, scope);
            }
            for (const handle of Array.from(scope.rafs)) {
                cancelTrackedRaf(handle, scope);
            }
            removeTrackedListeners(scope);
            for (const cleanup of scope.cleanup) {
                try { cleanup(); } catch (error) { safeLog(logger, error); }
            }
            scope.cleanup.length = 0;
            for (const node of scope.nodes) removeNode(node);
            scope.nodes.length = 0;
        }

        function appendParticlePool(layer, definition, effectId, shotId) {
            if (!documentImpl?.createElement) throw new Error('zone3_fx_dom_unavailable');
            const requested = Math.max(0, Math.floor(definition.particleCount || 0));
            const count = Math.min(requested, LIMITS.PARTICLE_COUNT);
            for (let index = 0; index < count; index += 1) {
                const particle = documentImpl.createElement('span');
                const position = storyParticlePosition(effectId, shotId, index);
                particle.className = 'z3-fx-particle';
                setAttribute(particle, 'aria-hidden', 'true');
                particle.style?.setProperty('--z3-particle-x', `${position.x}%`);
                particle.style?.setProperty('--z3-particle-y', `${position.y}%`);
                particle.style?.setProperty('--z3-particle-delay', `${position.delay}s`);
                particle.style?.setProperty('--z3-particle-duration', `${position.duration}s`);
                particle.style?.setProperty('--z3-particle-size', `${position.size}px`);
                layer.appendChild(particle);
            }
        }

        function buildEffectNode(definition, effectId, request, reducedMotion) {
            if (!documentImpl?.createElement) throw new Error('zone3_fx_dom_unavailable');
            const layer = documentImpl.createElement('span');
            layer.className = [
                'z3-fx-layer',
                'z3-fx-effect',
                `z3-fx-${definition.kind}`,
                `z3-effect-${slug(effectId)}`,
            ].join(' ');
            setAttribute(layer, 'aria-hidden', 'true');
            setAttribute(layer, 'data-z3-effect-id', effectId);
            if (validShot(request?.shotId)) {
                setAttribute(layer, 'data-z3-shot-id', String(request.shotId));
            }
            setClass(layer, 'z3-fx-reduced-motion', reducedMotion);
            layer.style?.setProperty('--z3-fx-intensity', String(request?.intensity || 'low'));
            if (definition.kind === 'particles' || definition.kind === 'burst'
                || definition.kind === 'debris') {
                appendParticlePool(layer, definition, effectId, request?.shotId);
            } else {
                const accent = documentImpl.createElement('span');
                accent.className = 'z3-fx-accent';
                setAttribute(accent, 'aria-hidden', 'true');
                layer.appendChild(accent);
            }
            return layer;
        }

        function start(effectId, request) {
            const id = String(effectId || '');
            const definition = EFFECT_DEFINITIONS[id];
            if (destroyed) return result(false, { skipped: true, reason: 'destroyed', effectId: id });
            if (!definition) return result(false, { skipped: true, reason: 'unknown_effect', effectId: id });
            if (!host || !documentImpl) {
                return result(false, { skipped: true, reason: 'host_unavailable', effectId: id });
            }
            if (activeEffects.has(id)) stop(id);
            if (activeEffects.size >= LIMITS.SIMULTANEOUS_EFFECT_COUNT) {
                return result(false, { skipped: true, reason: 'effect_cap', effectId: id });
            }

            const optionsForEffect = request && typeof request === 'object' ? request : {};
            const reducedMotion = prefersReducedMotion(optionsForEffect);
            const scope = {
                effectId: id,
                nodes: [],
                timers: new Set(),
                rafs: new Set(),
                listeners: new Set(),
                cleanup: [],
            };

            try {
                const node = buildEffectNode(definition, id, optionsForEffect, reducedMotion);
                host.appendChild(node);
                scope.nodes.push(node);
                activeEffects.set(id, scope);
                setClass(host, 'z3-reduced-motion', reducedMotion);
                trackAbort(scope, optionsForEffect.signal);
                const requestedDuration = optionsForEffect.durationMs === undefined
                    ? definition.durationMs
                    : optionsForEffect.durationMs;
                const duration = clamp(
                    finiteOr(requestedDuration, definition.durationMs),
                    0,
                    LIMITS.EFFECT_ANIMATION_DURATION_MS,
                );
                if (!definition.loop && duration > 0 && !reducedMotion) {
                    scheduleTimer(scope, () => stop(id), duration);
                }
                return result(true, {
                    effectId: id,
                    name: definition.name,
                    reducedMotion,
                    loop: definition.loop,
                });
            } catch (error) {
                cleanupScope(scope);
                activeEffects.delete(id);
                safeLog(logger, error);
                return result(false, {
                    skipped: true,
                    reason: 'presentation_failure',
                    effectId: id,
                });
            }
        }

        function stop(effectId) {
            const id = String(effectId || '');
            const scope = activeEffects.get(id);
            if (!scope) return false;
            activeEffects.delete(id);
            cleanupScope(scope);
            return true;
        }

        function rememberStyle(state, property, value) {
            if (!state.previousStyles.has(property)) {
                state.previousStyles.set(property, host?.style?.getPropertyValue(property) || '');
            }
            try { host?.style?.setProperty(property, value); }
            catch (error) { safeLog(logger, error); }
        }

        function restoreStyles(state) {
            for (const [property, value] of state.previousStyles) {
                try {
                    if (value) host?.style?.setProperty(property, value);
                    else host?.style?.removeProperty(property);
                } catch (error) { safeLog(logger, error); }
            }
            state.previousStyles.clear();
        }

        function cameraTarget() {
            try {
                return host?.querySelector?.('[data-z3-camera-target]') || host;
            } catch (error) {
                safeLog(logger, error);
                return host;
            }
        }

        function removeCameraClasses() {
            for (const mode of CAMERA_MODES) setClass(host, `z3-camera-${slug(mode)}`, false);
            setClass(host, 'z3-camera-reduced-motion', false);
            setClass(host, 'z3-camera-active', false);
            setClass(host, 'z3-camera-impact-frame', false);
            setClass(cameraTarget(), 'z3-camera-target-active', false);
        }

        function stopCamera() {
            if (!cameraState) return false;
            const state = cameraState;
            cameraState = null;
            for (const handle of Array.from(state.timers)) cancelTrackedTimer(handle, state);
            for (const handle of Array.from(state.rafs)) cancelTrackedRaf(handle, state);
            removeCameraClasses();
            restoreStyles(state);
            return true;
        }

        function startCameraCue(shotId, request) {
            const id = String(shotId || '');
            const cue = CAMERA_CUES[id];
            if (destroyed) return result(false, { skipped: true, reason: 'destroyed', shotId: id });
            if (!cue || !host) {
                return result(false, { skipped: true, reason: 'camera_unavailable', shotId: id });
            }
            stopCamera();
            const optionsForCamera = request && typeof request === 'object' ? request : {};
            const reducedMotion = prefersReducedMotion(optionsForCamera);
            const duration = clamp(
                finiteOr(optionsForCamera.durationMs, cue.durationMs),
                0,
                LIMITS.CAMERA_ANIMATION_DURATION_MS,
            );
            const state = {
                shotId: id,
                timers: new Set(),
                rafs: new Set(),
                previousStyles: new Map(),
            };
            cameraState = state;
            setClass(host, 'z3-camera-active', true);
            setClass(host, `z3-camera-${slug(cue.mode)}`, !reducedMotion);
            setClass(host, 'z3-camera-reduced-motion', reducedMotion);
            setClass(cameraTarget(), 'z3-camera-target-active', true);
            rememberStyle(state, '--z3-camera-duration', `${duration}ms`);
            rememberStyle(state, '--z3-camera-x', `${cue.x}%`);
            rememberStyle(state, '--z3-camera-y', `${cue.y}%`);
            rememberStyle(state, '--z3-camera-scale-from', String(cue.scaleFrom || 1));
            rememberStyle(state, '--z3-camera-scale-to', String(cue.scaleTo || 1));
            rememberStyle(state, '--z3-camera-dx', `${cue.dxPct || 0}%`);
            rememberStyle(state, '--z3-camera-dy', `${cue.dyPct || 0}%`);
            rememberStyle(state, '--z3-camera-amplitude', `${cue.amplitudePx || 0}px`);
            if (!reducedMotion && duration > 0) {
                scheduleTimer(state, () => stopCamera(), duration);
            }
            if (!reducedMotion && cue.mode === 'bounded_impact_impulse') {
                scheduleRaf(state, () => setClass(host, 'z3-camera-impact-frame', true));
            }
            return result(true, { shotId: id, mode: cue.mode, reducedMotion });
        }

        function stopAll() {
            for (const id of Array.from(activeEffects.keys())) stop(id);
            stopCamera();
            return true;
        }

        function transitionShot(shotId, effectIds, request) {
            const id = String(shotId || '');
            if (!validShot(id)) return result(false, { skipped: true, reason: 'unknown_shot', shotId: id });
            stopAll();
            // The normal runtime path does not supply an explicit list.  Include
            // the shot's optional presentation cues there as well; otherwise
            // SHOT_OPTIONAL_EFFECTS is contract-only and cues such as the Shui
            // pulse never reach the real transition lifecycle.  Explicit lists
            // remain a low-level override for bounded tests/tools.
            const ids = Array.isArray(effectIds) ? effectIds : getShotEffects(id, true);
            const started = ids.map((effectId) => start(effectId, { ...(request || {}), shotId: id }));
            const camera = startCameraCue(id, request);
            return result(true, { shotId: id, effects: started, camera });
        }

        function getShotEffects(shotId, includeOptional) {
            const id = String(shotId || '');
            if (!validShot(id)) return Object.freeze([]);
            const required = SHOT_EFFECTS[id] || [];
            if (!includeOptional) return required;
            return Object.freeze([
                ...required,
                ...(SHOT_OPTIONAL_EFFECTS[id] || []),
            ]);
        }

        function getResourceStats() {
            let nodeCount = 0;
            for (const scope of activeEffects.values()) nodeCount += scope.nodes.length;
            return Object.freeze({
                activeTimerCount: activeTimers.size,
                activeRafCount: activeRafs.size,
                temporaryEffectNodeCount: nodeCount,
                activeEventListenerCount: activeListeners.size,
                activeEffectCount: activeEffects.size,
                activeCamera: Boolean(cameraState),
                destroyed,
            });
        }

        function getActiveEffectIds() {
            return Object.freeze(Array.from(activeEffects.keys()));
        }

        function getContract() {
            return Object.freeze({
                version: VERSION,
                zoneKey: ZONE_KEY,
                zoneNameZh: ZONE_NAME_ZH,
                zoneNameEn: ZONE_NAME_EN,
                effectIds: EFFECT_IDS,
                effects: EFFECT_DEFINITIONS,
                shotIds: SHOT_IDS,
                shotEffects: SHOT_EFFECTS,
                shotOptionalEffects: SHOT_OPTIONAL_EFFECTS,
                cameraCues: CAMERA_CUES,
                limits: LIMITS,
                parallaxImplemented: PARALLAX_IMPLEMENTED,
                parallaxRecommendedClassification: PARALLAX_RECOMMENDED_CLASSIFICATION,
                reducedMotionCoverage: '12/12 visual effects plus all camera cues',
                presentationFailure: 'STATIC_PRESENTATION_CONTINUES',
            });
        }

        function destroy() {
            if (destroyed) return false;
            stopAll();
            destroyed = true;
            setClass(host, 'z3-reduced-motion', false);
            setClass(host, 'z3-camera-impact-frame', false);
            return true;
        }

        return Object.freeze({
            start,
            stop,
            stopAll,
            startCameraCue,
            stopCamera,
            transitionShot,
            getShotEffects,
            getResourceStats,
            getActiveEffectIds,
            getContract,
            destroy,
        });
    }

    return Object.freeze({
        VERSION,
        ZONE_KEY,
        ZONE_NAME_ZH,
        ZONE_NAME_EN,
        PARALLAX_IMPLEMENTED,
        PARALLAX_RECOMMENDED_CLASSIFICATION,
        LIMITS,
        EFFECT_IDS,
        SHOT_IDS,
        SHOT_EFFECTS,
        SHOT_OPTIONAL_EFFECTS,
        EFFECT_DEFINITIONS,
        CAMERA_CUES,
        create,
    });
}));
