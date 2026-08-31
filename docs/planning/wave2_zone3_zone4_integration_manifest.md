# Wave 2 Zone 3 Template / Zone 4 Misty Forest Integration Manifest

`TASK=WAVE2_ZONE3_TEMPLATE_EXTRACTION_AND_ZONE4_MISTY_FOREST_VERTICAL_SLICE_FOUNDATION_001`
`BASE=b3d37e22e7471d0429d882c43c3ee16049c68ea1`
`APP_PY_WRITE=FORBIDDEN`
`PRODUCTION_QUERY=NO`
`PRODUCTION_MUTATION=NO`
`MASTER_MERGE=NO`
`DEPLOY=NO`

## Implemented foundation

The E055 Zone 3 authority has been mechanically split into a reusable
`adventure_zone_authority_template.py` and a Zone3 content wrapper that keeps
the existing public symbols and persistence format. Zone4 uses that template
through `adventure_zone4_misty_forest_authority.py`.

The reusable seam owns only:

- explicit server-created M-ID bindings;
- deterministic question-identity selection from an explicit normal roster;
- persisted source/version/profile validation;
- combat-profile construction; and
- presentation-only projection.

It does not own routes, schema, progression, Lords, Bosses, rewards, Spirit
state, Quest state, or client state. Drops and rewards continue to reference
the existing server settlement registries.

## Zone3 inventory

| Area | Canonical path | Boundary |
|---|---|---|
| Zone3 authority | `adventure_zone3_monster_authority.py` | E055 Goblin Cave content; 13 normal bindings |
| reusable profiles | `monster_profiles.py`, `monster_combat_profiles.py` | profile and combat projections |
| settlement | `monster_settlement.py` | server-owned defeat event, drops, rewards, idempotency |
| drop/reward references | `monster_drop_profiles.py`, `monster_reward_profiles.py` | existing registries, no new channel |
| browser projection | `js/map_battle_v1_adapter.js` | reads authoritative response fields |
| player-facing copy/continuation | `index.html`, `i18n.js` | existing Adventure encounter continuation and bilingual Zone3 copy |
| app integration | `app.py` | unchanged and deferred behind the Incident019B writer lock |

Zone3's 13 normal IDs remain `M022–M033` plus `M060`; `goblin_centurion`
remains `LORD_ONLY` and is not a normal binding. Existing E055 tests remain
the compatibility regression contract.

## Zone4 content foundation

| Field | Value |
|---|---|
| key/name | `k11_15` / Misty Forest |
| existing book rows | `7迷霧森林`, `8迷霧森林深處` from `app.ADVENTURE_ZONES[k11_15].books` |
| normal roster | `M034,M035,M036,M037,M038,M039,M040,M041,M042,M043,M044,M045` |
| normal/elite/boss | `12 / 0 / 0` |
| Lord | `misty_phantom_rabbit_king` (`LORD_ONLY`) |
| binding/profile | `wave2.zone4.binding.v1` / `wave2.zone4.normal.v1` |
| storyboard | 4 existing `go_misty_forest_scene_01..04.webp` files |
| VO | 8 existing files: 4 zh and 4 en |
| new art | `0`; M034 reuses the existing runtime asset and M035–M045 reuse canonical art |
| new audio | `0`; approved/reviewed BGM and existing bilingual storyboard VO are reused |
| question rows | the book binding is canonical; question data is not tracked in this repository and is not fabricated here |

No M121+ identity, ART003 B12 generation, new Boss/Elite semantics, schema, or
production change was introduced.

## Deferred app.py integration

The next integration task is deterministic and limited to these existing app
callers:

1. import Zone4 authority symbols;
2. add a parallel fail-closed `_map_battle_zone4_binding` resolver;
3. route Zone4 through the existing Map Battle profile/public-state seams;
4. select and persist the Zone4 binding from the server-owned question ID;
5. decode the binding at answer/settlement and pass the Zone4 registries to
   `monster_settlement`; and
6. extend the existing art allowlist for the already-canonical Zone4 assets.

The existing `k11_15` book mapping, `misty_phantom_rabbit_king` Lord identity,
selected-zone/progression-zone distinction, server settlement, and normal
defeat-versus-zone-clear boundary must remain unchanged. The app integration
must not create schema or infer Boss, stars, unlocks, drops, rewards, Spirit,
or progression from client or historical counts.

`READY_FOR_ZONE4_INTEGRATION_AFTER_WRITER_UNLOCK=YES_FOUNDATION_ONLY`

## Exact output

```text
ZONE3_TEMPLATE_INVENTORY=COMPLETE_E055_13_NORMAL_BINDINGS
REUSABLE_ZONE_AUTHORITY_MODULES=adventure_zone_authority_template.py
ZONE3_SPECIFIC_PATHS=adventure_zone3_monster_authority.py;E055 tests;existing app/map-battle callers
ZONE4_EXISTING_CANONICAL_ROWS=BOOK_BINDING_PRESENT;QUESTION_DATA_NOT_TRACKED
ZONE4_MONSTER_BINDING_COUNT=12
ZONE4_STORYBOARD_AVAILABLE=YES
ZONE4_VO_AVAILABLE=YES_8_FILES
NEW_ART_REQUIRED_COUNT=0
NEW_AUDIO_REQUIRED_COUNT=0
NON_APP_PY_IMPLEMENTATION_COMPLETED=YES
FOCUSED_TESTS=tests/test_wave2_zone4_misty_forest_foundation.py;tests/test_e055_zone3_vertical_slice.py
REGRESSION_TESTS=existing monster settlement/profile/combat and asset publication contracts
APP_PY_INTEGRATION_DEFERRED=YES
DEFERRED_APP_PY_CALLERS=import;binding resolver;profile/public state;attempt selection;answer settlement;art allowlist
SCHEMA_CHANGE_REQUIRED=NO
OWNER_DECISION_REQUIRED=YES_INCIDENT019B_WRITER_UNLOCK_AND_APP_INTEGRATION_GATE
READY_FOR_ZONE4_INTEGRATION_AFTER_WRITER_UNLOCK=YES_FOUNDATION_ONLY
NEXT_TASK=ZONE4_APP_PY_INTEGRATION_AFTER_INCIDENT019B_WRITER_UNLOCK_AND_OWNER_GATE
```
