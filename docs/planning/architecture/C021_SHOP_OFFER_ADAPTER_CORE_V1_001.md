# C021 — Shop Offer Adapter Core V1

Status: implementation candidate; Owner review required.

R1 closure: zero-price `FREE_OFFER` facts are now rejected before
normalization. The R1 commit is a focused descendant of the original C021
head `f8124b4d77cf04f2b9fb09fd5e8a5f14faeb93fe`; it does not expand the C019
positive-price contract.

C021 is a pure server-domain normalization layer. It turns caller-supplied
facts already resolved from an existing server catalog into a deterministic,
server-owned Coin offer shape that can later be passed to the accepted C019
`CoinShopOffer` contract. It does not execute a purchase.

## Provenance and boundaries

| Field | Value |
|---|---|
| Repository | `D:\go-website` |
| Start `origin/master` | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| Base | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| Branch | `codex/c021-shop-offer-adapter-core-v1` |
| C019 accepted reference | `cb8f7e07350edb873c6300bfae3680819b0329f6` |
| C020 accepted reference | `2d2d20afad69fe7b7e0b00f2c78c74f9b9d7694c` |
| Runtime source changed | `shop_offer_adapter.py` only; no existing route is wired |
| App / schema / Production | untouched |

The canonical checkout had a pre-existing tracked planning change before this
work. The C021 work was performed in an isolated worktree and did not alter
that checkout.

## No second catalog

`shop_offer_adapter.py` contains no `SHOP_ITEMS`, cosmetic product table,
daily-slot table, price table, or product grant catalog. Its input is either a
`ServerCatalogFacts` value or a caller-supplied mapping containing facts such
as:

- stable existing `product_id` and resolved `item_id`;
- server-resolved `server_price` and its `price_reference`;
- server-resolved destination, class, quantity, and duplicate policy;
- catalog and eligibility references;
- optional date and grant-shape facts.

The caller remains responsible for obtaining those facts from the existing
server source. A client price, client quantity, or client offer ID is not an
accepted input. The adapter derives `offer_id`; it never trusts an incoming
`offer_id`.

## Normalized contract

`NormalizedCoinShopOffer.as_dict()` returns exactly these C021 fields:

| Field | Rule |
|---|---|
| `offer_id` | deterministic server-derived identity |
| `offer_version` | `vN` for fixed offers; `vN@YYYY-MM-DD` for daily offers |
| `product_id` | existing machine identity, not localized text |
| `item_id` | one canonical item identity for a ready single-result offer |
| `quantity` | positive server-resolved integer |
| `currency` | always `COINS` |
| `server_price` | positive server-resolved integer; no zero-price exception |
| `destination` | ready shapes are `shop_inventory` or `player_wardrobe` |
| `acquisition_class` | existing V1 item taxonomy |
| `duplicate_policy` | `STACK`, `REJECT_IF_OWNED`, or `ALLOW_DUPLICATE` |
| `eligibility_reference` | server eligibility evidence/reference |
| `price_reference` | server price evidence/reference |
| `catalog_reference` | source catalog evidence/reference |
| `offer_kind` | canonical shape such as `FIXED_ITEM` or `DAILY_WARDROBE` |
| `metadata` | JSON-serializable presentation/source metadata only |

`as_c019_mapping()` supplies the corresponding C019 names too:
`currency_type=COINS`, `price=server_price`, `offer_type`,
`eligibility_metadata`, and `presentation_metadata`. A later integration layer
can call:

```python
offer = CoinShopOffer.from_mapping(normalized.as_c019_mapping())
```

That import and the C019 transaction remain outside C021. C021 does not debit
Coins, acquire an item, create a purchase operation, open or commit a
transaction, write D5A, or invoke D5C.

## Stable offer identity

Offer IDs are derived from the server product identity and a version token:

| Shape | Derived ID |
|---|---|
| fixed item | `shop.item.<product_id>.v1` |
| fixed wardrobe | `shop.cosmetic.<product_id>.v1` |
| daily item | `shop.daily.item.<product_id>.v1` |
| daily wardrobe | `shop.daily.appearance.<product_id>.v1` |

The product/business identity is date-independent. For a daily offer, the
server-supplied `business_date` participates in both:

```text
offer_version          = v1@YYYY-MM-DD
eligibility_reference  = daily_shop:YYYY-MM-DD:<product_id>
```

The date is therefore part of C019 mutation/replay semantics without making a
client-authored or date-only ID the business identity. The client cannot
choose the ID, date, version, or price through this module.

## Accepted and rejected shapes

### Ready shapes

The adapter directly returns `READY` for one server-resolved result targeting:

- `shop_inventory` with an existing canonical item class and a declared V1
  duplicate policy;
- `player_wardrobe` with `COSMETIC` class and no declared gameplay effect.

Pure cosmetics remain wardrobe-owned and cannot become combat power through
this adapter.

### Explicit non-ready classifications

`adapt_shop_offer()` returns a decision with no normalized offer for:

- `pet_inventory` → `NEEDS_DESTINATION_ADAPTER`;
- more than one grant component → `NEEDS_MULTI_GRANT_PROFILE`;
- a pet multi-grant → both blockers, with destination adapter reported as the
  primary status.

`normalize_shop_offer()` turns those non-ready decisions into `OfferNotReady`
so a future purchase caller cannot accidentally execute them.

### Fail-closed policy exclusions

The adapter rejects, rather than silently normalizing:

- Premium cash subscriptions and Premium entitlements;
- `robe_premium` from the Coin path;
- gacha, loot-box, or random-reward shapes;
- legacy effect-bearing appearance facts;
- unknown destinations;
- unknown duplicate policies;
- client-authored `offer_id`, `price`, price override, or requested quantity;
- negative, zero, floating-point, bool, or missing Coin prices;
- `FREE_OFFER`, including `free_offer_approved=true`, because a free grant is
  not a zero-Coin C019 purchase;
- `xp_amulet`, which remains `HOLD_FOR_AUTHORITY`;
- `go_stone_black`, which remains `TROPHY / INVENTORY_ONLY / NO_COMBAT_POWER`.

Direct cash Revenue V1 remains Premium-only. C021 introduces no Coin packs,
cash equipment, cash consumables, paid PvE power, gacha, or random paid
rewards.

### Free-grant boundary

`FREE_OFFER` is retained only as an explicit rejected input classification.
It never produces a `NormalizedCoinShopOffer`, never receives a `shop.free.*`
ID, and never reaches `as_c019_mapping()`. The future topology is:

```text
server promotional/free-grant eligibility
    -> separately approved free-grant authority
    -> acquisition result / D5A as applicable
```

It is not a zero-Coin debit, a special C019 purchase, or a C019-owned free
item authority. The current rejection carries the precise status
`NEEDS_FREE_GRANT_AUTHORITY` in its typed error details.

## Grant handling

A single grant is accepted only when its item and quantity agree with the
normalized `item_id` and `quantity`. A product with multiple grants is not
flattened into the first component or a fake bundle item. It remains
`NEEDS_MULTI_GRANT_PROFILE` for a later C019-compatible multi-grant result
contract.

## Relation to current catalog authorities

C020 identified the current source surfaces as `app.py:SHOP_ITEMS`, daily shop
slots, `COSMETIC_COMMERCE_PRODUCTS`, the gacha route, and Premium cash plans.
C021 does not merge those surfaces or declare a new catalog. The future
application wiring task must choose the existing server source for each fact
set, then call this adapter. Premium cash and gacha sources must be filtered
before C019 wiring, while current pet-food and multi-grant products require
the explicit adapter statuses above.

## Public API

```python
decision = adapt_shop_offer(server_facts)
offer = normalize_shop_offer(server_facts)  # READY only; otherwise raises
offers = normalize_shop_offers(server_fact_iterable)
```

The batch helper only normalizes ready offers and rejects derived offer-ID
collisions. It does not store the result or make it globally authoritative.

## Validation evidence

The focused suite covers:

- fixed Coin, daily discounted, and wardrobe shapes;
- deterministic repeat normalization and derived IDs;
- C019 mapping aliases and server-price provenance;
- client price and client offer-ID rejection;
- Premium cash, `robe_premium`, gacha, and legacy-effect rejection;
- `pet_inventory` destination classification;
- single- and multi-grant handling;
- unknown destination and duplicate-policy fail-closed behavior;
- positive-price C019 compatibility and zero-price/free-grant rejection;
- batch duplicate-ID detection.

No database was opened or mutated. No Shop route, UI, payment provider,
Premium entitlement, C019 purchase transaction, D5A lineage, or D5C item-use
path was changed.

## Next wiring boundary

The next implementation task must remain responsible for selecting the
existing `app.py` server catalog facts, applying live eligibility, and passing
only `READY` normalized offers into C019. It must not copy this module into a
second catalog, trust a browser price, route Premium cash through Coins, or
implement pet/multi-grant acquisition without the declared adapters.
