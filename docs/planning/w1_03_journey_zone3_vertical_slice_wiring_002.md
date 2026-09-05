# W1_03 — Zone 3 vertical-slice journey wiring

Task: `W1_03_JOURNEY_ZONE3_VERTICAL_SLICE_WIRING_002`

Base: `d6afb957a12891e69f4709b3909cf41f13cfbcd9`

This pass connects the accepted first-session journey contract to the
existing E9/legacy Adventure boundaries for Zone 3 (`k16_20`). It does not
add an endpoint, progression writer, reward writer, or artwork.

## Connected flow

`zone-selected` is an authoritative bootstrap snapshot used only to select a
presentation target. `current_zone_key` is retained separately as
`progressionZoneKey`; selecting Zone 3 never moves the player there.

The safe path is:

`Zone entry`
→ text-only first-entry cinematic fallback
→ existing `enterAdventureZoneInPage()` / question-loader handoff
→ existing Map Battle V1 attempt and answer projection
→ Battlefield Boss progress presentation
→ server bootstrap Lord-ready state
→ explicit Lord CTA
→ existing `/api/adventure/boss/start` and Lord review runtime
→ existing `/api/adventure/boss/finish` result
→ `BattlefieldBossRewardConsumer` projection
→ text-only post-clear fallback
→ server bootstrap Zone 4 (`k11_15`) hook
→ explicit replay-safe return to the map.

The Battlefield Boss and Lord Trial remain separate phases. An ordinary Map
Battle defeat does not clear a zone, grants no reward, and cannot trigger the
post-clear hook.

## Style-lock boundary

`zone3_entry_cinematic` and `zone3_post_clear_cinematic` are explicit
`PENDING_FINAL_ASSETS` slots with `runtimeAsset: null`, `finalArtwork: null`,
and `visualDetails: null`. The runtime fallback is `SAFE_TEXT_ONLY`. Existing
Zone 3 map landmark data remains a map presentation surface only; no new
Lord, companion, biome, palette, storyboard, or final audio language is
introduced here.

## Authority and replay

- Existing Adventure bootstrap owns Zone 3/4 entry, current location, boss
  readiness, clear state, and the Zone 4 hook.
- Map Battle V1 owns attempt identity, server monster projection, damage, and
  defeat feedback.
- Lord start/review/finish remains the existing server-backed gameplay path.
- `BattlefieldBossRewardConsumer` renders only the server reward projection.
  The page-memory journey controller deduplicates accepted reward events by
  the server's `entitlement_id`/`source_operation_id`; it never derives an
  item or grant.
- Lord replays may show the post-clear presentation, but the replay response
  is `NO_REWARD` and cannot enter the reward event.
- Skip/return are presentation actions. No seen marker, progression, unlock,
  reward, equipment, or payment state is written by the new modules.

## Shell boundary

The only shared-shell changes are the authorized Zone 3/onboarding slot,
script, CSS, and i18n wiring in `index.html` and `i18n.js`. The generic
`js/game/cinematic_replay.js` contract is unchanged. The E9 additions remain
non-critical and E9 production flags remain off by default.
