(function (global) {
    'use strict';

    // ModeContext is intentionally a small, read-only context adapter.  It
    // centralizes mode identity without acquiring transport, progression,
    // persistence, or rendering authority.
    const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);

    function read(dependencies, name, fallback = null) {
        const value = dependencies[name];
        if (typeof value !== 'function') return fallback;
        try { return value(); } catch (error) { return fallback; }
    }

    function modeFrom(dependencies) {
        if (read(dependencies, 'getBossMode', false)) return 'lord';
        const mapMode = read(dependencies, 'getMapBattleMode', null);
        if (mapMode === 'active' || mapMode === true) return 'map_battle';
        if (read(dependencies, 'getChallengeId', null) != null) return 'friend_challenge';
        if (read(dependencies, 'getDailyMode', false)) return 'daily';
        if (read(dependencies, 'getAdventureMode', false)
            || (mapMode === 'pending' && read(dependencies, 'getAdventureQuestions', false))) {
            return 'adventure';
        }
        return 'normal';
    }

    function sourceContextFor(mode, dependencies) {
        if (mode === 'lord') {
            return { surface: 'lord_trial', flow: 'lord_review', kind: 'question' };
        }
        if (mode === 'map_battle') {
            return { surface: 'map_battle', flow: 'map_battle_load', kind: 'question' };
        }
        if (mode === 'friend_challenge') {
            return { surface: 'friend_challenge', flow: 'question_load', kind: 'question' };
        }
        if (mode === 'daily') {
            return { surface: 'daily', flow: 'question_load', kind: 'question' };
        }
        if (mode === 'adventure') {
            return { surface: 'adventure', flow: 'question_load', kind: 'question' };
        }
        const supplied = read(dependencies, 'getSourceContext', null);
        return supplied && typeof supplied === 'object'
            ? { ...supplied }
            : { surface: 'practice', flow: 'question_load', kind: 'question' };
    }

    function create(dependencies = {}) {
        if (!dependencies || typeof dependencies !== 'object') {
            throw new TypeError('ModeContext dependencies must be an object');
        }

        const currentMode = () => modeFrom(dependencies);

        const metadata = () => Object.freeze({
            mode: currentMode(),
            attemptId: read(dependencies, 'getBossAttemptId', null)
                ?? read(dependencies, 'getMapBattleAttemptId', null),
            challengeId: read(dependencies, 'getChallengeId', null),
            daily: currentMode() === 'daily',
        });

        const capabilities = () => Object.freeze({
            mode: currentMode(),
            lord: currentMode() === 'lord',
            mapBattle: currentMode() === 'map_battle',
            friendChallenge: currentMode() === 'friend_challenge',
            daily: currentMode() === 'daily',
            adventure: currentMode() === 'adventure',
        });

        const identityOptions = (question, overrides = {}) => {
            const mode = currentMode();
            const mapState = read(dependencies, 'getMapBattleState', null);
            const derived = {
                mode,
                attemptId: mode === 'lord'
                    ? read(dependencies, 'getBossAttemptId', null)
                    : (mode === 'map_battle' ? (mapState?.attemptId || null) : null),
                lordIndex: mode === 'lord' ? read(dependencies, 'getLordIndex', null) : null,
                lifecycleGeneration: read(dependencies, 'getLifecycleGeneration', null),
                sourceContext: sourceContextFor(mode, dependencies),
            };
            const supplied = overrides && typeof overrides.identityOptions === 'object'
                ? overrides.identityOptions
                : {};
            const result = { ...derived, ...supplied };
            Object.keys(overrides || {}).forEach((key) => {
                if (key !== 'identityOptions' && hasOwn(overrides, key)) result[key] = overrides[key];
            });
            return result;
        };

        const context = () => Object.freeze({
            ...metadata(),
            sourceContext: Object.freeze(sourceContextFor(currentMode(), dependencies)),
            capabilities: capabilities(),
        });

        return Object.freeze({
            currentMode,
            mode: currentMode,
            resolve: currentMode,
            metadata,
            capabilities,
            context,
            identityOptions,
            identityFor: identityOptions,
            presentationMode: currentMode,
        });
    }

    const api = Object.freeze({ create });
    global.GoOdysseyModeContext = api;
    global.ModeContext = api;
})(window);
