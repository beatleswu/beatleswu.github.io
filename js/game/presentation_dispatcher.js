/**
 * Observer-only review presentation dispatch.
 *
 * This module owns no transport, progression, or retry authority.  It
 * consumes an already-committed result and isolates presentation failures.
 */
(function (global) {
    'use strict';

    function normalizeDependencies(dependencies) {
        const deps = dependencies || {};
        if (!deps.badge || typeof deps.badge !== 'object') return deps;

        let badgeDefinitions = [];
        const badgeState = typeof deps.badge.state === 'function'
            ? deps.badge.state
            : () => [];
        const badgeSeen = typeof deps.badge.seen === 'function'
            ? deps.badge.seen
            : null;

        return {
            mergeBadges: ids => {
                const state = badgeState(ids);
                badgeDefinitions = Array.isArray(state) ? state : [];
            },
            earned: {},
            getBadgeDef: bid => badgeDefinitions.find(definition => definition?.id === bid) || null,
            onBadge: typeof deps.badge.show === 'function' ? deps.badge.show : null,
            onMonster: typeof deps.monster === 'function' ? deps.monster : null,
            onQuest: typeof deps.quest === 'function' ? deps.quest : null,
            fetch: badgeSeen
                ? (url, options) => {
                    if (url === '/api/badges/seen') {
                        const payload = JSON.parse(options?.body || '{}');
                        return badgeSeen(payload.ids || []);
                    }
                    return Promise.resolve({ ok: true, json: async () => ({}) });
                }
                : null,
            now: () => new Date().toISOString(),
        };
    }

    function create(dependencies) {
        const deps = dependencies || {};
        const mergeBadges = typeof deps.mergeBadges === 'function'
            ? deps.mergeBadges
            : () => {};
        const earned = deps.earned || {};
        const getBadgeDef = typeof deps.getBadgeDef === 'function'
            ? deps.getBadgeDef
            : () => null;
        const onBadge = typeof deps.onBadge === 'function' ? deps.onBadge : null;
        const onMonster = typeof deps.onMonster === 'function' ? deps.onMonster : null;
        const onQuest = typeof deps.onQuest === 'function' ? deps.onQuest : null;
        const fetchImpl = typeof deps.fetch === 'function'
            ? deps.fetch
            : (typeof global.fetch === 'function' ? global.fetch.bind(global) : null);
        const now = typeof deps.now === 'function'
            ? deps.now
            : () => new Date().toISOString();

        function dispatchReviewPresentation(data, { onError } = {}) {
            if (!data || data.ok !== true) {
                return { ok: false, skipped: true, failures: [] };
            }

            const failures = [];
            const reportFailure = (stage, error) => {
                const failure = {
                    stage,
                    errorType: error?.name || 'Error',
                    message: error?.message || String(error || ''),
                };
                failures.push(failure);
                if (typeof onError === 'function') {
                    try { onError(failure); } catch (observerError) { /* diagnostic only */ }
                }
            };
            const dispatch = (stage, callback, payload) => {
                if (typeof callback !== 'function') return;
                try { callback(payload); } catch (error) { reportFailure(stage, error); }
            };

            if (data.new_badges && data.new_badges.length) {
                try {
                    mergeBadges(data.new_badges);
                    data.new_badges.forEach(bid => {
                        earned[bid] = now();
                        const def = getBadgeDef(bid);
                        if (def) dispatch('badge', onBadge, def);
                    });
                } catch (error) {
                    reportFailure('badge_state', error);
                }
                try {
                    if (fetchImpl) {
                        const seenRequest = fetchImpl('/api/badges/seen', {
                            credentials: 'include',
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ ids: data.new_badges })
                        });
                        if (seenRequest && typeof seenRequest.catch === 'function') {
                            seenRequest.catch(error => reportFailure('badge_seen', error));
                        }
                    }
                } catch (error) {
                    reportFailure('badge_seen', error);
                }
            }

            if (data.monster) dispatch('monster', onMonster, data.monster);
            if (data.quest_updates) dispatch('quest', onQuest, data.quest_updates);
            return { ok: failures.length === 0, skipped: false, failures };
        }

        return { dispatchReviewPresentation };
    }

    function dispatch(data, dependencies) {
        const deps = dependencies || {};
        return create(normalizeDependencies(deps)).dispatchReviewPresentation(data, {
            onError: deps.onError,
        });
    }

    const api = { create, dispatch };
    global.GoOdysseyPresentationDispatcher = api;
    global.PresentationDispatcher = api;
})(typeof window !== 'undefined' ? window : globalThis);
