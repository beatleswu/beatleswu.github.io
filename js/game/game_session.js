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
            // Ordinary public Review recovery is separate from the render-session
            // identity. invalidate()/endReview() must not discard an uncertain
            // HTTP submission. Stored acknowledgements are never commit authority.
            this._publicReviewStores = new Map();
            this._publicReviewInFlight = new Set();
            // Server-confirmed outcomes observed by THIS page instance. Persisted
            // state alone can never settle an answer (storage is client-writable).
            this._publicReviewConfirmed = new Set();
        }

        _publicReviewStore(userId) {
            const owner = Number(userId);
            if (!Number.isSafeInteger(owner) || owner <= 0) {
                throw new Error('public_review_authenticated_owner_required');
            }
            if (!this._publicReviewStores.has(owner)) {
                const storageKey = `go:public-review:v1:${owner}`;
                const raw = global.sessionStorage.getItem(storageKey);
                const entries = raw ? JSON.parse(raw) : {};
                if (!entries || typeof entries !== 'object' || Array.isArray(entries)) {
                    throw new Error('public_review_recovery_state_invalid');
                }
                this._publicReviewStores.set(owner, { storageKey, entries });
            }
            return this._publicReviewStores.get(owner);
        }

        _savePublicReview(userId) {
            const store = this._publicReviewStore(userId);
            // Fail before POST if persistence is unavailable; never silently
            // replace a pending identity on reentry or a browser reload.
            global.sessionStorage.setItem(store.storageKey, JSON.stringify(store.entries));
        }

        beginPublicReview(userId, command, mode = 'normal') {
            if (!command || command.source_context !== 'practice'
                || command.internal || command.boss_answer || command.guild_answer
                || command.training_set_id != null
                || Object.keys(command).some((field) => ![
                    'question_id', 'grade', 'unit_name', 'unit_done', 'response_ms',
                    'source_context', 'training_set_id', 'is_scaffolding', 'submission_id',
                ].includes(field))) {
                throw new Error('public_review_recovery_scope_mismatch');
            }
            const store = this._publicReviewStore(userId);
            const key = JSON.stringify([mode, Number(command.question_id), command.unit_name || null]);
            const lockKey = `${userId}:${key}`;
            if (this._publicReviewInFlight.has(lockKey)) return null;
            let entry = store.entries[key];
            if (!entry) {
                if (!global.crypto || typeof global.crypto.randomUUID !== 'function') {
                    throw new Error('public_review_secure_identity_unavailable');
                }
                entry = {
                    command: JSON.parse(JSON.stringify({ ...command, submission_id: global.crypto.randomUUID() })),
                    state: 'CREATED', sent: false, uiSettled: false,
                };
                store.entries[key] = entry;
                this._savePublicReview(userId);
            } else if (!entry.command || typeof entry.command !== 'object'
                || Array.isArray(entry.command)
                || typeof entry.command.submission_id !== 'string'
                || !entry.command.submission_id
                || entry.command.source_context !== 'practice'
                || entry.command.training_set_id != null
                || Object.keys(entry.command).some((field) => ![
                    'question_id', 'grade', 'unit_name', 'unit_done', 'response_ms',
                    'source_context', 'training_set_id', 'is_scaffolding', 'submission_id',
                ].includes(field))) {
                throw new Error('public_review_recovery_state_invalid');
            }
            if (entry.uiSettled && !this._publicReviewConfirmed.has(lockKey)) {
                // A persisted "settled" flag is client-writable. Never trust it on a
                // fresh page: re-verify through the idempotent resend (same
                // submission id -> the server answers DUPLICATE, no second effect).
                entry.uiSettled = false;
                entry.state = 'UNKNOWN_UNCONFIRMED';
                this._savePublicReview(userId);
            }
            if (!entry.uiSettled) {
                // Telemetry and the now-current unit completion projection are
                // not a new logical payload. Reuse their original wire values.
                for (const field of ['question_id', 'grade', 'unit_name', 'source_context',
                    'training_set_id', 'is_scaffolding']) {
                    if (JSON.stringify(entry.command[field]) !== JSON.stringify(command[field])) {
                        throw new Error('public_review_pending_payload_changed');
                    }
                }
                this._publicReviewInFlight.add(lockKey);
            }
            return Object.freeze({
                userId: Number(userId), key, lockKey, settled: !!entry.uiSettled,
                firstRequest: !entry.sent,
                command: Object.freeze(JSON.parse(JSON.stringify(entry.command))),
            });
        }

        publicReviewCommand(attempt, unitDone) {
            const entry = this._publicReviewStore(attempt.userId).entries[attempt.key];
            if (!entry.sent) {
                entry.command.unit_done = !!unitDone;
                entry.sent = true;
                entry.state = 'UNKNOWN_UNCONFIRMED';
                this._savePublicReview(attempt.userId);
            }
            return Object.freeze(JSON.parse(JSON.stringify(entry.command)));
        }

        recordPublicReviewOutcome(attempt, state) {
            if (!['SERVER_REJECTED', 'UNKNOWN_UNCONFIRMED', 'NEW_COMMITTED',
                'DUPLICATE_COMMITTED_RECOVERED'].includes(state)) {
                throw new Error('public_review_outcome_invalid');
            }
            const entry = this._publicReviewStore(attempt.userId).entries[attempt.key];
            entry.state = state;
            if (['NEW_COMMITTED', 'DUPLICATE_COMMITTED_RECOVERED'].includes(state)) {
                this._publicReviewConfirmed.add(attempt.lockKey);
            } else {
                this._publicReviewConfirmed.delete(attempt.lockKey);
            }
            this._savePublicReview(attempt.userId);
        }

        settlePublicReview(attempt) {
            const entry = this._publicReviewStore(attempt.userId).entries[attempt.key];
            if (entry.uiSettled) return false;
            if (!this._publicReviewConfirmed.has(attempt.lockKey)
                || !['NEW_COMMITTED', 'DUPLICATE_COMMITTED_RECOVERED'].includes(entry.state)) {
                throw new Error('public_review_commit_not_confirmed');
            }
            entry.uiSettled = true;
            this._savePublicReview(attempt.userId);
            return true;
        }

        endPublicReview(attempt) {
            if (attempt) this._publicReviewInFlight.delete(attempt.lockKey);
        }

        newPublicReviewAttempt(attempt) {
            const store = this._publicReviewStore(attempt.userId);
            const entry = store.entries[attempt.key];
            if (!entry || this._publicReviewInFlight.has(attempt.lockKey)
                || (!entry.uiSettled && entry.state !== 'SERVER_REJECTED')) return false;
            delete store.entries[attempt.key];
            this._savePublicReview(attempt.userId);
            return true;
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
