# W1-OWNER-POSTDEPLOY-ACCEPTANCE-CORRECTIVE-FINAL-001 — handoff at the BUILD_APP blocker

Status: **CODE COMPLETE, NOT ARTIFACT-READY.**
`GO_MERGE` and `GO_DEPLOY` are **NOT** requested. `PRODUCTION_MUTATION = NO`.
Stopped at the Owner's explicit instruction after the BUILD_APP gate blocked on a
pre-existing governance defect. No further `deploy/` governance file was touched.

## Candidate identity

| Field | Value |
| --- | --- |
| Worktree | `…/scratchpad/w1fix2` |
| Branch | `claude/w1-owner-postdeploy-acceptance-corrective-001` |
| HEAD | `5a8e8b47a81f3950f1a0e6a5f53bc94ff82c0003` |
| TREE | `380be4aa72291125735c77d58b1abef2974b752b` |
| Base | `e8531290f641d5daec145864993d10f5fea457d4` (= `origin/master`, the deployed commit) |
| Commits ahead | 5 |
| Working tree | clean, LF-only |

Control worktree at the same base, for A/B: `…/scratchpad/ctl2`.

## The three Owner-reproduced failures

### Issue A — Zone 1 has no questions

**Root cause.** In `loadQuestion()`, reselection after a PERMANENT map-battle
question failure was gated on `failure.quarantined` — the *result* of a
bookkeeping write, not the failure itself. `SRS.quarantineQuestion()` returns
false when the failure envelope's `question_id` is not an integer, so when that
write did not land the client skipped reselection entirely and fell through to
`_showSessionNoValidQuestion()`, which only sets a message and never builds a
board. One permanently-rejected record stranded the whole zone.

Verified against the real `srs.js` in a VM: integer and numeric-string ids
record, a UUID id does not. The comment originally also named "an envelope
without a usable revision/fingerprint", which is impossible —
`_isPermanentMapBattleQuestionFailure` requires one before it sets `permanent`.
Corrected.

**Fix.** Reselection is unconditional on a permanent failure. The failed
question is excluded for the session *before* reselection, through a shared
predicate every selector already consults. The `SRS.findNextAvailableQuestion`
fallback is filtered through that same predicate, since it knows only the
revision-bound quarantine and could otherwise hand back the excluded question in
exactly the failure mode this repairs. `enterAdventureZoneInPage` no longer
leaves a revealed-but-empty board on its no-target path, and both the empty-pool
and no-target cases emit a trace so the two are distinguishable from production.

`_sessionUnplayableQuestionIds` shares the SRS session quarantine's lifetime —
all five reset boundaries (logout, governed boss attempt, daily round,
challenge, fresh document) go through `_clearSessionQuestionExclusions()`.
Without this, a Map Battle prepare failure would have kept excluding that
question from Daily Training, **Premium Weekly Training** and Friend Challenge
for the rest of the page session.

### Issue B — Zone 3 story played as one movie

**Two independent defects.**

1. `showZone3EntrySafeFallback` had **no seen gate at all**. Zone 3
   short-circuits out of `showStageIntroCinematic` *above* the
   `adventureIntroSeen(zone)` check every other zone uses, so the opening
   autoplayed on every entry, including into a cleared zone. The text
   safe-fallback branch also never recorded "seen", so a gate alone would have
   re-armed on every entry.
2. `_maybeTriggerZone3BossReadyFilm` refused only a *second* `boss_ready` run,
   despite its own comment claiming it refused "any other intro-film run". An
   account already Lord-ready on first entry — the Owner's own account —
   satisfies the readiness condition the instant the entry cinematic starts, and
   `updateMapProgress` re-derives readiness on every bootstrap. **This is the
   mechanism behind "Shots 1–10 as one movie".** Both Zone 3 bootstrap triggers
   now bail out while the shared `#boss-cinematic` surface is in use.

Segmentation itself was already correct in data
(`FIRST_ENTRY` = SHOT01–05, `BOSS_READY` = SHOT06–07, `POST_CLEAR` = SHOT08–10)
and in `_zone3CinematicLocaleConfig`. What was missing was the lifecycle gate.

The seen gate mirrors the sibling contract: a map-node entry (`first_entry`) on
a seen account returns to the Zone Card; only the legacy "start training" CTA
enters gameplay directly. `manual_replay` bypasses the gate and writes nothing.

Segment B/C markers moved off browser `localStorage` onto the existing
server-side `account_cinematic_state` relation — a pure allowlist widening of
`E10_CINEMATIC_KEY_REGISTRY` (10 → 30 keys). **No DDL, no migration, no schema
change.** The mid-playback PENDING flag stays browser-local by design: it is
crash recovery for one playback, not a record of what the account has seen.

That move introduced a failure mode the base did not have — a localStorage write
cannot fail, a POST can — closed two ways:
`markAdventureCinematicPhaseSeen` records intent in the in-page snapshot before
the POST (the snapshot is overwritten wholesale from bootstrap on every load, so
the server stays the only authority), and `finishPostClearFilm` releases the
POST_CLEAR pending marker **only once the durable write landed**. Clearing it
unconditionally would have left `seen=false` *and* `pending=false`, permanently
disarming the resume path and losing the ending with no way to recover it.

### Issue C — duplicate map language control

`css/e9/reference_world_map.css` promoted the E10 session strip into a fixed
floating utility, surfacing a second goban brand mark plus an EN / 中 switcher on
the map. The strip is now `display: none` — not clipped, because a clipped
element is still focusable and still an active hit target. Dead inner-layout
rules removed from `css/e9/immersive_rpg.css`. Both stylesheets got a fresh
cache-bust revision (`v=20260910w1c1`) so returning browsers cannot keep serving
the superseded CSS.

## Evidence

### Regression, candidate vs pristine base

Both suites run with cleared pytest caches, same machine, same day.

| | failed | passed | errors |
| --- | --- | --- | --- |
| Control (`ctl2`, pristine e853) | 130 | 5604 | 9 |
| Candidate (`w1fix2`) | 129 | 5638 | 9 |

Set difference: the only delta is different parameter subsets of one test,
`tests/deployment/test_community_rewards_execution_control.py::test_generated_remote_shell_failures_are_durable_single_launch_and_fail_closed`
— 5 "new" in the candidate, 6 "fixed". Run in isolation it passes **117/117 in
both worktrees, twice each**. Load-sensitive flakiness present at the base.

**`CANDIDATE_INTRODUCED_FAILURE_COUNT = 0`.**

Note for whoever repeats this: many `art003_*` and `master_lane_*` guards fail on
*any* non-empty working tree. Verified by control probe — four inert comment
lines appended to `index.html`, `app.py` and the two CSS files in the pristine
tree reproduced 24 of 26 apparent "new" failures. 21 cleared once the work was
committed. Do not treat them as regressions without that check.

### Behavioral, by running the shipped code

`tests/e2e/run_w1_owner_zone3_story_segmentation.mjs` evaluates the real
`showZone3EntrySafeFallback`, `_continueZone3SafeEntry`,
`_maybeTriggerZone3BossReadyFilm` and `_resumeZone3PostClearIfPending` against
injected authority facts.

```
ZONE3_FIRST_ENTRY                        [PLAY:pre_play:5:first_entry]
ZONE3_SEGMENT_A_REPEAT_AUTOPLAY          NO
ZONE3_CLEARED_REENTRY_AUTOPLAY           NO
ZONE3_MANUAL_REPLAY_PLAYS                YES
ZONE3_MANUAL_REPLAY_WRITES_STATE         NO
ZONE3_SEGMENT_B_SPLICED_ONTO_SEGMENT_A   NO
ZONE3_SEGMENT_B_ONCE_WHEN_SURFACE_FREE   [SEGMENT_B]
ZONE3_SEGMENT_C_ONCE_ON_PENDING_RECOVERY [SEGMENT_C]
```

On the pristine base the same harness reports
`ZONE3_SEGMENT_A_REPEAT_AUTOPLAY = YES`, and a reduced control extracting only
`_maybeTriggerZone3BossReadyFilm` from the base reports
`ZONE3_SEGMENT_B_SPLICED_ONTO_SEGMENT_A = YES`.

Also green: `run_map_battle_incompatible_question_reselection` (Issue A subject),
`run_e10_generic_cinematic_replay`, `run_e10_replay_story_availability_contract`.
`playwright-core` is not installed in this environment, so the viewport runners
cannot execute — pre-existing, identical at the base.

### Issue C, real browser

Live page over a static server, `data-e10-visual-skin="immersive-rpg"` present,
real `.cg-nav[data-e10-session-strip="1"]` present, both stylesheets loaded at
the new revision. Desktop 1280×720, tablet 768×1024, mobile 375×812:

- `display: none`, rect 0×0, `offsetHeight` 0 — no reserved space
- `clip-path: none` — a removal, not an sr-only clip
- the goban link and the EN / 中 buttons exist in the DOM but **cannot be
  focused** (`document.activeElement` stays `BODY`) and have **zero client
  rects** — no invisible hit target
- nothing inside the strip is hit-tested at the map's top-right corner
- no horizontal overflow at any of the three widths
- `I18n.setLang('en')` retranslates and restores; `#e10-settings-language` hosts
  a live switcher → `PRIMARY_LANGUAGE_SWITCHING_STILL_WORKS = YES`

### Independent clean-context review

Ran adversarially against `git diff e8531290f`. **No violation of any Owner hard
constraint** — `js/game/cinematic_replay.js` byte-identical, no DDL, no payment
/ Turnstile / secret / env / shop / loadout change, `app.py` limited to the
registry constant. Six substantive findings, all acted on in `7111139af`; see
that commit message. Three were mine and behavioral, including the
`clearAdventurePostClearPending` race above.

## The blocker

`scripts/release/build-release-image.ps1` fails closed. Dry run passes
(source separation PASS, product worktree clean, `product_runtime_diff_from_product: 0`,
image tag would be `go-odyssey-app:7111139a`), but the BUILD_APP gate blocks.

`deploy/runtime-source-provenance.json` pins each governed runtime file's source
commit, SHA-256 and size. **Eight of its 98 entries were already stale at the
deployed base e853**: `index.html`, `i18n.js`, `js/e9/world_stage.js`, `sw.js`,
`srs.js`, `js/game/review_transport.js`, `sound.js`,
`guild_quest_answer_service.py`. The provenance test fails on the *first* drift
it meets and `index.html` sorts first, which is why the tracked BUILD_APP
baseline describes the known failure as an `index.html` drift — it has been
masking the other seven.

`index.html` has been re-recorded (commit `5a8e8b47a`), since this task did
legitimately change it. That entry now passes. The tests consequently trip on
`i18n.js` instead, with a different message and therefore a different signature,
so the gate reports `unrecognized_or_changed_failure`.

Gate state on the committed clean tree, from
`python -X utf8 -m pytest -q tests/deployment/ --junitxml <path>`
(two independent runs, identical signatures):

| nodeid | signature | tracked baseline |
| --- | --- | --- |
| `test_e9_css_inventory_exactly_matches_source_directory` | `67a57dde…` | matches, unchanged |
| `test_working_tree_matches_recorded_content_sha256` | `413bf327…` | baseline holds `85a8e961…` |
| `test_working_tree_matches_recorded_source_commit_blob` | `6bdf67c8…` | baseline holds `4ba15510…` |

Signatures are **run-context sensitive** — computing them from a narrower pytest
selection yields different values. Use the exact command above and the
evaluator's own `failure_signature()`.

`baseline_source_sha 0861d72cc…` is confirmed an ancestor of the candidate HEAD,
so the baseline's identity binding remains valid; only signatures would need to
move.

### Two routes were offered and both declined

- **Repair the seven.** Verified feasible and truthful: every one has a real
  commit in history whose blob byte-matches the current working file, and all
  six distinct commits are ancestors of `origin/master`, satisfying the
  manifest's ancestry rule. Both provenance tests would pass outright and **no
  baseline signature would need rewriting**.
- **Move the two baseline signatures**, with descriptions naming all seven
  genuinely drifted files.

Owner chose neither. This corrective therefore cannot produce an artifact until
the provenance manifest is repaired as separate, separately-authorized work.

## Not done

`IMAGE_BUILD`, `PACKAGE_NONINTERACTIVE`, `PACKAGE_ARTIFACT_READY`,
`STATIC_PRELIVE_CLOSURE`, `ROLLBACK_PATH_SAFE`, `FINAL_CONSISTENCY_REVIEW`.

## Separate pre-existing defects found in passing

1. **A test rewrites a tracked production asset.**
   `tests/test_w1_03_journey_zone3_final_audio_production.py::test_final_generation_is_resumable_and_does_not_regenerate_valid_assets`
   imports and runs the real generator at `tools/e10_zone3_audio/generate_zone3_audio.py`,
   which rewrites `assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json`
   in the working tree — **silently reverting every owner-approved
   `PRONUNCIATION_OVERRIDE` block to `null`**. Any full test run leaves the repo
   dirty, which then breaks the release tooling's clean-tree check.
2. **Zones 1 and 2 carry the identical cinematic-splice defect** fixed here for
   Zone 3. Deliberately not touched — the task book forbade unrelated Adventure
   redesign and only Zone 3 was reported. One-line guard each.
3. **The provenance manifest is broadly stale** (8 of 98 entries at e853), and
   the BUILD_APP baseline's description has been masking seven of them.
4. **CRLF hazard.** Windows-side tooling that rewrites a tracked text file
   desynchronises the working tree from the committed blob. `.gitattributes`
   normalises on commit so the shipped bytes stay correct, but the release image
   is built **from the working tree**, and only one deployment test would catch
   it. This bit this task and was corrected.

## Reproduction

```
cd <w1fix2>
python -m pytest tests -q -p no:randomly            # full suite
node tests/e2e/run_w1_owner_zone3_story_segmentation.mjs
python -m pytest tests/test_w1_owner_zone1_permanent_failure_reselection.py \
                tests/test_w1_owner_zone3_story_segmentation.py \
                tests/test_w1_owner_map_duplicate_language_control_removed.py -q -p no:randomly
python -X utf8 -m pytest -q tests/deployment/ --junitxml <path>   # BUILD_APP gate input
```
