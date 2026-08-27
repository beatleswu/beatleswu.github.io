# D032 Adventure Spirit Unlock Result Transport Contract

## Scope

D032 defines the server-authored response fragment
`adventure_spirit_unlock_results` for the D031 presentation.  It is a pure
validator/projector over an already completed D030-R2 outcome.  It does not
wire `app.py`, call a database, mutate `pet_collection`, or create another
Spirit/world authority.

The later route writer attaches the serialized list only after the
authoritative Adventure settlement has run D030's milestone catch-up through
the existing B023 `SPIRIT_UNLOCK` sink.  D032 deliberately does not change
the current route response.

## Authority and mapping

The input is accepted only when it carries the D030 facts:

`ADVENTURE_ZONE_MILESTONE` → `adventure_boss_progress.cleared=1` →
`SPIRIT_UNLOCK` → `pet_collection`.

The transport imports D030's `resolve_milestone_for_zone`; it does not copy or
redefine the mapping.  The locked outcomes remain:

| D030 zone key | Zone | Spirit |
| --- | ---: | --- |
| `k11_15` | 4 | `starpath_antlerling` |
| `k1_5` | 6 | `fatty` |
| `d3_4` | 8 | `obsidian_bastion` |

No `selectedZone`, Monster, Battlefield Boss, Quest, client flag, or UI state
is read.

## Contract

Transport field: `adventure_spirit_unlock_results`

Contract version: `ADVENTURE_SPIRIT_UNLOCK_RESULT_TRANSPORT_V1`

Each list item retains the D030/D031-compatible server fields and adds the
normalized result semantics:

| Field | Meaning |
| --- | --- |
| `result_state` | `UNLOCKED`, `NO_OP`, or `NOT_ELIGIBLE`; D030 `REPLAY` normalizes to `NO_OP`. |
| `ownership_created` | True only for a D030 `UNLOCKED` mutation count of one. |
| `already_owned` | True for D030 `NO_OP` and replayed `REPLAY`; never a compensation signal. |
| `historical_catchup` | Explicit server-caller context; D032 fails closed if omitted. |
| `replay` | Transport/replay fact; it is independent from new ownership. |
| `reason_code` | Stable transport classification derived from the validated D030 terminal state. |

The retained fields include `user_id`, exact `zone_key`, `zone_number`,
mapped `spirit_id`, D030 `operation_id`, `source_reference`, source authority
and fact, `operation_status`, `replayed`, mutation counts, zero compensation
and replacement counts, `ownership_store=pet_collection`, and
`client_completion_authority=false`.

`historical_catchup` is intentionally explicit because D030's current result
dictionary is shared by normal settlement and catch-up.  The future route
caller must pass `false` for a normal settlement result and `true` for the
catch-up result list.  This is server context, not a client field.  If an
embedded marker is present, it must agree with the caller context.

## State rules

- `UNLOCKED`: `ownership_created=true`, `already_owned=false`, `replay=false`,
  eligible/cleared true, completed operation, counts one.
- `NO_OP`: `ownership_created=false`, `already_owned=true`, `replay=false`,
  eligible/cleared true, completed operation, counts zero.
- `REPLAY`: `result_state=NO_OP`, `ownership_created=false`,
  `already_owned=true`, `replay=true`, completed operation, counts zero.
- `NOT_ELIGIBLE`: `ownership_created=false`, `already_owned=null` because
  D030 has not read the ownership row on this branch,
  `replay=false`, eligible/cleared false, no operation status, counts zero.

Unknown statuses such as `SUCCESS`, `REJECTED`, incomplete operations,
mismatched zone/Spirit/operation/source identities, client completion
authority, non-zero compensation/replacement, and conflicting normalized
fields fail closed.  The transport never fabricates an unlock result.

Lists are sorted by D030 zone number and duplicate `(user_id, zone_key)`
items are rejected.  JSON serialization is stable.  D031's existing
`normalizeResult` consumes the retained D030 fields directly; no client
inference was added.

## Explicit non-authority boundaries

- D030 owns eligibility, exact milestone mapping, historical catch-up, and
  B023 execution.
- B023/`pet_collection` remains the Spirit ownership authority.
- Adventure progression remains the World authority.
- D032 performs no grant, unlock, retry, transaction, database, schema,
  lineage, Quest, Monster, Battlefield Boss, or UI authority action.
- D031 remains presentation-only and receives only this server-authored list
  when a later `app.py` transport task is authorized.
