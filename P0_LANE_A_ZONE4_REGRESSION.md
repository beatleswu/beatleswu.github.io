# P0 Lane A Zone4 regression evidence

## Baseline proof

An actual VM harness extracted the two functions from the untouched fresh
origin/master world_stage.js and invoked their runtime results. The baseline
result was:

BASELINE_RUNTIME_HARNESS=8/10 passed
BASELINE_EXIT_CODE=1
BASELINE_ZONE1_3=6/6 passed
BASELINE_ZONE4_CINEMATIC=FAIL actual=null expected=e10_zone4_intro_v1
BASELINE_ZONE4_GUARD=FAIL actual=zone2EntryInFlight expected=zone4EntryInFlight
BASELINE_ZONE5_UNKNOWN=2/2 passed

This proves the pre-fix assertions fail on the actual functions, not on a
source-text convention.

## Candidate targeted evidence

NODE_HARNESS=6/6 passed
PYTEST_WRAPPER=4 passed in 0.42s

The Node harness executes the real mapping functions and verifies:

- Zone4 key and dedicated guard;
- unchanged Zones 1-3 behavior;
- distinct key and guard sets;
- Zone5 and later remain null/unwired;
- unknown keys remain null/unwired.

## E9/E10 regression collections

E9_E10_CINEMATIC_PYTEST=203 passed in 10.76s
STATIC_PACKAGING_PYTEST=14 passed, 104 skipped in 9.05s

The skips are pre-existing environment/device-gated tests. No skip or xfail
was added by this candidate.

The broader relevant collection produced:

BROAD_COLLECTION=226 passed, 104 skipped, 1 failed in 132.23s

The single failure was:

tests/test_e10_zone1_deployment_asset_closure.py::test_actual_governed_static_bundle_contains_closure_and_no_broad_assets

The same test failed on a clean untouched origin/master baseline:

BASELINE_BROAD_FAILURE=1 failed in 17.16s

Its extra staged assets are the existing Zone3/Zone4/equipment closure versus
the older Zone1 expected set. This is a pre-existing stale static-closure
baseline, not a candidate-only product regression, and was not changed here.

The browser contract tests/e2e/run_intro_film_narration_contract.mjs could not
start because the isolated worktree has no playwright-core dependency:

BROWSER_CONTRACT=ENVIRONMENT_GAP
BROWSER_CONTRACT_ERROR=Cannot find package playwright-core

No candidate source failure was observed in that attempt. The direct Node
harness and Python E9/E10 collections provide the relevant runtime evidence.

## Scope regression

CHANGED_RUNTIME_FILES=1
APP_PY_CHANGED=NO
DB_CHANGED=NO
ASSET_OR_AUDIO_DIFF=NO
ZONE5_DIFF=NO
PROGRESSION_REWARD_LORD_DIFF=NO
TEST_WEAKENING_COUNT=0
CANDIDATE_ONLY_PRODUCT_FAILURE_COUNT=0

