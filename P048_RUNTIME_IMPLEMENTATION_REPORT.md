# P048 Three.js Runtime V1 — First-Wave Integration

## Result

`PASS_048_THREEJS_RUNTIME_V1_READY_FOR_OWNER_VISUAL_UAT`

This is an isolated, presentation-only candidate. The real WebGL preview is
available at the Local/LAN URLs in `P048_OWNER_UAT_CHECKLIST.md`. Owner visual
UAT remains `NOT_RUN` until the Owner reviews it.

## Required final report

```text
TASK=GO_ODYSSEY_3D_SHOP_THREEJS_RUNTIME_V1_FIRST_WAVE_INTEGRATION_048
TASK_START_ORIGIN_MASTER=357d56a1de273c691e1e2c36974c0b5e2df63cae
TASK_START_ORIGIN_TREE=05ec3a69b22e1f19f7b620b8432a600d4be1d786
BRANCH=codex/3d-shop-threejs-runtime-v1-first-wave-048
FOUNDATION_CANONICAL_PRESENT=YES
THREE_JS_RUNTIME_IMPLEMENTED=YES
P045_RUNTIME_ASSETS_PROMOTED=H06 Beanie; H06 Top Hat; H06 Frog Hat; H06 Santa Hat; H06 Sunglasses; B02 Backpack; C01; C04; V01 Confetti
SOURCE_SHA_VALIDATION=PASS
DERIVATIVE_SHA_VALIDATION=PASS
HERO_RENDER=PASS
HERO_ROTATION_MOUSE=PASS
HERO_ROTATION_TOUCH=PASS
HEAD_SWITCH_COUNT=5
HEAD_ALL_FIVE=PASS
DUPLICATE_HEAD_OBJECTS=0
HEAD_ATTACHMENT_DRIFT=0
B02_BACK=PASS
C01_RUNTIME_PROFILE=RIGID_TRANSFORM
C01_RUNTIME=PASS
C04_RUNTIME_PROFILE=SKINNED_SEGMENTED_TIMELINE
C04_IDLE=PASS
C04_WALK=PASS
C04_ATTACK=PASS
V01_RUNTIME_DERIVATIVE=2048
V01_TRIGGER=PASS
V01_RETRIGGER=PASS
SHOP_GRID_REALTIME_RENDERERS=0
MAX_ACTIVE_REALTIME_RENDERERS=1
DEFAULT_OFF_PRESENTATION_GATE=PASS
MODEL_REQUEST_WHEN_GATE_OFF=0
NORMAL_NON_3D_PAGE_MODEL_REQUESTS=0
PREVIEW_MUTATES_OWNERSHIP=NO
PREVIEW_MUTATES_EQUIPMENT=NO
PRODUCT_SKU_CREATED=0
COMMERCE_AUTHORITY_CHANGE=NO
PAID_ASSET_PURCHASE_COUNT=0
APP_PY_CHANGED=NO
DB_MIGRATION=NO
DB_SCHEMA_CHANGE=NO
FOUNDATION_TESTS=29 passed
PLAYER_PRESENTATION_TESTS=37 passed
RUNTIME_TESTS=9 passed
RELEVANT_REGRESSION_TESTS=33 passed, 2 skipped
DESKTOP_VISUAL_EVIDENCE=PASS
IPAD_LANDSCAPE_EVIDENCE=PASS
IPAD_PORTRAIT_EVIDENCE=PASS
MOBILE_PORTRAIT_EVIDENCE=PASS
JS_ERRORS=0
WEBGL_ERRORS=0
LOCAL_PREVIEW=YES
LOCAL_PREVIEW_URL=http://127.0.0.1:8048/p048_3d_shop_preview.html?preview=1
LAN_PREVIEW=YES
LAN_PREVIEW_URL=http://192.168.0.237:8048/p048_3d_shop_preview.html?preview=1
WORKTREE_CLEAN=YES
MERGE=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
OWNER_VISUAL_UAT=NOT_RUN
```

## Implementation boundaries

- The P047 canonical manifest remains authoritative and is verified by its
  external sorted-compact-JSON SHA-256:
  `9739f2a8d477dd0ad45174a40e3a5112d8d43d13008483d1acd74aa871e306e7`.
- The P048 projection promotes only the nine approved P045 logical entries.
  H01, B01, B19 and paid candidates H09, A10, T01, V05 remain hold/not
  promoted.
- The runtime uses one bounded renderer, lazy GLB/texture loading, the shared
  HEAD/BACK contracts, rigid C01 presentation, segmented C04 `clip`, and V01
  as a `VICTORY_EFFECT` with `PROPOSED_ONLY` runtime timing.
- `3D_SHOP_PRESENTATION_ENABLED` remains default-OFF. The page requires the
  explicit `?preview=1` override; the default URL produced zero renderers and
  zero model requests.
- Preview controls are presentation-only. They do not mutate ownership,
  equipment, Product, Commerce, payment, DB, or gameplay state.
- The approved source/runtime bytes are preserved; the manifest validator
  verifies every promoted runtime hash and C01's external texture hash.

## Browser evidence

The responsive run used the actual WebGL runtime and recorded:

| Surface | Viewport | Renderer | Model requests | JS/WebGL | Overflow |
| --- | ---: | ---: | ---: | ---: | ---: |
| Desktop | 1280×800 | 1 | 10 after full interaction set | 0 / 0 | no |
| iPad landscape | 1180×820 | 1 | 5 after representative controls | 0 / 0 | no |
| iPad portrait | 820×1180 | 1 | 1 baseline | 0 / 0 | no |
| Mobile portrait | 390×844 | 1 | 1 baseline | 0 / 0 | no |

Desktop exercised all five HEAD switches, B02 show/hide, C01, C04 idle/walk/
attack, V01 trigger/retrigger, all four views, reset, and mouse drag. A real
touch gesture on the mobile viewport recorded `touch_rotation_events=2`.
The final desktop diagnostics recorded `duplicate_head_objects=0`,
`head_attachment_drift=0`, `v01_trigger_count=2`,
`v01_retrigger_count=1`, and `v01_resource_leak=0`.

See [P048_VISUAL_EVIDENCE.md](P048_VISUAL_EVIDENCE.md) for the actual canvas
captures.

## Source control

The branch is based on the fresh `origin/master` snapshot above. Origin had
four release-only drift commits touching six release/deployment files since
the P046 parent; no Foundation-relevant or semantic conflict was found.
The preserved local `secret_key.txt` is excluded from the candidate commit and
was not read, staged, or changed.

No merge or deploy was performed.
