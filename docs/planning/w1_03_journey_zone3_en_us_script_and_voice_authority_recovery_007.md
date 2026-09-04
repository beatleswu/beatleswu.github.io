# W1-03 Zone 3 en-US script and voice-authority recovery

Task: `W1_03_JOURNEY_ZONE3_EN_US_SCRIPT_AND_VOICE_AUTHORITY_RECOVERY_007`

## Source lock

- Source head: `f77bce46302974c8a8aa9d296ae0ea548a707691`
- Source tree: `14131e16578699392aa4b599531a601b16a63a1a`
- Accepted zh-TW dialogue source: `assets/e10/i18n/zone3/zone3-cinematic-subtitles.json`
- Accepted zh-TW audio remains unchanged and is not reused for en-US.

## Current authority audit

Zone 1 and Zone 2 both have Owner-locked English Hero audio using Anvay,
voice ID `6aOpkucJD6a4vTXyUKon`. Zone 3 has the accepted 97-beat zh-TW
manifest, but its current `i18n.js` entries intentionally have empty `en`
values and its runtime audio manifest is zh-TW-only. No current 97-beat
English Zone 3 dialogue or English Zone 3 runtime audio exists at the source
lock. `ZONE3_EXISTING_ENGLISH_SCRIPT_CLASSIFICATION = NONE` for the current
97-beat contract. Older screenplay prose is not promoted as the current
English script.

The continuity decision is therefore:

| Character | en-US authority | Wave 1 action |
| --- | --- | --- |
| Hero | Existing canonical Anvay mapping from Zone 1 and Zone 2 | Preserve; no replacement audition |
| Grik | None | One Owner-review audition using Zack `DSyEP4HEaCKur8rFFOri` |
| Centurion | None | One Owner-review audition using Kevin Tu `BrbEfHMQu0fyclQR7lfh` |

## Exact en-US script

The exact 97-beat script is in:

`assets/e10/i18n/zone3/zone3-cinematic-subtitles-en-US.json`

It preserves every accepted `SHOT_ID`, `BEAT_ID`, `CHARACTER`, story-order
position, and lifecycle. The application locale alias is `en -> en-US`.
This is a subtitle contract only; it does not approve or bind any English
voice.

The English wording keeps the child-readable story facts intact: displaced
goblin families, household belongings, Grik's fatigue and guardedness, the
shrinking cave, the blocked water route, Centurion's protective last-gate
role, the intent test, the fragile truce, the ordinary Stone Shard, and the
Misty Forest hook. The Centurion anchor is `I am the last gate.` The Stone
Shard is described as a clue and a record of an old path, never as magical,
runed, legendary, or powerful. The final Grik reminder is split across the
same two beats as zh-TW: `Don't just remember the path—` / `Remember who lives
along it, too.`

## English audition contract

The bounded generator is:

`tools/e10_zone3_en_us_voice_preflight/generate_auditions.py`

It reads only the already-authorized `ELEVENLABS_API_KEY` process environment
and delegates TTS requests to the established Zone 1 helper. It writes only
Owner-review files under `tools/e10_zone3_audio/_local_review/auditions/en-US`
and the package manifest
`tools/e10_zone3_audio/zone3_en_us_voice_audition_manifest.json`. It has no
runtime output path, no cross-language fallback, and no full-production mode.

The package is created only after both exact one-line auditions decode and
have recorded bytes, duration, and SHA-256. New voice choices remain
`OWNER_APPROVAL: PENDING`; technical QA cannot approve acting quality.

At the time of this preflight, `ELEVENLABS_API_KEY` was unavailable in the
authorized process environment, so the two audio files and Owner package
were not fabricated. The generator fails closed with
`BLOCKED_AUDIO_AUTH_ONLY`; re-run it after the Owner supplies the authorized
environment credential. No credential value is recorded here.

## Boundaries

- No full 97-beat en-US audio was generated.
- No English audio was bound to runtime.
- No zh-TW content, runtime authority, gameplay, progression, reward,
  equipment, shop, payment, SFX, VFX, World, or Hero asset was changed.
- Replay remains compatible at the data-contract level because en-US uses the
  same stable beat identities and i18n keys; final runtime locale/audio
  selection remains a later integration gate.
