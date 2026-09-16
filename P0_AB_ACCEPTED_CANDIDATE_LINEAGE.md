# P0 A+B accepted candidate lineage

## Lane A

~~~text
LANE_A_BRANCH=codex/GO_ODYSSEY_P0_LANE_A_ZONE4_STATIC_HOTFIX_001
LANE_A_FINAL_HEAD=c996a1b63d4cd1c39bea8426e15eef288aca5fac
LANE_A_FINAL_TREE=3fbc9972a71d0fe4fd6f93316bc42c9ef0c9e917
LANE_A_IMPLEMENTATION_HEAD=f2e89da2d1eccf673e1f3d9ab16ec99c214728a9
LANE_A_IMPLEMENTATION_TREE=de7391393aaba4d1920e9cccfda768c1b94bfb46
LANE_A_IMPLEMENTATION_IS_ANCESTOR=YES
~~~

git merge-base --is-ancestor f2e89da2... c996a1b6... returned success.
The exact base-to-final diff is eight files and contains the authorized shape:

~~~text
P0_LANE_A_ZONE4_CANONICAL_RECONCILIATION.md
P0_LANE_A_ZONE4_COORDINATOR_READINESS.md
P0_LANE_A_ZONE4_HOTFIX_IMPLEMENTATION.md
P0_LANE_A_ZONE4_REGRESSION.md
P0_LANE_A_ZONE4_STATIC_PROMOTION_PLAN.md
js/e9/world_stage.js
tests/e9_node_tests/run_zone4_intro_cinematic_wiring_tests.js
tests/test_post007c_008_zone4_intro_cinematic_wiring.py
~~~

The accepted semantics are present: k11_15 resolves to e10_zone4_intro_v1
and zone4EntryInFlight; Zones 1–3 remain unchanged and Zone5+ remain
unwired.

## Lane B

~~~text
LANE_B_BRANCH=codex/p0-lane-b-adventure-forward-repair-001
LANE_B_FINAL_HEAD=2b28843a2347ca9ae9b94e7932b331d7b14b01ac
LANE_B_FINAL_TREE=0bd2e0e6b07923b4105171e0b55721204d1bf498
LANE_B_AUTHORIZED_DIFF=YES
~~~

The exact ten-file diff matched the reviewed manifest:

~~~text
docs/planning/p0_lane_b_adventure_forward_repair_001/P0_LANE_B_ADVENTURE_CONTEXT_FIX.md
docs/planning/p0_lane_b_adventure_forward_repair_001/P0_LANE_B_AUTHENTICATED_ADVENTURE_ACCEPTANCE.md
docs/planning/p0_lane_b_adventure_forward_repair_001/P0_LANE_B_COORDINATOR_READINESS.md
docs/planning/p0_lane_b_adventure_forward_repair_001/P0_LANE_B_MAP_BATTLE_MODE_PREFLIGHT.md
docs/planning/p0_lane_b_adventure_forward_repair_001/P0_LANE_B_PRACTICE_SEPARATION_REGRESSION.md
docs/planning/p0_lane_b_adventure_forward_repair_001/P0_LANE_B_PRODUCTION_ENABLE_PLAN.md
index.html
tests/e2e/run_p0_lane_b_adventure_forward_repair.mjs
tests/test_map_battle_legacy_adapter.py
tests/test_p0_lane_b_adventure_forward_repair.py
~~~

No additional Product file was present in the Lane B final diff. The accepted
semantics are fail-closed Adventure handling for disabled, pending,
not-eligible, and runtime/init-failure states; ordinary Practice remains
Practice; successful Map Battle remains the existing authoritative path.

## Integration method

Only the implementation/evidence commits named above were cherry-picked onto
the fresh canonical base. Lane C, P051-C1, Zone5, MBV1 retirement, historical
recovery, and unrelated pending candidates were not selected.
