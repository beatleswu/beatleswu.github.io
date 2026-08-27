# D033 Adventure Boss Finish Spirit Result Response Adapter

## Scope

D033 prepares the additive response boundary for
`/api/adventure/boss/finish`. It does not change `app.py`, the route, the
Adventure settlement, the D030 milestone service, B023 Spirit ownership, or
the D031 presentation code.

The adapter accepts only an already validated
`AdventureSpiritUnlockTransportResult` from D032. It appends the serialized
list under the exact response key:

```text
adventure_spirit_unlock_results
```

No request field, selected zone, Monster result, Battlefield Boss result,
Quest result, UI flag, or client-authored state participates in composition.

## Existing response preservation

`compose_adventure_boss_finish_response(existing_response, result)` returns a
new mapping containing every existing key and value plus exactly one additive
`adventure_spirit_unlock_results` key. It does not rename, nest, recalculate,
or overwrite existing response data. If the field is already present, the
adapter fails closed with `RESPONSE_FIELD_ALREADY_PRESENT` so a later route
cannot accidentally attach two response authorities.

The current route continues to return its existing response shape because
D033 intentionally does not wire `app.py`.

## D032 state preservation

The response adapter never re-resolves the D030 zone-to-Spirit mapping. D032
has already validated it through the D030 resolver and remains the sole
transport normalizer.

| D032 input | serialized meaning |
| --- | --- |
| `UNLOCKED` | new server-committed Spirit ownership; `ownership_created=true` |
| `NO_OP` | already-owned no-op; no new ownership, compensation, or replacement |
| `REPLAY` | replay transport fact; retained as `status=REPLAY`, with D032 `result_state=NO_OP` and zero new unlocks |
| `NOT_ELIGIBLE` | explicit neutral result for a known mapped zone; no ownership claim |

The exact locked upstream mappings remain D030-owned:

```text
k11_15 -> starpath_antlerling
k1_5   -> fatty
d3_4   -> obsidian_bastion
```

The mapping is not copied into the response adapter.

## No-result and historical semantics

When the server has no Spirit milestone result (for example, a failed boss
attempt that did not run D030 catch-up), the adapter emits:

```json
{"adventure_spirit_unlock_results": []}
```

This is the neutral empty-list representation. It does not fabricate a
Spirit, ownership, `UNLOCKED`, or `NO_OP` object. When D030 supplies a known
mapped but ineligible result, the explicit D032 `NOT_ELIGIBLE` object is
serialized instead.

Historical catch-up is serialized as `UNLOCKED` only when the D030/B023
authoritative mutation actually produced that result. The D032
`historical_catchup` field is preserved only when explicitly supplied by the
server caller; the adapter never guesses it from a zone or response shape.

## Fail-closed boundary

The adapter accepts a D032 immutable typed result or a list/tuple of those
results. Raw D030 dictionaries, client-shaped objects, unknown states,
altered typed fields, duplicate `(user_id, zone_key)` identities, and
malformed transport values fail closed. A failed composition returns no
partial fabricated result.

The result is revalidated through D032 before serialization. This means a
directly constructed or altered dataclass cannot be silently repaired at the
response boundary.

## D031 compatibility

The value at `adventure_spirit_unlock_results` is passed directly to D031's
existing `normalizeResults`/`present` consumer. No extra client normalization
or client inference is required. D031 continues to map server statuses to
presentation states and remains presentation-only.

## Future thin `app.py` wiring site

The future single-writer change belongs in the existing
`adventure_boss_finish()` response construction path, after the authoritative
D030 catch-up has run in the caller-owned Adventure settlement transaction and
before the existing `jsonify(...)` return.

The intended sequence is only:

1. retain the D030 catch-up outcome instead of discarding it;
2. convert that outcome through D032's typed transport builder;
3. call `compose_adventure_boss_finish_response(existing_response, typed_result)`;
4. return the composed response.

If there is no D030 outcome for a failed/non-milestone settlement, pass
`None` and the adapter supplies the neutral empty list. The route remains the
Adventure/World settlement authority; this helper only composes a response.

## Explicit non-authority boundaries

- Adventure settlement remains the authority for `adventure_boss_progress`.
- D030 remains the authority for milestone eligibility and the B023 unlock
  execution sink.
- B023 and `pet_collection` remain Spirit ownership authority.
- D031 remains presentation-only.
- This module performs no database reads/writes, transactions, retry,
  unlock, compensation, Quest, Monster, Battlefield Boss, World, or UI
  authority action.
