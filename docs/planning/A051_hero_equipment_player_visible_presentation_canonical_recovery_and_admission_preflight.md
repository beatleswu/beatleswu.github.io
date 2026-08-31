# A051 Hero Equipment Player-Visible Presentation Admission Preflight

Status: admission preflight prepared; merge, deployment, and Production mutation were not performed.

## Required fields

```text
A051_AUTHORITATIVE_CANDIDATE_FOUND=YES
A051_VERIFICATION_CLASS=EXACT_TWO_PATH_CANDIDATE_REBASED_CLEANLY_TO_FRESH_CURRENT_MASTER
A051_BASE_SHA=62cd841a3af78a66c4c5aba16cdfebb7814513da
A051_HEAD_SHA=c9d43fa163835a68c80fda1c6f11c11cd28b0f68
A051_TREE_SHA=41d3b3c611f0ab561f8c108e31360cf6c501ff24
REMOTE_HEAD_VERIFIED=YES; origin/codex/a051-wooden-sword-equip-hero-vertical-slice=c9d43fa163835a68c80fda1c6f11c11cd28b0f68
ALREADY_CANONICAL_PATH_COUNT=0; A051 source delta paths are not in fresh origin/master
STALE_OR_SUPERSEDED_PATH_COUNT=97; endpoint-only divergence, excluded from the candidate
CURRENT_MASTER_CONFLICT_COUNT=0
REBASING_BASE_SHA=b3d37e22e7471d0429d882c43c3ee16049c68ea1
REBASING_CANDIDATE_SHA=3995a87c519f2e38277cf21ac8c48c833d2db1f0
REBASING_CANDIDATE_TREE_SHA=f8b1a27e554b834e5bdb6c946a6dc7cc19731b0f
PATH_DIFF=2; inventory.html; tests/test_a051_wooden_sword_equip_to_hero_projection_vertical_slice.py
PLAYER_VISIBLE_BEHAVIOR=server-equipped wooden_sword projection to Hero is exercised through the Backpack/equipment route; iron_sword mapping is regression-checked; reload rehydrates from server state; unequip clears the projection
A056_A057_COMPATIBILITY=COMPATIBLE_SEMANTICALLY_BUT_SEPARATE_REVIEW_LANE; A051 retains current master waist-sheathed presentation metadata and does not import ONE_HAND_SWORD_POSE_V1 hand-held assets or activation
HERO_EQUIPMENT_PRESENTATION_CLOSURE=YES_FOR_EXISTING_CURRENT_MASTER_SERVER_EQUIPPED_HERO_PROJECTION; A051 adds only a test-only two-key UI override and regression proof, not default player enablement
APP_PY_REQUIRED=NO
SOURCE_IMPLEMENTATION_REQUIRED=NO; current master already contains the authoritative route, projection hydration, registry, and renderer
OWNER_VISUAL_REVIEW_REQUIRED=NO_FOR_THIS_TEST_ONLY_DELTA; any future hand-held pose-family activation remains separately owner-review gated
READY_FOR_CANONICAL_ADMISSION_PREFLIGHT=YES
READY_FOR_OWNER_GO_MERGE=NO; explicit Owner GO_MERGE remains required
NEXT_TASK=A051_OWNER_GO_MERGE_GATE_PACKET_001
```

## Scope and authority

The source candidate is exactly the two-path patch from `c9d43fa`: the inventory UI's default-off functional-loadout guard gains a two-key test-harness override, and the focused A051 test is added. The shipped/default guard remains closed. The browser action still calls the canonical server endpoint; the test override does not grant ownership, equip locally, or change server state.

The test covers acquisition staying unequipped, the disabled server path remaining a no-op, enabled canonical equip/unequip, wooden and iron presentation mappings, Hero projection hydration, and a new-client reload. Combat effects and equipment state remain server-owned; no Shop, Loadout, payment, schema, or `app.py` changes are included.

A056/A057's `ONE_HAND_SWORD_POSE_V1` work is compatible as a future presentation-family contract, but it is a separate hand-held pose/review lane. It is not needed to admit A051's existing player-visible waist-sheathed projection and must not be folded into this candidate. A055 Live2D and the failed A053/A054 visual iterations remain out of scope.

## Verification evidence

- A051 source worktree: `4 passed`.
- Fresh-master-based A051 candidate (`3995a87c`): `4 passed`.
- Current-master Hero/equipment regression matrix: `47 passed`.
- A056 pose-family contract: `8 passed`.
- A057-R1 Paladin compatibility contract: `6 passed`.
- Exact A051 patch applied to fresh `origin/master` with no conflict; synthetic final tree: `f8b1a27e554b834e5bdb6c946a6dc7cc19731b0f`.

The old A051 endpoint differs from fresh master by 99 paths. Only its exact two-path commit delta is admissible; the other 97 endpoint-only paths are stale lineage and are intentionally excluded.
