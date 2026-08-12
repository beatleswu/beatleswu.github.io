# E10 Zone 2 Final Bilingual Integration Gate

Status: `IMPLEMENTATION_PENDING_OWNER_REVIEW`

This gate records the single-PR Zone 2 integration prepared from the exact
latest `origin/master` captured on 2026-08-12. It does not authorize merge or
Production deployment.

## Immutable inputs

- Base: `8910160855030d6266b52b63242b7a9c384d0e24`
- Branch: `codex/e10-zone2-final-bilingual-integration-001`
- Script: `OWNER_APPROVED_V2`
- Final art: `assets/storyboards/e10_z2_shot01.webp` through
  `e10_z2_shot10.webp`, attachment order preserved.
- Runtime phases: FIRST_ENTRY `1-4`, BOSS_READY `5-7`, POST_CLEAR `8-10`.
- Progress: historical correct-answer mastery at 30%.
- Post-clear authority: authoritative Lord success only.

## Locked audio

- Herder zh-TW: V5 James, `UwT0JPexcCbH107hq7i5`.
- Herder en: same James identity, cross-language identity preserved.
- Hero zh-TW: Roy, `XXxvxx0YUt8icTEFE3c6`.
- Hero en: Anvay, `6aOpkucJD6a4vTXyUKon`.
- Shui: nonverbal, selected reaction 2.
- BGM: A3 / B3 / C3 for discovery / escalation / recovery.
- Pronunciation lock: `睡個安穩覺` uses `jiào`.
- Package: 23 exact-byte files, including 6 bilingual dialogue files.

## Runtime and locale contract

The Zone 2 cinematic resolves all player-facing copy through the existing
`I18n` dictionary (`en` and the project `zh` locale, representing zh-TW) and
selects locale-matched dialogue audio. BGM, ambience, and SFX are shared.
Portrait and landscape alter presentation only; they cannot alter shot order,
locale semantics, progression, Lord authority, or map unlock state.

Lord success remains the only source that can present POST_CLEAR. Zone 3 clear
and route state are read from the server response; the client only visualizes
the returned state and does not write unlock authority. Zone 3 cinematic/audio
runtime is intentionally not implemented.

## Scope boundary

Allowed: Zone 2 final art, locked bilingual audio, cinematic wiring, i18n,
responsive layout, Lord/map handoff, focused tests, manifests, and this gate
documentation. Forbidden: Zone 3 implementation, SGF, Workflow V2, Player
Avatar Marker, Production mutation, deployment, and secret sentinel access.
