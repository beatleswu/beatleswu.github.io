(function (global) {
    'use strict';

    const hasOwn = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
    const IDENTITY_FIELDS = Object.freeze([
        'questionId',
        'mode',
        'attemptId',
        'lordIndex',
        'lifecycleGeneration',
        'sourceContext',
    ]);
    const SOURCE_CONTEXT_FIELDS = Object.freeze([
        'surface',
        'origin',
        'flow',
        'entry',
        'zone',
        'stage',
        'kind',
    ]);

    function finiteNumber(value, field, required) {
        if (value == null || value === '') {
            if (required) throw new TypeError(`${field} must be a finite Number`);
            return null;
        }
        const normalized = Number(value);
        if (!Number.isFinite(normalized)) {
            if (required) throw new TypeError(`${field} must be a finite Number`);
            return null;
        }
        return normalized;
    }

    function textValue(value) {
        if (value == null) return null;
        if (typeof value === 'string') return value;
        if (typeof value === 'number' && Number.isFinite(value)) return String(value);
        if (typeof value === 'boolean') return String(value);
        return null;
    }

    function sourceContextValue(value) {
        if (value == null) return null;
        const scalar = textValue(value);
        if (scalar !== null) return scalar;
        if (typeof value !== 'object' || Array.isArray(value)) return null;

        const bounded = {};
        SOURCE_CONTEXT_FIELDS.forEach((field) => {
            if (hasOwn(value, field)) {
                const item = textValue(value[field]);
                if (item !== null) bounded[field] = item;
            }
        });
        return Object.freeze(bounded);
    }

    function inertSourceIdentity(value) {
        if (value == null) return null;
        const scalar = textValue(value);
        return scalar === null ? null : scalar;
    }

    function fieldValue(question, options, field, aliases) {
        if (hasOwn(options, field)) return options[field];
        for (const alias of aliases) {
            if (hasOwn(question, alias)) return question[alias];
        }
        return null;
    }

    function createIdentity(question, options = {}) {
        if (!question || typeof question !== 'object') {
            throw new TypeError('question must be an object');
        }
        if (!options || typeof options !== 'object') {
            throw new TypeError('options must be an object');
        }

        const questionId = finiteNumber(
            fieldValue(question, options, 'questionId', ['questionId', 'id', 'question_id']),
            'questionId',
            true,
        );
        const identity = {
            questionId,
            mode: textValue(fieldValue(question, options, 'mode', ['mode'])),
            attemptId: textValue(fieldValue(question, options, 'attemptId', ['attemptId', 'attempt_id'])),
            lordIndex: finiteNumber(
                fieldValue(question, options, 'lordIndex', ['lordIndex', 'lord_index']),
                'lordIndex',
                false,
            ),
            lifecycleGeneration: finiteNumber(
                fieldValue(question, options, 'lifecycleGeneration', [
                    'lifecycleGeneration',
                    'lifecycle_generation',
                ]),
                'lifecycleGeneration',
                false,
            ),
            sourceContext: sourceContextValue(
                fieldValue(question, options, 'sourceContext', ['sourceContext', 'source_context']),
            ),
        };

        if (hasOwn(question, 'sourceIdentity') || hasOwn(options, 'sourceIdentity')) {
            const source = hasOwn(options, 'sourceIdentity')
                ? options.sourceIdentity
                : question.sourceIdentity;
            identity.sourceIdentity = inertSourceIdentity(source);
        }
        return Object.freeze(identity);
    }

    function identityFromValue(value) {
        if (!value || typeof value !== 'object') return null;
        try {
            const source = {
                questionId: value.questionId,
                mode: value.mode,
                attemptId: value.attemptId,
                lordIndex: value.lordIndex,
                lifecycleGeneration: value.lifecycleGeneration,
                sourceContext: value.sourceContext,
            };
            if (hasOwn(value, 'sourceIdentity')) source.sourceIdentity = value.sourceIdentity;
            return createIdentity(source, source);
        } catch (error) {
            return null;
        }
    }

    function stableKey(value) {
        const identity = identityFromValue(value);
        if (!identity) return null;
        // sourceIdentity is intentionally excluded: it is reserved and inert.
        return JSON.stringify(IDENTITY_FIELDS.map((field) => identity[field]));
    }

    function equals(left, right) {
        const leftKey = stableKey(left);
        const rightKey = stableKey(right);
        return leftKey !== null && leftKey === rightKey;
    }

    function boundedContext(value) {
        const identity = identityFromValue(value);
        if (!identity) return null;
        return Object.freeze({
            questionId: identity.questionId,
            mode: identity.mode,
            attemptId: identity.attemptId,
            lordIndex: identity.lordIndex,
            lifecycleGeneration: identity.lifecycleGeneration,
            sourceContext: identity.sourceContext,
            identityKey: stableKey(identity),
        });
    }

    const QuestionIdentity = Object.freeze({
        fromQuestion: createIdentity,
        normalize: identityFromValue,
        key: stableKey,
        equals,
        reviewContext: boundedContext,
        presentationContext: boundedContext,
    });

    function questionMatchesIdentity(question, identity) {
        if (!question || typeof question !== 'object') return false;
        let candidate;
        try {
            candidate = createIdentity(question);
        } catch (error) {
            return false;
        }
        if (candidate.questionId !== identity.questionId) return false;

        const questionFields = [
            ['mode', ['mode']],
            ['attemptId', ['attemptId', 'attempt_id']],
            ['lordIndex', ['lordIndex', 'lord_index']],
            ['lifecycleGeneration', ['lifecycleGeneration', 'lifecycle_generation']],
            ['sourceContext', ['sourceContext', 'source_context']],
        ];
        return questionFields.every(([field, aliases]) => {
            const present = aliases.some((alias) => hasOwn(question, alias));
            if (!present) return true;
            if (field !== 'sourceContext') return candidate[field] === identity[field];
            return JSON.stringify(candidate[field]) === JSON.stringify(identity[field]);
        });
    }

    class GameSession {
        constructor(dependencies = {}) {
            if (!dependencies || typeof dependencies !== 'object') {
                throw new TypeError('dependencies must be an object');
            }
            this._getCurrentQuestion = typeof dependencies.getCurrentQuestion === 'function'
                ? dependencies.getCurrentQuestion
                : null;
            this._getLifecycleGeneration = typeof dependencies.getLifecycleGeneration === 'function'
                ? dependencies.getLifecycleGeneration
                : null;
            this._currentIdentity = null;
            this._reviewInFlightKey = null;
        }

        currentQuestionIdentity() {
            return this._currentIdentity;
        }

        adoptQuestion(question, options = {}) {
            const nextIdentity = QuestionIdentity.fromQuestion(question, options);
            if (!QuestionIdentity.equals(this._currentIdentity, nextIdentity)) {
                this._reviewInFlightKey = null;
            }
            this._currentIdentity = nextIdentity;
            return nextIdentity;
        }

        isCurrent(identity, options = {}) {
            const candidate = identityFromValue(identity);
            if (!candidate || !QuestionIdentity.equals(candidate, this._currentIdentity)) {
                return false;
            }

            if (options && hasOwn(options, 'question')
                && !questionMatchesIdentity(options.question, candidate)) {
                return false;
            }

            if (options && hasOwn(options, 'lifecycleGeneration')
                && finiteNumber(options.lifecycleGeneration, 'lifecycleGeneration', false)
                    !== candidate.lifecycleGeneration) {
                return false;
            }

            if (this._getCurrentQuestion) {
                let currentQuestion;
                try {
                    currentQuestion = this._getCurrentQuestion();
                } catch (error) {
                    return false;
                }
                if (!questionMatchesIdentity(currentQuestion, candidate)) return false;
            }

            if (this._getLifecycleGeneration) {
                let currentGeneration;
                try {
                    currentGeneration = this._getLifecycleGeneration();
                } catch (error) {
                    return false;
                }
                if (finiteNumber(currentGeneration, 'lifecycleGeneration', false)
                    !== candidate.lifecycleGeneration) {
                    return false;
                }
            }
            return true;
        }

        beginReview(identity) {
            const key = QuestionIdentity.key(identity);
            if (key === null || this._reviewInFlightKey === key) return false;
            this._reviewInFlightKey = key;
            return true;
        }

        endReview(identity) {
            const key = QuestionIdentity.key(identity);
            if (key === null || this._reviewInFlightKey !== key) return false;
            this._reviewInFlightKey = null;
            return true;
        }

        presentationContext(identity) {
            return QuestionIdentity.presentationContext(identity || this._currentIdentity);
        }

        invalidate() {
            this._currentIdentity = null;
            this._reviewInFlightKey = null;
        }
    }

    const api = Object.freeze({
        QuestionIdentity,
        GameSession,
        create: (dependencies) => new GameSession(dependencies),
    });
    global.GoOdysseyGameSession = api;
})(window);
