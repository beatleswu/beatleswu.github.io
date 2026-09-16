# P0 A+B combined regression

All commands below were run against the combined candidate tree, not
Production.

| Gate | Command | Result |
|---|---|---|
| Zone4 direct runtime | node tests/e9_node_tests/run_zone4_intro_cinematic_wiring_tests.js | 6/6 passed |
| Zone4 wrapper | pytest -q tests/test_post007c_008_zone4_intro_cinematic_wiring.py | 4 passed |
| E9/E10 cinematic relevant collection | selected E9/E10 cinematic/world-stage files | 238 passed |
| Static packaging/tooling collection | pytest -q tests/deployment/test_static_release_tooling.py tests/deployment/test_zone4_static_packaging.py tests/deployment/test_e9_runtime_asset_packaging.py | 105 passed, 104 skipped |
| Lane B client contract | node tests/e2e/run_p0_lane_b_adventure_forward_repair.mjs | PASS contract |
| Lane B source contract | pytest -q tests/test_p0_lane_b_adventure_forward_repair.py | 10 passed |
| Map Battle integration | reviewed Lane B Map Battle command, excluding real_container | 93 passed, 1 deselected |
| Adventure/first-clear | reviewed Lane B Adventure command, excluding real_container | 82 passed |
| Global non-admin E2E | pytest -q tests/test_map_battle_legacy_adapter.py -k global_non_admin_adventure_answer_progresses_once_and_replays_safely | 1 passed, 41 deselected |

The specific global E2E proves authenticated non-admin global admission,
server CORRECT, mbv1 evidence, first progression applied, replay duplicate,
and one persisted review/progression contribution.

## Required behavior result

~~~text
ZONE1=PASS
ZONE2=PASS
ZONE3=PASS
ZONE4_CINEMATIC_KEY=e10_zone4_intro_v1
ZONE4_GUARD=zone4EntryInFlight
ZONE5_PLUS=UNWIRED
ADVENTURE_DISABLED_NOT_PRACTICE=PASS
ADVENTURE_PENDING_NOT_PRACTICE=PASS
ADVENTURE_NOT_ELIGIBLE_NOT_PRACTICE=PASS
ADVENTURE_RUNTIME_FAILURE_NOT_PRACTICE=PASS
ORDINARY_PRACTICE_REMAINS_PRACTICE=PASS
SUCCESSFUL_MAP_BATTLE_PATH=PASS
DUPLICATE_GUARD=PASS
~~~

The 104 skips are environment/device-gated skips in the static collection;
the combined candidate added no skip or xfail. Accepted Lane A evidence also
records a broader collection's one stale baseline static-closure failure and a
Playwright dependency gap; neither is a candidate-only Product failure, and
the focused combined collections above passed.

~~~text
ZONE4_COMBINED_PASS=YES
ADVENTURE_FAIL_CLOSED_COMBINED_PASS=YES
GLOBAL_NON_ADMIN_E2E_PASS=YES
PRACTICE_NON_PROGRESS_PASS=YES
DUPLICATE_GUARD_PASS=YES
~~~

No test exercised a Production endpoint or performed a data/config write.
