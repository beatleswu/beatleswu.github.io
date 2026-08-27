# D031 — Spirit Adventure Milestone Unlock Presentation

## Contract

D031 is a presentation-only consumer of the server-authored result returned
by the D030 Adventure milestone service. It does not determine eligibility,
write Spirit ownership, or call an unlock operation.

The only accepted transport field is the optional
`adventure_spirit_unlock_results` field on the authoritative Adventure boss
settlement response. Each entry must preserve the D030 result facts:

| Server status | Presentation state | Meaning |
| --- | --- | --- |
| `UNLOCKED` | `NEW_SPIRIT_UNLOCK` | D030 committed one new `pet_collection` ownership mutation. |
| `NO_OP` or `REPLAY` | `ALREADY_OWNED_NO_OP` | The milestone is already recorded; no new ownership is created. |
| `NOT_ELIGIBLE` | `NO_MILESTONE_UNLOCK` | No eligible milestone unlock was committed. |

Any missing, mismatched, unknown, or contradictory result fact fails closed.
An absent transport field is also silent: D031 never derives a result from a
selected zone, a Monster result, a Battlefield Boss result, a Quest flag, or a
client-authored field.

## Stable mapping

The presentation mapping is a display lookup keyed by the exact D030 stable
zone key. It is not an ownership catalog and does not replace the Adventure
or B023 authority.

| Zone number | Stable zone key | Spirit | Presentation asset |
| ---: | --- | --- | --- |
| 4 | `k11_15` | `starpath_antlerling` | `pet_starpath_antlerling_stage1.webp` |
| 6 | `k1_5` | `fatty` | `pet_fatty_stage1.webp` |
| 8 | `d3_4` | `obsidian_bastion` | `pet_obsidian_bastion_stage1.webp` |

The server-provided `spirit_id` is checked against this mapping; it is not
replaced by a display label or arbitrary asset key. A missing asset only
produces a visual fallback and cannot change unlock state.

## Presentation rules

- `NEW_SPIRIT_UNLOCK` shows the mapped Spirit and that it joined the player’s
  collection.
- `ALREADY_OWNED_NO_OP` shows that the milestone is already recorded and
  creates no new ownership affordance.
- `NO_MILESTONE_UNLOCK` shows a neutral result with no acquisition promise.
- The card has only a Continue/close action. It does not claim, retry, grant,
  compensate, replace, randomize, equip, or activate combat behavior.
- No coins, rarity, drop chance, cash value, or Spirit combat effect is
  presented.

When D030 returns several valid results (for example, historical catch-up),
the consumer presents actionable results in stable zone-number order and
collapses ineligible-only noise to one neutral card. Replays remain no-op
presentation states.

## Runtime transport boundary

At the D031 parent (`c116341d4bee35212ba2bcdb3283d1ce09f8334d`),
`/api/adventure/boss/finish` calls the D030 catch-up service but does not yet
include its returned results in the JSON response. The `index.html` hook is
therefore deliberately conditional and dormant until a separately authorized
server transport change exposes the exact field. D031 does not modify
`app.py`, and the review fixture supplies explicit D030-shaped server facts
only for contract and visual verification.

This preserves the authority direction:

```text
Adventure settlement + D030 result
        ↓
optional server response field
        ↓
D031 presentation consumer
```

## Validation evidence

Focused Node coverage is in
`tests/e9_node_tests/run_d031_spirit_unlock_presentation_tests.js`.
The visual fixture is
`tests/e2e/fixtures/d031_spirit_unlock_presentation.html`; its URL accepts
`case=zone4`, `case=zone6`, `case=zone8`, `case=already-owned`, or
`case=no-unlock`. Captured review images live under `docs/review/d031/`.

No D031 code changes `app.py`, schema/migrations, World progression, Spirit
ownership, Quest, Battlefield Boss, or Learning correctness.
