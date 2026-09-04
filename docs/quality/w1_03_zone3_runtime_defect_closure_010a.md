# W1-03 Zone 3 runtime defect closure 010A

This is the quality record for the three real-Chromium defects handed off by
`W1_05_QUALITY_ZONE3_BROWSER_DEBT_AND_FINAL_ACCEPTANCE_HARNESS_005`.  The
amendment is limited to the authorized E9/Zone 3 seams and does not perform
final integrated-candidate, physical-device, merge, deploy, or Production
acceptance.

## Exact reproductions and closure

The baseline was freshly reproduced from quality authority
`ae429f0b47aee91ef41fa5e87e4c13d5e9aa8e42` before the runtime edits.

| Debt | Exact baseline observation | Closure evidence |
| --- | --- | --- |
| E9 layout | 16 bounded on/off states; all 8 ON states reported the duplicate Beginner generic CTA and locked-zone actionability failure. | `run_e9_layout_contract.mjs`: 16/16 states pass; locked tile remains labeled/focusable, pointer/Enter/Space activation is canceled/non-navigating, and the surface-owned CTA is singular. |
| E9 fetch | First activation requested `/api/srs/due` twice and `/api/mistakes/stats` twice. | `run_e9_fetch_contract.mjs --only single_activation_request_counts`: 1 bounded case pass; both endpoints are 1 request, owned by the shared ActivityState path. |
| Replay final return | First replay dismissal left `boss-cinematic show intro-film`; a later dismissal could close it. | `run_e10_replay_story_button_real_click.mjs`: desktop, iPad landscape, iPad portrait, and mobile portrait each pass two dismissals, exactly three canonical segment skips per return, with zero orphan replay timers/audio/effects. |

## Root causes and scope

* `js/e9/world_stage.js` configured a generic details CTA in parallel with
  the surface-specific Beginner CTA and allowed pointer activation to enter
  the first-entry dispatch path for locked/unenterable tiles.  The fix hides
  and detaches the duplicate owner for the completed Beginner tile and makes
  locked pointer and keyboard paths inspectable but non-navigating.  It does
  not change unlock authority or progression.
* `index.html` called legacy `SRS.init` and fetched mistake statistics while
  `js/e9/right_cards.js` used the E9 ActivityState adapter for the same data.
  `srs.js`, `index.html`, and `js/e9/adapters/activity_state.js` now share
  one request/in-flight/cache owner for the E9 refresh path.  Invalidation
  clears the shared results, so freshness is preserved.
* A cleared-zone selection queued first-entry playback behind the replay
  click.  The delayed first-entry start could overwrite the presentation-only
  replay.  `js/e9/world_stage.js` no longer dispatches first-entry playback for
  an authoritative completed zone, and `index.html` clears the replay
  continuation before hiding the overlay and returning to the Zone Card.

## Boundaries and debt

The existing full E9 fetch contract still reaches its separate historical
`critical_fallback_restores_legacy_ambient` expectation (`bootstrap` expected
0, observed 1) after the target first-activation case passes.  This is kept
as `HARNESS_DEBT / STALE_EXPECTATION`; it is not used as evidence against the
closed duplicate-fetch defect.  The established `TEST_STALE`, `HARNESS_DEBT`,
and `HARNESS_DEBT / TEST_ISOLATION_SHARED_STATE` classifications remain
recorded in the Wave 1 matrices.

Browser viewport results are emulation only.  Full human perceptual
acceptance, physical iPad landscape/portrait acceptance, and physical iPhone
acceptance remain later Owner/final-quality gates.

## Verification commands

```text
pytest -q tests/test_w1_03_zone3_runtime_defect_closure.py tests/test_w1_05_quality_wave1_acceptance_harness.py tests/test_w1_05_quality_zone3_vertical_slice_acceptance_harness.py tests/test_e10_generic_cinematic_replay.py tests/test_e10_replay_story_cross_surface_hotfix.py tests/test_e10_replay_story_button_hotfix.py tests/test_e9_1b_real_data_contract.py
node tests/e2e/run_w1_05_zone3_final_browser_acceptance_unit_tests.mjs
node tests/e2e/run_e9_acceptance_helpers_unit_tests.mjs
node tests/e2e/run_e9_acceptance_error_monitor_contract.mjs
node tests/e2e/run_e9_layout_contract.mjs --out <bounded-output> --screens <bounded-screens>
node tests/e2e/run_e9_fetch_contract.mjs --only single_activation_request_counts --out <bounded-output>
node tests/e2e/run_e10_replay_story_button_real_click.mjs --viewport desktop
node tests/e2e/run_e10_replay_story_button_real_click.mjs --viewport ipad-landscape
node tests/e2e/run_e10_replay_story_button_real_click.mjs --viewport ipad-portrait
node tests/e2e/run_e10_replay_story_button_real_click.mjs --viewport mobile
```

No skips, xfails, arbitrary sleeps, timeout inflation, or assertion
weakening were added to the amendment gate.  `app.py`, progression/unlock
authority, source art, source audio, database/schema, payment, and Production
configuration are unchanged.
