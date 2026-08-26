# E030 Shop Coin Purchase and Equipment Runtime Integration

Status: implementation candidate with E030-R1 closure applied; Owner review required.

Original E030 base: `18de673fa62b82c7be0b2c89ee80dd421148bd1d`.
E030-R1 recovery base: `e10735cf580fb5074e07811f76ab60445562760c`.

E030 integrates accepted service authorities into the current Flask runtime
without changing schema, enabling a feature, querying Production, or deploying.
Lane E is the only `app.py` writer for this candidate.

## Runtime seams

| Seam | Existing entry point | E030 orchestration | Authority retained |
| --- | --- | --- | --- |
| Monster functional Equipment grant | `_settle_monster_defeat_in_tx` → nested `grant_functional_item` | `grant_equipment_ownership(..., source="drop")` once per quantity; exact inserted row is read back by returned id | Monster settlement decides the drop; B040 writes ownership |
| Admin functional Equipment grant | `admin_set_equipment` | `grant_equipment_ownership(..., source="admin")` | Existing admin authentication, validation, audit, and response |
| Equip/Unequip | `POST /api/player/inventory/equip` → `equip_item` | B034 desired-state service only when the loadout gate is on | B034 owns canonical slot/state; B036 legacy lock behavior remains when off |
| Coin Shop purchase | `POST /api/shop/buy` → `shop_buy`; daily cosmetics via `POST /api/shop/buy_appearance` → `shop_buy_appearance` | server facts → C025/C029 projection → C019/C026 purchase → commit → D024 adapter | Existing catalog/ownership/lineage services |

## Feature gates

The following request-time environment gates use the repository’s existing
`_env_flag_enabled` convention and default to false when absent:

* `CANONICAL_COIN_SHOP_PURCHASE_ENABLED`
* `EQUIPMENT_CANONICAL_LOADOUT_ENABLED`

When either gate is off, the existing route body remains in control. E030 does
not set either flag in repository, Production, or deployment configuration.

When the loadout gate is on, a missing or malformed B033 schema returns a stable
schema error and does not fall back to direct legacy equip SQL. The narrow B036
legacy `xp_amulet` unequip recovery therefore remains part of the gate-off
compatibility path; new functional equip is still rejected and
`go_stone_black` remains non-equippable.

## Canonical Coin purchase flow

The enabled path resolves only server-owned facts. The request may identify a
current `item_key`, `product_id`, `item_id`, or derived `offer_id`, and must
provide a stable `purchase_operation_id`, `operation_id`, or `Idempotency-Key`.
The server route never invents an operation identity; the real Shop client
now creates one secure UUID per purchase intent and reuses it for retry.
Client price, quantity,
destination, acquisition class, canonical slot, and grant details are ignored
as authority.

The call sequence is:

```text
authenticated session
  → server Shop facts / daily rotation
  → normalize_shop_offer (C025/C029)
  → StaticShopOfferAuthority (C019)
  → purchase_with_coins (C026)
  → caller commit
  → committed operation + D5A evidence
  → adapt_committed_shop_purchase (D024)
  → JSON response
```

C026 remains the sole Coin debit/operation/acquisition authority. Its caller
transaction includes operation reservation, the server-priced Coin debit,
ownership mutation, exact ownership reference, D5A lineage, and committed
result payload. E030 never commits inside a service and never returns success
before the commit.

After commit, D024 adaptation is read-only. If adaptation fails, the route
returns `canonical_result_unavailable`; a retry with the same operation identity
replays the committed C026 result and does not debit or acquire again.

For `player_inventory`, the response and D024 result use the exact C026
`player_inventory:{inserted_row_id}` reference. E030 does not use `MAX(id)`, a
latest-row query, timestamps, or reconstructed ownership identities.

## Catalog scope

`SHOP_ITEMS` currently has zero real functional Equipment offers. E030 adds no
products. The canonical runtime accepts current single-grant stackable Shop
items and pure Coin wardrobe products already represented by the server
catalog. Existing bundles, pet grants, legacy effect-bearing products, and
other multi-grant shapes remain on their existing route until a separately
approved adapter exists.

Synthetic Weapon, Armor, and Accessory facts are used only by disposable tests;
they are not inserted into `SHOP_ITEMS` or exposed as real offers.

`xp_amulet` remains `AUTHORITY_HOLD`; `go_stone_black` remains
`TROPHY_INVENTORY_ONLY`. Neither is a functional Coin Equipment offer.

## Schema and release boundary

E030 does not run migrations. The canonical purchase path requires the already
accepted C026 purchase-operation schema and its acquisition dependencies when
enabled; absent schema fails closed. Canonical loadout mode requires valid B033
schema/invariants when enabled; legacy mode remains available before B033.

The safe release sequence remains B039 Option C:

1. merge compatible runtime code;
2. perform a fresh Production read-only preflight;
3. freeze `player_inventory` mutation traffic;
4. receive `GO_PRODUCTION_DB_MIGRATION` and apply approved schemas;
5. deploy compatible current-master application code;
6. receive explicit authorization before enabling canonical loadout or Shop;
7. validate invariants and smoke tests;
8. reopen traffic.

E030 performs none of steps 2–8.

## Validation boundary

The focused E030 suite covers legacy and post-B033 B040 grants, B034 default-off
and opt-in behavior, locked-item protections, current stackable and wardrobe
purchase paths, synthetic functional Equipment, exact ownership references,
same-operation replay, insufficient Coins rollback, and post-commit D024
presentation failure recovery. E030-R1 adds pre-mutation dispatch, real
Shop-client operation identity lifecycle, and exact duplicate ownership-row
loadout coverage. Existing B034/B036/B040/C026/C029/D024 suites remain
required regressions.

E030-R1 changes only the real `shop.html` callers for operation identity; it
does not change `sw.js`. The repository's static release tooling governs the
`i18n.js`/`sw.js` static pack, while HTML uses the existing network-first
behavior, so no Service Worker version bump is required for this HTML change.

## E030-R1 closure

The R1 repair closes the three Owner-review blockers without changing product
catalog facts or enabling either feature:

1. Both Shop POST routes classify the server-owned request before any
   operation reservation, Coin debit, ownership mutation, legacy grant, or
   commit. `CANONICAL_READY` uses C025/C029 → C019/C026 → D024;
   `LEGACY_ONLY` falls through to the unchanged legacy implementation; and
   `INVALID` fails closed. A canonical or post-commit presentation failure is
   never retried through the legacy path.
2. `shop.html` `buyItem` and `buyAppearance` call the shared
   `requestShopPurchase` helper. It uses `crypto.randomUUID()` (or the
   browser's cryptographic UUID fallback), scopes the pending intent to route
   and offer, retains it for network/503/in-progress recovery, and clears it
   on success or a definitive terminal error.
3. The authenticated `inv_id` lookup supplies the server row's `id` and
   `equip_id` to B041 as `ownership_row_id` and never uses body `equip_id`,
   `slot`, or `canonical_slot` as target authority. Duplicate rows therefore
   equip or unequip only the requested ownership row.

The real current catalog still contains zero functional Equipment Shop
offers. `xp_amulet` remains authority-held and `go_stone_black` remains
trophy/inventory-only. B040 Monster/Admin writers, B034/B041 loadout mode,
Option C release sequencing, and all Production boundaries remain unchanged.
