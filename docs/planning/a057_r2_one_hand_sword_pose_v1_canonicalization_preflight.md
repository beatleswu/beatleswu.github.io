# A057-R2 — One-Hand Sword Pose V1 Canonical Scope Reconciliation

RESULT = PASS_A057_R2_CANONICAL_SCOPE_RECONCILIATION_PREFLIGHT

This is a canonicalization preflight only. It does not admit the source
packages to master, change runtime presentation, or consume an Owner merge or
deployment gate.

MASTER_MERGE = NO · MASTER_PUSH = NO · DEPLOY = NO

## Fresh identity and source inputs

| field | value |
|---|---|
| FRESH_ORIGIN_MASTER_HEAD | b3d37e22e7471d0429d882c43c3ee16049c68ea1 |
| FRESH_ORIGIN_MASTER_TREE | 39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93 |
| A056_REMOTE_HEAD | ac4c7ea49945b473a91753b0685dca487955148b |
| A056_REMOTE_TREE | 47367ab9f910828f9b46f1761af646dffd85806d |
| A057_R1_REMOTE_HEAD | 90127f9a4b9eb2055cd9004733d27a9f7b9e8b10 |
| A057_R1_REMOTE_TREE | 787da96569d7b18beaadc093c7ec7dec2f981fa4 |
| A056_OWNER_PASS_VERIFIED | YES — supplied Owner decision; source contract remains a historical pre-acceptance record |
| A057_R1_OWNER_PASS_LOCKED | YES — supplied Owner decision; both normal Paladin renders accepted |

The source branches were verified at their exact remote heads. A056 supplies
the Apprentice pose-family implementation and independent wooden/iron layers.
A057-R1 supplies the second-character Paladin review package and proves that
the same pose family can be reused with character-local geometry.

## Corrected contract

The reusable contract is deliberately small and anatomy-neutral:

pose_id, pose_family, slot, shoulder_action_intent, elbow_action_intent,
forearm_direction, wrist_orientation, grip_point_semantics,
grip_axis_semantics, grip_width_semantics, weapon_swap_contract, and
default_pose_fallback.

Character-specific adapter metadata is separate for apprentice and paladin.
The adapter retains only attachment and composition data needed by a
precomposed character pose: character_id, full_pose_asset, right_hand_socket,
local_scale, local_rotation_degrees, sleeve_armor_clearance, occlusion_order,
and fallback_asset.

Shoulder anchor, elbow target, wrist angle, palm center, and local forearm
vectors remain review geometry where the pose is precomposed; they are not
promoted into a second runtime abstraction. The Paladin review geometry is
preserved in the machine-readable evidence, but its weapon-free source remains
review-only and is not silently promoted to a runtime asset.

## Exact path reconciliation

The task-owned machine-readable contract is
[a057_r2_one_hand_sword_pose_v1_canonicalization_preflight.json](a057_r2_one_hand_sword_pose_v1_canonicalization_preflight.json).
The JSON-pointer suffixes below identify sections in that single metadata
file; there are no separate runtime adapter registries.

| category | exact proposed paths |
|---|---|
| GENERIC_CONTRACT_PATHS | docs/planning/a057_r2_one_hand_sword_pose_v1_canonicalization_preflight.json |
| APPRENTICE_ADAPTER_PATHS | docs/planning/a057_r2_one_hand_sword_pose_v1_canonicalization_preflight.json#/character_adapters/apprentice |
| APPRENTICE_ASSET_PATHS | A056 assets/pose/* (2 files) plus A056 wooden/iron assets/weapons/* (6 files) |
| PALADIN_ADAPTER_PATHS | docs/planning/a057_r2_one_hand_sword_pose_v1_canonicalization_preflight.json#/character_adapters/paladin |
| PALADIN_ASSET_PATHS | Existing assets/hero/characters/wave2_p1/paladin_p1.png fallback; existing accepted pose review evidence and the A057-R1 weapon-free source are listed as review-only evidence, not runtime admission |
| TEST_PATHS | 13 focused/related test files listed verbatim in the JSON artifact |
| REVIEW_EVIDENCE_PATHS | A056 review/source-reference directories, A057-R1 review/source-reference directories, and the existing Paladin pose review variant |

TOTAL_PROPOSED_CANONICAL_PATH_COUNT = 12: the task-owned contract, the eight
A056 pose/weapon assets, the A056 builder, and the A056/R1 focused tests. The
source package union is 37 paths: 20 review-page/image paths and 6
superseded/source-evidence paths are excluded from automatic canonicalization.
There is no duplicate character-specific weapon pose and no fox_fang path in
the proposed scope.

## Registry and authority decision

| decision | value | reason |
|---|---|---|
| EXISTING_REGISTRY_EXTENSION_SAFE | NO | The existing wearable/runtime metadata explicitly preserves WAIST_SHEATHED and hand-held static = FORBIDDEN; adding this pose would be a runtime change |
| SEPARATE_PRESENTATION_METADATA_REQUIRED | YES | R2 needs a static, reviewable generic contract plus two adapters without runtime activation |
| NEW_RUNTIME_REGISTRY_REQUIRED | NO | Existing item identity and server-owned equipped state remain the authority |

The preflight is app.py-free. APP_PY_CHANGED = NO, RUNTIME_CHANGED = NO,
COMBAT_AUTHORITY_CHANGED = NO, EQUIPMENT_AUTHORITY_CHANGED = NO,
SCHEMA_CHANGED = NO, PRODUCTION_QUERY = NO, and PRODUCTION_MUTATION = NO.

## Weapon and grip invariants

wooden_sword and iron_sword both use ONE_HAND_SWORD_POSE_V1 in MAIN_HAND. They
share grip point and axis semantics while retaining their grip widths (39 px
and 41 px in the A056 evidence). The same character pose is used for both
weapon variants; no weapon-specific character pose is introduced.

Both accepted normal-render contracts preserve:

HANDLE_ENTERS_PALM = YES · FOUR_FINGERS_WRAP = YES · THUMB_OPPOSES = YES ·
WRIST_CONTINUITY = PASS · FOREARM_CONTINUITY = PASS ·
SHOULDER_TO_HAND_ACTION = PASS

FOX_FANG_SCOPE = EXCLUDED.

## Fresh-master synthetic review

The exact A056 and A057-R1 source deltas were applied to a temporary index
initialized from fresh origin/master; no merge was performed.

| field | value |
|---|---|
| SYNTHETIC_BASE_HEAD | b3d37e22e7471d0429d882c43c3ee16049c68ea1 |
| SYNTHETIC_BASE_TREE | 39392e8c0df272fb3b0d3df2ec0c1f4f21ab7a93 |
| SYNTHETIC_FINAL_TREE | 906360976d6e2e3e46ffa0b297ae436962a4633f |
| PATH_CONFLICT_COUNT | 0 |
| SEMANTIC_CONFLICT_COUNT | 0 |
| UNEXPECTED_PATH_COUNT | 0 |
| A056/R1_PATH_OVERLAP_COUNT | 0 |

The semantic zero is based on matching pose ID/family/slot, matching grip
point/axis semantics, character-local socket coordinates, zero
weapon-specific full-character poses, and the explicit fox_fang exclusion.

## Tests

Focused tests:

| suite | result |
|---|---|
| A056 pose-family, layer, transform, asset-integrity tests | 8 passed |
| A057-R1 Paladin adapter, weapon swap, review, grip, firewall tests | 6 passed |
| FOCUSED_TEST_COUNT | 14 |
| FOCUSED_PASS / FAIL / SKIP | 14 / 0 / 0 |

Related tests:

| suite | result |
|---|---|
| A053-R3 true-handle grip regression | 10 passed |
| A054-P0 split-weapon grip regression | 11 passed |
| Existing pose/weapon/armor suites | 17 passed |
| Existing runtime presentation and authority suites | 24 passed |
| Existing P3 wearable runtime suite | 10 passed, 1 failed |
| RELATED_TEST_COUNT | 73 |
| RELATED_PASS / FAIL / SKIP | 72 / 1 / 0 |

The one failure is pre-existing on the untouched fresh-master base:
test_all_runtime_overlays_and_masks_are_true_alpha_and_normalized reports that
assets/hero/equipment/wearables/overlays/go_stone_black.png is absent while
wearable_registry.json references it. It is unrelated to A057-R2;
TASK_INTRODUCED_FAILURES = 0.

## Gate result

READY_FOR_OWNER_A057_CANONICAL_ADMISSION_GATE = YES

This preflight recommends the next task:

NEXT_TASK = A057_R3_OWNER_CANONICAL_ADMISSION_GATE_PACKET_001

No master merge, master push, deployment, runtime enablement, authority change,
or secret access occurred during this task. The pushed evidence for this
result is this Markdown report and its machine-readable JSON equivalent.
