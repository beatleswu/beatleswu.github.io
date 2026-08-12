# E10 Zone 2 Bilingual Audio Integration Gate

Status: `OWNER_AUDIO_LOCKED / BILINGUAL_RUNTIME_INTEGRATED_PENDING_REVIEW`

This record captures the Owner's final Zone 2 audio lock and the corresponding
runtime-only integration performed in the isolated worktree. It is not a merge,
deployment, or Production authorization.

## Identity

- Repository: `D:\\go-website`
- Historical worktree (preserved, not reused for the final PR):
  `D:\\e10-zone2-complete-production-20260812-01`
- Final fresh worktree: `D:\\e10-zone2-final-bilingual-integration-20260812-01`
- Final branch: `codex/e10-zone2-final-bilingual-integration-001`
- Final base captured before local work:
  `8910160855030d6266b52b63242b7a9c384d0e24`
- Script: `OWNER_DIALOGUE_V3` (Owner-approved V3 bilingual dialogue)

## Owner lock

| Lock | Selected identity |
|---|---|
| Herder | `HERDER_V5_JAMES` (`UwT0JPexcCbH107hq7i5`) |
| BGM A / FIRST_ENTRY | `A3` |
| BGM B / BOSS_READY | `B3` |
| BGM C / POST_CLEAR | `C3` |
| Shui reaction | `SFX_SHUI_REACTION_B` / `2` |
| Other ambient/SFX | `APPROVED_AS_CURRENT` |
| Mandarin pronunciation | `睡個安穩覺` verified as `jiào` (`ㄐㄧㄠˋ`) |

Rejected Herder candidates V1–V4 and V6, Shui reaction A, and the V5
pronunciation-only review sample remain review evidence and are not runtime
assets. The written script retains `覺`; the narrow TTS-only homophone control
used `叫` to obtain the verified `jiào` pronunciation.

## Promoted canonical assets

- Final art: `10/10`, attachment order preserved, `1280x720` WebP.
- Audio: `53` selected files (36 V3 dialogue, 3 BGM, 3 ambience, 11 SFX), each SHA-256 verified by
  `assets/e10/audio/zone2/zone2-audio-package.json`.
- Dialogue: Owner V3 Hero and Herder beats on Shots 2, 3, 4, 7, 9, and 10 in
  both `zh-TW` and `en`; Shots 1, 5, 6, and 8 remain silent by design.
  English Hero reuses Anvay (`6aOpkucJD6a4vTXyUKon`). Chinese Herder uses
  Brb (`BrbEfHMQu0fyclQR7lfh`); English Herder uses the approved clean retake
  of Ali (`dqdOhmL2BvMSx2KtSAtN`).
- Swarm Lord: creature-vocal/liquid rumble SFX only; no human Lord dialogue.
- Water Spirit Horse: remains nonverbal; selected reaction is SFX `2`.

## Runtime phase wiring

- `FIRST_ENTRY`: Shots 1–4, A3 + plains ambience.
- `BOSS_READY`: Shots 5–7, B3 + hive ambience; player still explicitly
  starts the Lord Trial.
- `POST_CLEAR`: Shots 8–10, C3 + recovery ambience; only authoritative Lord
  success reaches this phase and the existing server-derived Zone 3 reveal.
- Lord card, ritual, result, and route-reveal cues use the selected Zone 2 SFX
  package. The UI continues to visualize server unlock state and does not write
  unlock authority.

English audio was generated with the locked Zone 1 identities and exact-byte
promoted into the final package. The English lines are semantically aligned
with `OWNER_DIALOGUE_V3`; no locale falls back to the other locale's dialogue.

## V3 dialogue lock update

The prior sparse V2 Shot 2/4/9 dialogue remains historical audition evidence
only. It is not present in the runtime package; in particular, the former
"same sickness" line is removed from runtime subtitles and audio mapping.

## Gate boundaries

`ZONE2_RUNTIME_INTEGRATED=YES_IN_FRESH_LATEST_MASTER_WORKTREE`

`ZONE2_EN_AUDIO_COMPLETE=YES`

`ZONE2_I18N_COMPLETE=YES`

`ZONE2_RWD_VALIDATION=REQUIRED_BEFORE_PR`

`ZONE2_AUDIO_LOCK=YES`

`ZONE2_PROVENANCE_REFRESH=DEFERRED`

`ZONE2_MERGED=NO`

`PRODUCTION_MUTATION=NO`

`DEPLOY_EXECUTED=NO`

`ZONE3_STARTED=NO`

`SGF_TOUCHED=NO`

`WORKFLOW_V2_TOUCHED=NO`

`SECRET_SENTINEL_TOUCHED=NO`
