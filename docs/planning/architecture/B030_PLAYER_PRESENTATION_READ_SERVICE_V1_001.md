# B030 Player Presentation Read Service V1

Status: implementation candidate; route-agnostic read boundary only.

Implementation base: B028 accepted head
`2c8b879a8667c0247c23e560475ee29fafad508d`.

Origin/master observed at B030 start:
`58d9b7047f285751a048fc551c955909c87984ac`.

This document defines a service boundary for a future authenticated API
caller. It does not create a Player authority, a functional Hero authority,
a route, a migration, or a mutation path.

## Purpose and authority rule

B028 remains the only Player/Hero state aggregator:

```text
caller-owned connection + authenticated user ID
    -> build_player_presentation_state(...)
        -> B028 build_player_state_read_model(...), exactly once
            -> stable, detached, JSON-safe service envelope
```

`player_presentation_read_service.py` performs no SQL. It does not own the
connection lifecycle, authentication, Flask session, Player mutation,
equipment mutation, Spirit mutation, combat calculation, or World
progression. The caller owns the connection and transaction boundary.

## Service contract

The public builder is:

```python
build_player_presentation_state(conn, *, user_id)
```

On a valid read it returns:

```text
{
  "contract_version": "PLAYER_PRESENTATION_READ_CONTRACT_V1",
  "status": "OK | PARTIAL | INVALID_STATE | UNAVAILABLE",
  "player_state": <complete B028 player_hero_state projection>,
  "warnings": <B028-supplied warnings, otherwise []>,
  "read_only": true,
  "mutates": false
}
```

The complete B028 object remains under `player_state`; fields are not
flattened into a second Hero, progression, equipment, Spirit, or World
authority. B028 provenance and group-level projection statuses are retained
unchanged.

The service maps B028 top-level statuses as follows:

| B028 projection status | B030 service status |
| --- | --- |
| `OK` | `OK` |
| `PARTIAL` or `OPTIONAL_PROJECTION_UNAVAILABLE` | `PARTIAL` |
| `INVALID_STORED_STATE` | `INVALID_STATE` |
| `AUTHORITY_AMBIGUOUS` | `INVALID_STATE` |
| `AUTHORITY_UNAVAILABLE` | `UNAVAILABLE` |

An invalid or ambiguous B028 projection is never converted to `OK`.

## Stable error boundary

`PlayerPresentationReadServiceError` exposes only `code` and `status` to a
future API layer. It never serializes SQL text, credentials, filesystem
paths, or a traceback.

| Condition | Service error code | Status |
| --- | --- | --- |
| Non-positive, boolean, or non-integer user ID | `INVALID_USER_ID` | `INVALID_STATE` |
| B028 missing player or unavailable required authority | `PLAYER_STATE_UNAVAILABLE` | `UNAVAILABLE` |
| B028 ambiguous/invalid projection, malformed state, or unsupported result | `PLAYER_STATE_INVALID` | `INVALID_STATE` |

The error object has `as_dict()` for a future route adapter. No Flask
`Response` is returned from this module.

## JSON and mutation boundary

`build_player_presentation_state` creates a detached JSON-safe copy of the
B028 projection. Common legacy `datetime`, `date`, `time`, `Decimal`, and
`UUID` values receive deterministic representations; arbitrary driver or
custom objects fail closed as `PLAYER_STATE_INVALID`. The separate
`serialize_player_presentation_state(result)` helper uses sorted keys and
compact separators for deterministic API serialization.

B030 contains no `INSERT`, `UPDATE`, `DELETE`, DDL, commit, rollback, or
connection lifecycle operation. A connection spy test proves the service
delegates to B028 without issuing SQL itself, and a call-count test proves
the B028 entrypoint is invoked once per read.

## Preserved B028 authority groups

| Group | B028 authority preserved by B030 | B030 behavior |
| --- | --- | --- |
| Hero | `player_appearance.character_key` | `authority_scope=presentation_only`; no functional Hero fields |
| XP/level | `user_stats.xp`, `rank_level`, `rank_xp`, existing level resolver | pass through; no new XP formula or ledger |
| Persistent HP | `user_stats.player_hp`, `player_max_hp` | pass through persistent/global boundary only |
| Encounter HP | Map Battle/encounter-local state | excluded from the Player field; boundary metadata remains intact |
| Equipment | `player_inventory` ownership/equipped rows | pass through resolved slots; conflicts remain unresolved |
| Spirit | B022/D008 server active-Spirit projection | pass through one active Spirit; no B027 evaluation |
| Cosmetics | `player_wardrobe` and `player_appearance` | presentation-only; no combat power |
| World | World system authority | boundary metadata only; no guessed progression fields |

In particular:

* `xp_amulet` remains `HOLD_FOR_AUTHORITY`.
* `go_stone_black` remains an inventory-only trophy with no combat power.
* B028-R1's conflicted equipped slot remains unresolved, and no item in that
  slot is effectively equipped.
* A missing Hero selection remains truthful (`hero_id=None`) with B028's
  presentation fallback metadata; B030 does not persist or promote it.
* `selectedZone`, quest state, zone clear, Stars, Lord readiness, and other
  World progression are not invented or promoted into Player state.

## Future route topology

The future single-owner route should authenticate first, then pass its
caller-owned connection and authenticated user ID to this service, and
serialize the returned envelope. The route must not re-query or reassemble
Hero, XP/level, HP, Equipment, Spirit, Cosmetics, or World fragments.

This task does not add that route. E023/A024/F011 remain owners of their
respective integration and presentation decisions.

## Validation

The focused B030 tests cover:

* valid complete projection and exactly-one B028 invocation;
* presentation-only Hero, missing/invalid Hero propagation;
* XP/level and persistent-HP projection with encounter-HP exclusion;
* valid equipment, conflicting slots, and duplicate equipped-item rows;
* active/no-active Spirit and cosmetic/world boundaries;
* detached deterministic JSON-safe serialization;
* invalid user IDs and stable B028/unexpected-error mapping;
* connection-spy proof that B030 issues no SQL of its own.

Observed validation on the B030 worktree:

* B030 focused suite: **15 passed**;
* B028 focused suite, including B028-R1 conflict cases: **18 passed**;
* combined Player/Equipment/Spirit regression selection (including D007
  lineage and E019 harness): **102 passed, 14 pre-existing Pillow deprecation
  warnings**.

The B028 focused suite remains a separate regression gate. No `app.py`,
`player_state_read_model.py`, frontend, schema, migration, or Production
surface is changed by B030.

## Explicit exclusions

B030 does not create or own:

* a functional Hero selector, Hero roster expansion, or Hero gameplay stats;
* an XP ledger, level curve, or progression mutation;
* persistent encounter HP or combat settlement;
* equipment ownership/equip/consume authority or combat stats;
* Spirit ownership, activation, progression, evolution, or B027 effects;
* cosmetic gameplay power;
* World progression, quests, zones, Boss/Lord state, or reward authority;
* an API route, UI adapter, migration, deployment, or Production mutation.
