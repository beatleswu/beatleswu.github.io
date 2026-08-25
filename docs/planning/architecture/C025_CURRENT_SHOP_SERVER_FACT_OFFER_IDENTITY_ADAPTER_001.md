# C025 Current Shop Server-Fact Offer Identity Adapter

Task: `C025_CURRENT_SHOP_SERVER_FACT_OFFER_IDENTITY_ADAPTER_001`

This candidate implements the thin adapter recommended by C024-R1. It projects
caller-supplied, already server-resolved Shop facts into deterministic
C021-compatible offer identity and version fields. It is not a Shop catalog,
purchase service, ownership writer, or route integration.

## Provenance and boundary

| Fact | Value |
|---|---|
| Implementation base | `67b31b3c9fdb5526b2d7f86a568d21951c70eb1a` |
| C021-R1 input | `8af8e69cd22b1fddb2dab8e9b769067091d51d90` |
| C023 input | `ab588aa28cbae92a8c29bffe575b67b1f3207793` |
| C024-R1 input | `e761a589c6bbb4ff5301266fa67c900e33195685` |
| D022 input | `7ab57ee78c74aa4526bfa29b6a8a0aa998604882` |
| Runtime route wiring | Not performed |
| Coin debit / ownership grant | Not performed |
| Database writes | None |

The module does not import `app.py`, does not copy `SHOP_ITEMS`,
`APPEARANCE_DEFS`, `COSMETIC_COMMERCE_PRODUCTS`, `PET_FOOD_CATALOG`, payment
plans, or gacha pools, and does not create `purchase_operation_id`.

The caller remains responsible for resolving the existing server catalog and
for supplying trusted facts. A client request, display price, or client offer
ID cannot be passed through as an authoritative field.

## Input and output contract

`ServerShopOfferFacts` accepts the following server-fact concepts:

- offer family and authoritative item/product identity;
- item ID, quantity, positive integer `server_price`, and `currency`;
- destination, acquisition class, duplicate policy;
- eligibility, price, and catalog references;
- optional daily flag/date, grant profile, and exclusion flags.

`project_shop_offer()` returns a `ShopOfferProjection`. A `READY` result
contains `NormalizedShopOffer`; blocked source facts return an explicit status
and do not produce an executable offer. `normalize_shop_offer()` is the
fail-closed convenience API that raises `OfferNotReady` for a blocked result.

The ready projection includes:

```text
offer_id
offer_version
product_id
item_id
quantity
currency=COINS
server_price
destination
acquisition_class
duplicate_policy
eligibility_reference
price_reference
catalog_reference
offer_kind
metadata
```

`NormalizedShopOffer.as_c019_mapping()` maps the projection to the accepted
C019 `CoinShopOffer.from_mapping()` shape. It contains no transaction or
purchase-operation identity.

## Identity rules

### Static Shop items

The first slice uses the exact namespaced identity:

```text
shop.static.<authoritative item_key>
```

The item key is a server fact. It is stable across retries and does not depend
on client input, time, randomness, database row order, or a newly-created
catalog table.

### Explicit Coin cosmetics

When the server has an explicit mapped product identity, the projection uses:

```text
shop.cosmetic.<authoritative product_id>
```

The product ID is preferred over deriving a business identity from display text
or an appearance slot. Premium-only products are not eligible for this path.

### Version projection

`offer_version` is deterministic and uses the documented algorithm
`sha256-canonical-server-facts-v1`. The version payload includes the derived
business identity and the authoritative facts that affect purchase semantics:

- offer family and daily flag/date;
- product ID, item key, and item ID;
- currency and positive server price;
- quantity, destination, acquisition class, and duplicate policy;
- canonical single-grant profile.

The emitted form is `v1-<20 hex characters>` for static offers. Daily offers
use `v1-<YYYY-MM-DD>-<20 hex characters>`. Thus a price, quantity, destination
or grant-semantics change changes the version without changing a static
business identity. A daily offer keeps its logical identity across dates while
the shop date changes its version.

The version is not a purchase operation ID. C025 explicitly leaves
`PURCHASE_OPERATION_ID_READY=NO` for the later C019 route/idempotency seam.

## Supported first slice

The 14 C024-R1 ready identities are intentionally narrow:

| Shape | Identities | Destination | Duplicate policy |
|---|---|---|---|
| Direct stackable Shop item | `hint_ticket`, `ai_explain_ticket`, `extra_questions_small`, `extra_questions`, `grand_training_pass`, `small_xp_potion`, `xp_potion`, `grand_xp_potion`, `streak_shield`, `double_streak_shield`, `rare_appearance_fragment`, `pet_evolution_core` | `shop_inventory` | `STACK` |
| Explicit Coin cosmetic | `robe_plain`, `robe_bamboo` | `player_wardrobe` | `REJECT_IF_OWNED` |

The module does not broaden this slice to make blocked catalog rows appear
ready. Direct item facts are required to be non-cosmetic, single-grant,
stackable Shop-inventory acquisitions. Explicit Coin cosmetics require one
wardrobe grant, quantity one, and a server product ID.

## Explicit exclusions and blockers

| Source fact | Result |
|---|---|
| `pet_inventory` | `NEEDS_DESTINATION_ADAPTER` |
| More than one grant | `NEEDS_MULTI_GRANT_PROFILE` |
| Daily appearance without product identity | `NEEDS_CATALOG_NORMALIZATION` |
| Legacy effect-bearing appearance | `LEGACY_EFFECT_EXCLUDED` |
| Zero-price/free offer | `NEEDS_FREE_GRANT_AUTHORITY` |
| Premium cash | `PREMIUM_CASH_SEPARATE` |
| Premium entitlement, including `robe_premium` | `PREMIUM_ENTITLEMENT_SEPARATE` |
| Gacha/random offer | `GACHA_EXCLUDED` |
| `xp_amulet` | `AUTHORITY_HOLD` |
| `go_stone_black` | `TROPHY_INVENTORY_ONLY` |

The C019 price contract remains positive integer Coins only. A free grant is a
future separate promotional/grant authority, not a zero-Coin purchase. C025
does not implement that authority.

The C024-R1 classification counts retained by the focused regression fixture
are:

```text
READY_FOR_C021_C019       14
NEEDS_DESTINATION_ADAPTER  4
NEEDS_MULTI_GRANT_PROFILE  5
NEEDS_CATALOG_NORMALIZATION 16
LEGACY_EFFECT_EXCLUDED     4
```

These are classification assertions, not a second runtime catalog.

## Authority boundaries

```text
existing server catalog / route facts
              |
              v
  shop_offer_identity_projection
              |
              +--> stable offer_id
              +--> deterministic offer_version
              +--> C021-compatible normalized offer
              |
              +--> explicit blocked classification

later C019 route/service
              |
              +--> purchase operation identity
              +--> Coin debit
              +--> acquisition / D5A
              +--> deterministic replay
```

C025 does not execute `purchase_with_coins`, call `_spend_coins`, write
`player_inventory` or `player_wardrobe`, append D5A, use D5C, or invoke C023's
Equipment writer. D022 ownership references and canonical-slot projections are
also outside this adapter.

## Validation evidence

The focused test module covers:

- static identity/version stability and semantic version changes;
- daily same-date stability and cross-date version changes;
- product-based mapped cosmetic identity;
- server-only positive pricing and client-field rejection;
- zero/free, Premium, gacha, legacy-effect, locked-item, pet, multi-grant,
  and unmapped daily-cosmetic exclusions;
- C019 mapping shape without purchase-operation identity;
- the 14/4/5/16/4 classification counts;
- source-level absence of copied catalog registries and mutation/DB helpers.

The module is projection-only; no test opens a database or mutates ownership,
Coins, D5A, or purchase operations.

## Deferred integration

The next route integration task must obtain one server-owned fact record from
the existing catalog/route boundary, call this adapter, and pass only a
`READY` normalized offer to C019. It must resolve the purchase operation ID
separately, preserve C023's slot source injection boundary, and keep Premium,
free grants, gacha, pet inventory, and multi-grant profiles on their approved
separate paths.
