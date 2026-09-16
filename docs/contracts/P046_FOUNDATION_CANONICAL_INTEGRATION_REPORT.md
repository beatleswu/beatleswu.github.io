# GO_ODYSSEY_3D_SHOP_V1_FOUNDATION_CANONICAL_INTEGRATION_046

This is the canonical integration candidate for the presentation-only 3D
Shop V1 foundation. It is not the Three.js Product runtime and it does not
enable the feature gate.

## Fresh canonical reconciliation

The worktree was created from the fetched `origin/master` at:

```text
TASK_START_ORIGIN_MASTER=038203ad13fe6211ada665e48a6b04a689efd733
TASK_START_ORIGIN_TREE=8114c929aa2eae0a801cbb2d703d466cb89599e3
PARENT=038203ad13fe6211ada665e48a6b04a689efd733
BRANCH=codex/3d-shop-v1-foundation-canonical-integration-046
```

The previous Foundation PASS was not reachable as a branch, commit, or
file-level implementation in the fetched refs/current filesystem. The
current canonical source was searched for the exact Foundation symbols and
fields before adding this bounded implementation. No equivalent
`HeroBase3DRegistry`, `3D_SHOP_PRESENTATION_ENABLED`, normalized-scale, or
local-forward-offset implementation existed in `origin/master`.

Therefore the reconciliation classification is:

```text
FOUNDATION_RECONCILED_TO_CURRENT_CANONICAL=YES
CANONICAL_DRIFT_FILES=0
FOUNDATION_CONFLICT_FILES=0
SEMANTIC_CONFLICT_COUNT=0
```

The zero counts mean that no file-level Foundation delta or conflicting
implementation was present in the current canonical base; the prior task
authority was reconciled semantically from the supplied P045/P040 contracts
and current source-of-truth readers. The canonical checkout's pre-existing
untracked files were not cleaned, staged, reset, or copied into this worktree.

## Implemented contract

`shop_3d_presentation_foundation.py` provides:

- a typed `(authority_domain, authority_id, presentation_id)` bridge;
- strict fail-closed validation for the reference manifest;
- recursive rejection of business/commerce/ownership fields and ambiguous
  self-hashing fields;
- deterministic canonical JSON bytes plus an external admission SHA-256;
- HEAD/BACK transform fields, including normalized scale, presentation scale,
  local position offset, local forward offset, and adapter profile;
- a bounded `HeroBase3DRegistry` keyed by existing character keys;
- C01 rigid-transform and C04 segmented-timeline companion profiles;
- V01 `VICTORY_EFFECT` atlas metadata with `PROPOSED_ONLY` timing; and
- a default-OFF `3D_SHOP_PRESENTATION_ENABLED` model-request seam.

The P045 reference manifest contains 9 metadata entries: 5 HEAD, 1 BACK, 2
COMPANION, and 1 VICTORY_EFFECT. Every entry includes source/license and
source/derivative SHA-256 evidence. The runtime assets remain in the isolated
P045 admission package:

```text
P045_RUNTIME_ASSET_PROMOTION_DEFERRED=YES
canonical_asset_promotion=false
```

No P045 binary, Shop SKU, Product record, or universal `item_id` was added.

P040 remains a precedent contract, not a new equipment authority:

```text
sword_presentation_scale=5.0
shield_presentation_scale=3.5
shield_original_baseline=0.3315
shield_world_scale=1.16025
shield_local_forward_offset=[0,0,0.13]
shield_local_forward_direction=+Z
```

## Authority and boundary results

```text
COMPANION_AUTHORITY_RECONCILED=YES
pet_inventory=food/supply quantity only
functional_ownership=pet_collection.pet_key
active_selection=user_pets.pet_key
UNIVERSAL_ITEM_ID_CREATED=NO
MANIFEST_HASH_POLICY=external SHA-256 over sorted-key compact UTF-8 JSON; no self-hash field
DEFAULT_OFF_PRESENTATION_GATE=PASS
MODEL_REQUEST_WHEN_GATE_OFF=0
APP_PY_CHANGED=NO
DB_MIGRATION=NO
DB_SCHEMA_CHANGE=NO
COMMERCE_AUTHORITY_CHANGE=NO
PAYMENT_CHANGE=NO
THREE_JS_PRODUCT_RUNTIME_IMPLEMENTED=NO
PRODUCT_SKU_CREATED=0
PAID_ASSET_ADDED=NO
```

## Verification

```text
FOUNDATION_TESTS=29 passed
PLAYER_PRESENTATION_TESTS=36 passed
COMPANION_REGRESSION=7 passed, 2 skipped
SHOP_EQUIPMENT_REGRESSION=21 passed
RELEVANT_REGRESSION_TESTS=64 passed, 2 skipped
```

The skipped tests are the existing B023 test skips; there was no new failure.
The Foundation suite explicitly covers valid manifests, forbidden-field
rejection, identity separation, hash determinism, scale/offset semantics,
HEAD/BACK contracts, C01/C04 profiles and exact subclip ranges, V01 role and
timing authority, HeroBase3DRegistry, companion authority, the default-OFF
gate, and zero model requests while the gate is off.

## Scope gate

Only the following files are Task 046 candidate files:

```text
shop_3d_presentation_foundation.py
schemas/3d_shop_presentation_manifest.schema.json
docs/contracts/3d_shop_v1_p045_presentation_reference_manifest.json
docs/contracts/P046_FOUNDATION_CANONICAL_INTEGRATION_REPORT.md
P046_FOUNDATION_VALIDATION_EVIDENCE.json
tests/test_3d_shop_presentation_foundation.py
```

`app.py`, migrations, commerce/equipment authority writers, runtime UI, and
Three.js code are unchanged. The final commit/tree identity and final
`origin/master` check are recorded in the delivery report for this task after
the last Git gate.

```text
MERGE=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
```
