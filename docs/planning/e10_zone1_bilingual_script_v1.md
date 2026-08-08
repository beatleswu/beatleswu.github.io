# E10 Zone 1 Bilingual Script v1.0 — Subtitle / Voice Localization Canon

Status: `READY_FOR_OWNER_PR_REVIEW`

Sprint: `E10-Z1-BILINGUAL-SCRIPT-CANON-001`

Scope: **Documentation / localization only.** No runtime implementation, no audio generation, no
art changes, no deploy. This document canonicalizes the already Owner-approved Zone 1 bilingual
cinematic script text into the repository so it no longer depends on chat history or a
conversation-scoped attachment.

Source of narrative truth: `docs/planning/e10_final_screenplay_v1.md`, Zone 1 (Shots 1–10). This
document does not alter, supersede, or re-derive that screenplay's dialogue — it adds the approved
`en` localization alongside the existing `zh-TW` canonical text and locks the subtitle/voice
behavior rules that govern how the two locales are consumed at runtime.

---

## Zone 1 — Bilingual Shot Text

| Shot | zh-TW | English (en) |
|---|---|---|
| S1 Anna | 清晨的鐘聲還沒響起，村子的風，已經帶來一絲……不尋常的氣息。 | The morning bells haven't rung yet, but the village wind already carries a hint of… something unusual. |
| S2 Elder | 孩子，天亮了。 | Morning, child. |
| S2 Hero | 早啊，小水。 | Morning, Shui. |
| S3 | SILENCE | SILENCE |
| S4 Elder | 你看，那片雲。 | Look at that cloud. |
| S4 Elder | 它已經停在那裡三天了。 | It's been sitting there for three days. |
| S4 Elder | 而且……每天都更近一點。 | And… every day, it gets a little closer. |
| S5 | SILENCE | SILENCE |
| S6 Hero | 我不知道自己行不行…… | I don't know if I can do this… |
| S6 Hero | 但我想去看看。 | But I want to go see for myself. |
| S7 | SILENCE | SILENCE |
| S8 Elder | 想出村，就先陪我下一局。 | If you want to leave the village, play one game with me first. |
| S8 Elder | 別急。 | Don't rush. |
| S8 Elder | 看清楚，再落子。 | Look carefully. Then make your move. |
| S9 | SILENCE | SILENCE |
| S10 Runner | 村長！ | Elder! |
| S10 Runner | 史萊姆平原的商隊…… | The caravan from the Slime Plains… |
| S10 Runner | 三天了，還沒回來！ | It's been three days, and they still haven't come back! |

`ZONE1_SHOTS = 10/10`. All shot text above is an exact match to `e10_final_screenplay_v1.md`
Zone 1 (Shots 1–10); no new dialogue was introduced by this Sprint.

### DL-01 — Protected Dialogue

The Zone 1 boss-identity thesis line (DL-01, Shot 8) remains protected in its Chinese form per the
integration contract:

```
zh-TW (protected source): 看清楚，再落子。
en (canonical localization, not a replacement): Look carefully. Then make your move.
```

The English line is a localization of DL-01, not a substitute for it. `e10_final_screenplay_v1.md`
remains the sole authority for the Chinese protected text; this document only adds its approved
English rendering.

### Approved Character Name Localization

```
小水 (given name of 水靈馬, per e10_final_screenplay_v1.md Zone 1 Shot 2) → Shui
```

This is the approved Zone 1 English spoken/subtitle localization for v1. No other character name
localizations are canonized by this Sprint.

---

## Locale and Fallback Rules

```
SUPPORTED_LOCALES = zh-TW, en
```

- The **active locale selects subtitle and voice together** — there is no independent
  subtitle-locale / voice-locale selection in v1.
- **`zh-TW` mode must never fall back to English voice.**
- **`en` mode must never fall back to Chinese voice.**
- **Missing same-language voice asset:** the correct-language subtitle still renders; voice falls
  back to silent (no audio plays). A missing `en` voice asset never triggers `zh-TW` voice
  playback, and vice versa.

```
WRONG_LANGUAGE_AUDIO_FALLBACK = FORBIDDEN
```

### Silence Shots

Shots S3, S5, S7, and S9 are structurally silent in the canonical screenplay (no dialogue, no
narration — see `e10_final_screenplay_v1.md` continuity notes for each). For both locales:

```
S3 / S5 / S7 / S9:
  SUBTITLE = NONE
  VOICE = NONE
```

This applies identically in `zh-TW` and `en` — silence is not locale-dependent, and no locale may
introduce narration text or a spoken line into these shots.

### Shared vs. Localized Elements

| Element | Behavior |
|---|---|
| BGM | Shared across languages — not localized |
| Ambience | Shared across languages — not localized |
| SFX | Shared across languages — not localized |
| Subtitle | Localized per active locale |
| Spoken voice | Localized per active locale |

---

## Voice Casting Status

This Sprint does **not** invent or canonize any voice casting decision. It records the currently
known status only.

### Chinese (zh-TW)

- Narrator direction: **Anna Su — Casual, Friendly and Bright**
- Current approved existing voice evidence: **Z1S1 zh-TW narration**
- All other character voices (Elder, Hero, Runner): **CASTING / AUDIO ASSET STATUS TO BE
  VERIFIED**

### English (en)

- Narrator and all character voices: **`PENDING_OWNER_AUDIO_CASTING`**

No English voice asset exists or is implied by this document. No Chinese voice asset beyond the
recorded Z1S1 narration evidence is asserted as approved by this document.

---

## Validation

```
ZONE1_SHOTS = 10/10
ZH_SCRIPT = COMPLETE
EN_SCRIPT = COMPLETE
SILENCE_SHOTS = S3/S5/S7/S9
DL01_ZH = EXACT
WRONG_LANGUAGE_AUDIO_FALLBACK = FORBIDDEN
NEW_DIALOGUE = 0
STORY_MUTATION = NONE
ART_MUTATION = NONE
RUNTIME_MUTATION = NONE
AUDIO_ASSET_MUTATION = NONE
```

`E10_Z1_BILINGUAL_SCRIPT_CANON_001: READY_FOR_OWNER_PR_REVIEW`
