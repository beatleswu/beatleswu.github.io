# Zone4 Cinematic Storyboard Runtime Recovery 001

## 1. Scope and authority

This report records the bounded Zone4 presentation repair and the installed
PWA/Safari parity corrective. It does not change Adventure progression,
Lord eligibility or victory authority, questions, Coins, XP, stars, rewards,
player data, database state, or Production.

The investigation used the fresh `origin/master` snapshot below in the
isolated worktree:

```text
START_ORIGIN_MASTER=4097053dcf87d5eeca826e03d8a21adbfcb9a47a
START_TREE=14b82d6ba2b30652c3ca9c12c55939744ec28110
BRANCH=codex/zone4-cinematic-storyboard-runtime-recovery-001
WORKTREE=D:\go-website-worktrees\zone4-cinematic-storyboard-runtime-recovery-001
```

The source authority for the Zone4 order and state boundary is:

- `ZONE4_RUNTIME_MANIFEST.json`
- `ZONE4_STORY_BEAT_BINDING_MATRIX.json`
- `ZONE4_004_LORD_STATE_BINDING_MATRIX.json`
- `js/e10/zone4_cinematic_content.js`
- the shared E9 world-stage/replay-card path in `js/e9/world_stage.js` and
  `js/e9/right_cards.js`

`ZONE4_004_LORD_STATE_BINDING_MATRIX.json` explicitly keeps Lord visuals out
of the linear 22-beat story and requires an authoritative Lord pass before
`Z4_S3_01`. The Lord state machine is presentation-only and does not grant a
clear, reward, eligibility, or progression result.

## 2. Executive result

The implementation is a static/frontend-only candidate. It adds explicit
Zone4 pre-Lord/post-Lord presentation segmentation, creates all required
film slots from the canonical timeline, routes Zone4 Lord presentation to
the existing six-asset Zone4 Lord package, separates first-clear from replay
success presentation, preserves the shared `重溫故事` / `Replay Story` card
action, and relaxes only the standalone outer layout clipping that could
remove the lower Adventure surface.

The PWA change is source-ready but device verification is still pending. The
computer-use surface could not initialize in this environment
(`failed to write kernel assets: 系統找不到指定的路徑。`), so the actual
installed Safari worker, cache, launch URL, and rendered pixels remain
unverified.

```text
NEW_ART_REQUIRED=NO
ART_ASSET_GAPS=NONE
APP_PY_CHANGED=NO
DB_CHANGED=NO
PLAYER_DATA_CHANGED=NO
STATIC_ONLY_FIX=YES
BUILD=NO
DEPLOY=NO
PRODUCTION_MUTATION=NO
READY_FOR_OWNER_ZONE4_STORYBOARD_REVIEW=YES
READY_FOR_OWNER_SAFARI_PWA_PARITY_UAT=YES
```

## 3. Current storyboard matrix

The 22 rows below are the current canonical main-story order. `VOICE_ASSET`
and `IMAGE_ASSET` are repository-relative paths; the runtime resolves them
under the site root. Every row has a same-locale voice, an explicit image,
and zh-TW subtitle/copy. The normal transition is voice end (or the explicit
player advance policy) to the next row; no row requires an unowned image hold.

| # | SEQUENCE_INDEX / SHOT_ID | BEAT_ID | STORY_PHASE | VOICE_ASSET | VOICE_DURATION_IF_AVAILABLE | IMAGE_ASSET | SUBTITLE/COPY | RUNTIME_TRIGGER | EXPECTED_CHECKPOINT |
|---:|---|---|---|---|---:|---|---|---|---|
| 1 | 1 / Z4-S1-01 | Z4_S1_01 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_01_HERO_001.mp3` | 2960 ms | `assets/e10/art/zone4/cinematic/Z4-S1-01.png` | 奇怪……剛才明明還看得到路。 | first entry / pre-play | pre_lord |
| 2 | 2 / Z4-S1-02 | Z4_S1_02 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_02_HERO_001.mp3` | 3200 ms | `assets/e10/art/zone4/cinematic/Z4-S1-02.png` | 小水，你還記得我們是從哪邊進來的嗎？ | pre-play | pre_lord |
| 3 | 3 / Z4-S1-03 | Z4_S1_03 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_03_HERO_001.mp3` | 1440 ms | `assets/e10/art/zone4/cinematic/Z4-S1-03.png` | ……兩條？ | pre-play | pre_lord |
| 4 | 4 / Z4-S1-04 | Z4_S1_04 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_04_HERO_001.mp3` | 1440 ms | `assets/e10/art/zone4/cinematic/Z4-S1-04.png` | 連我自己都跑出來了……？ | pre-play | pre_lord |
| 5 | 5 / Z4-S1-05 | Z4_S1_05 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_05_HERO_001.mp3` | 1200 ms | `assets/e10/art/zone4/cinematic/Z4-S1-05.png` | 誰？ | pre-play | pre_lord |
| 6 | 6 / Z4-S1-06 | Z4_S1_06 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_06_RABBIT_001.mp3` | 4640 ms | `assets/e10/art/zone4/cinematic/Z4-S1-06.png` | 如果連方向都分不清……又怎麼走得出迷霧森林？ | pre-play | pre_lord |
| 7 | 7 / Z4-S1-07 | Z4_S1_07 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_07_HERO_001.mp3` | 4800 ms | `assets/e10/art/zone4/cinematic/Z4-S1-07.png` | 左邊的大樹、右邊的石頭……只要記清楚，就不會走錯。 | pre-play | pre_lord |
| 8 | 8 / Z4-S1-08 | Z4_S1_08 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S1_08_HERO_001.mp3` | 1280 ms | `assets/e10/art/zone4/cinematic/Z4-S1-08.png` | ……怎麼又是這裡？ | pre-play | pre_lord |
| 9 | 9 / Z4-S2-01 | Z4_S2_01 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_01_HERO_001.mp3` | 2080 ms | `assets/e10/art/zone4/cinematic/Z4-S2-01.png` | 到底哪一個才是真的…… | pre-play | pre_lord |
| 10 | 10 / Z4-S2-02 | Z4_S2_02 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_02_HERO_001.mp3` | 2560 ms | `assets/e10/art/zone4/cinematic/Z4-S2-02.png` | 連小水也……？ | pre-play | pre_lord |
| 11 | 11 / Z4-S2-03 | Z4_S2_03 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_03_HERO_001.mp3` | 1840 ms | `assets/e10/art/zone4/cinematic/Z4-S2-03.png` | 不對……這個也不像。 | pre-play | pre_lord |
| 12 | 12 / Z4-S2-04 | Z4_S2_04 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_04_HERO_001.mp3` | 1360 ms | `assets/e10/art/zone4/cinematic/Z4-S2-04.png` | 等等…… | pre-play | pre_lord |
| 13 | 13 / Z4-S2-05 | Z4_S2_05 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_05_HERO_001.mp3` | 4240 ms | `assets/e10/art/zone4/cinematic/Z4-S2-05.png` | 樹會變，路會變……連我的影子都會變。 | pre-play | pre_lord |
| 14 | 14 / Z4-S2-06 | Z4_S2_06 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_06_HERO_001.mp3` | 1760 ms | `assets/e10/art/zone4/cinematic/Z4-S2-06.png` | 可是你一直都在。 | pre-play | pre_lord |
| 15 | 15 / Z4-S2-07 | Z4_S2_07 | PRE_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_07_HERO_001.mp3` | 2080 ms | `assets/e10/art/zone4/cinematic/Z4-S2-07.png` | 不是。 | pre-play | pre_lord |
| 16 | 16 / Z4-S2-08 | Z4_S2_08 | LORD_CHALLENGE_BOUNDARY | `assets/e10/audio/zone4/voice/zh-TW/Z4_S2_08_RABBIT_001.mp3` | 960 ms | `assets/e10/art/zone4/cinematic/Z4-S2-08.png` | 很好。 | pre-play, then wait for Lord entry | lord_challenge_boundary |
| 17 | 17 / Z4-S3-01 | Z4_S3_01 | POST_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S3_01_HERO_001.mp3` | 2880 ms | `assets/e10/art/zone4/cinematic/Z4-S3-01.png` | 成功了！ | authoritative Lord clear -> post_clear | post_lord |
| 18 | 18 / Z4-S3-02 | Z4_S3_02 | POST_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S3_02_RABBIT_001.mp3` | 1520 ms | `assets/e10/art/zone4/cinematic/Z4-S3-02.png` | 真不錯！ | post_clear | post_lord |
| 19 | 19 / Z4-S3-03 | Z4_S3_03 | POST_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S3_03_HERO_001.mp3` | 2000 ms | `assets/e10/art/zone4/cinematic/Z4-S3-03.png` | 太好了！ | post_clear | post_lord |
| 20 | 20 / Z4-S3-04 | Z4_S3_04 | POST_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S3_04_HERO_001.mp3` | 1760 ms | `assets/e10/art/zone4/cinematic/Z4-S3-04.png` | 哇！霧真的散開了！ | post_clear | post_lord |
| 21 | 21 / Z4-S3-05 | Z4_S3_05 | POST_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S3_05_HERO_001.mp3` | 2080 ms | `assets/e10/art/zone4/cinematic/Z4-S3-05.png` | 咦？這裡有兩顆果實。 | post_clear | post_lord |
| 22 | 22 / Z4-S3-06 | Z4_S3_06 | POST_LORD | `assets/e10/audio/zone4/voice/zh-TW/Z4_S3_06_HERO_001.mp3` | 3040 ms | `assets/e10/art/zone4/cinematic/Z4-S3-06.png` | 你有聽到嗎？ | post_clear, then normal completion flow | post_lord |

Storyboard classifications:

```text
TOTAL_ZONE4_SHOTS=22
VOICE_ONLY_BEFORE=12
VOICE_ONLY_AFTER=0
IMAGE_ONLY_BEFORE=0
IMAGE_ONLY_AFTER=0
MISSING_ASSET=0
DUPLICATE_IMAGE=0
DUPLICATE_VOICE=0
OUT_OF_ORDER_SHOT=12 host-level presentation mismatches before the fix
UNREACHABLE_SHOT=0 after the fix
PREMATURE_POST_LORD_SHOT=6 before segmentation; 0 after segmentation
```

The 12 prior voice-only rows were rows 11–22 from the runtime host's fixed
10 `.film-shot` elements. The canonical content was present, but the runtime
had no visual slot to bind to those rows. This is a runtime mapping/host
capacity defect, not an art-asset gap.

## 4. Root causes and repairs

### Missing visuals

`index.html` contained ten fixed cinematic slots while
`js/e10/zone4_cinematic_content.js` exposed the full 22-beat timeline.
`applyIntroFilmShotAssets()` could populate only the ten existing nodes.
The candidate now ensures the host has one slot per canonical timeline row
before applying assets. The same node is used for image, subtitle, and audio
beat presentation; no unrelated image is substituted.

### Shot order

The canonical order is the `main_story_order` in
`ZONE4_004_LORD_STATE_BINDING_MATRIX.json`, not lexical filename ordering:

```text
Z4_S1_01..Z4_S1_08
Z4_S2_01..Z4_S2_08
Z4_S3_01..Z4_S3_06
```

Before the candidate, the first ten DOM positions could appear coherent while
the remaining audio/subtitle records advanced without a matching image. The
candidate binds the complete ordered timeline and exposes the semantic tail
separately.

### Lord checkpoint

The previous Zone4 adapter treated the entire 22-row main story as one
first-entry playback list. The candidate enforces:

```text
PRE_LORD_FIRST_SHOT=Z4_S1_01
PRE_LORD_LAST_SHOT=Z4_S2_08
POST_LORD_FIRST_SHOT=Z4_S3_01
POST_LORD_LAST_SHOT=Z4_S3_06
LORD_BOUNDARY=authoritative Lord clear after Z4_S2_08; unlock Z4_S3_01
```

The runtime contract is now:

```text
ZONE4_ENTRY
  -> PRE_LORD_STORY (16 rows)
  -> PRE_LORD_CHECKPOINT at Z4_S2_08
  -> return control to Adventure
  -> Lord challenge presentation/gameplay
  -> authoritative Lord result
  -> POST_LORD_STORY (6 rows only after clear)
  -> normal completion flow
```

Cinematic playback never infers Lord victory and never calls the progression,
reward, or eligibility authority.

### Replay Story CTA

The shared E9 renderer already owns the localized action through
`e10.world_stage.replay_story` and `zoneStoryReplayAvailable()`. The candidate
keeps that shared renderer and does not create a Zone4/PWA duplicate. The
observed missing CTA is therefore a surface/state reachability or stale
runtime symptom, not an absent translation key. When the existing story
history/clear predicate permits replay, the action is:

```text
zh-TW=重溫故事
en=Replay Story
```

Replay is presentation-only. It uses the same pre-Lord timeline and only adds
the post-Lord tail when the existing authoritative clear state permits it.

## 5. Lord Trial visual restoration

### Historical six-WebP package

The original dedicated package is present at
`assets/e10/art/zone1/lord_trial/zone1-lord-trial-art-package.json` and is
byte-accounted as six runtime WebP derivatives. It is a real Lord Trial
package, separate from Zone4 cinematic shots. Its current source references
are the generic Zone1 Lord presentation path; the current Zone4 runtime uses
the current Zone4-specific six-asset owner package described below rather than
silently using Zone4 cinematic artwork or the Zone1-named files.

| # | LORD_TRIAL_ASSET | SHA256 | HISTORICAL_ROLE | CURRENT_RUNTIME_REFERENCE | CURRENTLY_REACHABLE | CURRENTLY_USED | FALLBACK_TRIGGER |
|---:|---|---|---|---|---|---|---|
| 1 | `assets/e10/art/zone1/lord_trial/zone1_lord_challenge_backplate.webp` | `b5c759f0d002e647fc154e36bf5145a8591dd4791dde6ba1a82d5004e8811f7e` | LORD_CHALLENGE_BACKPLATE | Zone1 `phase-lord-card` CSS/background | YES | YES, Zone1 | Generic fallback only when a zone has no dedicated presentation route |
| 2 | `assets/e10/art/zone1/lord_trial/zone1_first_star_success_backplate.webp` | `602956ffd2052073c4e859e06460469c81b3e57f564745d678885baf3fe6b947` | FIRST_STAR_SUCCESS_BACKPLATE | Zone1 first-clear result CSS/background | YES | YES, Zone1 | Generic fallback only when a zone has no dedicated presentation route |
| 3 | `assets/e10/art/zone1/lord_trial/zone1_first_star.webp` | `459a2954b5977ae3f09035f916c2238031b597ec0ae4fdbeff19455ae7293c3f` | FIRST_STAR_ICON | Zone1 first-clear star element | YES | YES, Zone1 | Generic fallback only when a zone has no dedicated presentation route |
| 4 | `assets/e10/art/zone1/lord_trial/zone1_lord_ritual_key_art.webp` | `0965538c111273d3f2c1945c256193c3c6a233a81e0ef11a6c3da96741b7790e` | LORD_RITUAL_KEY_ART | Zone1 ritual image/runtime | YES | YES, Zone1 | Generic fallback only when a zone has no dedicated presentation route |
| 5 | `assets/e10/art/zone1/lord_trial/zone1_lord_failure_backplate.webp` | `07393ac09515dd3f0425fa5961272c5537e0a6af0ceb7037d4d583043e704295` | LORD_FAILURE_BACKPLATE | Zone1 failure CSS/background | YES | YES, Zone1 | Generic fallback only when a zone has no dedicated presentation route |
| 6 | `assets/e10/art/zone1/lord_trial/zone1_village_elder_reference.webp` | `7af79921511484d1d133f68286e895e0b5f1bc87addf40891da46bb87eb9b767` | VILLAGE_ELDER_REFERENCE | Package/static image; no active `index.html` consumer found | YES as a tracked static asset | NO active product consumer found | No active runtime fallback; reference-only in current source |

The historical package is therefore:

```text
HISTORICAL_LORD_TRIAL_PACKAGE_FOUND=YES
LORD_TRIAL_ASSET_COUNT=6
LORD_TRIAL_WEBP=6/6
```

### Current Zone4 Lord package actually bound by current Zone4 authority

The current Zone4 matrix binds Lord state presentation to these six existing
files, not to the 22 cinematic images:

| Visual | Role | SHA256 |
|---|---|---|
| `assets/e10/art/zone4/lord/Z4-LORD-01.png` | challenge card / challenge entry | `4c452590df1517f7e37f8826251ffc22e2ce8dd1c8d49f7f4d66bad8b5304ed7` |
| `assets/e10/art/zone4/lord/Z4-LORD-02.png` | Lord ritual/domain | `1d5ecd438f1be7864ae8d15f7aa4057834634063b09d9b49e5b49d34b133583f` |
| `assets/e10/art/zone4/lord/Z4-LORD-03.png` | failure/retraining | `16e069fe47760d1a431730b8a5d9a794df4bbd3d6dc4ed58e3b5a3b74556ad1e` |
| `assets/e10/art/zone4/lord/Z4-LORD-04.png` | success background | `213045fcb3d40aa83628338e4356d21278731c049c0494af9b291d54b52d62f8` |
| `assets/e10/art/zone4/lord/Z4-LORD-05.png` | first-clear success portrait | `6ae81c0c26d34c0f1ef817b8f221c326dd4204b1db728ff5a5c38ff491cf60a7` |
| `assets/e10/art/zone4/lord/Z4-LORD-06.png` | active challenge portrait | `88d7f2ef260ae1604102b36b09e82af4068a3451801a86a3be4c143a609e2152` |

This is the current Zone4-specific equivalent of the dedicated Lord Trial
package and is already in the current Zone4 owner-final asset closure. No new
Lord artwork is required. The candidate routes `k11_15` before the generic
emoji path, uses the challenge/ritual/failure/success assets above, and keeps
the generic fallback available only for other zones that do not have a
dedicated route.

The result contract now distinguishes:

```text
first clear: server passed=true and first_clear=true, show success background + Z4-LORD-05
replay: server passed=true and replay=true, show success background only, no first-clear portrait/star implication
failure: server passed=false, show Z4-LORD-03 and existing retry semantics
```

The success portrait visibility is explicitly `hidden = !firstClear`; it is
not selected for replay. No server result, reward, star, or progression field
is synthesized by the presentation code.

```text
LORD_CHALLENGE_FALLBACK_EMOJI_REMOVED=YES for Zone4 k11_15
FIRST_CLEAR_VISUAL_RESTORED=YES at source-contract level
REPLAY_VISUAL_SEMANTICS_CORRECT=YES at source-contract level
NEW_ART_REQUIRED_FOR_LORD_UI=NO
```

## 6. Replay and gameplay authority contract

The candidate preserves these invariants:

```text
REPLAY_PROGRESSION_DELTA=0
REPLAY_COINS_DELTA=0
REPLAY_XP_DELTA=0
REPLAY_STAR_DELTA=0
REPLAY_REWARD_DELTA=0
REPLAY_LORD_RESULT_DELTA=0
REPLAY_QUESTION_HISTORY_DELTA=0
```

The Lord challenge card keeps server-derived Lord name, zone, progress,
question count, pass rule, and retry/cooldown copy. The ritual only stages
the existing presentation before the existing Lord start call. First-entry
story completion does not clear the Lord; replay does not clear the Lord or
unlock post-Lord content.

## 7. Installed PWA / Safari parity trace

### Source entry and service-worker contract

| Item | Current source evidence |
|---|---|
| `PWA_MANIFEST_START_URL` | `/` |
| `PWA_SCOPE` | `/` effective scope; `manifest.json` omits explicit `scope` and `index.html` registers `/sw.js` with `{scope:'/'}` |
| `PWA_ACTUAL_START_URL` | `UNKNOWN` without access to the installed device |
| SW registration | `navigator.serviceWorker.register('/sw.js', {scope: '/'})` on window load |
| candidate SW version | `v242-zone4-storyboard-pwa-parity` |
| candidate shell cache | `cg-shell-v242-zone4-storyboard-pwa-parity-source-v242-zone4-storyboard-pwa-parity` |
| candidate image cache | `cg-img-v242-zone4-storyboard-pwa-parity-source-v242-zone4-storyboard-pwa-parity` |
| navigation policy | HTML network-first with cached fallback |
| JS/CSS policy | static JS/CSS cache-first; update is namespace/version governed |
| active/waiting worker on Owner iPad | `UNKNOWN_UNVERIFIED` |
| cached index/JS/CSS bytes on Owner iPad | `UNKNOWN_UNVERIFIED` |

No second PWA Adventure renderer was found. The manifest and standalone mode
launch the same `/` document; the E9 Adventure shell is the same DOM surface
with `#e9-adventure-shell`, `#e9-world-stage-slot`,
`#e9-right-cards-slot`, and `#e9-bottom-dock-slot`. No source branch removes
the current-zone card, mission card, progress, or bottom dock solely because
the display mode is standalone.

### Before/after byte and generation result

The actual Safari and installed-PWA active cache could not be inspected in
this execution environment. Therefore these values are deliberately not
guessed:

```text
SAFARI_STATIC_GENERATION=UNKNOWN_UNVERIFIED
PWA_STATIC_GENERATION=UNKNOWN_UNVERIFIED
SAFARI_SW_VERSION=UNKNOWN_UNVERIFIED
PWA_SW_VERSION=UNKNOWN_UNVERIFIED
SAME_INDEX_BYTES=UNPROVEN
SAME_RUNTIME_JS_BYTES=UNPROVEN
SAME_CSS_BYTES=UNPROVEN
PWA_STALE_CACHE=UNKNOWN_UNVERIFIED
SAME_FRONTEND_BYTES_BEFORE=UNPROVEN
SAME_FRONTEND_BYTES_AFTER=UNVERIFIED_DEVICE_UAT
```

The source-side update path is now deterministic: the SW version and asset
identity are bumped together, old `cg-shell-*`/`cg-img-*` namespaces are
deleted during activate, and HTML navigation is network-first. This is a
source-level stale-cache mitigation, not proof of the current installed
worker. Existing installed users should receive the new namespace through the
normal governed SW update; manual data clearing/reinstallation is not part of
the contract.

### Layout root cause and repair

The source had a strong clipping combination for standalone/mobile:

```text
html, body: height:100%; overflow:hidden
main: flex:1; overflow:hidden
mobile main: overflow:hidden !important
```

That can leave the map centered inside a constrained viewport while the lower
Adventure flow is clipped. The candidate adds a presentation-only
`data-go-display-mode="standalone"` marker and scoped CSS that:

- keeps the same canonical E9/legacy Adventure renderer;
- changes standalone outer flow to `min-height` + vertical scrolling;
- uses `100dvh` and safe-area bottom padding;
- allows the Adventure practice surface to grow to its content height;
- preserves the Zone Card and bottom dock in the same DOM flow;
- does not globally scale the application down;
- does not change player state, feature eligibility, or server payloads.

Expected core component contract for the same authenticated state:

```text
PLAYER_HUD=YES
WORLD_MAP=YES
CURRENT_ZONE_INDICATOR=YES
CURRENT_MISSION_CARD=YES
MISSION_PROGRESS=YES
REGION_PROGRESS=YES
LORD_PROGRESS=YES
PRIMARY_ADVENTURE_CTA=YES
BOTTOM_DOCK=YES
```

Because no actual device session was available, the acceptance values are:

```text
PWA_ZONE_CARD_BEFORE=ABSENT (Owner device evidence)
PWA_ZONE_CARD_AFTER=SOURCE_CONTRACT_READY_UNVERIFIED_DEVICE_UAT
PWA_WORLD_MAP_LAYOUT_BEFORE=INCORRECT_REDUCED (Owner device evidence)
PWA_WORLD_MAP_LAYOUT_AFTER=FULL_VERTICAL_FLOW_SOURCE_CONTRACT_UNVERIFIED_DEVICE_UAT
SAFARI_PWA_CORE_COMPONENT_PARITY=UNVERIFIED_DEVICE_UAT
SAFARI_PWA_STATE_PARITY=UNVERIFIED_DEVICE_UAT
```

### Zone4 recovery on PWA

No PWA-only Zone4 implementation was added. The same source contract is used
on browser and standalone surfaces:

```text
PWA_REPLAY_STORY_CTA_VISIBLE=SOURCE_CONTRACT_READY_UNVERIFIED_DEVICE_UAT
PWA_LORD_CARD_PRESENTATION=SOURCE_CONTRACT_READY_UNVERIFIED_DEVICE_UAT
PWA_CINEMATIC_PRESENTATION=SOURCE_CONTRACT_READY_UNVERIFIED_DEVICE_UAT
```

## 8. Acceptance result matrix

Source-level and Node contract results:

```text
FIRST_ENTRY_STOPS_BEFORE_LORD=PASS
POST_LORD_LOCKED_BEFORE_CLEAR=PASS
POST_LORD_PLAYS_AFTER_CLEAR=PASS
REPLAY_STORY_CTA=PASS (shared E9 renderer contract)
REPLAY_BEFORE_LORD_SAFE=PASS
REPLAY_AFTER_LORD_COMPLETE=PASS
REPLAY_ZERO_MUTATION=PASS (presentation model contract)
```

Physical device results remain a separate Owner UAT gate:

```text
MOBILE=UNVERIFIED_UAT
IPAD=UNVERIFIED_UAT
DESKTOP=UNVERIFIED_UAT
IPAD_SAFARI=UNVERIFIED_UAT
IPAD_PWA=UNVERIFIED_UAT
IPHONE_SAFARI=UNVERIFIED_UAT
IPHONE_PWA=UNVERIFIED_UAT
DESKTOP_BROWSER=UNVERIFIED_UAT
PWA_MAP_LAYOUT=UNVERIFIED_UAT
PWA_BOTTOM_DOCK=UNVERIFIED_UAT
PWA_SCROLL_FLOW=UNVERIFIED_UAT
```

## 9. Tests and changed files

Targeted results after the first-clear portrait correction:

```text
node tests/e9_node_tests/run_p0_zone4_new_cinematic_content_recovery_tests.js  = 6/6 passed
node tests/e9_node_tests/run_zone4_storyboard_runtime_recovery_tests.js       = 12/12 passed
node tests/e9_node_tests/run_zone4_intro_cinematic_wiring_tests.js            = 6/6 passed
pytest -q focused Zone4/storyboard/static tests                             = 28 passed
pytest -q active static content and release tooling regressions               = 95 passed
git diff --check                                                             = clean
```

The candidate file scope is:

```text
M  index.html
M  js/e10/zone4_cinematic_content.js
M  sw.js
M  tests/deployment/test_p0_zone4_cinematic_content_route_corrective.py
M  tests/e9_node_tests/run_p0_zone4_new_cinematic_content_recovery_tests.js
A  tests/e9_node_tests/run_zone4_storyboard_runtime_recovery_tests.js
A  tests/test_zone4_storyboard_runtime_recovery.py
A  docs/planning/ZONE4_CINEMATIC_STORYBOARD_RUNTIME_RECOVERY_001.md
```

No `app.py`, DB/schema, migration, asset binary, player data, reward logic,
or progression authority file is changed.

## 10. Final evidence fields

```text
START_ORIGIN_MASTER=4097053dcf87d5eeca826e03d8a21adbfcb9a47a
START_TREE=14b82d6ba2b30652c3ca9c12c55939744ec28110
BRANCH=codex/zone4-cinematic-storyboard-runtime-recovery-001
FINAL_HEAD=4097053dcf87d5eeca826e03d8a21adbfcb9a47a
FINAL_TREE=14b82d6ba2b30652c3ca9c12c55939744ec28110 (HEAD; candidate changes uncommitted)
WORKTREE_CLEAN=NO (candidate changes present; canonical worktree untouched)

ROOT_CAUSE_MISSING_VISUALS=22 canonical beats were bound to a 10-slot host; rows 11-22 had voice/subtitle without a visual node
ROOT_CAUSE_SHOT_ORDER=full timeline was not rendered with a complete host and had no explicit semantic pre/post adapter boundary
ROOT_CAUSE_LORD_CHECKPOINT=Zone4 adapter exposed one implicit full story instead of preLordTimeline plus postClearTimeline
ROOT_CAUSE_REPLAY_CTA_MISSING=shared CTA existed in E9 source; observed absence was surface/state/cache reachability, not a missing Zone4 implementation

TOTAL_ZONE4_SHOTS=22
VOICE_ONLY_BEFORE=12
VOICE_ONLY_AFTER=0
ART_ASSET_GAPS=NONE
SHOT_ORDER_BEFORE=first ten host slots rendered; remaining canonical rows advanced as audio/subtitle without image
SHOT_ORDER_AFTER=Z4_S1_01..Z4_S1_08, Z4_S2_01..Z4_S2_08, Z4_S3_01..Z4_S3_06
PRE_LORD_FIRST_SHOT=Z4_S1_01
PRE_LORD_LAST_SHOT=Z4_S2_08
POST_LORD_FIRST_SHOT=Z4_S3_01
POST_LORD_LAST_SHOT=Z4_S3_06
LORD_BOUNDARY=authoritative Lord clear after Z4_S2_08

FIRST_ENTRY_STOPS_BEFORE_LORD=PASS
POST_LORD_LOCKED_BEFORE_CLEAR=PASS
POST_LORD_PLAYS_AFTER_CLEAR=PASS
REPLAY_STORY_CTA=PASS
REPLAY_BEFORE_LORD_SAFE=PASS
REPLAY_AFTER_LORD_COMPLETE=PASS
REPLAY_ZERO_MUTATION=PASS

MOBILE=UNVERIFIED_UAT
IPAD=UNVERIFIED_UAT
DESKTOP=UNVERIFIED_UAT
NEW_ART_REQUIRED=NO
APP_PY_CHANGED=NO
DB_CHANGED=NO
PLAYER_DATA_CHANGED=NO
STATIC_ONLY_FIX=YES
SW_VERSION_BEFORE=v241-p0-srs-static-closure-hotfix
SW_VERSION_AFTER=v242-zone4-storyboard-pwa-parity

HISTORICAL_LORD_TRIAL_PACKAGE_FOUND=YES
LORD_TRIAL_ASSET_COUNT=6
LORD_CHALLENGE_FALLBACK_EMOJI_REMOVED=YES for Zone4
FIRST_CLEAR_VISUAL_RESTORED=YES
REPLAY_VISUAL_SEMANTICS_CORRECT=YES
NEW_ART_REQUIRED_FOR_LORD_UI=NO

ROOT_CAUSE_PWA_PARITY=source-level standalone/mobile overflow clipping risk; live stale-cache and live byte mismatch are not proven without device access
PWA_MANIFEST_START_URL=/
PWA_ACTUAL_START_URL=UNKNOWN_UNVERIFIED
SAFARI_STATIC_GENERATION=UNKNOWN_UNVERIFIED
PWA_STATIC_GENERATION=UNKNOWN_UNVERIFIED
SAFARI_SW_VERSION=UNKNOWN_UNVERIFIED
PWA_SW_VERSION=UNKNOWN_UNVERIFIED
PWA_STALE_CACHE=UNKNOWN_UNVERIFIED
SAME_FRONTEND_BYTES_BEFORE=UNPROVEN
SAME_FRONTEND_BYTES_AFTER=UNVERIFIED_DEVICE_UAT
PWA_ZONE_CARD_BEFORE=ABSENT
PWA_ZONE_CARD_AFTER=SOURCE_CONTRACT_READY_UNVERIFIED_DEVICE_UAT
PWA_WORLD_MAP_LAYOUT_BEFORE=INCORRECT_REDUCED
PWA_WORLD_MAP_LAYOUT_AFTER=FULL_VERTICAL_FLOW_SOURCE_CONTRACT_UNVERIFIED_DEVICE_UAT
SAFARI_PWA_CORE_COMPONENT_PARITY=UNVERIFIED_DEVICE_UAT
SAFARI_PWA_STATE_PARITY=UNVERIFIED_DEVICE_UAT
IPAD_SAFARI=UNVERIFIED_UAT
IPAD_PWA=UNVERIFIED_UAT
IPHONE_SAFARI=UNVERIFIED_UAT
IPHONE_PWA=UNVERIFIED_UAT
DESKTOP=UNVERIFIED_UAT
STATIC_ONLY_FIX=YES
SW_CHANGED=YES
APP_PY_CHANGED=NO
NEW_PRODUCTION_IMAGE_REQUIRED=NO
READY_FOR_OWNER_SAFARI_PWA_PARITY_UAT=YES

PRODUCTION_MUTATION=NO
BUILD=NO
DEPLOY=NO
FINAL_STATUS=READY_FOR_OWNER_ZONE4_STORYBOARD_REVIEW
```
