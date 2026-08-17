(function (global) {
    'use strict';

    function normalizeOptions(options) {
        if (!options || typeof options !== 'object') return {};
        return { ...options };
    }

    function normalizeQuestion(question) {
        if (!question || typeof question !== 'object') return null;
        const id = Number(question.id ?? question.questionId ?? question.question_id);
        if (!Number.isFinite(id)) return null;
        return question;
    }

    function create(dependencies = {}) {
        if (!dependencies || typeof dependencies !== 'object') {
            throw new TypeError('QuestionLoader dependencies must be an object');
        }

        let generation = 0;
        let active = null;

        const notifyGeneration = (value, reason) => {
            if (typeof dependencies.onGeneration === 'function') {
                try {
                    dependencies.onGeneration(value, reason);
                } catch (error) {
                    // A compatibility projection cannot invalidate loading.
                }
            }
        };

        const isCurrent = (token) => active === token && token.generation === generation;

        const identityOptions = (question, options, token, overrides = {}) => {
            const supplied = options.identityOptions && typeof options.identityOptions === 'object'
                ? options.identityOptions
                : {};
            const derived = typeof dependencies.getIdentityOptions === 'function'
                ? dependencies.getIdentityOptions(question, options, token)
                : {};
            return {
                ...derived,
                ...supplied,
                ...overrides,
                lifecycleGeneration: token.generation,
            };
        };

        const commit = (token, options = {}) => {
            if (!isCurrent(token) || token.committed) return false;
            token.committed = true;
            if (typeof dependencies.setCurrentQuestion === 'function') {
                dependencies.setCurrentQuestion(token.question, {
                    generation: token.generation,
                    options,
                });
            }
            if (dependencies.gameSession && typeof dependencies.gameSession.adoptQuestion === 'function') {
                token.identity = dependencies.gameSession.adoptQuestion(
                    token.question,
                    identityOptions(token.question, token.options, token, options),
                );
            }
            if (typeof dependencies.onCommit === 'function') {
                try {
                    dependencies.onCommit(token.question, token.identity, token.generation);
                } catch (error) {
                    // Commit observers are diagnostics/compatibility only.
                }
            }
            return token.identity || true;
        };

        const load = (question, rawOptions = {}) => {
            const normalized = normalizeQuestion(question);
            const options = normalizeOptions(rawOptions);
            if (active && active.committed
                && dependencies.gameSession
                && typeof dependencies.gameSession.invalidate === 'function') {
                try { dependencies.gameSession.invalidate(); } catch (error) {}
            }
            generation += 1;
            const token = {
                question: normalized,
                options,
                generation,
                committed: false,
                identity: null,
            };
            active = token;
            notifyGeneration(generation, 'load');

            if (!normalized) {
                if (typeof dependencies.onInvalid === 'function') {
                    try { dependencies.onInvalid(question, generation); } catch (error) {}
                }
                return Promise.resolve(false);
            }

            const context = Object.freeze({
                question: normalized,
                options,
                generation,
                isCurrent: () => isCurrent(token),
                commit: (commitOptions) => commit(token, commitOptions),
                invalidate: () => {
                    if (isCurrent(token)) invalidate('load_context');
                },
                identity: () => token.identity,
            });

            let result;
            try {
                result = typeof dependencies.load === 'function'
                    ? dependencies.load(normalized, context)
                    : context.commit();
            } catch (error) {
                result = false;
                if (typeof dependencies.onError === 'function') {
                    try { dependencies.onError(error, normalized, generation); } catch (observerError) {}
                }
            }

            return Promise.resolve(result).then((value) => {
                if (!isCurrent(token)) return false;
                return value;
            }, (error) => {
                if (typeof dependencies.onError === 'function') {
                    try { dependencies.onError(error, normalized, generation); } catch (observerError) {}
                }
                return false;
            });
        };

        function invalidate(reason = 'invalidate') {
            generation += 1;
            active = null;
            notifyGeneration(generation, reason);
            if (dependencies.gameSession && typeof dependencies.gameSession.invalidate === 'function') {
                // Session invalidation is deliberately explicit; callers can
                // opt out when navigation must preserve an existing identity.
                if (reason === 'session' || reason === 'navigation') {
                    try { dependencies.gameSession.invalidate(); } catch (error) {}
                }
            }
            return generation;
        }

        function adoptIdentity(overrides = {}) {
            const token = active;
            if (!token || !token.committed || !isCurrent(token)
                || !dependencies.gameSession
                || typeof dependencies.gameSession.adoptQuestion !== 'function') {
                return null;
            }
            const options = normalizeOptions(overrides);
            token.identity = dependencies.gameSession.adoptQuestion(
                token.question,
                identityOptions(token.question, token.options, token, options),
            );
            return token.identity;
        }

        return Object.freeze({
            load,
            invalidate,
            adoptIdentity,
            generation: () => generation,
            current: () => active ? active.question : null,
            isCurrent: (candidateGeneration) => active !== null
                && (candidateGeneration == null || Number(candidateGeneration) === generation),
            commit: () => false,
        });
    }

    const api = Object.freeze({ create });
    global.GoOdysseyQuestionLoader = api;
    global.QuestionLoader = api;
})(window);
