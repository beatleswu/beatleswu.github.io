# W2-01 Zone 4 Misty Forest — Story and Content Authority Review Package

**Task:** `W2_01_ADVENTURE_ZONE4_MISTY_FOREST_STORY_AND_CONTENT_AUTHORITY_LOCK_002`
**Parent:** `17a5f80574100c495f5bc023b0b1d1e3ea0019f6`
**Parent tree:** `52812083cc7352514a53a0fe03915714ae2295c4`
**Scope:** Owner creative review only. This document does not grant runtime, progression, unlock, combat, reward, art, or audio authority.

## Authority legend

- **EXISTING_CANONICAL** — directly recovered from the current repository's approved screenplay or existing server-owned metadata.
- **PRESENT_BUT_LEGACY** — exists in the current application/package, but is not promoted over the newer canonical screenplay.
- **DERIVED_MAPPING** — a traceable scene-to-shot relationship needed to explain the existing package; it is not new story authority.
- **NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL** — deliberately new wording or production guidance supplied for review only.

## Recovered source ledger

| Evidence | Classification | Recovered authority |
|---|---|---|
| `docs/planning/e10_final_screenplay_v1.md:80-96` | **EXISTING_CANONICAL** | Zone 4 theme is trust rather than out-calculation; Shots 1–7 are `PRE_PLAY`, gameplay follows Shot 7, Shots 8–9 are `POST_CLEAR`, and Shot 10 is `POST_CLEAR_HOOK`. It supplies the exact three spoken beats, intentional silences, visual actions, audio direction, Zone 3 entry, and Zone 5 hook. |
| `docs/planning/e10_final_screenplay_integration_contract_v1.md:38-40,105-108` | **EXISTING_CANONICAL** | `DL-02` is exactly 「小水。帶我走。」 at Zone 4 Shot 7; Zone 4 is the first doubt seed where the Hero chooses to trust 水靈馬. |
| `app.py:11688,11703` | **EXISTING_CANONICAL** | `k11_15` is 迷霧森林 / Misty Forest; the existing Lord metadata is `misty_phantom_rabbit_king` / 迷霧幻影兔王. |
| `app.py:7285-7286,7398,7423-7424` and `monster_profiles.py:100-101` | **EXISTING_CANONICAL** | Existing Battlefield records are `legacy_bf_04_normal` / `LV4 森林精靈` and `legacy_bf_04_boss` / `LV4 霧林手筋師` (`LV4 Mistwood Tesuji Adept`), with separate profiles and assets. |
| `index.html:15930-16020` | **PRESENT_BUT_LEGACY** | The supported runtime currently exposes four Zone 4 narration scenes with four storyboard images, four zh-TW MP3s, four English MP3s, and procedural cue names `mystic`, `pulse`, `woodhit`, and `journey`. Its long narration text is not used as canonical dialogue here. |
| `assets/storyboards/go_misty_forest_scene_01.webp`–`04.webp` and the matching eight MP3s | **PRESENT_BUT_LEGACY** | Existing review/reference media only. These files are not final ten-shot art or approved final voice authority. |
| Parent `assets/adventure/zone4/zone4-misty-forest-vertical-slice.json` | **DERIVED_MAPPING** | The accepted isolated implementation already records the ten-shot lifecycle, three zh-TW beat keys, legacy image status, and fail-closed authority gaps. |

## Existing canonical story material

### Canonical lifecycle

**EXISTING_CANONICAL:**

```text
Zone 3 transition
  → Z4_S01–Z4_S07 PRE_PLAY
  → gameplay handoff after Z4_S07
  → authoritative Zone 4 clear
  → Z4_S08–Z4_S09 POST_CLEAR
  → Z4_S10 POST_CLEAR_HOOK
  → Zone 5 / Orc Tribe hook
```

This is presentation sequencing only. The isolated controller does not unlock Zone 4, clear a zone, settle a reward, or select a Lord.

### Existing canonical zh-TW dialogue

The following three beats are **EXISTING_CANONICAL** and must remain textually exact:

| Shot | Character | Exact zh-TW dialogue |
|---|---|---|
| `Z4_S02` | Hero | 「奇怪……我們剛才，是從哪邊進來的？」 |
| `Z4_S05` | Misty Phantom Rabbit King / Lord voice | 「哪一個……才是你？還是……連你自己也不知道？」 |
| `Z4_S07` | Hero | 「小水。帶我走。」 |

**EXISTING_CANONICAL:** Shots 1, 3, 4, 6, 8, 9, and 10 are intentionally silent in the recovered screenplay. Shui / 水靈馬 has no human dialogue. No additional zh-TW line is authored in this package.

### Named characters and environmental events

**EXISTING_CANONICAL:**

- Hero and 水靈馬 enter the forest edge; Shui remains visually steady in the fog.
- `虛空貓` is only an unresolved background eye-glint in Shot 1 and is not a new Zone 4 encounter or guaranteed owned companion.
- Phantom Hero copies emerge, form a ring, and remain visually ambiguous; they are a story presentation event, not M-ID enemy authority.
- The Misty Phantom Rabbit King speaks from an unfixed position in Shot 5; the riddle is before gameplay, not the Lord Trial itself.
- After the clear, an ancient tree reveals black and white fruit; the fruit handoff is a presentation/story relic beat, not a client reward grant.
- A scorched trail and distant drums point toward Zone 5 / Orc Tribe.

## Four existing scenes → ten-shot lifecycle

The current application has four storyboard scenes. The following is the complete **DERIVED_MAPPING** used only to account for every canonical shot:

```text
go_misty_forest_scene_01.webp  → Z4_S01–Z4_S02  (forest edge / disorientation)
go_misty_forest_scene_02.webp  → Z4_S03–Z4_S07  (phantom copies / riddle / trust choice)
go_misty_forest_scene_03.webp  → Z4_S08–Z4_S09  (ancient tree / fruit handoff)
go_misty_forest_scene_04.webp  → Z4_S10          (trail / next-zone hook)
```

This relationship is not a claim that one legacy image contains five final shots. It is a review map showing where the existing four-scene package can be used as reference while the final ten-shot art package is still absent.

`UNMAPPED_SHOT_COUNT=0` for story/lifecycle mapping. `FINAL_ART_PRESENT_COUNT=0` because none of the four images is admitted as final ten-shot art.

## Ten-shot story map

`REQUIRED_ART_STATUS`, `REQUIRED_SFX_STATUS`, `REQUIRED_BGM_STATUS`, and `RUNTIME_TRIGGER_STATUS` below are deliberately classified; they are not silent completion claims.

| Shot | Source scene | Setting | Visible action / characters present | Story purpose | ZH-TW dialogue | EN-US dialogue status | Required art status | Required SFX status | Required BGM status | Runtime trigger status |
|---|---|---|---|---|---|---|---|---|---|---|
| `SHOT_01` | `scene_01` (**DERIVED_MAPPING**) | Forest edge; mist rolls in; violet eyes are only a background hint. | Hero and 水靈馬 enter; `虛空貓` remains unresolved/background-only. (**EXISTING_CANONICAL**) | Establish Zone 3 → Zone 4 arrival and uncertainty without a scare sting. | Silent; no narration. (**EXISTING_CANONICAL**) | Canonical silence; no translation required. | No final art. Existing scene 01 is **PRESENT_BUT_LEGACY** reference only. | Final mist/forest bed and subtle eye-glint are required; legacy `mystic` is reference only. | Uneasy restrained drone / forest ambience required; no dedicated Zone 4 BGM exists. | `PRE_PLAY` entry contract only; shared Journey trigger not wired. |
| `SHOT_02` | `scene_01` (**DERIVED_MAPPING**) | Fog at the forest edge. | Hero stops disoriented; 水靈馬 stays sharp and stable. (**EXISTING_CANONICAL**) | Make the loss of orientation legible through Hero's question. | Hero: 「奇怪……我們剛才，是從哪邊進來的？」 (**EXISTING_CANONICAL**) | British-English translation proposal only; not locked. | No final art; scene 01 legacy reference only. | Mist bed holds; no new character speech/SFX authority. | Same restrained drone; no dedicated package. | `PRE_PLAY`; isolated controller only. |
| `SHOT_03` | `scene_02` (**DERIVED_MAPPING**) | Deep mist. | Phantom copies rise into a loose ring around the Hero. (**EXISTING_CANONICAL**) | Introduce the visual illusion without explanatory narration. | Silent; visual/audio carries the reveal. (**EXISTING_CANONICAL**) | Canonical silence. | No final art; scene 02 legacy reference only. | Overlapping whisper texture / phantom shimmer required; legacy `pulse` is not final authority. | Dissonant transition required; no dedicated package. | `PRE_PLAY`; no gameplay authority. |
| `SHOT_04` | `scene_02` (**DERIVED_MAPPING**) | Ring of copies, real Hero indistinguishable. | Copies gesture identically; Hero remains inside the ring. (**EXISTING_CANONICAL**) | Raise ambiguity before the Rabbit King's riddle. | Silent. (**EXISTING_CANONICAL**) | Canonical silence. | No final art; scene 02 legacy reference only. | Dissonance peaks; overlapping whispers remain bounded and child-safe. | Escalation bed required; no dedicated package. | `PRE_PLAY`; no gameplay authority. |
| `SHOT_05` | `scene_02` (**DERIVED_MAPPING**) | Close, no single face held. | Misty Phantom Rabbit King speaks from everywhere; no fixed face. (**EXISTING_CANONICAL**) | Turn the visual ambiguity into the story question. | Lord voice: 「哪一個……才是你？還是……連你自己也不知道？」 (**EXISTING_CANONICAL**) | British-English translation proposal only; not locked. | No final art; scene 02 legacy reference only. | Single restrained uncanny tone and echo required; no dedicated cue. | Held tension required; no dedicated package. | `PRE_PLAY`; this is not the Lord Trial trigger. |
| `SHOT_06` | `scene_02` (**DERIVED_MAPPING**) | Tight on 水靈馬 against soft-focus copies. | Shui stands still; no aura or explanatory gesture. (**EXISTING_CANONICAL**) | Give the player one stable visual truth. | Silent. (**EXISTING_CANONICAL**) | Canonical silence. | No final art; scene 02 legacy reference only. | Dissonance recedes; no human Shui voice. | Recovery bed required; no dedicated package. | `PRE_PLAY`; no gameplay authority. |
| `SHOT_07` | `scene_02` (**DERIVED_MAPPING**) | Close on Hero with Shui at the edge. | Hero resolves into a quiet decision and asks Shui to lead. (**EXISTING_CANONICAL**) | Seed trust and end the cinematic before gameplay. | Hero: 「小水。帶我走。」 / `DL-02` (**EXISTING_CANONICAL**) | British-English translation proposal only; not locked. | No final art; scene 02 legacy reference only. | One clear resolving note required; no dedicated cue. | Transition to gameplay needs a bounded hold; no dedicated package. | `HANDOFF_TO_GAMEPLAY_AFTER_SHOT`; isolated contract only, no unlock/clear mutation. |
| `SHOT_08` | `scene_03` (**DERIVED_MAPPING**) | Ancient tree; black and white fruit above. | Hero looks up; fog clears gradually; Rabbit King does not speak. (**EXISTING_CANONICAL**) | Show visual resolution after the authoritative gameplay clear. | Silent; no defeat/acceptance speech. (**EXISTING_CANONICAL**) | Canonical silence. | No final art; scene 03 legacy reference only. | Leaves/fog-dissipation bed required; legacy `woodhit` is reference only. | Recovery/opening theme required; no dedicated package. | `POST_CLEAR`; must depend on server-owned clear in later integration. |
| `SHOT_09` | `scene_03` (**DERIVED_MAPPING**) | Close on an open hand beneath the tree. | Black/white fruit falls; Hero catches it without reaching. (**EXISTING_CANONICAL**) | Present the Black/White Fruit as story memory without inventing a reward transaction. | Silent. (**EXISTING_CANONICAL**) | Canonical silence. | No final art; scene 03 legacy reference only. | Quiet relief and soft landing sound required; no dedicated cue. | Calm, no victory fanfare; no dedicated package. | `POST_CLEAR`; presentation only. |
| `SHOT_10` | `scene_04` (**DERIVED_MAPPING**) | Fog edge; scorched trail toward the horizon. | Hero and 水靈馬 face the trail; distant drums carry the next-zone hook. (**EXISTING_CANONICAL**) | Point toward Zone 5 / Orc Tribe without resolving its story. | Silent; trail and drums carry the hook. (**EXISTING_CANONICAL**) | Canonical silence. | No final art; scene 04 legacy reference only. | Low rhythmic pulse and distant drums required; legacy `journey` is reference only. | Fade to a restrained forward-looking transition; no dedicated package. | `END_CINEMATIC_SEQUENCE_AFTER_SHOT`; next-zone authority remains server-owned. |

## Child-readability assessment

The standard is: image clearly shows what is happening → dialogue explains why → feeling/position is legible → next action is obvious. Because final art is absent, the following is a lock-readiness assessment, not a claim that the legacy frames pass final child QA.

| Shot | Action visually clear | Cause explained | Character feeling / position clear | Next action clear | Evidence-based note |
|---|---|---|---|---|---|
| 01 | PARTIAL | PARTIAL | PARTIAL | PARTIAL | Legacy entry frame exists; final mist composition and the non-central eye-glint are missing. |
| 02 | PARTIAL | PASS | PARTIAL | PARTIAL | The exact Hero question supplies orientation context, but final Shui/Hero staging is not available. |
| 03 | NO | PARTIAL | PARTIAL | PARTIAL | Canonical silence is intentional; final phantom-copy compositing is missing. |
| 04 | NO | PARTIAL | PARTIAL | PARTIAL | The escalating visual must distinguish ambiguity from threat; final ring composition is missing. |
| 05 | NO | PASS | PARTIAL | PARTIAL | The riddle explains the challenge, but the voice-only framing and final image are missing. |
| 06 | NO | PARTIAL | PASS | PARTIAL | The stable Shui beat is clear in the screenplay; final contrast against copies is missing. |
| 07 | NO | PASS | PASS | PASS | The exact line makes the next gameplay handoff clear; final Hero/Shui decision frame is missing. |
| 08 | NO | PARTIAL | PARTIAL | PARTIAL | The clear is an external authoritative state; final tree/fog resolution art is missing. |
| 09 | NO | PARTIAL | PARTIAL | PARTIAL | The visual fruit handoff is specified, but the final close-up and story-memory treatment are missing. |
| 10 | NO | PARTIAL | PARTIAL | PASS | The screenplay names the scorched-trail/Zone 5 hook; final trail and drum transition art/audio are missing. |

**Owner readability decision:** approve the intentional silent beats as visual-first, or authorize new bridging dialogue in a later content revision. No new zh-TW dialogue is added here.

## Dialogue authority and translation proposals

`EXISTING_CANONICAL_ZH_DIALOGUE_COUNT=3`
`NEW_ZH_DIALOGUE_PROPOSAL_COUNT=0`
`EN_US_TRANSLATION_PROPOSAL_COUNT=3`
`ENGLISH_ACCENT_POLICY=BRITISH_ENGLISH`

The following English is **NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL**. It is not written into runtime i18n or used to generate voice in this task.

| Beat | Proposed British English | Status |
|---|---|---|
| `Z4_S02_B001` | “Strange... where did we come in from just now?” | **NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL** |
| `Z4_S05_B001` | “Which one... is really you? Or... do you not even know yourself?” | **NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL** |
| `Z4_S07_B001` | “Little Shui. Lead me.” | **NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL** |

No optional replacement is proposed for the seven canonical silent shots. Any added narration or character line would be a new Owner decision, not a recovery of existing authority.

## Character, monster, Battlefield Boss, and Lord authority

| Scope | Current status | Authority classification |
|---|---|---|
| Normal candidates | `M034`–`M045`, 12 identities with existing planning/presentation art references | **PRESENT_BUT_LEGACY / PRESENTATION_ONLY**; candidate identity is not Adventure runtime authority. |
| Adventure-authorized normal monsters | None (`0`) | **MISSING**. The parent fail-closed boundary intentionally refuses to resolve these as Adventure encounters. |
| Battlefield normal anchor | `legacy_bf_04_normal` / `LV4 森林精靈` / `forest_spirit_chibi.png` | **EXISTING_CANONICAL**, Battlefield scope only. |
| Battlefield Boss | `legacy_bf_04_boss` / `LV4 霧林手筋師` / `LV4 Mistwood Tesuji Adept` / `mist_dryad_chibi.png` | **EXISTING_CANONICAL**, Battlefield Boss scope only. |
| Lord | `misty_phantom_rabbit_king` / 迷霧幻影兔王 | **EXISTING_CANONICAL** Lord metadata; final Lord art and a Zone4 Adventure integration package are not supplied here. |

`BATTLEFIELD_BOSS_SEPARATE_FROM_LORD=YES` — `legacy_bf_04_boss` is not `misty_phantom_rabbit_king`.

Before any M034–M045 identity can enter Adventure runtime, Owner and systems authority must supply all of the following: stable persisted M-ID mapping; approved Adventure combat/profile values; question selector and allowlist binding; encounter-class semantics; existing drop/reward settlement references; presentation asset and locale keys; clear/unlock/Lord-boundary behavior; and regression tests proving client fields and presentation cannot become authority. No such binding is created by this package.

## Art and audio gap package

`FINAL_ART_PRESENT_COUNT=0`
`FINAL_ART_MISSING_COUNT=10`

Every visual brief below is **NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL**. No placeholder or generated art is included.

| Shot | Final art status | Owner-ready visual brief |
|---|---|---|
| 01 | Missing | Wide child-safe forest edge; mist rolls in; Hero and Shui enter; a violet eye-glint stays small and background-only. |
| 02 | Missing | Medium frame with Hero nearly swallowed by fog and Shui remaining visually steady; no new aura. |
| 03 | Missing | Slow, readable emergence of translucent Hero copies from the mist into a loose ring; no horror styling. |
| 04 | Missing | Ring composition where copies gesture alike and the real Hero is intentionally hard to identify without becoming visually noisy. |
| 05 | Missing | Close, voice-only Rabbit King presence with no fixed face; keep the riddle restrained and child-readable. |
| 06 | Missing | Tight Shui frame with clear silhouette against soft-focus copies; no magical aura or explanatory text baked into art. |
| 07 | Missing | Close Hero resolving into trust with Shui at the edge; composition must read as a calm decision before gameplay. |
| 08 | Missing | Upward view of an ancient tree with black and white fruit; fog opens gradually; no victory spectacle. |
| 09 | Missing | Close-up of open hand as the two fruits fall into it; clear story-prop handoff, not a UI reward claim. |
| 10 | Missing | Wide fog-edge view of a scorched trail and distant drums; readable forward hook toward Zone 5 without showing Zone 5 final art. |

### Audio status

**EXISTING_SFX — PRESENT_BUT_LEGACY:** `mystic`, `pulse`, `woodhit`, and `journey` procedural references in `index.html`; four zh-TW and four en-US legacy narration MP3s. These are not final Zone4 audio authority.

**DEDICATED_SFX_REQUIRED — NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL:** mist/forest bed, bounded phantom whispers/shimmer, restrained riddle echo, clear trust note, leaves/fog movement, soft fruit landing, and distant drums. Shui remains nonverbal.

**BGM_REQUIRED — NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL:** a restrained Zone4 discovery/escalation/recovery treatment matching the screenplay's uneasy drone, bounded dissonance, quiet resolution, and forward hook. No dedicated Zone4 BGM package currently exists.

**VOICE_REQUIRED — NEW_PROPOSAL_REQUIRES_OWNER_APPROVAL:** zh-TW voice for the three canonical spoken beats and a future Owner-approved British-English package for the three proposed translations. No VO is generated or selected here.

## Owner decisions required

`OWNER_DECISION_ITEM_COUNT=8`

1. Approve the recovered ten-shot lifecycle and the intentional silence in Shots 1, 3, 4, 6, 8, 9, and 10.
2. Approve the derived four-scene → ten-shot reference mapping without promoting legacy storyboard frames to final art.
3. Approve the three exact zh-TW dialogue beats as locked and decide whether any later child-readability pass may add bridging lines.
4. Approve or revise the three British-English translation proposals; approve the future English voice direction separately.
5. Approve final-art briefs and the ten-shot visual language before image generation.
6. Decide the M034–M045 Adventure roster/profile/persistence/settlement authority; presentation art alone must not unlock it.
7. Confirm `legacy_bf_04_boss` remains Battlefield-only and `misty_phantom_rabbit_king` remains the separate Lord authority, including final Lord art ownership.
8. Approve the dedicated Zone4 VO/SFX/BGM production brief and the later Zone3→Zone4 / Zone4→Zone5 runtime trigger contract.

## Boundary and readiness

The parent Zone4 manifest, content contract, authority boundary, isolated presentation controller, component, and responsive CSS are preserved byte-for-byte. This artifact adds no runtime wiring and no i18n/audio/art asset.

```text
SHARED_RUNTIME_INTEGRATION_CHANGE_COUNT=0
APP_PY_CHANGED=NO
ZONE3_SOURCE_CHANGED=NO
VOICE_AUTHORITY_READY=NO
DEDICATED_SFX_PACKAGE_READY=NO
DEDICATED_BGM_PACKAGE_READY=NO
MERGED=NO
DEPLOYED=NO
PRODUCTION_MUTATED=NO
READY_FOR_OWNER_ZONE4_CONTENT_REVIEW=YES
```
