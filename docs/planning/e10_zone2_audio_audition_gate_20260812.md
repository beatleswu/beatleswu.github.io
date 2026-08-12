# E10 Zone 2 Audio Audition Gate 001

`E10_ZONE2_AUDIO_AUDITION_GATE_001`

This report records Phase 3 only. It is an audition pack, not a runtime
integration or a production asset lock.

Historical note: the `PENDING_OWNER` values below describe the state when this
Phase 3 pack was generated. The Owner subsequently locked V5 James, A3/B3/C3,
Shui reaction 2, and the approved ambient/SFX palette. The current Phase 4/5
record is [e10_zone2_audio_integration_gate_20260812.md](e10_zone2_audio_integration_gate_20260812.md).

## Identity and boundaries

| Field | Value |
|---|---|
| `BASE` | `fc8cd5dfe9451a7df872ef8866566b785acc6a70` |
| `WORKTREE` | `D:/e10-zone2-complete-production-20260812-01` |
| `BRANCH` | `codex/e10-zone2-complete-production-001` |
| `SCRIPT_VERSION` | `OWNER_APPROVED_V2` |
| `PROVIDER` | ElevenLabs |
| `MODEL` | `eleven_v3` |
| `AUDITION_PACK` | `tools/e10_zone2_audio/_local_review/zone2_audio_audition/` |
| `IPAD_PACK` | `owner_audition_embedded.html` (self-contained, 31 controls) |
| `CANONICAL_MANIFEST_CREATED` | `NO` |
| `ZONE2_RUNTIME_INTEGRATED` | `NO` |
| `ZONE2_AUDIO_LOCK` | `PENDING_OWNER` |

## Voice audition

- `HERDER_VOICE_CANDIDATES=3/3`: `HERDER_V1` Ling, `HERDER_V2` Yui,
  `HERDER_V3` Zack. All three read the exact locked V2 Herder line in zh-TW.
  They are not assigned to any Zone 1 locked role and remain
  `AUDITION_REQUIRED`.
- `PROTAGONIST_VOICE_CONTINUITY=PASS`: the locked Zone 1 Hero identity
  (`XXxvxx0YUt8icTEFE3c6`) rendered exact V2 Shot 2 and Shot 9 lines (`2/2`),
  with unchanged Zone 1 zh/en reference bytes included separately.
- `WATER_SPIRIT_HORSE_AUDIO_CONTINUITY=NONVERBAL`: no human dialogue; two
  subtle creature-reaction candidates were generated for listening only.
- `SWARM_LORD_AUDIO_MODEL=NONVERBAL_LIQUID_CREATURE_VOCAL`: emergence,
  movement, low-rumble, defeat, and crest-impact SFX were generated; no human
  Swarm Lord TTS or dialogue was generated.

## Music and sound candidates

| Family | Result |
|---|---:|
| `BGM_A_CANDIDATES` (Shots 1–4) | `3/3` |
| `BGM_B_CANDIDATES` (Shots 5–7) | `3/3` |
| `BGM_C_CANDIDATES` (Shots 8–10) | `3/3` |
| `SFX_AUDITION_STATUS` | `15/15` |
| MP3 manifest/hash/duration verification | `PASS` |

The 15 sound candidates cover grassland ambience, frightened and normal slime
movement, distant and close bee activity, hive cave ambience, Swarm Lord
emergence/movement/low rumble/defeat, crown crest impact, plains recovery,
Zone 3 route reveal, and two Shui reactions.

## Review artifacts

- `audition_manifest.json`: candidate IDs, prompts, voice IDs, durations,
  bytes, SHA-256 values, and generation provenance.
- `shot_audio_map.md`: provisional Shot 1–10 mapping; no candidate is final.
- `audition_notes.md`: listening order and Owner decision fields.
- `index.html`: relative-path iPad/desktop review page.
- `owner_audition_embedded.html`: self-contained iPad/desktop page with all 31
  review audio controls embedded as data URLs.

## Explicit non-actions

```text
ZONE2_RUNTIME_INTEGRATED=NO
ZONE2_CANONICAL_AUDIO_MANIFEST=NOT_CREATED
ZONE1_MODIFIED=NO
ZONE3_STARTED=NO
SGF_TOUCHED=NO
WORKFLOW_V2_TOUCHED=NO
PRODUCTION_MUTATION=NO
DEPLOY_EXECUTED=NO
SECRET_SENTINEL_TOUCHED=NO
```

Next gate: Owner listens and selects `HERDER_VOICE`, `BGM_A`, `BGM_B`,
`BGM_C`, the SFX palette, Shui reaction, and Swarm Lord rumble. Only after
those choices may `ZONE2_AUDIO_LOCK=YES` and Phase 4 final asset preparation
begin.
