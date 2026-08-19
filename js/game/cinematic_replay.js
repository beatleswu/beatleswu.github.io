(function (global) {
    'use strict';

    // Zone-agnostic cinematic replay model (E10_ZONE_GENERIC_CINEMATIC_REPLAY_001).
    //
    // Owner product rule this encodes:
    //
    //   A zone's story cinematics may be replayed once the player has
    //   legitimately unlocked them; replay is presentation only and may never
    //   repeat progression, reward, unlock, or player-position mutation.
    //
    // This module owns exactly two decisions and nothing else:
    //
    //   1. SEGMENT ORDER  -- the canonical lifecycle order of a zone's
    //      cinematic segments.
    //   2. SEGMENT UNLOCK -- whether the player has legitimately unlocked a
    //      given segment, decided from authoritative zone state supplied by
    //      the caller.
    //
    // It deliberately has no DOM, no fetch, no storage, and no playback
    // authority, so it can be exercised directly and can never itself mutate
    // progression. Callers keep the presentation and the server remains the
    // only authority for cleared/boss-ready/unlock state -- this module reads
    // that state, it never computes or asserts it.
    //
    // Nothing here is keyed on a zone identity. A zone participates purely by
    // declaring which segments it has; a zone that declares none produces an
    // empty sequence. Zones 3-10 therefore need no code change here when they
    // acquire cinematics -- they only need to declare their segments.

    // Canonical lifecycle order. A zone declares any subset, in any order, and
    // is always replayed in this order. Extending a zone's lifecycle with a
    // new phase is an addition to this list, never a per-zone branch.
    var SEGMENT_ORDER = [
        'pre_play',
        'mid_play',
        'boss_ready',
        'post_clear',
        'post_clear_hook',
        'ending',
    ];

    // The Owner's three-act naming maps onto the internal phase strings the
    // existing sequencer already uses. 'pre_play' is FIRST_ENTRY's historical
    // spelling and is kept verbatim to avoid an unrelated rename churn.
    var LIFECYCLE_PHASE = {
        pre_play: 'FIRST_ENTRY',
        mid_play: 'MID_PLAY',
        boss_ready: 'BOSS_READY',
        post_clear: 'POST_CLEAR',
        post_clear_hook: 'POST_CLEAR_HOOK',
        ending: 'ENDING',
    };

    // Segments at or after POST_CLEAR are the "post-victory" tail: the
    // segment(s) a Lord Trial success presents. Derived from SEGMENT_ORDER so
    // a future phase inserted before POST_CLEAR does not silently join the
    // victory tail, and one appended after it does.
    var POST_VICTORY_FROM = 'post_clear';

    function indexOfPhase(phase) {
        return SEGMENT_ORDER.indexOf(phase);
    }

    function isPlainObject(value) {
        return !!value && typeof value === 'object' && !Array.isArray(value);
    }

    function callGuarded(fn, arg, fallback) {
        if (typeof fn !== 'function') return fallback;
        try {
            return fn(arg);
        } catch (error) {
            return fallback;
        }
    }

    // A declared segment is either a bare timeline array or a descriptor
    // object carrying the timeline plus optional per-segment overrides:
    //
    //   { timeline: [...], unlock: fn(zone, state), replayEligible: false }
    //
    // The object form exists so a future zone can express an unlock condition
    // its phase default does not cover, without a zone-specific branch here.
    function normalizeDeclaration(declaration) {
        if (Array.isArray(declaration)) {
            return { timeline: declaration, unlock: null, replayEligible: true };
        }
        if (isPlainObject(declaration)) {
            var timeline = Array.isArray(declaration.timeline) ? declaration.timeline : [];
            return {
                timeline: timeline,
                unlock: typeof declaration.unlock === 'function' ? declaration.unlock : null,
                replayEligible: declaration.replayEligible !== false,
            };
        }
        return null;
    }

    function create(dependencies) {
        var deps = dependencies && typeof dependencies === 'object' ? dependencies : {};

        // Authoritative state reads. Each is a caller-supplied predicate over
        // the zone record the server already returned; this module never
        // derives any of them.
        function isCleared(zone) {
            return callGuarded(deps.isCleared, zone, false) === true;
        }

        function isBossReady(zone) {
            return callGuarded(deps.isBossReady, zone, false) === true;
        }

        function canEnter(zone) {
            return callGuarded(deps.canEnter, zone, false) === true;
        }

        function hasSeen(zone, phase) {
            if (typeof deps.hasSeen !== 'function') return false;
            try {
                return deps.hasSeen(zone, phase) === true;
            } catch (error) {
                return false;
            }
        }

        function declarationsFor(zone) {
            var declared = callGuarded(deps.getSegments, zone, null);
            return isPlainObject(declared) ? declared : {};
        }

        // Default unlock per lifecycle phase.
        //
        // The load-bearing rule is that reaching a later phase proves the
        // earlier ones were passed: a cleared player has necessarily been
        // boss-ready, so BOSS_READY stays unlocked forever even though
        // isBossReady() goes false once the zone is cleared. Without that,
        // clearing a zone would silently revoke a segment the player had
        // already legitimately earned.
        function defaultUnlock(phase, zone) {
            if (phase === 'pre_play') {
                return canEnter(zone) || isBossReady(zone) || isCleared(zone) || hasSeen(zone, phase);
            }
            if (phase === 'mid_play') {
                return isCleared(zone) || isBossReady(zone) || hasSeen(zone, phase);
            }
            if (phase === 'boss_ready') {
                return isCleared(zone) || isBossReady(zone) || hasSeen(zone, phase);
            }
            // POST_CLEAR and everything after it require an authoritative
            // clear. Never a client-declared "I cleared it", never a seen
            // marker -- a seen marker would let a wiped/rolled-back clear keep
            // the ending unlocked.
            return isCleared(zone);
        }

        function segmentsForZone(zone) {
            var declared = declarationsFor(zone);
            var state = {
                cleared: isCleared(zone),
                bossReady: isBossReady(zone),
                canEnter: canEnter(zone),
            };
            var segments = [];
            for (var index = 0; index < SEGMENT_ORDER.length; index += 1) {
                var phase = SEGMENT_ORDER[index];
                var normalized = normalizeDeclaration(declared[phase]);
                if (!normalized || !normalized.timeline.length) continue;
                var unlocked = normalized.unlock
                    ? callGuarded(function (target) {
                        return normalized.unlock(target, state);
                    }, zone, false) === true
                    : defaultUnlock(phase, zone);
                segments.push({
                    id: phase,
                    phase: phase,
                    lifecycle: LIFECYCLE_PHASE[phase] || phase.toUpperCase(),
                    order: index,
                    timeline: normalized.timeline,
                    unlocked: unlocked === true,
                    replayEligible: normalized.replayEligible !== false,
                    seen: hasSeen(zone, phase),
                });
            }
            return segments;
        }

        function unlockedSegments(zone) {
            return segmentsForZone(zone).filter(function (segment) {
                return segment.unlocked;
            });
        }

        // Replay Story: every legitimately unlocked, replay-eligible segment,
        // in canonical lifecycle order.
        function replaySequence(zone) {
            return unlockedSegments(zone).filter(function (segment) {
                return segment.replayEligible;
            });
        }

        // Lord Trial success: the post-victory tail only. On a first clear and
        // on a replay this returns the same segments -- the difference between
        // the two lives entirely in the caller's completion handling (state
        // writes on first clear, nothing on replay), never in what is shown.
        function postVictorySequence(zone) {
            var from = indexOfPhase(POST_VICTORY_FROM);
            return replaySequence(zone).filter(function (segment) {
                return segment.order >= from;
            });
        }

        function hasReplayableStory(zone) {
            return replaySequence(zone).length > 0;
        }

        return Object.freeze({
            segmentsForZone: segmentsForZone,
            unlockedSegments: unlockedSegments,
            replaySequence: replaySequence,
            postVictorySequence: postVictorySequence,
            hasReplayableStory: hasReplayableStory,
        });
    }

    var api = Object.freeze({
        create: create,
        SEGMENT_ORDER: Object.freeze(SEGMENT_ORDER.slice()),
        LIFECYCLE_PHASE: Object.freeze(Object.assign({}, LIFECYCLE_PHASE)),
        POST_VICTORY_FROM: POST_VICTORY_FROM,
    });

    global.GoOdysseyCinematicReplay = api;
})(typeof window !== 'undefined' ? window : this);
