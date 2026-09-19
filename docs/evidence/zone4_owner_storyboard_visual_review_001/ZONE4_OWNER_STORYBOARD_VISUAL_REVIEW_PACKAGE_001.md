# Zone4 Owner Storyboard Visual Review Package 001

## Review scope

This is an Owner-review evidence package generated from the accepted,
uncommitted `ZONE4_CINEMATIC_STORYBOARD_RUNTIME_RECOVERY_001` candidate.
It adds no gameplay, commerce, progression, reward, database, or Production
behavior. The generated images are review artifacts only.

```text
APP_PY_CHANGED=NO
DB_CHANGED=NO
PLAYER_DATA_CHANGED=NO
PRODUCTION_MUTATION=NO
BUILD=NO
DEPLOY=NO
```

`REAL_OWNER_DEVICE_UAT=PENDING`. The Safari/PWA images below are deterministic
responsive mock captures derived from the current shared Adventure structure;
they are not screenshots of the Owner's iPad.

## 1. Storyboard contact sheet

[ZONE4_STORYBOARD_CONTACT_SHEET.png](./ZONE4_STORYBOARD_CONTACT_SHEET.png)

The contact sheet contains all 22 main-story shots in exact runtime order.
Each tile shows the shot ID, section, image, speaker, zh-TW dialogue copy,
voice filename, and manifest duration.

```text
STORYBOARD_SHOTS=22
IMAGE_AND_VOICE_COMPLETE=YES
VOICE_ONLY_COUNT=0
PRE_LORD_RANGE=Z4_S1_01–Z4_S2_08 (16 shots)
POST_LORD_RANGE=Z4_S3_01–Z4_S3_06 (6 shots)
LORD_CHECKPOINT_VISIBLE_IN_CONTACT_SHEET=YES
CHECKPOINT=Z4_S2_08 -> authoritative Lord result -> Z4_S3_01
```

The red divider is intentionally labeled:

```text
=== LORD CHALLENGE CHECKPOINT ===
```

No post-Lord visual appears in the pre-Lord group. The sheet is generated
from `ZONE4_RUNTIME_MANIFEST.json`, so the image/voice pairing is not inferred
from filenames alone.

## 2. Lord card contact sheet

[LORD_TRIAL_CONTACT_SHEET.png](./LORD_TRIAL_CONTACT_SHEET.png)

This sheet shows the historical dedicated 6/6 WebP package on the left and
the current Zone4-selected presentation on the right. It makes the important
distinction visible: the historical package is not Zone4 cinematic art, and
the current Zone4 Lord UI is bound to `assets/e10/art/zone4/lord/`, not to the
`assets/e10/art/zone4/cinematic/` shots.

```text
LORD_ASSET_COUNT=6
HISTORICAL_LORD_TRIAL_WEBP=6/6
ZONE4_LORD_ASSET=assets/e10/art/zone4/lord/Z4-LORD-01.png (challenge entry; six-asset package total)
EMOJI_FALLBACK_REMOVED=YES for Zone4 k11_15
```

Current Zone4 role mapping shown in the sheet:

| Historical role | Current Zone4 selected asset |
|---|---|
| Lord challenge backplate | `Z4-LORD-01.png` |
| First-star success backplate | `Z4-LORD-04.png` |
| First-star icon | `Z4-LORD-05.png` as first-clear success portrait; no standalone Zone4 star-icon asset is substituted |
| Lord ritual key art | `Z4-LORD-02.png` |
| Lord failure backplate | `Z4-LORD-03.png` |
| Village elder reference | No direct Zone4 selection; reference-only |

## 3. Zone4 card evidence

These are representative source-derived mock captures at an iPad portrait
viewport. They show the shared Zone Card action ordering without changing any
authority:

- [ZONE4_CARD_EVIDENCE_FIRST_CLEAR_MOCK.png](./ZONE4_CARD_EVIDENCE_FIRST_CLEAR_MOCK.png)
  - normal/pre-Lord state
  - `繼續冒險`
  - `挑戰領主`
  - `補星修行`
- [ZONE4_CARD_EVIDENCE_REPLAY_MOCK.png](./ZONE4_CARD_EVIDENCE_REPLAY_MOCK.png)
  - cleared/replay-capable state
  - `繼續冒險`
  - `重溫故事`
  - `再次挑戰領主`
  - `補星修行`

The replay CTA is visibly placed in the same action row as the existing
Adventure/Lord/training actions. The capture labels replay as presentation-only:

```text
PROGRESSION_DELTA=0
COINS_DELTA=0
XP_DELTA=0
STAR_DELTA=0
REWARD_DELTA=0
LORD_RESULT_DELTA=0
QUESTION_HISTORY_DELTA=0
```

`FIRST_CLEAR_REPLAY_SEMANTICS_SEPARATED=YES`: first-clear success uses the
first-clear presentation; replay completion does not imply a new star or
first-clear reward.

## 4. Safari / installed PWA responsive evidence

- [SAFARI_RESPONSIVE_EVIDENCE_MOCK.png](./SAFARI_RESPONSIVE_EVIDENCE_MOCK.png)
  - simulated iPad Safari portrait surface
- [PWA_RESPONSIVE_EVIDENCE_MOCK.png](./PWA_RESPONSIVE_EVIDENCE_MOCK.png)
  - simulated iPad standalone/PWA portrait surface

Both deterministic mock captures retain:

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

The PWA mock shows `display-mode: standalone`, safe-area handling, and
vertical flow. It is evidence of the intended source layout contract only.
It does not prove active-worker/cache/byte parity on a real installed app.

```text
SAFARI_RESPONSIVE_EVIDENCE=DETERMINISTIC_MOCK
PWA_RESPONSIVE_EVIDENCE=DETERMINISTIC_MOCK
REAL_OWNER_DEVICE_UAT=PENDING
```

## 5. Evidence manifest

[EVIDENCE_MANIFEST.json](./EVIDENCE_MANIFEST.json) records the generated
PNG dimensions and SHA256 values. The generator is retained at
[generate_evidence.py](./generate_evidence.py) so the review package can be
reproduced from the same candidate and current repository assets.

## Final report

```text
STORYBOARD_SHOTS=22
IMAGE_AND_VOICE_COMPLETE=YES
VOICE_ONLY_COUNT=0

PRE_LORD_RANGE=Z4_S1_01–Z4_S2_08
POST_LORD_RANGE=Z4_S3_01–Z4_S3_06
LORD_CHECKPOINT_VISIBLE_IN_CONTACT_SHEET=YES

LORD_ASSET_COUNT=6
ZONE4_LORD_ASSET=assets/e10/art/zone4/lord/Z4-LORD-01.png (challenge entry; six-asset Zone4 package)
EMOJI_FALLBACK_REMOVED=YES

REPLAY_STORY_CTA_VISIBLE=YES in replay-capable source-derived mock
FIRST_CLEAR_REPLAY_SEMANTICS_SEPARATED=YES

STORYBOARD_CONTACT_SHEET=ZONE4_STORYBOARD_CONTACT_SHEET.png
LORD_CONTACT_SHEET=LORD_TRIAL_CONTACT_SHEET.png
ZONE4_CARD_EVIDENCE=ZONE4_CARD_EVIDENCE_FIRST_CLEAR_MOCK.png; ZONE4_CARD_EVIDENCE_REPLAY_MOCK.png
SAFARI_RESPONSIVE_EVIDENCE=SAFARI_RESPONSIVE_EVIDENCE_MOCK.png
PWA_RESPONSIVE_EVIDENCE=PWA_RESPONSIVE_EVIDENCE_MOCK.png

REAL_OWNER_DEVICE_UAT=PENDING

APP_PY_CHANGED=NO
DB_CHANGED=NO
PLAYER_DATA_CHANGED=NO
PRODUCTION_MUTATION=NO
BUILD=NO
DEPLOY=NO

FINAL_STATUS=READY_FOR_OWNER_VISUAL_STORYBOARD_REVIEW
```
