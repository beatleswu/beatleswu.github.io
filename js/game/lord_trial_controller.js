/**
 * Lord Trial authoritative review coordinator.
 *
 * This module deliberately knows nothing about badges, XP, pets, loot, or
 * other presentation effects.  It accepts only a committed review result and
 * owns the client-side exactly-once handoff to the next Lord state.
 */
(function (global) {
    'use strict';

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

        async function handleCommittedReview(reviewResult, submission = {}) {
            if (!reviewResult || reviewResult.ok !== true) {
                return { advanced: false, reason: 'review_not_committed' };
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
            trace('BOSS_TRANSITION_FROM_INDEX', {
                index: submittedIndex, qid: submittedQuestionId, grade: submission.grade,
            });
            trace('BOSS_TRANSITION_FROM_QID', {
                index: submittedIndex, qid: submittedQuestionId, grade: submission.grade,
            });
            trace('LORD_CONTROLLER_ENTER', {
                index: submittedIndex,
                qid: submittedQuestionId,
            });

            const nextIndex = submittedIndex + 1;
            const nextCorrect = Number(context.correct || 0)
                + (Number(submission.grade) >= 3 ? 1 : 0);
            try {
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
            handleCommittedReview,
            getState: () => ({ attemptId, inFlightKey, lastSettledKey }),
        };
    }

    global.GoOdysseyLordTrialController = { create: createLordTrialController };
})(window);
