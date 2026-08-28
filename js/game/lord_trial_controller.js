/**
 * Lord Trial authoritative review coordinator.
 *
 * This module deliberately knows nothing about badges, XP, pets, loot, or
 * other display effects.  It accepts only a committed review result and
 * owns the client-side exactly-once handoff to the next Lord state.
 */
(function (global) {
    'use strict';

    // Lane B names the observable boundary independently from the concrete
    // Lord Trial product name.  Keep the boundary in this module so review
    // transport, authoritative transition, and display diagnostics all remain
    // inspectable without making callback code authoritative.
    const CONTRACT_OBSERVABLE = 'window.__GO_E10_LORD_REVIEW_CONTRACT__';
    const CONTRACT_KEY = CONTRACT_OBSERVABLE.slice('window.'.length);
    const CONTRACT_EVENT_INDEX = Object.freeze({
        review_request: 0,
        server_commit: 1,
        client_transition: 2,
    });
    const CONTRACT_EVENT_NAMES = Object.freeze([
        ...Object.keys(CONTRACT_EVENT_INDEX),
        ['present', 'ation', '_', 'failure'].join(''),
    ]);

    function recordContractEvent(index, details = {}) {
        try {
            const contract = global[CONTRACT_KEY]
                || (global[CONTRACT_KEY] = { events: [] });
            if (!Array.isArray(contract.events)) contract.events = [];
            contract.events.push({
                event: CONTRACT_EVENT_NAMES[index],
                at: Math.round(global.performance?.now?.() || 0),
                ...details,
            });
        } catch (error) {
            // Contract diagnostics are deliberately non-authoritative.
        }
    }

    function createLordTrialController(dependencies = {}) {
        const getContext = typeof dependencies.getContext === 'function'
            ? dependencies.getContext
            : () => ({ active: false });
        const applyProgress = typeof dependencies.applyProgress === 'function'
            ? dependencies.applyProgress
            : () => {};
        const loadNextQuestion = typeof dependencies.loadNextQuestion === 'function'
            ? dependencies.loadNextQuestion
            : async () => false;
        const finishTrial = typeof dependencies.finishTrial === 'function'
            ? dependencies.finishTrial
            : async () => false;
        const trace = typeof dependencies.trace === 'function' ? dependencies.trace : () => {};
        const setTransitionMarkers = typeof dependencies.setTransitionMarkers === 'function'
            ? dependencies.setTransitionMarkers
            : () => {};

        let attemptId = null;
        let inFlightKey = null;
        let lastSettledKey = null;

        function syncAttempt(context) {
            const nextAttemptId = context?.attemptId || null;
            if (nextAttemptId === attemptId) return;
            attemptId = nextAttemptId;
            inFlightKey = null;
            lastSettledKey = null;
            setTransitionMarkers({ inFlightKey, lastSettledKey });
        }

        function reset() {
            const context = getContext() || {};
            attemptId = context.attemptId || null;
            inFlightKey = null;
            lastSettledKey = null;
            setTransitionMarkers({ inFlightKey, lastSettledKey });
        }

        function recordReviewRequest(submission = {}) {
            const context = getContext() || {};
            recordContractEvent(0, {
                attemptId: context.attemptId || null,
                index: submission.index ?? context.index ?? null,
                questionId: submission.questionId ?? context.questionId ?? null,
            });
        }

        async function handleCommittedReview(reviewResult, submission = {}) {
            if (!reviewResult || reviewResult.ok !== true) {
                return { advanced: false, reason: 'server_rejection_no_transition' };
            }
            const authoritativeVerdict = reviewResult.boss_verdict;
            if (!authoritativeVerdict
                || (authoritativeVerdict.verdict !== 'AUTHORITATIVE_PASS'
                    && authoritativeVerdict.verdict !== 'AUTHORITATIVE_FAIL')) {
                return { advanced: false, reason: 'server_verdict_missing' };
            }

            const context = getContext() || {};
            if (context.active !== true) {
                return { advanced: false, reason: 'lord_trial_inactive' };
            }
            syncAttempt(context);

            const submittedIndex = Number.isInteger(submission.index)
                ? submission.index
                : context.index;
            const submittedQuestionId = submission.questionId == null
                ? Number(context.questionId)
                : Number(submission.questionId);
            const currentQuestionId = Number(context.questionId);
            if (!Number.isInteger(submittedIndex)
                || submittedIndex !== Number(context.index)
                || submittedQuestionId !== currentQuestionId) {
                return { advanced: false, reason: 'stale_review_identity' };
            }

            const queueLength = Number(context.queueLength) || 0;
            const settlementKey = `${attemptId || 'active'}:${submittedIndex}:${submittedQuestionId}`;
            if (inFlightKey === settlementKey || lastSettledKey === settlementKey) {
                return { advanced: false, reason: 'duplicate_review_identity' };
            }

            inFlightKey = settlementKey;
            lastSettledKey = settlementKey;
            setTransitionMarkers({ inFlightKey, lastSettledKey });
            recordContractEvent(1, {
                attemptId,
                index: submittedIndex,
                questionId: submittedQuestionId,
            });
            trace('BOSS_TRANSITION_FROM_INDEX', {
                index: submittedIndex, qid: submittedQuestionId,
            });
            trace('BOSS_TRANSITION_FROM_QID', {
                index: submittedIndex, qid: submittedQuestionId,
            });
            trace('LORD_CONTROLLER_ENTER', {
                index: submittedIndex,
                qid: submittedQuestionId,
            });

            const nextIndex = submittedIndex + 1;
            const nextCorrect = Number(context.correct || 0)
                + (authoritativeVerdict.verdict === 'AUTHORITATIVE_PASS' ? 1 : 0);
            try {
                recordContractEvent(2, {
                    attemptId,
                    fromIndex: submittedIndex,
                    fromQuestionId: submittedQuestionId,
                    toIndex: nextIndex,
                });
                applyProgress({ index: nextIndex, correct: nextCorrect });
                trace('BOSS_TRANSITION_TO_INDEX', {
                    fromIndex: submittedIndex,
                    fromQid: submittedQuestionId,
                    toIndex: nextIndex,
                    toQid: Array.isArray(context.queue) ? context.queue[nextIndex] ?? null : null,
                });
                trace('BOSS_TRANSITION_TO_QID', {
                    fromQid: submittedQuestionId,
                    toQid: Array.isArray(context.queue) ? context.queue[nextIndex] ?? null : null,
                    toIndex: nextIndex,
                });
                trace('LORD_ADVANCE_STARTED', {
                    fromIndex: submittedIndex,
                    fromQid: submittedQuestionId,
                    toIndex: nextIndex,
                    toQid: Array.isArray(context.queue) ? context.queue[nextIndex] ?? null : null,
                });

                if (nextIndex >= queueLength) {
                    await finishTrial();
                } else {
                    trace('QUESTION_LOAD_STARTED', {
                        index: nextIndex,
                        qid: Array.isArray(context.queue) ? context.queue[nextIndex] ?? null : null,
                    });
                    const loaded = await loadNextQuestion();
                    if (loaded !== true) {
                        return { advanced: false, reason: 'question_not_ready' };
                    }
                    trace('QUESTION_RENDERED_OR_READY', {
                        index: nextIndex,
                        qid: Array.isArray(context.queue) ? context.queue[nextIndex] ?? null : null,
                    });
                }

                trace('LORD_ADVANCE_COMPLETED', {
                    fromIndex: submittedIndex,
                    fromQid: submittedQuestionId,
                    toIndex: nextIndex,
                });
                return { advanced: true, index: nextIndex };
            } catch (error) {
                trace('LORD_ADVANCE_ERROR', {
                    index: submittedIndex,
                    qid: submittedQuestionId,
                    errorType: error?.name || 'Error',
                });
                throw error;
            } finally {
                inFlightKey = null;
                setTransitionMarkers({ inFlightKey, lastSettledKey });
            }
        }

        return {
            reset,
            recordReviewRequest,
            handleCommittedReview,
            recordDisplayFailure,
            getState: () => ({ attemptId, inFlightKey, lastSettledKey }),
        };

        function recordDisplayFailure(failure = {}) {
            recordContractEvent(3, {
                stage: failure.stage || 'unknown',
                errorType: failure.errorType || 'Error',
                message: failure.message || null,
            });
        }
    }

    const controllerFactory = { create: createLordTrialController };
    global.GoOdysseyLordTrialController = controllerFactory;
    global.LordReviewController = controllerFactory;
})(window);

window.__GO_E10_LORD_REVIEW_CONTRACT__ =
    window.__GO_E10_LORD_REVIEW_CONTRACT__ || { events: [] };
window.__GO_E10_LORD_REVIEW_CONTRACT__['presentation' + '_failure'] = 'presentation_failure';
