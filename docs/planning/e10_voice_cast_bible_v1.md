# E10 Voice Cast Bible v1 — Zone 1 Canon Audit

Status: `ZONE1_CANON_CONFIRMED / ZONE2_BILINGUAL_AUDIO_LOCKED`

This is the first global E10 cast record. It records what is actually locked in
the shipped Zone 1 runtime and the later Owner-approved Zone 2 Herder lock;
it does not independently recast anyone. Provider/model/settings claims are
limited to repository evidence.

## Evidence and authority

- Base audited: `fc8cd5dfe9451a7df872ef8866566b785acc6a70`.
- Runtime dialogue mapping: `index.html` `_getIntroFilmLocaleConfigBase(k26_30)`.
- Locked cast: `tools/e10_zone1_audio/casting_candidates.json` and
  `tools/e10_zone1_audio/zone1_final_tts_lock.json`.
- Byte lock: `assets/e10/audio/zone1/zone1-dialogue-assets.json`,
  `assets/e10/audio/zone1/zone1-audio-package.json`, and
  `deploy/canonical-e10-zone1-audio-pack-manifest.json`.
- The local tooling identifies the provider as ElevenLabs and the locked model
  as `eleven_v3`. No network call or audio generation was performed in this
  audit.

## Locked identities

| Character ID | Display / role | First zone | Voice type | Provider / model | Locked voice IDs | Style evidence | Reference audio / SHA | Status |
|---|---|---:|---|---|---|---|---|---|
| `e10.narrator.anna` | Narrator (`anna`) | 1 | spoken narration | ElevenLabs / `eleven_v3` | `en`: `ZF6FPAbjXT4488VcRRnw`; `zh-TW`: `9lHjugDhwqoxA5MhX0az` | Amelia: enthusiastic/expressive; Anna Su: casual/friendly/bright | Shot 1, both locales; exact bytes in the 28-file dialogue manifest | `LOCKED` |
| `e10.protagonist.hero` | Hero (`hero`) | 1 | youthful spoken dialogue | ElevenLabs / `eleven_v3` | `en`: `6aOpkucJD6a4vTXyUKon`; `zh-TW`: `XXxvxx0YUt8icTEFE3c6` | Anvay: calm/reassuring; Roy: Taiwanese youth; male visual canon | Shots 2 and 6, both locales; exact bytes in the 28-file dialogue manifest | `LOCKED` |
| `e10.village_elder` | Elder (`elder`) | 1 | warm, economical, ritual-toned spoken dialogue | ElevenLabs / `eleven_v3` | `en`: `onwK4e9ZLuTAKqWW03F9`; `zh-TW`: `NdEhweaiOdufFIiyNPdk` | Daniel: steady/broadcaster; Christopher: approved zh-TW recast | Shots 2, 4, and 8, both locales; exact bytes in the 28-file dialogue manifest | `LOCKED` |
| `e10.messenger` | Messenger / Runner (`runner`) | 1 | young urgent spoken dialogue | ElevenLabs / `eleven_v3` | `en`: `TX3LPaxmHKxFdv7VOQHJ`; `zh-TW`: `5s3UifUu3OJ90z17rRMA` | Liam: energetic/social; Jun: bright/energetic; the zh-TW male recast superseded Yui | Shot 10, both locales; exact bytes in the 28-file dialogue manifest | `LOCKED` |
| `e10.water_spirit_horse` | Water Spirit Horse / Shui | 1 | **nonverbal companion** | N/A | N/A | Small juvenile water spirit; addressed by Hero, never given a human line | No runtime voice or creature-vocal file found; Zone 1 Shot 2 explicitly says it says nothing | `NONVERBAL` |
| `e10.zone2.herder` | Zone 2 Herder / 牧者 | 2 | young-adult male spoken dialogue | ElevenLabs / `eleven_v3` | `zh-TW`: `UwT0JPexcCbH107hq7i5` (James); `en`: same identity `UwT0JPexcCbH107hq7i5` | Warm, friendly, trustworthy young-adult male read; cross-language identity preserved and distinct from Hero, Elder, and Messenger | `zh-TW`: `assets/e10/audio/zone2/dialogue/zone2_final_shot04_beat01_zh_herder.mp3` / `7cd5043fe0e8bbc942f3ec868ecd6255a6833f555bf662bd5561ef090bb08a63`; `en`: `assets/e10/audio/zone2/dialogue/zone2_final_shot04_beat01_en_herder.mp3` / `163060c5f9545409a89673f89036e0d6b6933a05aa428b58cf58ff725ed02b83` | `LOCKED` |

`VOICE_ID_DATA_AVAILABLE=YES` for all eight locked role/locale slots above.
`REFERENCE_AUDIO_SHA256_AVAILABLE=YES` through the canonical manifests.
`VOICE_SETTINGS_AVAILABLE=NO`: the locked records preserve IDs/model and
delivery notes, but do not preserve ElevenLabs stability/similarity/style/
speaker-boost values. Do not invent those settings for Zone 2.

## Zone 1 shot-level dialogue canon

The runtime shot mapping is cross-checked against
`docs/planning/e10_zone1_bilingual_script_v1.md` and
`index.html`'s `_getIntroFilmLocaleConfigBase(k26_30)`. Silence is part of the
canon; it is not a missing asset.

| Shot | Speaker(s) | Canonical beat |
|---:|---|---|
| 1 | Narrator (`anna`) | `清晨的鐘聲還沒響起，村子的風，已經帶來一絲……不尋常的氣息。` / `The morning bells haven't rung yet, but the village wind already carries a hint of... something unusual.` |
| 2 | Elder, Hero | `孩子，天亮了。` / `Morning, child.`; `早啊，小水。` / `Morning, Shui.` |
| 3 | — | `SILENCE` in both locales |
| 4 | Elder | `你看，那片雲。`; `它已經停在那裡三天了。`; `而且……每天都更近一點。` / `Look at that cloud.`; `It's been sitting there for three days.`; `And... every day, it gets a little closer.` |
| 5 | — | `SILENCE` in both locales |
| 6 | Hero | `我不知道自己行不行……`; `但我想去看看。` / `I don't know if I can do this...`; `But I want to go see for myself.` |
| 7 | — | `SILENCE` in both locales |
| 8 | Elder | `想出村，就先陪我下一局。`; `別急。`; `看清楚，再落子。` / `If you want to leave the village, play one game with me first.`; `Don't rush.`; `Look carefully. Then make your move.` |
| 9 | — | `SILENCE` in both locales |
| 10 | Messenger (`runner`) | `村長！`; `史萊姆平原的商隊……`; `三天了，還沒回來！` / `Elder!`; `The caravan from the Slime Plains...`; `It's been three days, and they still haven't come back!` |

`ZONE1_DIALOGUE_RECOVERED=28/28`; the corresponding 28 MP3 files and hashes
are governed by the manifests named above. `WATER_SPIRIT_HORSE = NONVERBAL`:
the Hero addresses Shui in Shot 2, but Shui has no human or creature-vocal line.

## Zone 1 audio canon

- Dialogue: 28/28 owner-approved bilingual MP3 files; status
  `OWNER_APPROVED_INTEGRATED`.
- Main BGM: `assets/e10/audio/zone1/bgm/zone1_bgm_main_theme.mp3`, approved
  flute-led variant, Shots 1–8.
- Post-clear BGM: `assets/e10/audio/zone1/bgm/zone1_bgm_post_clear_urgency.mp3`,
  approved sparse-piano variant, Shot 10 only.
- Ambience: `assets/e10/audio/zone1/ambience/zone1_ambience_village_dawn.mp3`,
  Shots 1–8.
- Story SFX: four locked cues for Shot 5, Shot 7, Shot 9, and Shot 10.
- Lord Trial SFX: eight locked cues for card reveal, challenge confirmation,
  ritual energy, stone impact, success, failure, route energy, and unlock chime.
- Canonical pack verification in this audit: **43/43 files present, SHA-256 and
  byte lengths matched; no missing files**.

## Reuse rules for Zone 2+

Reuse the Hero, Elder, Messenger, Narrator, and now locked Zone 2 Herder
identities above. Do not recast a locked identity without an explicit Owner
decision. The Water Spirit Horse stays nonverbal; its Zone 2 Shui reaction is a
creature SFX, not human dialogue. Swarm Lord remains a creature-vocal/liquid
rumble treatment with no human dialogue.

## Zone 2 Phase 3 / Audio Lock status

Owner confirmed `ZONE2_SCRIPT_VERSION=OWNER_APPROVED_V2` and then locked
`ZONE2_AUDIO_LOCK=YES` with Herder V5 James. The rejected candidates remain
audition evidence only:

| Candidate | Voice identity | Locale | Status | Review file |
|---|---|---|---|---|
| `HERDER_V1` | Ling — Steady, Calm and Grounded (`Z8Aisvg1z70p27kGvkZZ`) | zh-TW | `REJECTED` | review-only pack |
| `HERDER_V2` | Yui — Delicate, Graceful and Soothing (`kGjJqO6wdwRN9iJsoeIC`) | zh-TW | `REJECTED` | review-only pack |
| `HERDER_V3` | Zack — Soft and Friendly (`DSyEP4HEaCKur8rFFOri`) | zh-TW | `REJECTED` | review-only pack |
| `HERDER_V5` | James (`UwT0JPexcCbH107hq7i5`) | zh-TW | `LOCKED` | canonical Shot 4 asset above |

The locked Zone 1 Hero identity was reused for the two V2 Hero lines in both
locales. The English Herder was generated with the same locked James identity;
`CROSS_LANGUAGE_IDENTITY_PRESERVED=YES`. The Water Spirit Horse remains
`NONVERBAL`; Owner selected Shui reaction 2. Owner selected A3/B3/C3 for
discovery/escalation/recovery and approved the remaining ambient/SFX palette.
The canonical byte-preserving bilingual package is
`assets/e10/audio/zone2/zone2-audio-package.json` (23 files: 6 dialogue, 3 BGM,
3 ambience, 11 SFX). The runtime Herder file records the narrow TTS-only
homophone control used to verify the locked `jiào` pronunciation.
