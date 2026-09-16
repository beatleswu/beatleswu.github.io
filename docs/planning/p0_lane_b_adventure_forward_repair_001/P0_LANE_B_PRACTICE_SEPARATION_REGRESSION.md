# P0 Lane B — Practice Separation Regression

## Defect contract

The prior defective behavior was:

```text
Adventure question
  → Map Battle disabled/not eligible/init failure
  → client leaves a board answerable
  → _incident002ServerPracticeFlow() becomes true
  → Practice evidence, zero Adventure progress
```

That contract is rejected. The repaired contract is:

```text
Adventure question + Map Battle unavailable
  → blocked/unavailable UI
  → no Practice transport
  → no zero-credit answer path
```

## Matrix

| Case | `_mapBattleV1Mode` representation | `practice` transport | metadata context | expected UI |
|---|---|---:|---|---|
| Adventure + disabled | `disabled` | `false` | `adventure_unavailable` | unavailable/fail closed |
| Adventure + initialization pending | `pending` | `false` | `adventure_unavailable` | no answer submission |
| Adventure + mode not eligible | `blocked` after server error | `false` | `adventure_unavailable` | unavailable/fail closed |
| Adventure + runtime/init failure | `blocked` | `false` | `adventure_unavailable` | unavailable/fail closed |
| Adventure + active valid battle | `active` + active state | `false` | not used for success settlement | Map Battle transport |
| Real Practice | no Adventure pool | `true` when Practice transport is available | `practice` | existing Practice UI |

The Node runner `tests/e2e/run_p0_lane_b_adventure_forward_repair.mjs`
executes all rows, including a separate not-eligible and runtime-failure case
that share the final blocked lifecycle but preserve their source reason in the
production code path.

## Construction-level protections

1. `_currentReviewMetadata()` computes `adventureUnavailable` directly from
   the Adventure question pool and Map Battle active state; it does not rely on
   a single submit caller to rewrite the result.
2. `_incident002ServerPracticeFlow()` explicitly requires
   `!_isAdventureZonePractice()`.
3. `submitSRS()` blocks before evaluating the Practice transport.
4. `_loadQuestionImplementation()` blocks before `_syncE10BattleActions(true)`
   and board setup when Map Battle did not become active.
5. Provider errors for disabled and not-eligible modes, missing adapter, and
   generic runtime errors enter `_blockAdventureProgression()`.

## Consumer safety

`adventure_unavailable` is deliberately not an authoritative marker:

- success progression continues to require server-created `mbv1:` evidence;
- `app.py` public review dispatch preserves `ProgressCreditPolicy.NEVER` for
  non-internal requests;
- Map Battle readers select `source_context LIKE 'mbv1:%'`, so the diagnostic
  cannot impersonate successful Adventure evidence;
- Boss/Guild reserved prefixes are still validated by the existing server
  path;
- no client flag can set `trusted`, `authoritative`, or `progression_eligible`.

No diagnostic request is issued by the repaired client after a failure. The
context exists for lifecycle metadata, runtime diagnostics, and safe audit
correlation if another consumer observes the state.

## Characterization audit

```text
CHARACTERIZATION_TESTS_CHANGED_COUNT=0
OLD_DEFECT_EXPECTATIONS_DOCUMENTED=YES
```

No existing test was changed from “Adventure failure falls back to Practice”
to make the candidate green. Existing tests that characterize current Map
Battle/Practice boundaries remain in place. New tests add the rejected failure
contract and the server success/replay contract.

## Regression command

```text
node tests/e2e/run_p0_lane_b_adventure_forward_repair.mjs
PASS_P0_LANE_B_ADVENTURE_FORWARD_REPAIR_CLIENT_CONTRACT

pytest -q tests/test_p0_lane_b_adventure_forward_repair.py
10 passed
```
