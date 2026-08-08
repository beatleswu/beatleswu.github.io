# E10 Final Screenplay — Repo Mapping Decision Closure v1

Status: `OWNER_REVIEW_ACCEPTED`. This document records only the final, accepted state of the
repo-mapping process. Earlier drafts of individual findings are not reproduced — see
`SUPERSEDED_FINDINGS` at the end for what changed and why.

## Accepted findings

**Scope covered.** 10 zones, 99 shots, mapped against production `index.html`/`app.py` at worktree HEAD
`539b1cdb8216a3f659df1d962233989e116e1ea0`. No repo file was modified during mapping. `git status` clean
throughout.

**Art.** Zero repo-secured candidate art for any zone except Zone 1 Shot 1
(`docs/planning/nv1c1_candidates_zone1/e10_z1_shot01_candidate_master.png`). Zones 2–10: `NEW_ART_REQUIRED`
for every shot, no exceptions found.

**Audio.** Three non-overlapping, mutually contradictory audio efforts exist (legacy 90-file narration,
an unimplemented Voice:0 MVP spec, this session's own full-narration Zone 1 prototype). Zero zone-level
BGM/ambience/SFX stems exist for Zones 2–10.

**Runtime.** A real, working single-cycle intro-film engine exists (`activate()`,
[index.html:13567](index.html:13567)) and already handles: silent-hold fallback for missing dialogue
(`computeShotHoldMs`/`finishAudioSilently`), single explicit skip (`skipIntroFilm`), replay
(`replayIntroFilm`), per-zone localStorage seen-tracking (`adventureIntroSeen`). It has **no** `MID_PLAY`
(pause/resume) capability anywhere.

**Adventure combat framing.** `ADVENTURE_COMBAT_FRAMING_RUNTIME_FIX: NOT_REQUIRED`. The taunt/hurt/die
monster-speech system does not run on the Adventure Zone gameplay path at all — confirmed via the exact
gating condition (`_isAdventureZonePractice()`, [index.html:8363](index.html:8363)) and the real
boss-completion UI's own strings ("領主通關"/"領主逃走了", [i18n.js:1585-1594](i18n.js:1585)), which are
already neutral. See integration contract §7 for the full evidence chain.

**Relic / Heartstone persistence.** `STATE_INTEGRATION_REQUIRED: CLOSED — NO NEW PERSISTENCE NEEDED`.
Both relic chains and the full Heartstone lifecycle derive entirely from existing per-user, per-zone
completion records (`adventure_boss_progress.cleared`, `app.py:3185-3198`; `adventure_zone_unlocks.source`,
`app.py:3201-3208`, for placement-skip detection). `JOURNEY_MEMORY_ELIGIBILITY` rule:

```
Wooden Sword       <- Zone 1 cleared
Stone Shard        <- Zone 3 cleared
Black/White Fruit  <- Zone 4 cleared
Dragon Scale       <- Zone 6 cleared
Crystal callback   <- Zone 2 cleared
Ore continuity     <- Zone 5 cleared
Heartstone CARRIED <- Zone 7 cleared, until Zone 10 completion
Heartstone ORDINARY_STONE <- Zone 10 cleared
```

Conservative by design: a player who briefly saw a relic's pickup shot but never cleared that zone (e.g.
via a later placement-skip) will not have that memory rendered at Zone 7/10. This never fabricates a
journey the player didn't complete; it may under-render one, which is the accepted, safer failure
direction. No schema, table, or migration required.

**Optional Guardians.** `CLOSED`. Ownership ledger is `pet_collection` (`app.py:3660-3665`), queried via
`_pet_owned_keys()` (`app.py:2321-2323`) — distinct from the static `PET_CATALOG` and from `user_pets`
(single currently-equipped companion only). Full entity mapping in the integration contract §11.

**Zone 6 `MID_PLAY`.** The one remaining known high-risk engineering requirement.
`ZONE6_MID_PLAY_OWNER_DECISION = TRUE_PAUSE_RESUME_REQUIRED`, approved as a future dedicated sprint, not a
story blocker and not authorized for implementation now.

**Content gates, both open:**
- `GO_LOGIC_GATE` — Zone 10's half-point board state needs real design/verification before art is made.
- `ANNA_AB_GATE` — 「……半目。」 (Zone 10 Shot 8) stays A/B-test-only pending an actual audio prototype.

## Final status

```
E10_FINAL_SCREENPLAY_REPO_MAPPING: OWNER_REVIEW_ACCEPTED
ZONES: 10/10
SHOTS: 99/99
BLOCKERS: 0 story blockers. 1 known future high-risk engineering requirement (ZONE6_TRUE_MID_PLAY_PAUSE_RESUME).
CONTENT_GATES: GO_LOGIC_GATE (open), ANNA_HALF_POINT_AB_TEST (open)
STATE_INTEGRATION: CLOSED — no new persistence required
ADVENTURE_COMBAT_FRAMING_RUNTIME_FIX: NOT_REQUIRED
```

---

## Superseded findings

Recorded for history only. None of the items below are active requirements. Do not reintroduce them.

| Superseded finding | What replaced it |
|---|---|
| "5 zones affected by a `monsterSpeakDie()`/taunt/hurt combat-framing conflict" | The conflict does not exist on the Adventure Zone gameplay path at all — see "Adventure combat framing" above. |
| "One shared non-lethal resolution-presentation runtime system should be built" | Not required. Existing neutral boss-clear overlay is kept; each zone's resolution is expressed by its own future `POST_CLEAR` cinematic content, authored as static zone metadata if ever needed — not a runtime build. |
| "Zone 8's Chaos Lord dies (a death that must merely avoid combat-victory framing)" | Chaos Lord is not killed by the Hero. Dissolution follows the underlying distortion stabilizing. `NON_LETHAL_RESOLUTION_REQUIRED`, not `NON_COMBAT_TRIAL_PRESENTATION_REQUIRED`. |
| "Relic-state persistence needs ~5 new per-user boolean/enum fields" | Zero new fields needed — fully derivable from `adventure_boss_progress.cleared`. |
| "Heartstone state machine includes a `thrown` state" | No `thrown` state exists in the corrected lifecycle. Heartstone remains `CARRIED` through Zone 9; Zone 9 does not consume or throw it. |
| "Zone 9 Shot 11 (recovered storyboard) should be protected exactly as-is, including the full five-relic narration and 「一色的棋盤，是死的」" | The protected line relocates to **Zone 9 Shot 10**. Shot 11 is redefined as the failed-convergence visual with no five-relic narration. The relic-memory payoff belongs to **Zone 10 Shots 7–8**. |
| "The directional-object repetition (crystal fragment / ore shard / star-map) is an unresolved Owner Decision" | Resolved by the Final Screenplay's actual behavior — each instance is distinct (subtle reaction / spoken coordinates / visual node-matching), not a repeated magical-pointer device. No longer tracked as an open decision. |
| "Zone 2's crystal fragment is one of the four relics Heartstone fuses at Zone 7, and the Wooden Sword is omitted" | Corrected — the Wooden Sword (Zone 1) is a Hero Journey Relic; the Zone 2 crystal belongs to the separate Corruption Evidence chain and never enters Heartstone's fusion. |
| "Relic state and combat resolution-style should share one per-user story-state table, since both are read per zone" | Rejected. Relic state is per-user progress; resolution style is fixed content metadata. They do not belong in the same table merely because both are zone-keyed reads. |
