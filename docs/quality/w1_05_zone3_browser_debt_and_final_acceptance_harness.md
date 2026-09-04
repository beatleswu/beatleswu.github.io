# W1_05 Zone 3 browser debt and final acceptance harness

Task: `W1_05_QUALITY_ZONE3_BROWSER_DEBT_AND_FINAL_ACCEPTANCE_HARNESS_005`

This is a bounded quality-engineering pass before the final integrated
candidate exists. It does not perform final candidate acceptance, physical
device acceptance, deployment, production mutation, or shared Journey edits.

## Exact baseline reproduction

The three known debts were run from the exact source baseline
`6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf` before the harness changes.

| Test ID | Runner | Viewport | Locale | Expected | Actual | Reproducible |
| --- | --- | --- | --- | --- | --- | --- |
| E9-LAYOUT | `tests/e2e/run_e9_layout_contract.mjs --out w1_05_baseline_e9_layout.json` | 360x800, 390x844, 430x932, 768x1024, 1024x768, 1366x768, 1440x900, 1920x1080 | default app locale; no locale override | all on/off layout contract assertions pass | every ON viewport reports the duplicate Beginner generic CTA visible and the locked-zone contract failure; 16 assertion failures total | YES |
| E9-FETCH | `tests/e2e/run_e9_fetch_contract.mjs --out w1_05_baseline_e9_fetch.json` | fixture browser | default app locale; language-switch subcase is also defined | one `/api/srs/due` and one `/api/mistakes/stats` request per activation | each endpoint was requested twice; 2 assertion failures | YES |
| REPLAY-FINAL-RETURN | `tests/e2e/run_e10_replay_story_button_real_click.mjs --viewport tablet` | tablet | default app locale; authenticated fixture/account | first replay dismissal returns to the Zone Card and repeat remains safe | first `finish_and_return.returned_to_zone_card=false`; overlay remained `boss-cinematic show intro-film`; later repeat closed it | YES after runner race removal |

The initial replay invocation also exposed a cold-mount race in the existing
runner (`zone tile not found: k26_30`). That quality-owned harness defect was
fixed by waiting for the authenticated Zone tile before each real click. The
remaining first-return failure reproduced twice after that fix, so it is not
classified as harness debt.

## Classification and handoff

All three remaining debts are classified as `PRODUCT_RUNTIME_DEFECT` because
they reproduce in a real Chromium session against the exact baseline and have
direct runtime evidence:

1. **E9 layout:** `js/e9/world_stage.js`,
   `renderSelectedZone`/`configureAdventureButton` keeps the generic details
   CTA visible alongside the surface-specific affordance; the real layout
   probe also observed `aria-disabled=null` for the locked tile. The minimal
   integration-writer scope is to reconcile the responsive CTA ownership and
   ensure locked-zone selection/click semantics remain inspectable but
   non-actionable, including the click handler guard.
2. **E9 fetch:** `index.html`, the authenticated E9 `window.onload`
   initialization, calls `SRS.init` and `/api/mistakes/stats` while
   `js/e9/right_cards.js` initialization independently calls
   `loadSrsDue`/`loadWeakness`. The minimal scope is one shared read path per
   activation, without changing server authority.
3. **Replay final return:** `index.html`, `skipIntroFilm`,
   `_playZoneCinematicSequence`, and `_finishZoneCinematicReplay`. The first
   presentation-only replay dismissal leaves the overlay in
   `boss-cinematic show intro-film`; a subsequent replay can close it. The
   minimal scope is deterministic one-dismissal termination and Zone Card
   return for the first presentation-only replay, with no reward/progression
   writes.

These runtime changes are intentionally left to the single integration
writer. Historical classifications `TEST_STALE`, `HARNESS_DEBT`, and
`HARNESS_DEBT / TEST_ISOLATION_SHARED_STATE` remain preserved and were not
used to mask these reproductions.

## Prepared final matrix

`tests/e2e/run_w1_05_zone3_final_browser_acceptance.mjs` defines exactly 40
bounded cases:

| Scenarios (10) | Emulated viewports (4) |
| --- | --- |
| zh-TW first entry; en-US first entry; locale switch; replay; reduced motion; global mute; cinematic lifecycle; route exit cleanup; presentation failure no-op; final-state return | desktop 1920x1080; iPad landscape 1180x820; iPad portrait 820x1180; mobile portrait 390x844 |

The runner has no arbitrary sleeps, skip, xfail, or broad timeout path. It
requires an explicit candidate ID and isolated credentials before `--run`.
The negative controls are: production host/IP rejection, physical-device
claim rejection, missing-candidate precondition blocking, and a 404
presentation-asset path that must remain a no-op with no domain write or
route change. The actual final integrated candidate run is not claimed here.

The accepted Owner art responsive contract remains recorded as `10/10` rows;
the two custom positions remain `SHOT09=58% 50%` and `SHOT10=58% 50%`. No
Owner source art is changed by this harness.

## Bounded verification

The structural matrix description and unit contract are executable without a
server. The pre-integration acceptance runner is ready to execute once the
integration writer supplies a candidate satisfying the preconditions. This
document records automation readiness only; full human perceptual and
physical iPad/iPhone acceptance remain future Owner/final-quality gates.
