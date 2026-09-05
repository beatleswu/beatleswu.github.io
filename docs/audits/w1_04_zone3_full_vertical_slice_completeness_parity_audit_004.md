# W1-04 Zone 3 Full Vertical-Slice Completeness and Parity Audit

Status: PASS_ZONE3_FULL_COMPLETENESS_MATRIX_LOCKED

This is a read-only cross-lane product completeness audit. It does not implement
missing features, alter runtime authority, merge candidates, deploy, or mutate
Production.

## 1. Audit basis and evidence boundary

The canonical integration reference was freshly verified:

| Reference | Value |
|---|---|
| canonical branch | origin/master |
| canonical master | 616d51b17abe010de1e862382ca4db7bec65936f |
| remote refs/heads/master | 616d51b17abe010de1e862382ca4db7bec65936f |
| audit base | origin/master at the exact SHA above |
| audit branch | codex/w1-04-zone3-full-vertical-slice-completeness-audit-004 |
| candidate integration method | none; candidate commits were inspected by immutable SHA only |

Accepted candidate inputs were all inspected without cherry-pick or merge:

| Lane | Candidate | Tree | Audit finding |
|---|---|---|---|
| WORLD | 39c587a216f6cc13efe572066d9d8f0299960f1b | 676da3... | Owner-approved ten-shot art and world package; responsive Journey binding remains a dependency |
| HERO | 8fa4184e775517403f66a3d56e7357d3470e67cf | e9132e... | Six Lord presentation slots and server-bound monster/Lord separation |
| JOURNEY | f77bce46302974c8a8aa9d296ae0ea548a707691 | 14131e... | 97 zh-TW subtitle/voice beats and final Journey candidate runtime |
| QUALITY | 6522b776ab839b40e8b1a8a3eadc3e6a5eab4edf | 325a3e... | Automated acceptance harness and explicit later browser/device gates |

The decisive integration boundary is that origin/master has the older four-shot
Zone 3 cinematic spine in index.html, while the ten-shot, six-slot Lord, and
97-beat artifacts are candidate-only evidence. Candidate automated PASS is not
canonical runtime completeness.

Evidence register:

| ID | Evidence |
|---|---|
| E1 | origin/master index.html Zone 3 cinematic configuration around 16024-16117: four legacy shots, legacy storyboard images, bilingual legacy voice files, and generic cues |
| E2 | origin/master adventure_zone3_monster_authority.py and tests/test_e055_zone3_vertical_slice.py: 13 normal IDs, zero elites, goblin_centurion Lord-only classification |
| E3 | origin/master adventure_zone_progression_authority.py and adventure_zone_star_progression.py: server progression/Lord eligibility and first-clear reward idempotence |
| E4 | origin/master assets/e10/audio/zone1/zone1-audio-package.json and assets/e10/audio/zone2/zone2-audio-package.json: integrated Zone 1/2 audio packages |
| E5 | origin/master index.html around 16645-16742: Zone 2 beeDistant and beeClose cue definitions and phase-slot use |
| E6 | origin/master sound.js and js/e9/top_hud.js: global UI audio and persisted mute; no user volume slider evidenced |
| E7 | origin/master index.html around 15243-15276, hideBossCinematic, and js/e9/shell.js: media/timer cleanup and shell lifecycle cleanup boundaries |
| E8 | origin/master index.html around 3492-3549 and Zone 2 responsive styles: blur, drift, transitions, reduced-motion rule, and bounded portrait presentation |
| E9 | origin/master js/game/cinematic_replay.js and index.html replay functions: presentation-only replay with no reward/progression writes |
| E10 | WORLD candidate assets/e10/art/zone3/cinematic/zone3-cinematic-asset-package.json and zone3-world-asset-package.json: ten owner-approved shots, content guards, and open responsive binding dependency |
| E11 | HERO candidate zone3_runtime_asset_bindings.py and tests: six Lord slots, same-identity hide fallback, no Monster-to-Lord fallback |
| E12 | JOURNEY candidate assets/e10/i18n/zone3/zone3-cinematic-subtitles.json and assets/e10/audio/zone3/zone3-cinematic-audio-manifest.json: 97 zh-TW beats, locale-scoped voice, subtitle-only missing-voice policy |
| E13 | JOURNEY candidate tools/e10_zone3_audio/zone3_voice_audition_manifest.json: OWNER_REVIEW_REQUIRED review samples; technical manifest approval is not perceptual listening acceptance |
| E14 | Candidate focused automated suites: WORLD 12 passed; HERO 14 passed; JOURNEY 53 passed; E055/legacy 20 passed; QUALITY 50 passed, 5 skipped |
| E15 | QUALITY candidate docs/quality/w1_05_zone3_vertical_slice_acceptance_matrix.md: physical-device acceptance and final runtime integration remain separate gates |

## 2. Zone 1 / Zone 2 parity inventory

“Present” means the behavior or layer exists in the current runtime or its
integrated package. It does not mean that physical-device or perceptual
acceptance is complete.

| Feature | Zone 1 | Zone 2 | Evidence / parity note |
|---|---|---|---|
| STORY | PRESENT | PRESENT | Story cards and cinematic handoff exist in the current runtime |
| CINEMATIC_ART | PRESENT | PRESENT | Both have ten-shot storyboard/runtime art packages |
| WORLD_ART | PRESENT | PRESENT | World/map/landmark presentation exists |
| MONSTERS | PRESENT | PRESENT | Server-owned encounter presentation and bindings |
| BATTLEFIELD_BOSS | PRESENT | PRESENT | Separate boss context and battle flow |
| LORD | PRESENT | PRESENT | Lord trial presentation and authority boundary |
| SUBTITLES | PRESENT | PRESENT | Global en/zh subtitle path |
| ZH_TW_VOICE | PRESENT | PRESENT | App zh maps to zh-TW production voice |
| EN_US_SUBTITLES | PRESENT | PRESENT | App en subtitle path |
| EN_US_VOICE | PRESENT | PRESENT | App en dialogue path |
| AMBIENCE | PRESENT | PRESENT | Integrated Zone 1/2 packages |
| SFX | PRESENT | PRESENT | Event and phase cues are wired |
| CREATURE_SFX | PARTIAL/PRESENT | PRESENT | Zone 2 has slime and bee cues; Zone 1 package does not separately enumerate every creature/nonverbal class |
| NONVERBAL_CHARACTER_AUDIO | NOT SEPARATELY ENUMERATED | NOT SEPARATELY ENUMERATED | No independent acceptance layer is identified in the current packages |
| BGM_OR_MUSIC | PRESENT | PRESENT | Integrated package category |
| VFX | PRESENT | PRESENT | CSS/overlay presentation effects are present |
| PARTICLES | PRESENT | PRESENT | CSS particle/ritual layers are present in the current Zone 1/2 presentation |
| LIGHTING_EFFECTS | PRESENT | PRESENT | Overlay/gradient/ritual lighting treatment exists |
| CAMERA_EFFECTS | PRESENT | PRESENT | Drift/scale presentation motion exists |
| PARALLAX | LIMITED | LIMITED | Blurred background plus foreground treatment; no independently authored multi-plane contract |
| TRANSITIONS | PRESENT | PRESENT | Opacity/scale and cinematic phase transitions |
| UI_FEEDBACK | PRESENT | PRESENT | Overlay controls, captions, buttons, and global UI audio |
| AUDIO_VOLUME_CONTROL | PARTIAL | PARTIAL | Fixed per-channel values exist; no user-facing volume slider was found |
| MUTE_BEHAVIOR | PRESENT | PRESENT | Global SFX mute is persisted and respected |
| LOCALE_SWITCHING | PRESENT | PRESENT | Supported application keys are en and zh |
| REPLAY | PRESENT | PRESENT | Presentation-only replay; no reward/progression replay |
| REDUCED_MOTION | PRESENT | PRESENT | Global reduced-motion styling disables drift/animation |
| ASSET_FAILURE_FALLBACK | PARTIAL | PARTIAL | Responsive/blur presentation fallback exists; asset-specific acceptance is not a complete production gate |
| AUDIO_FAILURE_FALLBACK | PRESENT | PRESENT | Missing/unplayable voice holds subtitle/visual timing without cross-language voice |
| SCENE_CLEANUP | PARTIAL | PARTIAL | Generic intro cleanup exists; route/lifecycle coverage is not fully explicit |
| MOBILE_PERFORMANCE | PARTIAL | PARTIAL | Responsive bounds and safe areas exist; no measured physical-device profile is evidenced |
| PHYSICAL_DEVICE_ACCEPTANCE | NOT EVIDENCED | NOT EVIDENCED | Current quality docs explicitly keep this as a later gate |

### Zone 2 bee audio/effect implementation

The current Zone 2 runtime defines:

- beeDistant: /assets/e10/audio/zone2/sfx/zone2_ambient_bee_distant.mp3
- beeClose: /assets/e10/audio/zone2/sfx/zone2_sfx_bee_close.mp3

The phase slots use beeDistant in the slime/bee approach shots, beeClose in
the close/boss-ready phase, and the reusable one-shot SFX slot staggers the
later cue by approximately 760 ms while stopping the previous one-shot. The
current source search found no separate bee particle emitter, bee sprite, or
bee VFX object; the bee implementation is audio cueing plus the existing
cinematic visual treatment, not a dedicated visual effect.

## 3. Localization definition of done

SUPPORTED_PRODUCTION_LOCALE_LIST = en-US (application key en), zh-TW
(application key zh). i18n.js accepts only en and zh application keys and
normalizes en-* and zh-* accordingly. No third production locale is currently
supported by the application shell.

| Locale | Subtitle status | Voice status | Fallback policy |
|---|---|---|---|
| zh-TW | PARTIAL: JOURNEY candidate has 97 final beats; canonical master still exposes the legacy four-shot Zone 3 path | PARTIAL: JOURNEY candidate has 97 zh-TW-scoped production references; canonical master has only the legacy four voice files | Missing zh-TW voice is SUBTITLE_ONLY; never use en-US voice |
| en-US | PARTIAL: canonical legacy four-shot path exists; no final ten-shot structured en-US Zone 3 subtitle package is evidenced in accepted inputs | PARTIAL: canonical legacy four voice files exist; JOURNEY final audio manifest is zh-TW only | Missing en-US voice is SUBTITLE_ONLY; never use zh-TW voice |

The candidate subtitle contract has schema E10_ZONE3_CINEMATIC_SUBTITLES_V1,
shots 1-10, and 97 beats. The candidate audio manifest has 97 unique beat
identifiers, all locale-scoped to zh-TW with voice language zh. Its explicit
MISSING_LOCALE_VOICE_FALLBACK is SUBTITLE_ONLY and
VOICE_LANGUAGE_MISMATCH is FORBIDDEN. The six-sample audition manifest is
OWNER_REVIEW_REQUIRED and is not evidence of human listening acceptance.

## 4. Complete audio stack

| Category | Zone 3 status | Finding |
|---|---|---|
| DIALOGUE_VOICE | PARTIAL | zh-TW has a candidate 97-beat production manifest; canonical runtime remains legacy bilingual four-shot |
| AMBIENCE | MISSING | No canonical Zone 3 ambience asset/package is integrated; QUALITY labels the BGM/ambience item candidate-gated |
| EVENT_SFX | PARTIAL | Canonical Zone 3 has generic legacy cues; no accepted final Zone 3 event-SFX package is integrated |
| CREATURE_OR_CHARACTER_SFX | MISSING | No Zone 3 creature/character SFX contract is evidenced; Zone 2 bee/slime cues are not Zone 3 authority |
| BGM_OR_MUSIC | MISSING | No canonical final Zone 3 BGM/music package is integrated |
| UI_AUDIO | PARTIAL | Global UI sound system is present and mute-aware; no Zone 3-specific UI acceptance is complete |

Zone 3 audio is therefore not complete for V1.

## 5. Complete visual presentation stack

| Category | Zone 3 status | Finding |
|---|---|---|
| STATIC_ART | PARTIAL | WORLD candidate supplies ten owner-approved runtime images and environment assets; canonical master still uses the four-shot legacy set |
| VFX | MISSING | No Zone 3-specific runtime VFX contract or accepted VFX layer is evidenced |
| PARTICLES | MISSING | No Zone 3-specific particle emitter/lifecycle contract is evidenced |
| LIGHTING | PARTIAL | Static art and generic overlays/blur exist; no Zone 3-specific authored lighting/effect layer is integrated |
| CAMERA_MOTION | PARTIAL | Generic storyboard drift/scale exists; final ten-shot camera treatment is not canonical |
| PARALLAX | MISSING | No authored Zone 3 parallax/multi-plane contract |
| TRANSITIONS | PARTIAL | Generic opacity/scale transitions exist; final ten-shot phase transition acceptance is open |
| UI_FEEDBACK | PARTIAL | Generic overlay/caption/control feedback exists; final candidate UI and handoff are not canonical |

Static cinematic art is not counted as VFX, particles, lighting, or parallax.

## 6. Accessibility and user settings

| Control | Zone 3 parity | Evidence / risk |
|---|---|---|
| prefers-reduced-motion | PARTIAL | Global CSS disables storyboard drift and candidate CSS includes reduced-motion handling; final candidate is not integrated on canonical master |
| mute | COMPLETE for global behavior | SFX.muted is persisted and the top HUD binds the control; final Zone 3 audio package is not integrated |
| volume | PARTIAL | Fixed playback levels exist; no user-facing volume control was found |
| subtitle visibility | PARTIAL | Caption rendering exists, but a final Zone 3-specific visibility acceptance and candidate integration are not evidenced |
| locale selection | PARTIAL | en/zh switch exists and maps to en-US/zh-TW; complete ten-shot locale parity is open |

No client/static presentation path is allowed to issue reward, clear a zone,
unlock progression, mark a Lord defeated, or mutate Historical Mastery.

## 7. Lifecycle and failure degradation

### Cleanup audit

| Resource | Shot transition | Cinematic exit | Replay exit | Route change | Status |
|---|---|---|---|---|---|
| audio loops | stopped/reused by intro cleanup | stopped | stopped before replay | not explicitly proven for every route path | PARTIAL |
| timers | cleared by intro cleanup | cleared | cleared before replay | route-level proof open | PARTIAL |
| animation frames | no dedicated Zone 3 RAF/particle loop | no dedicated loop | no dedicated loop | generic lifecycle cleanup exists, Zone 3 binding open | PARTIAL |
| particle emitters | none in canonical Zone 3 | none | none | none | MISSING layer, no active leak |
| event listeners | local handlers removed in intro cleanup | removed by cleanup path | replay path rebinds | shell cleanup exists, route-specific proof open | PARTIAL |
| temporary DOM nodes | overlay reset/closed | removed/reset | overlay reset | route change not fully evidenced | PARTIAL |
| media objects | audio paused/reseeked and handlers removed | same | same | source release/route proof open | PARTIAL |

Open lifecycle risk: the canonical generic _stopIntroFilm path cleans current
intro resources but is not an explicit Zone 3 resource owner registered across
all shell route-change paths. Any final Zone 3 implementation must add
route-change, cinematic-exit, replay-exit, and shot-transition assertions for
all resource classes before integrated-candidate approval.

### Failure degradation

| Failure | Current/candidate behavior | Gameplay authority result |
|---|---|---|
| cinematic image missing | presentation fallback/degraded frame; WORLD package rejects missing/invalid package members | no Zone clear, unlock, reward, item, Lord defeat, or mastery mutation |
| wrong asset hash | asset validation failure only | no gameplay mutation |
| duplicate Shot ID | package rejection | no gameplay mutation |
| voice missing | subtitle-only timing; no other-language voice and no implicit TTS | no gameplay mutation |
| SFX missing | presentation cue omitted/degraded | no gameplay mutation |
| ambience missing | presentation layer can omit ambience | no gameplay mutation |
| VFX initialization failure | presentation-only failure; no canonical Zone 3 VFX authority | no gameplay mutation |
| browser autoplay denial | audio unlock remains gesture-gated; subtitle/visual timing continues | no gameplay mutation |

PRESENTATION_FAILURE_MUST_NOT_BLOCK_GAMEPLAY = YES.

## 8. Replay parity and authority boundary

The current generic replay model is presentation-only and has no fetch, reward,
progression, unlock, player-position, or storage mutation. It preserves the
authoritative server state and does not replay first-clear rewards. However,
Zone 3 final content parity remains PARTIAL because canonical master does not
contain the candidate ten-shot/97-beat package.

Required replay preservation for the final Zone 3 candidate:

| Preserve on replay | Status |
|---|---|
| locale and subtitle selection | OPEN with final integrated content |
| voice selection | OPEN with locale-scoped package and subtitle-only fallback |
| image | OPEN with ten-shot package |
| SFX and ambience | OPEN; final packages missing |
| VFX and transition | OPEN; final layers missing/partial |
| no reward | CURRENT AUTHORITY PASS |
| no zone clear | CURRENT AUTHORITY PASS |
| no zone unlock | CURRENT AUTHORITY PASS |
| no Lord state mutation | CURRENT AUTHORITY PASS |

## 9. Performance audit

Current Zone 1/2 safeguards relevant to Zone 3:

- responsive cinematic stage and safe-area handling;
- portrait object-fit containment, bounded content height, and blurred
  background treatment;
- lazy/async image loading where used by Lord art;
- reusable audio slots and staggered one-shot SFX to limit overlap;
- reduced-motion disabling of image drift/animation;
- no numeric particle, audio-concurrency, memory, or blur budgets were found.

| Device class | Current safeguard | Zone 3 audit status |
|---|---|---|
| desktop | 16:9 stage, bounded controls, image drift, blur fallback | PARTIAL; no Zone 3 profiling or final package integration |
| iPad landscape | responsive stage and safe areas | PARTIAL; viewport automation only, no physical evidence |
| iPad portrait | contain treatment, bounded content, blurred background | PARTIAL; viewport automation only, no physical evidence |
| iPhone/mobile portrait | responsive controls, safe areas, gesture audio unlock, reduced motion | PARTIAL; no physical-device acceptance |

No numerical budgets are invented by this audit. The open performance task
must measure animation cost, particle count once particles exist, audio
concurrency, memory cleanup, and blur/filter cost on the four device classes.

## 10. Quality and human acceptance

| Layer | Zone 3 evidence | Status |
|---|---|---|
| AUTOMATED_ASSET_QA | WORLD and HERO manifest/hash/dimension tests; QUALITY asset harness | COMPLETE for candidate artifacts |
| AUTOMATED_RUNTIME_QA | Candidate focused suites: WORLD 12 passed, HERO 14 passed, JOURNEY 53 passed, E055/legacy 20 passed, QUALITY 50 passed and 5 skipped | COMPLETE for candidate contracts; not canonical integration proof |
| REAL_BROWSER_QA | Candidate E2E/viewport automation exists | PARTIAL; real browser Owner run not evidenced |
| PERCEPTUAL_AUDIO_QA | Six-sample audition manifest is OWNER_REVIEW_REQUIRED | MISSING |
| PHYSICAL_DEVICE_QA | QUALITY explicitly keeps physical-device acceptance for a later gate | MISSING |

Automated decode, hash, dimension, and manifest tests do not establish human
listening acceptance.

## 11. ZONE3_V1_DEFINITION_OF_DONE

This is the authoritative full-slice checklist. COMPLETE/PARTIAL/MISSING are
current canonical readiness classifications, not claims that a candidate has
been merged.

| ITEM_ID | CATEGORY | OWNER_LANE | REQUIRED | CURRENT_STATUS | EVIDENCE | PRODUCT_IMPACT | DEPENDENCY | MINIMUM_IMPLEMENTATION_SCOPE | NEXT_TASK_IF_OPEN |
|---|---|---|---|---|---|---|---|---|---|
| Z3-001 | STORY | WORLD/JOURNEY | YES | PARTIAL | E1,E10,E12 | Final story beats are not canonical | Ten-shot script and Journey wiring | Bind final story beats to server-owned entry/handoff | Bounded story integration task |
| Z3-002 | CINEMATIC_ART | WORLD/JOURNEY | YES | PARTIAL | E1,E10 | Canonical entry is four-shot, not owner-approved ten-shot | WORLD package plus Journey slot | Integrate ten runtime images without authority side effects | Bounded cinematic asset integration task |
| Z3-003 | WORLD_ART | WORLD | YES | PARTIAL | E1,E10 | Final environment/landmark package is candidate-only | WORLD package and responsive binding | Bind environment/map presentation to Zone 3 without gameplay writes | Bounded world presentation task |
| Z3-004 | MONSTERS | HERO/SYSTEMS | YES | COMPLETE | E2,E11,E14 | Server-owned 13-normal roster is stable | Existing authority modules | Preserve exact 13 IDs and zero elites | None |
| Z3-005 | BATTLEFIELD_BOSS | HERO/SYSTEMS | YES | COMPLETE | E2,E11,E14 | Boss/Lord separation is protected | Existing server boss binding | Preserve legacy_bf_03_boss as distinct from goblin_centurion | None |
| Z3-006 | LORD | HERO/SYSTEMS | YES | PARTIAL | E2,E11 | Lord presentation slots are candidate-only | Six-slot asset package and server eligibility | Bind presentation by existing Lord identity; no art-created eligibility | Bounded Lord presentation integration task |
| Z3-007 | GAMEPLAY_HANDOFF | JOURNEY/SYSTEMS | YES | PARTIAL | E3,E12,E14 | Final cinematic-to-gameplay handoff is not canonical | Server-selected Zone and final Journey runtime | Consume server facts only and prove no client-selected progression | Bounded handoff authority task |
| Z3-008 | SERVER_AUTHORITY_BOUNDARIES | SYSTEMS | YES | COMPLETE | E2,E3,E9,E11 | Core authority remains server-owned | Existing progression/reward/replay modules | Keep presentation read-only and fail closed | None |
| Z3-009 | ZH_TW_SUBTITLES | JOURNEY | YES | PARTIAL | E1,E12,E14 | Final 97-beat subtitle package is not canonical | Candidate subtitle manifest | Integrate locale-scoped beats with duplicate/missing-ID rejection | Bounded i18n integration task |
| Z3-010 | ZH_TW_VOICE | JOURNEY | YES | PARTIAL | E1,E12,E13,E14 | Candidate voice is not canonical and lacks perceptual acceptance | Audio manifest and Owner listening gate | Integrate 97 refs and complete listening acceptance | Bounded zh-TW voice task |
| Z3-011 | EN_US_SUBTITLES | JOURNEY | YES | PARTIAL | E1,E12 | Only legacy four-shot English path is canonical | Final English script/package decision | Supply and integrate final ten-shot English subtitles or Owner-approved intentional difference | Bounded en-US localization task |
| Z3-012 | EN_US_VOICE | JOURNEY | YES | PARTIAL | E1,E12 | Final audio candidate is zh-TW only | en-US production package or explicit Owner waiver | Provide en-US voice or keep fail-closed subtitle-only policy with approved scope | Bounded en-US voice decision/production task |
| Z3-013 | AMBIENCE | JOURNEY | YES | MISSING | E4,E15 | Full cinematic audio stack is incomplete | Zone 3 ambience package | Add authored ambience, loop ownership, mute/cleanup, and replay tests | Bounded Zone 3 ambience task |
| Z3-014 | EVENT_SFX | JOURNEY | YES | PARTIAL | E1,E4,E12 | Legacy generic cues do not prove final event coverage | Final shot/event cue manifest | Add and wire event cues without reward/progression effects | Bounded Zone 3 event-SFX task |
| Z3-015 | CREATURE_OR_CHARACTER_SFX | JOURNEY | YES | MISSING | E4,E5 | Monster/Lord presentation lacks Zone 3 creature/character audio contract | Audio design and owner package | Define only required cues, locale-independent, with missing-audio degradation | Bounded Zone 3 creature-SFX task |
| Z3-016 | NONVERBAL_CHARACTER_AUDIO | JOURNEY | NO | NOT_APPLICABLE | E4,E12 | No approved separate nonverbal layer is required by current inputs | Owner script/audio decision | Reclassify only if Owner adds nonverbal beats | Owner decision if scope changes |
| Z3-017 | BGM_OR_MUSIC | JOURNEY | YES | MISSING | E4,E15 | Zone 3 does not have a complete music bed | Zone 3 music package | Add BGM lifecycle, mute/volume, autoplay fallback, replay and cleanup coverage | Bounded Zone 3 BGM task |
| Z3-018 | UI_AUDIO | JOURNEY/SYSTEMS | YES | PARTIAL | E6 | Global UI audio exists but Zone 3 UI acceptance is open | Final integrated controls | Verify captions/buttons/transition cues under mute and replay | Bounded UI/audio acceptance task |
| Z3-019 | VFX | WORLD/JOURNEY | YES | MISSING | E8,E10 | Static art alone does not provide visual presentation parity | Art direction and runtime layer | Define and integrate Zone 3 VFX as presentation-only | Bounded Zone 3 VFX task |
| Z3-020 | PARTICLES | WORLD/JOURNEY | YES | MISSING | E8,E10 | No Zone 3 particle layer or cleanup contract is evidenced | VFX design and lifecycle owner | Add bounded particle effects and cleanup tests | Bounded Zone 3 particles task |
| Z3-021 | LIGHTING | WORLD/JOURNEY | YES | PARTIAL | E8,E10 | Generic overlays do not prove final Zone 3 lighting | Final visual treatment | Bind authored lighting treatment with reduced-motion fallback | Bounded Zone 3 lighting task |
| Z3-022 | CAMERA_MOTION | JOURNEY | YES | PARTIAL | E1,E8,E10 | Generic drift is not final ten-shot camera direction | Final shot manifest and responsive positions | Bind shot camera treatment with reduced-motion behavior | Bounded camera-motion task |
| Z3-023 | PARALLAX | WORLD/JOURNEY | YES | MISSING | E8,E10 | No multi-plane Zone 3 presentation contract | Art layers and responsive binding | Add only if V1 art direction requires it; otherwise Owner reclassifies intentionally different | Owner-scoped parallax decision/task |
| Z3-024 | TRANSITIONS | JOURNEY | YES | PARTIAL | E1,E8,E10 | Generic transition exists; final phase transitions not accepted | Ten-shot runtime and replay contract | Integrate transition sequencing and interruption cleanup | Bounded transition task |
| Z3-025 | UI_FEEDBACK | JOURNEY/QUALITY | YES | PARTIAL | E8,E15 | Final caption/control/handoff feedback not canonical | Integrated Journey candidate | Verify entry, skip, replay, blocked, and handoff states | Bounded UI acceptance task |
| Z3-026 | AUDIO_VOLUME_CONTROL | SYSTEMS/JOURNEY | YES | PARTIAL | E6 | Mute exists but user volume parity is incomplete | Existing global settings contract | Preserve control semantics and decide/implement required volume surface | Bounded settings parity task |
| Z3-027 | MUTE_BEHAVIOR | SYSTEMS | YES | COMPLETE | E6,E9 | Global mute authority is stable | Existing SFX.muted behavior | Keep all Zone 3 audio paths mute-aware | None |
| Z3-028 | SUBTITLE_VISIBILITY | JOURNEY/QUALITY | YES | PARTIAL | E1,E12,E15 | Final Zone 3 caption visibility acceptance is open | Global caption behavior and final runtime | Verify visibility control across locale, replay, missing voice, and reduced motion | Bounded subtitle-settings task |
| Z3-029 | LOCALE_SWITCHING | JOURNEY/SYSTEMS | YES | PARTIAL | E1,E12 | Shell switch exists but final content parity is incomplete | en-US/zh-TW package coverage | Ensure switch changes presentation only and never issues reward/progression | Bounded locale integration task |
| Z3-030 | REPLAY | SYSTEMS/JOURNEY | YES | PARTIAL | E9,E12,E14 | Authority-safe replay exists, final content parity is open | Final image/audio/VFX package | Preserve locale and presentation while proving no reward/clear/unlock/Lord mutation | Bounded replay parity task |
| Z3-031 | REDUCED_MOTION | JOURNEY/QUALITY | YES | PARTIAL | E8,E15 | Global rule exists; final Zone 3 layer coverage is open | Final VFX/camera/transition layers | Make every new animation honor the global control | Bounded accessibility task |
| Z3-032 | ASSET_FAILURE_FALLBACK | WORLD/JOURNEY | YES | PARTIAL | E10,E11,E15 | Candidate validation exists; canonical final runtime path is absent | Final asset manifests and runtime | Reject bad packages and degrade presentation without gameplay mutation | Bounded asset-fallback task |
| Z3-033 | AUDIO_FAILURE_FALLBACK | JOURNEY/SYSTEMS | YES | PARTIAL | E1,E12,E14 | Legacy generic fallback is not final package proof | Locale-scoped audio manifest | Missing voice/SFX/ambience must degrade locally and remain subtitle-only for voice | Bounded audio-fallback task |
| Z3-034 | SCENE_CLEANUP | JOURNEY/SYSTEMS | YES | PARTIAL | E7,E9,E15 | Route-change and all-resource cleanup proof is incomplete | Final runtime owner/lifecycle integration | Cover loops, timers, RAF, particles, listeners, DOM, media on all exits | Bounded lifecycle task |
| Z3-035 | MOBILE_PERFORMANCE | QUALITY/JOURNEY | YES | PARTIAL | E8,E15 | Responsive safeguards exist without device measurements | Final package and physical test devices | Profile four required viewport/device classes and tune only evidence-backed costs | Bounded performance task |
| Z3-036 | PHYSICAL_DEVICE_ACCEPTANCE | QUALITY | YES | MISSING | E15 | No physical acceptance evidence | iPad landscape/portrait and iPhone test runs | Execute Owner-approved device matrix and record results | Bounded physical QA task |
| Z3-037 | AUTOMATED_ASSET_QA | QUALITY/WORLD/HERO | YES | COMPLETE | E10,E11,E14 | Candidate asset contracts are technically covered | Candidate manifests | Retain hash/dimension/duplicate/missing coverage at integration | None |
| Z3-038 | AUTOMATED_RUNTIME_QA | QUALITY/JOURNEY/SYSTEMS | YES | COMPLETE | E2,E3,E9,E14 | Authority and candidate contracts have focused automated coverage | Canonical integration of candidates | Re-run focused suites after integration; do not substitute broad harness debt | None |
| Z3-039 | REAL_BROWSER_QA | QUALITY/JOURNEY | YES | PARTIAL | E14,E15 | Viewport automation is not Owner real-browser acceptance | Integrated browser build and test script | Run actual browser entry/replay/locale/failure flows | Bounded real-browser QA task |
| Z3-040 | PERCEPTUAL_AUDIO_QA | QUALITY/JOURNEY | YES | MISSING | E13,E15 | Technical audio tests do not establish listening quality | Owner listening review | Complete human review for dialogue, ambience, SFX, BGM, fallback, and locale correctness | Bounded perceptual audio QA task |

Checklist totals:

- COMPLETE: 6
- PARTIAL: 25
- MISSING: 8
- NOT_APPLICABLE: 1
- OPEN required items: 33

## 12. Required completion sequence

The open items are ready for bounded completion tasks, but they are not a
final integrated candidate. The next tasks must remain separated by owner lane:

1. Integrate ten-shot static/world and six-slot Lord presentation against the
   server-owned Journey seam.
2. Close locale package decisions, especially final en-US subtitles/voice and
   zh-TW listening acceptance; preserve subtitle-only missing-voice behavior.
3. Produce the missing Zone 3 ambience, BGM, creature/character SFX, VFX,
   particles, and any Owner-approved parallax/lighting layers.
4. Add explicit lifecycle and replay negative controls for every new resource.
5. Run real-browser, perceptual-audio, and physical-device acceptance.

No task in this audit grants permission to activate Wave 2 economy, alter
payment/revenue boundaries, change app.py, change shared shell files, merge,
deploy, or mutate Production.
