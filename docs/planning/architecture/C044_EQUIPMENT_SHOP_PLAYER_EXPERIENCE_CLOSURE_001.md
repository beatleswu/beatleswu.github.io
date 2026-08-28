# C044 Equipment Shop Player Experience Closure

Task: `C044_EQUIPMENT_SHOP_PLAYER_EXPERIENCE_CLOSURE_001`

This source candidate is based exactly on C043 commit
`00b4840a44d29ec09dcc800b83c8065e367ace44`, which is intentionally not merged
to `origin/master`. It closes the player-facing Shop contract without
reimplementing the C043 commerce service.

## Player journey

The source journey is:

```text
server equipment_offers
  -> Shop catalog/detail
  -> server-supplied COINS price and catalog Coins balance
  -> pending Buy state
  -> existing POST /api/shop/buy + C019 operation identity
  -> validated canonical acquisition result
  -> success or recoverable error feedback
  -> catalog/Coins/ownership refresh
  -> the same player_inventory ownership shown by Backpack
```

The Shop must not display an equipment offer unless the server catalog has
provided a valid C043 offer. The browser does not create products, prices,
rarity, discounts, stock, scarcity, DPS, timers, or compensation policy.

## Authority and boundaries

- Catalog and price authority remain the existing server Shop/catalog
  projection and C019 offer fields.
- Coins are displayed from the authoritative catalog response; a browser
  purchase does not permanently decrement the balance optimistically.
- Ownership is the canonical `player_inventory` authority. A Backpack link
  may be derived only from the exact validated
  `player_inventory:<positive-row-id>` reference returned by the server.
- C019's `purchase_operation_id` remains the idempotency/retry identity.
- `purchase != equip` and `acquire != equip`. The source candidate has no
  automatic equip action and does not bypass the disabled Loadout gate.
- NewebPay, PayPal, cash flows, callbacks, credentials, Production settings,
  schema, migrations, `app.py`, and the unapplied C043 patch are outside this
  change.

## State requirements

The Buy control has an explicit pending state and is disabled while its
request is in flight. A duplicate click/replay must not create a second
visual grant or a second browser-side ownership record. Only a server
response that passes the C043 canonical acquisition-result checks may enter
the success state. Error, timeout, network, stale-catalog, insufficient-Coins,
already-owned, and in-progress responses restore a usable CTA and provide a
useful message; none fabricates ownership or a balance mutation.

After a confirmed result, Shop reloads the authoritative catalog rather than
maintaining a Shop-only ownership cache. The resulting ownership badge/CTA
and the Backpack view therefore converge on the same server inventory. When
the server does not provide ownership metadata in the catalog, the browser
does not infer it.

## Release posture

This is a source candidate only. `SHOP_ENABLED=NO` and `LOADOUT_ENABLED=NO`
remain unchanged. An authenticated browser session is not required for this
contract artifact; runtime cross-surface evidence must be reported separately
if the harness is unavailable.
