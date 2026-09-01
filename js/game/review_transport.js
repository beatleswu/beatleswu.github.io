(function (root) {
    'use strict';

    const CORE20 = [
        'ok',
        'ease_factor',
        'interval',
        'due_date',
        'new_badges',
        'stats',
        'xp_gain',
        'combo_mult',
        'pet_xp_added',
        'pet_xp_ratio',
        'pet_xp_gained',
        'combo_streak',
        'shield_used',
        'xp_potion_active',
        'ranked_up',
        'new_rank_level',
        'pet',
        'practice',
        'training',
        'new_appearance_items'
    ];

    const T2_OPTIONAL_FIELDS = [
        'monster',
        'player',
        'quest_updates',
        'sp',
        'loot',
        'appearance_loot'
    ];

    const FULL26 = CORE20.concat(T2_OPTIONAL_FIELDS);
    const DUP4 = [
        'ok',
        'progression_applied',
        'progression_duplicate',
        'question_id'
    ];
    // Must mirror review_contracts.py's APPROVED_PRESENTATION_EXTENSION_FIELDS
    // exactly. The server (review_compatibility.py) already sets these aside
    // before classifying the legacy shape and re-attaches them afterward
    // (legacy_review_serializer.py); this client must do the same or any
    // response carrying one -- e.g. a review that triggers a level-up -- gets
    // rejected as invalid_review_response even though it was already durably
    // committed server-side.
    const APPROVED_PRESENTATION_EXTENSION_FIELDS = ['combat_stats', 'level_up_rewards', 'boss_verdict'];
    const PUBLIC_SUBMISSION_DUPLICATE = [
        'ok',
        'submission_duplicate',
        'submission_id',
        'question_id',
        'grade'
    ];

    class ReviewRejected extends Error {
        constructor(payload, status) {
            const code = payload && payload.error;
            const message = payload && payload.message
                ? payload.message
                : String(code || 'review_rejected');
            super(message);
            this.name = 'ReviewRejected';
            this.kind = 'REJECTED';
            this.code = code;
            this.status = status;
            this.payload = payload;
        }
    }

    class ReviewTransportError extends Error {
        constructor(code, message, cause) {
            super(message || code);
            this.name = 'ReviewTransportError';
            this.kind = 'TRANSPORT_ERROR';
            this.code = code;
            if (cause !== undefined) this.cause = cause;
        }
    }

    function isObjectPayload(payload) {
        return payload !== null && typeof payload === 'object' && !Array.isArray(payload);
    }

    function hasExactKeys(payload, fields) {
        const keys = Object.keys(payload);
        if (keys.length !== fields.length) return false;
        for (let index = 0; index < keys.length; index += 1) {
            if (fields.indexOf(keys[index]) === -1) return false;
        }
        return true;
    }

    function snapshot(payload) {
        const copy = new Object();
        const keys = Object.keys(payload);
        for (let index = 0; index < keys.length; index += 1) {
            const key = keys[index];
            copy[key] = payload[key];
        }
        return copy;
    }

    function invalidResponse() {
        return new ReviewTransportError(
            'invalid_review_response',
            'invalid_review_response'
        );
    }

    function withoutApprovedExtensions(payload) {
        const core = snapshot(payload);
        for (let index = 0; index < APPROVED_PRESENTATION_EXTENSION_FIELDS.length; index += 1) {
            delete core[APPROVED_PRESENTATION_EXTENSION_FIELDS[index]];
        }
        return core;
    }

    function buildRequest(command) {
        const value = command || {};
        const request = new Object();
        request.question_id = value.question_id;
        request.grade = value.grade;
        request.unit_name = value.unit_name || null;
        request.unit_done = !!value.unit_done;
        request.response_ms = value.response_ms == null ? null : value.response_ms;
        request.source_context = value.source_context || 'practice';
        if (value.boss_answer !== undefined) request.boss_answer = value.boss_answer;
        // Server-judged Guild evidence.  These are answer inputs, not
        // authority claims: the server re-derives eligibility and correctness.
        if (value.guild_answer !== undefined) request.guild_answer = value.guild_answer;
        if (value.guild_quest_key !== undefined) request.guild_quest_key = value.guild_quest_key;
        request.training_set_id = value.training_set_id == null ? null : value.training_set_id;
        request.is_scaffolding = !!value.is_scaffolding;
        // A public caller may reuse a server-validated retry identity.  Do
        // not serialize internal MapBattle identities through this client
        // transport; those calls use the server-side handoff directly.
        if (value.internal !== true && typeof value.submission_id === 'string' && value.submission_id) {
            request.submission_id = value.submission_id;
        }
        return request;
    }

    function mapOutcome(payload, options) {
        if (!isObjectPayload(payload)) throw invalidResponse();

        const internal = !!(options && options.internal === true);
        const core = withoutApprovedExtensions(payload);
        if (hasExactKeys(core, PUBLIC_SUBMISSION_DUPLICATE)) {
            if (internal || payload.ok !== true) throw invalidResponse();
            return { kind: 'PUBLIC_SUBMISSION_DUPLICATE', payload: snapshot(payload) };
        }
        if (hasExactKeys(core, DUP4)) {
            if (!internal || payload.ok !== true) throw invalidResponse();
            return { kind: 'INTERNAL_DUPLICATE', payload: snapshot(payload) };
        }

        if (payload.ok !== true) throw invalidResponse();
        if (hasExactKeys(core, FULL26)) {
            return { kind: 'PUBLIC_FULL', payload: snapshot(payload) };
        }
        if (hasExactKeys(core, CORE20)) {
            return { kind: 'PUBLIC_CORE', payload: snapshot(payload) };
        }
        throw invalidResponse();
    }

    async function review(command, fetchImpl) {
        const requester = typeof fetchImpl === 'function'
            ? fetchImpl
            : (typeof fetch === 'function' ? fetch : null);
        if (!requester) {
            throw new ReviewTransportError('review_transport_error', 'fetch_unavailable');
        }

        const headers = new Object();
        headers['Content-Type'] = 'application/json';
        const options = new Object();
        options.credentials = 'include';
        options.method = 'POST';
        options.headers = headers;
        options.body = JSON.stringify(buildRequest(command));

        let response;
        try {
            response = await requester('/api/srs/review', options);
        } catch (cause) {
            throw new ReviewTransportError('review_transport_error', 'review_transport_error', cause);
        }

        let payload;
        try {
            payload = await response.json();
        } catch (cause) {
            throw new ReviewTransportError(
                'review_response_parse_error',
                'review_response_parse_error',
                cause
            );
        }

        if (!response.ok) {
            if (isObjectPayload(payload) && typeof payload.error === 'string' && payload.error) {
                throw new ReviewRejected(payload, response.status);
            }
            throw new ReviewTransportError(
                'review_http_error',
                'review_http_error',
            );
        }

        return mapOutcome(payload);
    }

    async function legacyReview(questionId, grade, unitName, unitDone, metadata, fetchImpl) {
        const value = metadata || {};
        const command = {
            question_id: questionId,
            grade,
            unit_name: unitName,
            unit_done: unitDone,
            response_ms: value.response_ms,
            source_context: value.source_context,
            boss_answer: value.boss_answer,
            guild_answer: value.guild_answer,
            guild_quest_key: value.guild_quest_key,
            training_set_id: value.training_set_id,
            is_scaffolding: value.is_scaffolding,
            submission_id: value.submission_id
        };

        try {
            const outcome = await review(command, fetchImpl);
            return outcome.payload;
        } catch (error) {
            if (
                error &&
                error.kind === 'REJECTED' &&
                (error.code === 'premium_required' ||
                    error.code === 'daily_limit' ||
                    // INCIDENT_018: an expired Lord attempt is a server-owned
                    // gameplay state, not a transport fault.  Hand it back as
                    // a payload so the caller can say what actually happened
                    // instead of reporting a write failure.
                    error.code === 'boss_attempt_expired')
            ) {
                return error.payload;
            }
            throw error;
        }
    }

    root.ReviewTransport = {
        endpoint: '/api/srs/review',
        buildRequest,
        mapOutcome,
        review,
        legacyReview
    };
}(typeof window !== 'undefined' ? window : globalThis));
