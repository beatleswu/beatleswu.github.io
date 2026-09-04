# W1-04 Zone 3 final presentation-binding contract and test scaffold

Status: `PASS_ZONE3_FINAL_BINDING_CONTRACT_AND_SCAFFOLD_READY`

This is a Systems-owned integration-readiness contract. It prepares the later
Journey single-writer task; it does not perform final runtime binding.

## Immutable evidence boundary

| Input | Reference |
|---|---|
| source | `7da9bb235b6727f87f36d46c5890b337264260e2` / tree `5e14f3e0b2a1cb77b9814976b15563955c10aea4` |
| canonical master | `616d51b17abe010de1e862382ca4db7bec65936f` |
| WORLD FX package | `9c57faf4435fd3fa6a64ddf2d3b3559deec88d93` |
| JOURNEY locale voice manifests | `6e5d0b9d8999476776d1a48277c0604c26589916` |
| Playwright | `dddefed7b27ee17d65aba89823a47b0e0bd0d0ad` |
| integration checkpoint | `5fd9def812c230aa7089a8388be932bea8e7d0f7` |

The references are immutable inputs only. No candidate was cherry-picked or
merged. The JSON contract is the machine-readable source for this scaffold.

## Final component contract

- 10 cinematic shots: `SHOT01`–`SHOT10`, with `FIRST_ENTRY=SHOT01–05`,
  `BOSS_READY=SHOT06–07`, and `POST_CLEAR=SHOT08–10`.
- 2 World support images: the Zone 3 landmark and environment plate.
- 13 server-owned Normal monsters, 0 elites.
- Battlefield Boss `legacy_bf_03_boss` remains distinct from Lord
  `goblin_centurion`.
- 6 Lord presentation slots, all bound to the same Lord identity.
- 12 FX definitions and 10 camera cues from the WORLD runtime package.

Presentation assets, effects, locale selection, and replay are projections. They
cannot create or mutate zone clear, progression, rewards, Lord eligibility,
Lord defeat, Coins, items, purchase, equip, consume, payment, or revenue state.

## Locale and voice isolation

| Locale | Subtitle beats | Dialogue voice beats | Voice language | Missing/invalid voice |
|---|---:|---:|---|---|
| `zh-TW` | 97 | 97 | `zh` | subtitle-only, fail closed |
| `en-US` | 97 | 97 | `en` | subtitle-only, fail closed |

Cross-language voice fallback is `0`; a zh-TW voice cannot play for en-US and
vice versa. Locale switching changes presentation selection only and cannot issue
reward or complete cinematic/gameplay progression. Forged or duplicated beat IDs
are rejected/no-op.

## Audio controls and external dependencies

The later binding must preserve the existing global mute and fixed playback-level
architecture. `NEW_VOLUME_SLIDER=NO` and `NEW_AUDIO_MIXER_UI=NO`. Dialogue,
ambience, SFX, BGM, and transition audio all obey global mute.

W1-03 `_009` presentation audio and BGM are explicit external dependencies. The
fixture marks them `EXTERNAL_DEPENDENCY_PENDING`, with no manifest path, no fake
production audio, no placeholder assets, and no generation permitted. The
scaffold runs without those packages and becomes an input-consumption gate once
the exact owner-approved manifests are supplied.

## Replay, reduced motion, cleanup, and failure

Replay uses the same canonical 10-shot sequence, current locale, same-locale
subtitles/voice, and presentation FX. It may not duplicate persistent resources
or issue reward, zone-clear, zone-unlock, Lord-state, Coins, item, or mastery
mutations. The required cases are `FIRST_ENTRY`, `BOSS_READY`, `POST_CLEAR`, and
`REPLAY`.

Reduced motion keeps all story content and audio semantics available, reduces or
disables camera/nonessential motion according to the FX package, and does not
affect gameplay.

Cleanup is required at shot change, locale change, replay, cinematic exit, route
exit, and runtime presentation failure. It covers audio loops and one-shots,
timers, animation frames, particle emitters, event listeners, temporary DOM
nodes, and media objects. Post-cleanup gameplay remains available.

Missing images/audio, invalid hashes, VFX initialization failure, autoplay denial,
and forged/duplicated beat IDs degrade to presentation fallback or no-op. Missing
locale voice is subtitle-only. `PRESENTATION_FAILURE_MUST_NOT_BLOCK_GAMEPLAY=YES`.

## DoD mapping

The contract maps, without reopening the 40-item audit, to the existing open rows
for locales/voice isolation, presentation audio/mute, VFX/camera/transition,
reduced motion, replay, cleanup/fallback, browser acceptance, and authority-safe
handoff. See `master_dod_mapping` in the JSON and the existing 40-item matrix for
row status; this task changes no DoD classification.

## Scaffold checks

Test file: `tests/test_w1_04_zone3_final_presentation_binding_contract_006.py`

The checks cover:

- contract schema and exact component counts;
- same-locale voice and subtitle-only fail-closed fallback;
- global mute with no new slider/mixer UI;
- replay cases and no persistent mutation;
- reduced-motion semantics;
- cleanup resource coverage;
- presentation-failure gameplay no-op;
- Monster/Battlefield Boss/Lord separation;
- explicit external audio/BGM dependency without fake assets;
- mapping only to existing open DoD rows;
- zero presentation-owned authority writes.

## Boundaries

`JOURNEY_RUNTIME_CHANGED=NO`, `APP_PY_CHANGED=NO`, `GAMEPLAY_AUTHORITY_CHANGED=NO`,
`MERGED=NO`, `DEPLOYED=NO`, and `PRODUCTION_MUTATED=NO`. Final runtime binding
remains the separate Journey single-writer task.
