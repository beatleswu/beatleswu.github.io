# W1-04 Zone 3 40-Item DoD Evidence and Status Reconciliation

Status: `PASS_ZONE3_40ITEM_DOD_EVIDENCE_RECONCILED`

This is an audit-only reconciliation. It preserves the prior 40-item taxonomy, does not implement open items, merge candidates, deploy, or mutate Production.

## Audit identity and evidence boundary

| Field | Value |
|---|---|
| TASK | W1_04_SYSTEMS_ZONE3_40ITEM_DOD_EVIDENCE_AND_STATUS_RECONCILIATION_005 |
| SOURCE_AUDIT_HEAD | 291c1b64a8fbad84b8524a5393b3bafb6aba30c0 |
| CANONICAL_MASTER_REFERENCE | 616d51b17abe010de1e862382ca4db7bec65936f |
| AUDIT_BRANCH | codex/w1-04-zone3-40item-dod-evidence-reconciliation-005 |
| AUDIT_HEAD | Reported after the final documentation commit; omitted from the self-referential file content. |
| AUDIT_TREE | Reported after the final documentation commit; omitted from the self-referential file content. |
| CANDIDATE_HANDLING | Immutable SHA/manifests inspected; no cherry-pick or merge. |

Accepted input heads:

| Input | Head/status |
|---|---|
| WORLD_PRODUCT_HEAD | 39c587a216f6cc13efe572066d9d8f0299960f1b |
| WORLD_PRESENTATION_FX_PREFLIGHT_HEAD | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d |
| HERO_PRODUCT_HEAD | 8fa4184e775517403f66a3d56e7357d3470e67cf |
| JOURNEY_ZH_TW_COMPLETE_HEAD | f77bce46302974c8a8aa9d296ae0ea548a707691 |
| ZH_TW_INTEGRATION_CHECKPOINT_HEAD | 5fd9def812c230aa7089a8388be932bea8e7d0f7 |
| ZH_TW_INTEGRATION_CHECKPOINT_TREE | fc7ad4c566963aac8faa313974b0363aaafd75c0 |
| QUALITY_SOURCE_ART_HEAD | 6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf |
| EN_US_TASK | W1_03_JOURNEY_ZONE3_EN_US_SCRIPT_AND_VOICE_AUTHORITY_RECOVERY_007 |
| EN_US_TASK_STATUS | TASK_BOOK_ISSUED_NOT_YET_COMPLETED |
| PLAYWRIGHT_INFRA_STATUS | AVAILABLE |
| PLAYWRIGHT_INFRA_HEAD | dddefed7b27ee17d65aba89823a47b0e0bd0d0ad |
| PREVIOUS_PLAYWRIGHT_BLOCKER_RESOLVED | YES |

The Playwright update is evidence, not a new feature claim: infrastructure is available at `dddefed7b27ee17d65aba89823a47b0e0bd0d0ad`, while Zone 3 browser execution remains partial.

## Taxonomy and arithmetic

The previous 40-item taxonomy is unchanged; no duplicate, contradiction, or missing category was identified.

| TOTAL_ITEMS | 40 |
| COMPLETE | 6 |
| PARTIAL | 25 |
| MISSING | 8 |
| NOT_APPLICABLE | 1 |
| OPEN_REQUIRED_ITEM_COUNT | 33 |
| ARITHMETIC | 6 + 25 + 8 + 1 = 40; every open required item maps to exactly one row. |

## ZH-TW reconciliation

| Field | Status/evidence |
|---|---|
| SUBTITLE_BEATS | 97 |
| VOICE_BEATS | 97 |
| MISSING | 0 |
| DUPLICATE | 0 |
| INTEGRATED_CHECKPOINT | 5fd9def812c230aa7089a8388be932bea8e7d0f7 |
| ZH_TW_SUBTITLE_CONTENT_STATUS | COMPLETE |
| ZH_TW_SUBTITLE_INTEGRATION_STATUS | COMPLETE |
| ZH_TW_SUBTITLE_FINAL_ACCEPTANCE_STATUS | NOT_YET_TESTED |
| ZH_TW_VOICE_CONTENT_STATUS | COMPLETE |
| ZH_TW_VOICE_INTEGRATION_STATUS | COMPLETE |
| ZH_TW_VOICE_PERCEPTUAL_QA_STATUS | NOT_YET_TESTED |
| ZH_TW_VOICE_PHYSICAL_DEVICE_STATUS | NOT_YET_TESTED |
| FALLBACK_POLICY | SUBTITLE_ONLY |
| CROSS_LANGUAGE_VOICE_FALLBACK | FORBIDDEN |
| SPEAKER_COUNTS | HERO=41; GRIK=37; CENTURION=19 |
| MISSING/DUPLICATE | 0 / 0 |

Content and acceptance are deliberately separated: both zh-TW subtitle and voice content are `COMPLETE`; integration is `COMPLETE` at checkpoint `5fd9def812c230aa7089a8388be932bea8e7d0f7`; subtitle final acceptance, voice perceptual QA, and voice physical-device QA remain `NOT_YET_TESTED`.

## EN-US reconciliation

| Field | Status |
|---|---|
| EN_US_SCRIPT_STATUS | PENDING_EXTERNAL_TASK |
| EN_US_VOICE_AUTHORITY_STATUS | PENDING_EXTERNAL_TASK |
| EN_US_PRODUCTION_AUDIO_STATUS | PENDING_EXTERNAL_TASK |
| EXISTING_CANONICAL_CONTENT | legacy four-shot English subtitles and voice paths |
| FINAL_TEN_SHOT_CONTENT | not present in accepted final Journey evidence |
| EN_US_SCRIPT_DEPENDS_ON_007 | YES |
| EN_US_VOICE_AUTHORITY_DEPENDS_ON_007 | YES |
| EN_US_PRODUCTION_AUDIO_DEPENDS_ON_OWNER_AUDITION | YES |
| FALLBACK_POLICY | SUBTITLE_ONLY |
| CROSS_LANGUAGE_VOICE_FALLBACK | FORBIDDEN |

The canonical legacy four-shot English path is existing evidence only. The final ten-shot script and voice authority are pending `_007`; no English final production completion is claimed. Missing locale voice remains subtitle-only and cross-language voice fallback is forbidden.

## Presentation FX preflight versus implementation

`PRESENTATION_FX_PREFLIGHT_STATUS=DESIGN/PREFLIGHT COMPLETE`; `PRESENTATION_FX_IMPLEMENTATION_STATUS=MISSING`. The 008A manifest defines presentation intent and mappings only; it defines no runtime trigger code and does not change gameplay authority.

| Measure | Value |
|---|---|
| ZONE3_REQUIRED_AMBIENCE_COUNT | 5 |
| ZONE3_REQUIRED_EVENT_SFX_COUNT | 9 |
| ZONE3_REQUIRED_VFX_COUNT | 9 |
| ZONE3_OPTIONAL_VFX_COUNT | 1 |
| ZONE3_REQUIRED_LIGHT_COUNT | 1 |
| ZONE3_REQUIRED_TRANSITION_COUNT | 1 |
| ZONE3_TOTAL_PRESENTATION_CUE_COUNT | 26 |
| REUSABLE_AUDIO_ASSET_COUNT | 2 |
| NEW_AUDIO_ASSET_COUNT_REQUIRED | 13 |
| NEW_VFX_ASSET_COUNT_REQUIRED | 0 |
| CODE_ONLY_VFX_COUNT | 12 |
| AUDIO_EVALUATION_ROW_COUNT | 15 |
| PRIMARY_AUDIO_CUE_COUNT | 14 |
| TRANSITION_AUDIO_CUE_COUNT | 1 |
| AUDIO_CUE_TO_ASSET_MAPPING_COMPLETE | YES |

The accounting is not one-cue-one-file: 15 audio evaluation rows contain 2 reusable assets and 13 new assets; the cue sheet has 14 primary audio cues plus one transition row. The transition row combines a new wind placeholder and code-only fog VFX, while code-only VFX/light definitions do not require new raster/audio files.

### Exact 26-cue mapping from 008A

| CUE_ID | SHOT_ID | CATEGORY | EVALUATION_ID | ASSET_PATH_OR_PLACEHOLDER | REUSABLE_EXISTING_ASSET | NEW_ASSET_REQUIRED | RUNTIME_TRIGGER_CODE |
|---|---|---|---|---|---|---|---|
| Z3_A01 | SHOT01<br>SHOT02<br>SHOT03<br>SHOT04<br>SHOT05<br>SHOT06<br>SHOT07<br>SHOT08<br>SHOT09<br>SHOT10 | AMBIENCE | CAVE_ROOM_TONE | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/ambience/zone3_ambience_cave_room_tone.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_A02 | SHOT01<br>SHOT03<br>SHOT05<br>SHOT06<br>SHOT10 | AMBIENCE | DISTANT_CAVE_WIND | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/ambience/zone3_ambience_distant_cave_wind.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_A03 | SHOT01<br>SHOT04<br>SHOT06<br>SHOT08 | AMBIENCE | DISTANT_FAMILY_ACTIVITY | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/ambience/zone3_ambience_distant_family_activity.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_A04 | SHOT07 | AMBIENCE | TRIAL_TENSION_AMBIENCE | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/ambience/zone3_ambience_trial_tension.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_A05 | SHOT08 | AMBIENCE | FRAGILE_TRUCE_AMBIENCE | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/ambience/zone3_ambience_fragile_truce.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S01 | SHOT01 | SFX | REFUGEE_FOOTSTEPS | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/sfx/zone3_sfx_refugee_footsteps.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S02 | SHOT02 | SFX | BELONGINGS_MOVEMENT | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/sfx/zone3_sfx_belongings_movement.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S03 | SHOT03<br>SHOT04<br>SHOT05 | SFX | WATER_DRIP | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/sfx/zone3_sfx_water_drip.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S04 | SHOT03<br>SHOT05<br>SHOT08 | SFX | SHUI_WATER_SPIRIT_SOUND | assets/e10/audio/zone2/sfx/zone2_sfx_shui_reaction_2.mp3 | assets/e10/audio/zone2/sfx/zone2_sfx_shui_reaction_2.mp3 | NO | NOT_DEFINED_IN_008A |
| Z3_S05 | SHOT05 | SFX | ROCKFALL | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/sfx/zone3_sfx_rockfall.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S06 | SHOT05 | SFX | BLOCKED_WATER_FLOW | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/ambience/zone3_ambience_blocked_water_flow.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S07 | SHOT06 | SFX | CENTURION_ARMOR | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/sfx/zone3_sfx_centurion_armor.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S08 | SHOT07 | SFX | CENTURION_SPEAR_PLANT | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/sfx/zone3_sfx_centurion_spear_plant.mp3 | — | YES | NOT_DEFINED_IN_008A |
| Z3_S09 | SHOT09 | SFX | STONE_SHARD_PHYSICAL_HANDOFF | assets/e10/audio/zone1/sfx/zone1_sfx_shot07_stone_placement.mp3 | assets/e10/audio/zone1/sfx/zone1_sfx_shot07_stone_placement.mp3 | NO | NOT_DEFINED_IN_008A |
| Z3_L01 | SHOT01<br>SHOT02<br>SHOT03<br>SHOT04<br>SHOT05<br>SHOT06<br>SHOT07<br>SHOT08<br>SHOT09<br>SHOT10 | LIGHT | SUBTLE_WARM_LIGHT_FLICKER | CODE_ONLY_LIGHT:SUBTLE_WARM_LIGHT_FLICKER | — | NO | NOT_DEFINED_IN_008A |
| Z3_V01 | SHOT01<br>SHOT02<br>SHOT03<br>SHOT04<br>SHOT05<br>SHOT06<br>SHOT07<br>SHOT08<br>SHOT09<br>SHOT10 | VFX | CAVE_DUST_MOTES | CODE_ONLY_VFX:CAVE_DUST_MOTES | — | NO | NOT_DEFINED_IN_008A |
| Z3_V02 | SHOT05 | VFX | WATER_REFLECTION_SHIMMER | CODE_ONLY_VFX:WATER_REFLECTION_SHIMMER | — | NO | NOT_DEFINED_IN_008A |
| Z3_V03 | SHOT03<br>SHOT05<br>SHOT08 | VFX | SHUI_WATER_PARTICLES | CODE_ONLY_VFX:SHUI_WATER_PARTICLES | — | NO | NOT_DEFINED_IN_008A |
| Z3_V04 | SHOT03<br>SHOT05<br>SHOT08 | VFX | SHUI_TRANSLUCENT_PULSE | CODE_ONLY_VFX:SHUI_TRANSLUCENT_PULSE | — | NO | NOT_DEFINED_IN_008A |
| Z3_V05 | SHOT05 | VFX | ROCK_DUST_FALL | CODE_ONLY_VFX:ROCK_DUST_FALL | — | NO | NOT_DEFINED_IN_008A |
| Z3_V06 | SHOT05 | VFX | SMALL_ROCK_DEBRIS | CODE_ONLY_VFX:SMALL_ROCK_DEBRIS | — | NO | NOT_DEFINED_IN_008A |
| Z3_V07 | SHOT05 | VFX | BLOCKED_WATER_MIST | CODE_ONLY_VFX:BLOCKED_WATER_MIST | — | NO | NOT_DEFINED_IN_008A |
| Z3_V08 | SHOT07 | VFX | CENTURION_SPEAR_DUST_IMPULSE | CODE_ONLY_VFX:CENTURION_SPEAR_DUST_IMPULSE | — | NO | NOT_DEFINED_IN_008A |
| Z3_V09 | SHOT07 | VFX | TRIAL_SUBTLE_ENVIRONMENT_TENSION | CODE_ONLY_VFX:TRIAL_SUBTLE_ENVIRONMENT_TENSION | — | NO | NOT_DEFINED_IN_008A |
| Z3_V10 | SHOT08 | VFX | TRUCE_ENVIRONMENT_CALMING | CODE_ONLY_VFX:TRUCE_ENVIRONMENT_CALMING | — | NO | NOT_DEFINED_IN_008A |
| Z3_T01 | SHOT10 | TRANSITION | MISTY_FOREST_WIND_TRANSITION<br>MISTY_FOREST_FOG_TRANSITION | PLACEHOLDER_AUDIO:assets/e10/audio/zone3/transition/zone3_to_zone4_misty_forest_wind.mp3;CODE_ONLY_VFX:MISTY_FOREST_FOG_TRANSITION | — | YES | NOT_DEFINED_IN_008A |

`AUDIO_CUE_TO_ASSET_MAPPING_COMPLETE=YES`. All replay recommendations in the manifest are presentation reuse with no reward.

## BGM and audio controls

| Field | Zone 1 | Zone 2 | Zone 3 / decision |
|---|---|---|---|
| BGM_STATUS | COMPLETE | COMPLETE | MISSING |
| V1_REQUIRED | — | — | YES |
| INTENTIONALLY_NOT_REQUIRED | — | — | NO |
| OWNER_DECISION_REQUIRED | — | — | NO |
| OWNER_DECISION | — | — | Preserve Z3-017 as V1_REQUIRED=YES; no new creative reclassification was made. |

BGM is `V1_REQUIRED=YES` and currently `MISSING` for Zone 3; this preserves the prior DoD rather than making a new creative policy decision.

| Control | Zone 1 parity | Zone 2 parity | Zone 3 status |
|---|---|---|---|
| MUTE_SUPPORT | COMPLETE | COMPLETE | INHERITS_GLOBAL_MUTE_NOT_FINAL_INTEGRATED |
| VOICE_VOLUME | FIXED_PLAYBACK_LEVEL_ONLY | FIXED_PLAYBACK_LEVEL_ONLY | FIXED_PLAYBACK_LEVEL_ONLY |
| SFX_VOLUME | FIXED_PLAYBACK_LEVEL_ONLY | FIXED_PLAYBACK_LEVEL_ONLY | FIXED_PLAYBACK_LEVEL_ONLY |
| AMBIENCE_VOLUME | FIXED_PLAYBACK_LEVEL_ONLY | FIXED_PLAYBACK_LEVEL_ONLY | NOT_INTEGRATED |
| BGM_VOLUME | FIXED_PLAYBACK_LEVEL_ONLY | FIXED_PLAYBACK_LEVEL_ONLY | NOT_INTEGRATED |
| USER_VOLUME_SLIDER_EVIDENCE | NO | NO | NO |

Exact parity: global mute is complete and persisted; the architecture exposes fixed playback levels only, with no evidenced user-facing volume slider or separate user mixer controls. Zone 3 ambience/BGM are not integrated.

## Layer status reconciliation

For each layer, `DESIGN_COMPLETE`, `IMPLEMENTATION_COMPLETE`, `AUTOMATED_QA_COMPLETE`, and `FINAL_ACCEPTANCE_COMPLETE` are kept independent.

| ITEM_ID | LAYER | DESIGN_COMPLETE | IMPLEMENTATION_COMPLETE | AUTOMATED_QA_COMPLETE | FINAL_ACCEPTANCE_COMPLETE |
|---|---|---|---|---|---|
| Z3-019 | VFX | YES | NO | YES | NO |
| Z3-020 | PARTICLES | YES | NO | YES | NO |
| Z3-021 | LIGHTING | YES | NO | YES | NO |
| Z3-022 | CAMERA_FX | NO | NO | YES | NO |
| Z3-024 | TRANSITIONS | YES | NO | YES | NO |
| Z3-030 | REPLAY | YES | NO | YES | NO |
| Z3-031 | REDUCED_MOTION | YES | NO | YES | NO |
| Z3-032 | FAILURE_FALLBACK | YES | NO | YES | NO |
| Z3-034 | SCENE_CLEANUP | YES | NO | YES | NO |

VFX, particles, lighting, transitions, reduced motion, fallback, cleanup, and replay remain open at implementation and/or final acceptance. Static art is not counted as VFX.

## Browser QA reconciliation

| Field | Status |
|---|---|
| PLAYWRIGHT_INFRA_AVAILABLE | YES |
| PLAYWRIGHT_INFRA_HEAD | dddefed7b27ee17d65aba89823a47b0e0bd0d0ad |
| PREVIOUS_PLAYWRIGHT_BLOCKER_RESOLVED | YES |
| ZONE3_REAL_BROWSER_TEST_EXECUTED | PARTIAL |
| DESKTOP_BROWSER_QA | PARTIAL |
| IPAD_LANDSCAPE_BROWSER_QA | NOT_YET_TESTED |
| IPAD_PORTRAIT_BROWSER_QA | NOT_YET_TESTED |
| MOBILE_BROWSER_QA | NOT_YET_TESTED |
| MEDIA_RUNTIME_BROWSER_QA | NOT_YET_TESTED |
| LOCALE_SWITCH_BROWSER_QA | NOT_YET_TESTED |
| REPLAY_BROWSER_QA | PARTIAL |
| KNOWN_BROWSER_PRODUCT_TEST_DEBT_COUNT | 3 |
| INFRASTRUCTURE_BLOCKER | Resolved; remaining browser gaps are product-test debt, not infrastructure failure. |

Known product-test debt and relevance:

| Debt | Relevant DoD item(s) | Reconciliation |
|---|---|---|
| E9_LAYOUT | Z3-039 | Keeps real-browser QA acceptance open; does not classify Playwright infrastructure as unavailable and does not downgrade accepted content. |
| E9_FETCH | Z3-039 | Keeps browser/runtime transport evidence open; does not classify Playwright infrastructure as unavailable and does not create gameplay authority. |
| REPLAY_REAL_CLICK_FINAL_RETURN_ASSERTION | Z3-030<br>Z3-039 | Keeps replay browser acceptance and replay integration closure open until the final-return assertion passes; replay remains presentation-only. |

The three debts are not infrastructure failures. E9 layout and fetch keep browser/runtime acceptance open at `Z3-039`; the replay real-click final-return assertion also keeps `Z3-030` replay integration open. They do not downgrade accepted content or create gameplay authority.

## Human, physical, and quality gates

| Layer | Status | Evidence distinction |
|---|---|---|
| AUTOMATED_ASSET_QA | COMPLETE | Candidate manifest/hash/dimension checks; not human acceptance. |
| AUTOMATED_RUNTIME_QA | COMPLETE | Focused candidate suites: WORLD 12 passed; HERO 14 passed; JOURNEY 53 passed; E055/legacy 20 passed; QUALITY 50 passed, 5 skipped. |
| REAL_BROWSER_QA | PARTIAL | Playwright available; execution partial with 3 product debts; not infrastructure failure. |
| PERCEPTUAL_AUDIO_QA | NOT_YET_TESTED | Owner audition/listening remains open. |
| PHYSICAL_IPAD_LANDSCAPE_QA | NOT_YET_TESTED | No physical-device evidence inferred from viewport automation. |
| PHYSICAL_IPAD_PORTRAIT_QA | NOT_YET_TESTED | No physical-device evidence inferred from viewport automation. |
| PHYSICAL_IPHONE_QA | NOT_YET_TESTED | No physical-device evidence inferred from viewport automation. |

## Completion groups (proposed only)

No tasks were created. These are the smallest bounded packages represented by the existing open rows.

### COMPLETION_GROUP_A
| OWNER_LANE | WORLD/JOURNEY/HERO/SYSTEMS |
| ITEM_IDS | Z3-001<br>Z3-002<br>Z3-003<br>Z3-006<br>Z3-007<br>Z3-009<br>Z3-018<br>Z3-025<br>Z3-028<br>Z3-029<br>Z3-032<br>Z3-033<br>Z3-034 |
| DEPENDENCY | Accepted WORLD/HERO/JOURNEY packages plus server-owned progression/reward/Lord seams. |
| CAN_RUN_IN_PARALLEL_WITH | COMPLETION_GROUP_B<br>COMPLETION_GROUP_C |
| MUST_WAIT_FOR | Final runtime integration boundary and server-fact-only handoff review. |

### COMPLETION_GROUP_B
| OWNER_LANE | JOURNEY/QUALITY |
| ITEM_IDS | Z3-010<br>Z3-011<br>Z3-012<br>Z3-013<br>Z3-014<br>Z3-015<br>Z3-017 |
| DEPENDENCY | 008A cue mapping, 5fd zh-TW checkpoint, pending en-US _007, and Owner audio production/audition. |
| CAN_RUN_IN_PARALLEL_WITH | COMPLETION_GROUP_A<br>COMPLETION_GROUP_C |
| MUST_WAIT_FOR | _007 for en-US script/voice authority and Owner audition before final en-US production acceptance. |

### COMPLETION_GROUP_C
| OWNER_LANE | WORLD/JOURNEY/QUALITY |
| ITEM_IDS | Z3-019<br>Z3-020<br>Z3-021<br>Z3-022<br>Z3-023<br>Z3-024<br>Z3-030<br>Z3-031 |
| DEPENDENCY | 008A presentation FX design and final Journey visual slot/lifecycle. |
| CAN_RUN_IN_PARALLEL_WITH | COMPLETION_GROUP_A<br>COMPLETION_GROUP_B |
| MUST_WAIT_FOR | Final runtime binding before implementation acceptance; Owner decision if parallax remains intentionally different. |

### COMPLETION_GROUP_D
| OWNER_LANE | SYSTEMS/QUALITY |
| ITEM_IDS | Z3-026<br>Z3-035<br>Z3-036<br>Z3-039<br>Z3-040 |
| DEPENDENCY | Integrated candidate with final audio/FX plus existing global settings. |
| CAN_RUN_IN_PARALLEL_WITH | COMPLETION_GROUP_B<br>COMPLETION_GROUP_C |
| MUST_WAIT_FOR | Integrated candidate and audio for perceptual review, plus physical devices for device acceptance; Playwright infrastructure is available. |

## Full 40-row machine-readable matrix

The JSON companion is the machine-readable authority. This report repeats all 40 rows and all required fields.

| ITEM_ID | ITEM_NAME | CATEGORY | OWNER_LANE | V1_REQUIRED | CONTENT_STATUS | INTEGRATION_STATUS | AUTOMATED_QA_STATUS | HUMAN_QA_STATUS | PHYSICAL_DEVICE_STATUS | OVERALL_STATUS | EVIDENCE_HEAD | EVIDENCE_PATH_OR_TEST | OPEN_REASON | DEPENDENCIES | MINIMUM_CLOSURE_SCOPE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Z3-001 | STORY | STORY | WORLD/JOURNEY | YES | COMPLETE | PENDING_EXTERNAL_TASK | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 39c587a216f6cc13efe572066d9d8f0299960f1b | docs/audits/w1_04_zone3_full_vertical_slice_completeness_parity_audit_004.md<br>adventure_zone_progression_authority.py<br>tests/test_e055_zone3_vertical_slice.py | Story content is accepted, but final candidate-to-canonical runtime handoff and final human/device acceptance remain open. | final Journey runtime integration<br>server-owned progression authority<br>human/device acceptance | Integrate the accepted story presentation through the existing server-fact handoff; prove presentation completion cannot mutate progression or reward authority. |
| Z3-002 | CINEMATIC_ART | CINEMATIC_ART | WORLD/JOURNEY | YES | COMPLETE | PENDING_EXTERNAL_TASK | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 39c587a216f6cc13efe572066d9d8f0299960f1b<br>f77bce46302974c8a8aa9d296ae0ea548a707691 | assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json<br>tests/test_w1_01_zone3_10shot_asset_ingestion.py | Ten owner-approved runtime images pass candidate QA but are not integrated on canonical master. | WORLD ten-shot package<br>Journey responsive slot | Integrate ten runtime derivatives and preserve source hashes, replay presentation-only behavior, and failure fallback. |
| Z3-003 | WORLD_ART | WORLD_ART | WORLD | YES | COMPLETE | PENDING_EXTERNAL_TASK | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 39c587a216f6cc13efe572066d9d8f0299960f1b<br>f77bce46302974c8a8aa9d296ae0ea548a707691 | assets/e10/art/zone3/zone3-world-asset-package.json<br>tests/test_w1_01_zone3_world_asset_package.py | Environment and landmark content is accepted in the candidate but final world binding is open. | WORLD asset package<br>responsive world binding | Bind environment plate and landmark presentation without changing map/progression authority. |
| Z3-004 | MONSTERS | MONSTERS | HERO/SYSTEMS | YES | COMPLETE | COMPLETE | COMPLETE | NOT_APPLICABLE | NOT_APPLICABLE | COMPLETE | 616d51b17abe010de1e862382ca4db7bec65936f | adventure_zone3_monster_authority.py<br>tests/test_e055_zone3_vertical_slice.py |  | server monster authority | Preserve exact 13 normal IDs and zero elites. |
| Z3-005 | BATTLEFIELD_BOSS | BATTLEFIELD_BOSS | HERO/SYSTEMS | YES | COMPLETE | COMPLETE | COMPLETE | NOT_APPLICABLE | NOT_APPLICABLE | COMPLETE | 616d51b17abe010de1e862382ca4db7bec65936f<br>8fa4184e775517403f66a3d56e7357d3470e67cf | tests/test_e055_zone3_vertical_slice.py<br>zone3_runtime_asset_bindings.py |  | server boss binding<br>Lord boundary | Preserve legacy_bf_03_boss as distinct from goblin_centurion. |
| Z3-006 | LORD | LORD | HERO/SYSTEMS | YES | COMPLETE | PENDING_EXTERNAL_TASK | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 8fa4184e775517403f66a3d56e7357d3470e67cf<br>616d51b17abe010de1e862382ca4db7bec65936f | zone3_runtime_asset_bindings.py<br>tests/test_w1_02_zone3_lord_final_asset_ingestion_005.py<br>tests/test_w1_02_zone3_monster_lord_runtime_asset_binding_004.py | Six Lord presentation slots pass candidate checks but are not canonical integration; art cannot create eligibility. | six-slot Lord presentation package<br>server Lord eligibility | Bind six slots to existing goblin_centurion identity and eligibility; missing art hides the same identity. |
| Z3-007 | GAMEPLAY_HANDOFF | GAMEPLAY_HANDOFF | JOURNEY/SYSTEMS | YES | COMPLETE | PENDING_EXTERNAL_TASK | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>5fd9def812c230aa7089a8388be932bea8e7d0f7 | adventure_zone_progression_authority.py<br>docs/planning/w1_03_journey_zone3_vertical_slice_wiring_002.md<br>tests/test_w1_03_journey_zone3_vertical_slice_wiring.py | Authority seam exists, but final candidate-to-canonical handoff is not closed. | server-selected Zone<br>existing progression authority<br>final Journey runtime | Consume server facts only and prove cinematic completion cannot clear or unlock a Zone. |
| Z3-008 | SERVER_AUTHORITY_BOUNDARIES | SERVER_AUTHORITY_BOUNDARIES | SYSTEMS | YES | COMPLETE | COMPLETE | COMPLETE | NOT_APPLICABLE | NOT_APPLICABLE | COMPLETE | 616d51b17abe010de1e862382ca4db7bec65936f<br>8fa4184e775517403f66a3d56e7357d3470e67cf<br>5fd9def812c230aa7089a8388be932bea8e7d0f7 | adventure_zone3_monster_authority.py<br>adventure_zone_progression_authority.py<br>adventure_zone_star_progression.py<br>js/game/cinematic_replay.js |  | existing authority modules | Keep presentation read-only, fail closed, and separate from reward/progression/Lord state. |
| Z3-009 | ZH_TW_SUBTITLES | ZH_TW_SUBTITLES | JOURNEY | YES | COMPLETE | COMPLETE | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | f77bce46302974c8a8aa9d296ae0ea548a707691<br>5fd9def812c230aa7089a8388be932bea8e7d0f7 | assets/e10/i18n/zone3/zone3-cinematic-subtitles.json<br>tests/test_w1_03_journey_zone3_i18n_subtitle_voice_production.py<br>tests/test_w1_03_journey_zone3_vertical_slice_wiring.py | 97 beats, missing 0, duplicate 0; checkpoint integration is complete, final browser/device acceptance is not tested. | 5fd9def checkpoint<br>final acceptance | Retain all 97 beats, locale scoping, duplicate rejection, and subtitle-only behavior. |
| Z3-010 | ZH_TW_VOICE | ZH_TW_VOICE | JOURNEY | YES | COMPLETE | COMPLETE | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | f77bce46302974c8a8aa9d296ae0ea548a707691<br>5fd9def812c230aa7089a8388be932bea8e7d0f7 | assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json<br>tools/e10_zone3_audio/zone3_voice_audition_manifest.json<br>tests/test_w1_03_journey_zone3_final_audio_production.py | 97 locale-scoped voice refs are checkpoint-integrated; perceptual and physical acceptance are not tested. | 5fd9def checkpoint<br>Owner audition<br>physical playback | Retain 97 zh-TW refs, forbid cross-language fallback, and close listening/device gates. |
| Z3-011 | EN_US_SUBTITLES | EN_US_SUBTITLES | JOURNEY | YES | PENDING_EXTERNAL_TASK | PENDING_EXTERNAL_TASK | NOT_YET_TESTED | PENDING_EXTERNAL_TASK | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691 | index.html legacy four-shot Zone 3 configuration<br>i18n.js<br>W1_03_JOURNEY_ZONE3_EN_US_SCRIPT_AND_VOICE_AUTHORITY_RECOVERY_007 | Canonical legacy four-shot English path exists, but final ten-shot English script recovery _007 is not completed. | pending _007 script authority<br>ten-shot content integration | Complete and Owner-approve the ten-shot en-US script before binding it; do not infer it from zh-TW. |
| Z3-012 | EN_US_VOICE | EN_US_VOICE | JOURNEY | YES | PENDING_EXTERNAL_TASK | PENDING_EXTERNAL_TASK | NOT_YET_TESTED | PENDING_EXTERNAL_TASK | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691 | index.html legacy four-shot English voice paths<br>assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json<br>W1_03_JOURNEY_ZONE3_EN_US_SCRIPT_AND_VOICE_AUTHORITY_RECOVERY_007 | Legacy four-shot English voice exists; final en-US authority/production is pending _007 and Owner audition. | pending _007 voice authority<br>Owner audition<br>final en-US audio | Complete en-US authority and production separately; missing voice remains subtitle-only with no zh-TW fallback. |
| Z3-013 | AMBIENCE | AMBIENCE | JOURNEY | YES | MISSING | MISSING | NOT_YET_TESTED | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json<br>assets/e10/audio/zone3/ is absent at 008A source head<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | 008A defines five required ambience cues but supplies placeholders only; no production Zone 3 ambience package is integrated. | 008A preflight mapping<br>audio production<br>loop lifecycle | Produce and integrate five required ambience cues with mute, replay, autoplay fallback, and cleanup coverage. |
| Z3-014 | EVENT_SFX | EVENT_SFX | JOURNEY | YES | MISSING | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>616d51b17abe010de1e862382ca4db7bec65936f | docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json<br>index.html legacy Zone 3 generic cues<br>tests/test_w1_01_world_zone3_presentation_fx_preflight.py | Preflight contains nine required SFX slots, but final production assets are placeholders; legacy generic cues are only partial runtime coverage. | 008A preflight<br>new event SFX production<br>final Journey cue binding | Produce and bind nine required event cues without gameplay triggers; retain replay no-reward semantics. |
| Z3-015 | CREATURE_OR_CHARACTER_SFX | CREATURE_OR_CHARACTER_SFX | JOURNEY | YES | MISSING | MISSING | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>8fa4184e775517403f66a3d56e7357d3470e67cf | docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json<br>assets/e10/audio/zone2/sfx/zone2_sfx_bee_close.mp3 | Zone 3-specific creature/character SFX are not produced; Zone 2 bee/slime cues cannot be reused as Zone 3 authority. | audio design decision<br>new Zone 3 assets<br>missing-audio fallback | Define and produce only required Zone 3 creature/character cues, with no Lord or reward semantics. |
| Z3-016 | NONVERBAL_CHARACTER_AUDIO | NONVERBAL_CHARACTER_AUDIO | JOURNEY | NO | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | NOT_APPLICABLE | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>f77bce46302974c8a8aa9d296ae0ea548a707691 | 008A STORY_CONTRACTS.SHUI_HUMAN_SPEAKING=false<br>existing 40-item taxonomy | No separate approved nonverbal-only acceptance layer exists in the preserved taxonomy. | Owner scope decision if changed | Keep NOT_APPLICABLE unless Owner adds a distinct nonverbal production requirement. |
| Z3-017 | BGM_OR_MUSIC | BGM_OR_MUSIC | JOURNEY | YES | MISSING | MISSING | NOT_YET_TESTED | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | 616d51b17abe010de1e862382ca4db7bec65936f<br>00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | assets/e10/audio/zone1/zone1-audio-package.json<br>assets/e10/audio/zone2/zone2-audio-package.json<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Preserved 40-item definition marks Zone 3 BGM V1-required; no Zone 3 BGM production package is present. | Owner-approved V1 music package<br>audio settings<br>replay/cleanup | Produce and integrate required Zone 3 music, or obtain separate Owner reclassification before changing this row. |
| Z3-018 | UI_AUDIO | UI_AUDIO | JOURNEY/SYSTEMS | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | sound.js<br>js/e9/top_hud.js<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Global UI audio and mute exist, but Zone 3 final control/cue acceptance is not integrated. | global UI audio<br>final Zone 3 controls | Verify captions, buttons, replay, blocked, and handoff feedback under mute and final audio. |
| Z3-019 | VFX | VFX | WORLD/JOURNEY | YES | COMPLETE | MISSING | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d | docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json<br>tests/test_w1_01_world_zone3_presentation_fx_preflight.py | 008A designates 12 code-only VFX definitions and zero new VFX assets, but no canonical Zone 3 implementation is integrated. | 008A code-only VFX contract<br>Journey runtime compositor | Implement approved presentation-only VFX with reduced-motion and cleanup behavior. |
| Z3-020 | PARTICLES | PARTICLES | WORLD/JOURNEY | YES | COMPLETE | MISSING | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d | docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json<br>tests/test_w1_01_world_zone3_presentation_fx_preflight.py | Particle behavior is specified as code-only bounded particles, but no Zone 3 particle implementation exists on canonical master. | code-only particle contract<br>lifecycle owner | Implement bounded particles and prove cleanup at shot, exit, replay, and route transitions. |
| Z3-021 | LIGHTING | LIGHTING | WORLD/JOURNEY | YES | COMPLETE | MISSING | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>616d51b17abe010de1e862382ca4db7bec65936f | docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json<br>index.html generic cinematic overlay styles | Preflight lighting contract is complete, but only generic canonical overlays exist; final Zone 3 lighting is not integrated. | 008A light cue<br>final runtime styling<br>reduced motion | Bind authored Zone 3 lighting treatment and preserve reduced-motion behavior. |
| Z3-022 | CAMERA_MOTION | CAMERA_MOTION | JOURNEY | YES | PARTIAL | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691 | index.html legacy storyboardDrift<br>css/e9/zone3_vertical_slice.css<br>tests/test_w1_03_journey_zone3_cinematic_asset_slot_responsive_binding.py | Generic drift and responsive candidate positions exist, but final ten-shot camera treatment is not canonical. | final ten-shot runtime<br>responsive camera contract | Bind final shot camera treatment and reduced-motion behavior without changing gameplay state. |
| Z3-023 | PARALLAX | PARALLAX | WORLD/JOURNEY | YES | MISSING | MISSING | NOT_YET_TESTED | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | 616d51b17abe010de1e862382ca4db7bec65936f<br>00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d | previous 40-item audit<br>008A static art and code-only FX manifest | No authored Zone 3 multi-plane parallax contract or implementation is evidenced. | Owner art-direction decision<br>final layer model | Provide bounded V1 parallax or obtain Owner intentional-difference reclassification. |
| Z3-024 | TRANSITIONS | TRANSITIONS | JOURNEY | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>616d51b17abe010de1e862382ca4db7bec65936f | docs/planning/w1_01_world_zone3_presentation_fx_cue_manifest_008a.json<br>index.html cinematic transition styles<br>tests/test_w1_01_world_zone3_presentation_fx_preflight.py | One transition cue is preflight-complete and generic transitions exist, but final runtime sequencing and interruption cleanup are open. | 008A transition cue<br>final Journey timeline<br>cleanup | Integrate transition sequencing, replay, reduced motion, and interruption cleanup. |
| Z3-025 | UI_FEEDBACK | UI_FEEDBACK | JOURNEY/QUALITY | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | index.html cinematic overlay/caption controls<br>components/adventure/zone3_vertical_slice.html<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Generic UI feedback and candidate controls exist; final Zone 3 integrated entry/replay/handoff feedback is open. | final Journey runtime<br>quality acceptance | Verify entry, skip, replay, blocked, caption, and gameplay-handoff feedback states. |
| Z3-026 | AUDIO_VOLUME_CONTROL | AUDIO_VOLUME_CONTROL | SYSTEMS/JOURNEY | YES | PARTIAL | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f | sound.js<br>js/e9/top_hud.js<br>index.html playback role volume constants | Architecture has fixed playback levels and global mute, but no user-facing volume control is evidenced. | existing settings architecture<br>Owner V1 settings decision | Preserve fixed role levels and close only the required user-settings contract; do not invent a mixer. |
| Z3-027 | MUTE_BEHAVIOR | MUTE_BEHAVIOR | SYSTEMS | YES | COMPLETE | COMPLETE | COMPLETE | NOT_APPLICABLE | NOT_APPLICABLE | COMPLETE | 616d51b17abe010de1e862382ca4db7bec65936f | sound.js<br>js/e9/top_hud.js<br>js/game/cinematic_replay.js |  | SFX.muted global behavior | Keep all future Zone 3 audio paths mute-aware and replay-safe. |
| Z3-028 | SUBTITLE_VISIBILITY | SUBTITLE_VISIBILITY | JOURNEY/QUALITY | YES | COMPLETE | PARTIAL | NOT_YET_TESTED | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | index.html caption rendering<br>assets/e10/i18n/zone3/zone3-cinematic-subtitles.json<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Caption rendering exists, but final Zone 3 visibility across locale, replay, missing voice, and reduced motion is not accepted. | global caption behavior<br>final Journey runtime<br>QA flows | Add focused acceptance for subtitle visibility without changing subtitle content or authority. |
| Z3-029 | LOCALE_SWITCHING | LOCALE_SWITCHING | JOURNEY/SYSTEMS | YES | PARTIAL | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>5fd9def812c230aa7089a8388be932bea8e7d0f7 | i18n.js<br>assets/e10/i18n/zone3/zone3-cinematic-subtitles.json<br>assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json | Shell supports en/zh, but final en-US content is pending _007 and final Zone 3 locale parity is incomplete. | en-US _007<br>zh-TW checkpoint<br>no cross-language fallback | Ensure locale switching changes presentation only and issues no reward, progression, or completion mutation. |
| Z3-030 | REPLAY | REPLAY | SYSTEMS/JOURNEY | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>5fd9def812c230aa7089a8388be932bea8e7d0f7 | js/game/cinematic_replay.js<br>index.html replay functions<br>tests/test_w1_03_journey_zone3_vertical_slice_wiring.py | Authority-safe generic replay exists, but final ten-shot image/audio/VFX parity is not canonical and the replay real-click final-return assertion remains open. | final content packages<br>replay presentation contract | Preserve locale, subtitle, voice, image, SFX, ambience, VFX, and transition while proving no reward/clear/unlock/Lord mutation. |
| Z3-031 | REDUCED_MOTION | REDUCED_MOTION | JOURNEY/QUALITY | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | index.html reduced-motion CSS<br>css/e9/zone3_vertical_slice.css<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Global reduced-motion behavior and candidate rules exist, but all final Zone 3 effects are not integrated and accepted. | final VFX/camera/transition layers<br>global prefers-reduced-motion | Ensure every new Zone 3 animation honors the existing reduced-motion control. |
| Z3-032 | ASSET_FAILURE_FALLBACK | ASSET_FAILURE_FALLBACK | WORLD/JOURNEY | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 39c587a216f6cc13efe572066d9d8f0299960f1b<br>8fa4184e775517403f66a3d56e7357d3470e67cf<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | tests/test_w1_01_zone3_10shot_asset_ingestion.py<br>tests/test_w1_02_zone3_lord_final_asset_ingestion_005.py<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Candidate package rejection and same-identity fallback are tested, but final canonical runtime failure paths are open. | final asset manifests<br>Journey integration<br>server authority | Reject missing/hash-invalid/duplicate assets and degrade presentation only; never mutate Zone, reward, item, Lord, or mastery state. |
| Z3-033 | AUDIO_FAILURE_FALLBACK | AUDIO_FAILURE_FALLBACK | JOURNEY/SYSTEMS | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | f77bce46302974c8a8aa9d296ae0ea548a707691<br>5fd9def812c230aa7089a8388be932bea8e7d0f7<br>00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d | assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json<br>tests/test_w1_03_journey_zone3_final_audio_production.py<br>tests/test_w1_01_world_zone3_presentation_fx_preflight.py | Subtitle-only missing-voice policy is complete, but final ambience/SFX/BGM package integration is open. | locale-scoped audio manifest<br>final audio packages<br>autoplay policy | Make missing voice/SFX/ambience/BGM local presentation failures with no cross-language voice or gameplay mutation. |
| Z3-034 | SCENE_CLEANUP | SCENE_CLEANUP | JOURNEY/SYSTEMS | YES | COMPLETE | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | index.html _stopIntroFilm<br>js/e9/shell.js<br>js/game/cinematic_replay.js<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Generic cleanup is implemented and tested, but explicit Zone 3 route-change/resource-owner coverage is not closed. | final runtime resource owner<br>route lifecycle<br>all future media/VFX | Cover loops, timers, animation frames, particles, listeners, temporary DOM, and media on shot/exit/replay/route changes. |
| Z3-035 | MOBILE_PERFORMANCE | MOBILE_PERFORMANCE | QUALITY/JOURNEY | YES | PARTIAL | PARTIAL | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | PARTIAL | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | index.html responsive cinematic styles<br>css/e9/zone3_vertical_slice.css<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md | Responsive safeguards and candidate automation exist, but no measured final Zone 3 device profile is accepted. | final integrated package<br>desktop/iPad/iPhone test matrix | Measure animation cost, particle count, audio concurrency, memory cleanup, and blur/filter cost on required device classes. |
| Z3-036 | PHYSICAL_DEVICE_ACCEPTANCE | PHYSICAL_DEVICE_ACCEPTANCE | QUALITY | YES | NOT_APPLICABLE | PENDING_EXTERNAL_TASK | NOT_YET_TESTED | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | 6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md<br>docs/quality/w1_05_wave1_acceptance_matrix.md | No physical iPad or iPhone acceptance evidence exists; this is a required later gate. | integrated candidate<br>physical devices<br>Owner QA | Run and record iPad landscape, iPad portrait, and iPhone/mobile acceptance. |
| Z3-037 | AUTOMATED_ASSET_QA | AUTOMATED_ASSET_QA | QUALITY/WORLD/HERO | YES | NOT_APPLICABLE | COMPLETE | COMPLETE | NOT_APPLICABLE | NOT_APPLICABLE | COMPLETE | 39c587a216f6cc13efe572066d9d8f0299960f1b<br>8fa4184e775517403f66a3d56e7357d3470e67cf<br>00dd5e07e67f2a83e9eb5a06b04d498e72af2e6d<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | tests/test_w1_01_zone3_10shot_asset_ingestion.py<br>tests/test_w1_01_world_zone3_presentation_fx_preflight.py<br>tests/test_w1_02_zone3_lord_final_asset_ingestion_005.py |  | candidate manifests | Retain hash, dimension, missing, duplicate, and package-boundary tests at final integration. |
| Z3-038 | AUTOMATED_RUNTIME_QA | AUTOMATED_RUNTIME_QA | QUALITY/JOURNEY/SYSTEMS | YES | NOT_APPLICABLE | COMPLETE | COMPLETE | NOT_APPLICABLE | NOT_APPLICABLE | COMPLETE | 616d51b17abe010de1e862382ca4db7bec65936f<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>5fd9def812c230aa7089a8388be932bea8e7d0f7<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | tests/test_e055_zone3_vertical_slice.py<br>tests/test_w1_03_journey_zone3_vertical_slice_wiring.py<br>tests/test_w1_03_journey_zone3_final_audio_production.py |  | canonical authority<br>candidate focused suites | Rerun focused suites after integration; do not use broad historical harness debt as a substitute. |
| Z3-039 | REAL_BROWSER_QA | REAL_BROWSER_QA | QUALITY/JOURNEY | YES | NOT_APPLICABLE | PARTIAL | PARTIAL | NOT_YET_TESTED | NOT_APPLICABLE | PARTIAL | 6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf<br>f77bce46302974c8a8aa9d296ae0ea548a707691<br>dddefed7b27ee17d65aba89823a47b0e0bd0d0ad | docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md<br>tests/e2e/run_w1_03_journey_zone3_vertical_slice_wiring.mjs | Playwright infrastructure is available at dddefed7b27ee17d65aba89823a47b0e0bd0d0ad and Zone 3 browser execution is PARTIAL. Three product-test debts remain: E9 layout, E9 fetch, and the replay real-click final-return assertion. These are product-test gaps, not infrastructure failures. | integrated candidate<br>E9 layout and fetch product-test closure<br>replay real-click final-return assertion<br>Owner browser matrix | Close E9 layout and fetch product tests plus the replay real-click final-return assertion, then complete the remaining desktop, iPad landscape/portrait, mobile, media, locale, and replay browser flows. |
| Z3-040 | PERCEPTUAL_AUDIO_QA | PERCEPTUAL_AUDIO_QA | QUALITY/JOURNEY | YES | NOT_APPLICABLE | COMPLETE | COMPLETE | NOT_YET_TESTED | NOT_YET_TESTED | MISSING | f77bce46302974c8a8aa9d296ae0ea548a707691<br>6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | tools/e10_zone3_audio/zone3_voice_audition_manifest.json<br>docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md<br>tests/test_w1_03_journey_zone3_final_audio_production.py | Technical manifest/decode checks pass, but Owner perceptual listening acceptance is not tested. | Owner audition<br>final audio package<br>physical playback | Complete human review for dialogue, ambience, SFX, BGM, fallback, and locale correctness. |

### Open required-item decomposition

| OPEN_REQUIRED_ITEM_COUNT | 33 |
| OPEN_REQUIRED_ITEMS | Z3-001<br>Z3-002<br>Z3-003<br>Z3-006<br>Z3-007<br>Z3-009<br>Z3-010<br>Z3-011<br>Z3-012<br>Z3-013<br>Z3-014<br>Z3-015<br>Z3-017<br>Z3-018<br>Z3-019<br>Z3-020<br>Z3-021<br>Z3-022<br>Z3-023<br>Z3-024<br>Z3-025<br>Z3-026<br>Z3-028<br>Z3-029<br>Z3-030<br>Z3-031<br>Z3-032<br>Z3-033<br>Z3-034<br>Z3-035<br>Z3-036<br>Z3-039<br>Z3-040 |

Each listed open ID appears exactly once in the matrix. Complete content remains complete even where acceptance is open; `ALREADY_COMPLETE_CONTENT_REWORK_COUNT=0`.

## Required report

```text
TASK=W1_04_SYSTEMS_ZONE3_40ITEM_DOD_EVIDENCE_AND_STATUS_RECONCILIATION_005
SOURCE_AUDIT_HEAD=291c1b64a8fbad84b8524a5393b3bafb6aba30c0
HEAD=REPORTED_IN_FINAL_TASK_RESULT
TREE=REPORTED_IN_FINAL_TASK_RESULT
BRANCH=codex/w1-04-zone3-40item-dod-evidence-reconciliation-005

TOTAL_DOD_ITEMS=40
COMPLETE_ITEM_COUNT=6
PARTIAL_ITEM_COUNT=25
MISSING_ITEM_COUNT=8
NOT_APPLICABLE_ITEM_COUNT=1
OPEN_REQUIRED_ITEM_COUNT=33

ZH_TW_SUBTITLE_CONTENT_STATUS=COMPLETE
ZH_TW_SUBTITLE_INTEGRATION_STATUS=COMPLETE
ZH_TW_SUBTITLE_FINAL_ACCEPTANCE_STATUS=NOT_YET_TESTED
ZH_TW_VOICE_CONTENT_STATUS=COMPLETE
ZH_TW_VOICE_INTEGRATION_STATUS=COMPLETE
ZH_TW_VOICE_PERCEPTUAL_QA_STATUS=NOT_YET_TESTED
ZH_TW_VOICE_PHYSICAL_DEVICE_STATUS=NOT_YET_TESTED

EN_US_SCRIPT_STATUS=PENDING_EXTERNAL_TASK
EN_US_VOICE_AUTHORITY_STATUS=PENDING_EXTERNAL_TASK
EN_US_PRODUCTION_AUDIO_STATUS=PENDING_EXTERNAL_TASK

PRESENTATION_FX_PREFLIGHT_STATUS=DESIGN/PREFLIGHT COMPLETE
PRESENTATION_FX_IMPLEMENTATION_STATUS=MISSING
AUDIO_CUE_TO_ASSET_MAPPING_COMPLETE=YES

BGM_STATUS=MISSING
BGM_OWNER_DECISION_REQUIRED=NO

AUDIO_SETTINGS_STATUS=PARTIAL
REDUCED_MOTION_STATUS=PARTIAL
REPLAY_STATUS=PARTIAL
FAILURE_FALLBACK_STATUS=PARTIAL
SCENE_CLEANUP_STATUS=PARTIAL

PLAYWRIGHT_INFRA_AVAILABLE=YES
ZONE3_REAL_BROWSER_TEST_EXECUTED=PARTIAL

PERCEPTUAL_AUDIO_QA_STATUS=NOT_YET_TESTED
PHYSICAL_DEVICE_QA_STATUS=NOT_YET_TESTED

ALREADY_COMPLETE_CONTENT_REWORK_COUNT=0
COMPLETION_GROUP_COUNT=4

FULL_40_ROW_MATRIX_PATH=docs/audits/w1_04_zone3_40item_dod_evidence_reconciled_matrix_005.json
FULL_40_ROW_MATRIX_INCLUDED_IN_REPORT=YES

READY_FOR_BOUNDED_COMPLETION_TASKS=YES
READY_FOR_FINAL_INTEGRATED_CANDIDATE=NO
PRODUCT_DEFECTS_FOUND=NO
APP_PY_CHANGED=NO
RUNTIME_PRODUCT_FILES_CHANGED=NO
PRODUCTION_MUTATED=NO
MERGE=NO
DEPLOY=NO
STATUS=PASS_ZONE3_40ITEM_DOD_EVIDENCE_RECONCILED
```

Files changed by this task are audit documents only:

- `docs/audits/w1_04_zone3_40item_dod_evidence_reconciled_matrix_005.json`
- `docs/audits/w1_04_zone3_40item_dod_evidence_status_reconciliation_005.md`
