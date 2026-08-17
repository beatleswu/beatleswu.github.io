(function (global) {
    'use strict';

    // GameBootstrap owns lifecycle coordination only.  It deliberately has no
    // knowledge of review transport, questions, modes, progression, or DOM
    // rendering.  Product modules register their own cleanup boundaries.
    function create(dependencies = {}) {
        if (!dependencies || typeof dependencies !== 'object') {
            throw new TypeError('GameBootstrap dependencies must be an object');
        }

        let initialized = false;
        let destroyed = false;
        let lifecycleGeneration = 0;
        const listeners = new Set();
        const listenerSpecs = new Set();
        const cleanups = new Set();
        const timers = new Set();
        const timerKeys = new Map();
        const intervalSpecs = new Map();

        function attachListener(record) {
            if (!record || record.active) return;
            record.target.addEventListener(record.eventName, record.handler, record.options);
            record.active = true;
            listeners.add(record);
        }

        function init() {
            if (initialized && !destroyed) return false;
            initialized = true;
            destroyed = false;
            lifecycleGeneration += 1;
            for (const record of listenerSpecs) {
                try { attachListener(record); } catch (error) {}
            }
            for (const spec of intervalSpecs.values()) {
                if (!timerKeys.has(spec.key)) scheduleInterval(spec.callback, spec.delay, { key: spec.key });
            }
            if (typeof dependencies.onInit === 'function') {
                try { dependencies.onInit(lifecycleGeneration); } catch (error) {}
            }
            return true;
        }

        function removeTimer(record) {
            if (!record || !timers.has(record)) return;
            timers.delete(record);
            if (record.key != null && timerKeys.get(record.key) === record) timerKeys.delete(record.key);
            try { record.clear(record.id); } catch (error) {}
        }

        function registerCleanup(cleanup) {
            if (typeof cleanup !== 'function') return cleanup;
            cleanups.add(cleanup);
            return cleanup;
        }

        function registerListener(target, eventName, handler, options) {
            if (!target || typeof target.addEventListener !== 'function' || typeof handler !== 'function') {
                return () => {};
            }
            const record = { target, eventName, handler, options, active: false };
            listenerSpecs.add(record);
            attachListener(record);
            const detach = () => {
                listenerSpecs.delete(record);
                if (record.active) {
                    record.active = false;
                    listeners.delete(record);
                    try { target.removeEventListener?.(eventName, handler, options); } catch (error) {}
                }
            };
            return detach;
        }

        function scheduleTimeout(callback, delay = 0, options = {}) {
            if (typeof callback !== 'function') return null;
            const key = options.key;
            if (key != null && timerKeys.has(key)) removeTimer(timerKeys.get(key));
            const capturedGeneration = lifecycleGeneration;
            const record = { id: null, clear: clearTimeout, key, active: true };
            const invoke = () => {
                if (!record.active) return;
                timers.delete(record);
                if (key != null && timerKeys.get(key) === record) timerKeys.delete(key);
                record.active = false;
                if (destroyed || capturedGeneration !== lifecycleGeneration) return;
                try { callback(); } catch (error) {
                    if (typeof dependencies.onError === 'function') {
                        try { dependencies.onError(error, 'timeout'); } catch (observerError) {}
                    }
                }
            };
            record.id = setTimeout(invoke, Math.max(0, Number(delay) || 0));
            timers.add(record);
            if (key != null) timerKeys.set(key, record);
            return record.id;
        }

        function scheduleInterval(callback, delay = 0, options = {}) {
            if (typeof callback !== 'function') return null;
            const key = options.key;
            if (key != null && timerKeys.has(key)) return timerKeys.get(key).id;
            if (key != null) intervalSpecs.set(key, { key, callback, delay });
            const record = { id: null, clear: clearInterval, key, active: true };
            const invoke = () => {
                if (!record.active || destroyed) return;
                try { callback(); } catch (error) {
                    if (typeof dependencies.onError === 'function') {
                        try { dependencies.onError(error, 'interval'); } catch (observerError) {}
                    }
                }
            };
            record.id = setInterval(invoke, Math.max(0, Number(delay) || 0));
            timers.add(record);
            if (key != null) timerKeys.set(key, record);
            return record.id;
        }

        function invalidate(reason = 'invalidate') {
            lifecycleGeneration += 1;
            for (const record of Array.from(timers)) {
                if (record.clear === clearTimeout) removeTimer(record);
            }
            if (typeof dependencies.onInvalidate === 'function') {
                try { dependencies.onInvalidate(lifecycleGeneration, reason); } catch (error) {}
            }
            return lifecycleGeneration;
        }

        function capture(extra = {}) {
            return Object.freeze({
                lifecycleGeneration,
                ...extra,
            });
        }

        function isCurrent(token) {
            return !destroyed
                && !!token
                && Number(token.lifecycleGeneration) === lifecycleGeneration;
        }

        function destroy() {
            if (destroyed) return true;
            destroyed = true;
            initialized = false;
            lifecycleGeneration += 1;
            for (const record of Array.from(timers)) removeTimer(record);
            for (const record of Array.from(listeners)) {
                try { record.target.removeEventListener?.(record.eventName, record.handler, record.options); } catch (error) {}
                record.active = false;
            }
            listeners.clear();
            for (const cleanup of Array.from(cleanups).reverse()) {
                try { cleanup(); } catch (error) {}
            }
            cleanups.clear();
            if (typeof dependencies.onDestroy === 'function') {
                try { dependencies.onDestroy(lifecycleGeneration); } catch (error) {}
            }
            return true;
        }

        function remount() {
            destroy();
            return init();
        }

        return Object.freeze({
            init,
            destroy,
            remount,
            invalidate,
            capture,
            isCurrent,
            registerCleanup,
            registerListener,
            scheduleTimeout,
            scheduleInterval,
            lifecycleGeneration: () => lifecycleGeneration,
            isInitialized: () => initialized && !destroyed,
            listenerCount: () => listeners.size,
            timerCount: () => timers.size,
        });
    }

    const api = Object.freeze({ create });
    global.GoOdysseyGameBootstrap = api;
    global.GameBootstrap = api;
})(window);
