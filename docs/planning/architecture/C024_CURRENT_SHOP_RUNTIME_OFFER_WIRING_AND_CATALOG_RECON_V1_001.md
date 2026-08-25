# C024-R1 Current Shop Runtime Offer Reconciliation

`TASK=C024_R1_PUBLICATION_ARTIFACT_COMPLETION_AND_CURRENT_MASTER_OVERLAY_001`

`STATUS=DOCS_JSON_COMPLETION_AND_PUBLICATION_CANDIDATE`

This report completes the original C024 reconciliation from a fresh current
master. It does not implement C019, C021, or C023 runtime behavior, does not
change `app.py`, and does not treat accepted candidate commits as merged code.

## 1. Provenance

| Field | Value |
|---|---|
| `ORIGINAL_C024_HEAD` | `0c166440a9894bcd07bcea6b0dbeea8372bdb32b` |
| `ORIGINAL_RECON_START_MASTER` | `b75308d44806bb7c2e2b131a73ba06a71c188b3c` |
| `CURRENT_RECONCILED_MASTER` | `a1ad78154858b9369e90c748f842401c40fb18cd` |
| Current branch | `codex/c024-r1-current-shop-runtime-offer-recon` |
| Current branch base | `a1ad78154858b9369e90c748f842401c40fb18cd` |
| Canonical remote | `https://github.com/beatleswu/beatleswu.github.io.git` |
| C020 status | Historical evidence only |
| `B035_USED_IN_INITIAL_RECON` | `NO` |
| `B035_OVERLAY_REFERENCE` | `9361f7de31c0f1a189b19202ce20dd21c6cd690b` |

Accepted references remain unmerged candidates:

| Candidate | Owner status | Current-master runtime |
|---|---|---|
| C019 `cb8f7e07350edb873c6300bfae3680819b0329f6` | Accepted reference | No |
| C021-R1 `8af8e69cd22b1fddb2dab8e9b769067091d51d90` | Accepted reference | No |
| C023 `ab588aa28cbae92a8c29bffe575b67b1f3207793` | `OWNER_ACCEPTED_UNMERGED_CANDIDATE` | No |
| B035 `9361f7de31c0f1a189b19202ce20dd21c6cd690b` | Owner-accepted recon | No Commerce runtime |

## 2. Current-master overlay

The post-initial-recon history between `b75308d4` and current master contains
PR400 Player Presentation work and PR401's `xp_amulet` guard.

### PR400

PR400 merge base/result: `e2669bfa8582239dd001dbb41b2cd134923e9e27`.
Its `app.py` change adds the authenticated read-only
`GET /api/player/presentation` route and imports presentation read/contract
services. The remaining PR400 files are presentation read-model modules,
contract tests, and route tests. They do not define or mutate:

- `SHOP_ITEMS` or `COSMETIC_COMMERCE_PRODUCTS`;
- `/api/shop/*` or `/api/cosmetic-commerce/*` purchase routes;
- `_spend_coins`, `_grant_coins`, `daily_shop`, or gacha cost/randomness;
- `PAY_PLANS`, `PAYPAL_PLANS`, or Premium cash pricing.

### PR401

Current master is the PR401 merge commit. Its `app.py` runtime addition is a
server-side rejection of equipping `xp_amulet`. It does not alter Shop catalog,
Coin price/debit, daily generation, Premium cash products, or gacha behavior.

```text
SOURCE_DRIFT_INVALIDATES_C024=NO
```

The source-count assertions below were recomputed from current `app.py`, not
copied from C020 or the initial C024 report.

## 3. Current source-of-truth map

| Source | Current authority | Consumers | Ownership/mutation role |
|---|---|---|---|
| `app.py:SHOP_ITEMS` | 21 static product definitions and positive integer prices | `/api/shop/catalog`, `/api/shop/buy`, `/api/shop/use`, gacha item pool | Price/product/grant facts; not a C019 operation store |
| `app.py:_daily_shop_slots` + `daily_shop` | Server-date rotation: 3 item slots plus 2 appearance slots | `/api/shop/catalog`, `/api/shop/buy`, `/api/shop/buy_appearance` | Dynamic server price/eligibility facts; no explicit C021 offer version in response |
| `app.py:APPEARANCE_DEFS` | 64 appearance identities; 22 visible common/uncommon daily candidates | Daily rotation and cosmetic presentation | Appearance identity/definition; not Coin ownership authority |
| `app.py:COSMETIC_COMMERCE_PRODUCTS` | 2 Coin products and 1 Premium product | `/api/cosmetic-commerce/*` | Explicit cosmetic product identity and price facts |
| `app.py:APPEARANCE_EFFECTS` | 20 effect-bearing appearance identities | Appearance effect projection | Gameplay-effect authority; effect-bearing identities are not pure cosmetics |
| `app.py:PET_FOOD_CATALOG` | 3 Spirit food identities | Shop grants and companion surfaces | Definition only; quantity authority is `pet_inventory` |
| `app.py:PAY_PLANS` / `PAYPAL_PLANS` | 4 Premium cash plan entries | Payment routes and callbacks | Cash/Premium authority, outside C019 |
| `rpg_item_registry.py` | Read-only product/grant/art projection | Shop catalog response and presentation | Not price, ownership, Coin, or acquisition authority |
| `shop.html` | Server-response presentation and identity-only requests | Shop UI | Client only; no authoritative price or grant input |

## 4. Reconciled current counts

The denominators are explicit. Static products, daily appearance views, and
gacha reward identities are not blindly added as separate ownership rows.

| Metric | Current value |
|---|---:|
| `TOTAL_DECLARED_SERVER_DEFINITIONS` | 28 |
| `STATIC_SHOP_ITEMS` | 21 |
| `DISTINCT_COIN_PURCHASABLE_IDENTITIES` | 43 |
| `DAILY_APPEARANCE_IDENTITIES` | 22 |
| `PREMIUM_CASH_ENTRIES` | 4 |
| `GACHA_REWARD_IDENTITIES` | 41 |
| `LEGACY_FALLBACK_APPEARANCE_ENTRIES` | 20 |
| `VISIBLE_EFFECT_BEARING_DAILY_APPEARANCES` | 4 |
| `APPEARANCE_DEFS` | 64 |
| `HIDDEN_UNRELEASED_APPEARANCES` | 5 |
| `PET_FOOD_IDENTITIES` | 3 |
| `COSMETIC_PRODUCTS` | 3 |

Validation details:

```text
SHOP_KEYS_UNIQUE=YES
SHOP_POSITIVE_INTEGER_PRICES=YES
STATIC_DAILY=16
STATIC_WEEKLY=3
STATIC_MONTHLY=2
GACHA_ENABLED_STATIC=16
BUNDLE_PRODUCTS=9
COIN_COSMETIC_PRODUCTS=2
PREMIUM_COSMETIC_PRODUCTS=1
VISIBLE_EFFECT_IDS=aura_green,pet_cat,pet_rabbit,pet_turtle
```

The four effect-bearing daily identities are legacy-effect offers, not pure
cosmetics. The 20 fallback appearance entries are those without an explicit
`COSMETIC_COMMERCE_PRODUCTS.product_id`; 16 are pure-cosmetic fallback
identities and 4 are the effect-bearing exclusions.

## 5. Current route authority

| Route | Request | Server facts | Debit/grant | C019 status |
|---|---|---|---|---|
| `GET /api/shop/catalog` | None | `SHOP_ITEMS`, daily slots, gacha config, inventory projection | Read only | Not a purchase entry point |
| `POST /api/shop/buy` | `item_key`, bounded `qty` | Static item and daily server price override | `_spend_coins` then `_grant_shop_purchase` to `shop_inventory`/`pet_inventory` | Legacy; no operation identity, replay, or C019 |
| `POST /api/shop/buy_appearance` | `item_id` | Today's server rotation and price; mapped product if available | `_purchase_cosmetic` or `_spend_coins` plus `player_wardrobe` | Legacy compatibility path; no C019 operation identity |
| `POST /api/cosmetic-commerce/purchase` | `product_id`; optional client price ignored | Product mapping, product price, Premium entitlement | `_purchase_cosmetic`; mapped new grant appends scoped D5A | Separate cosmetic route; not C019 |
| `POST /api/shop/gacha` | No meaningful identity | Cost 150, random bucket, pity and reward pool | `_spend_coins` then random grant/refund path | Random, non-replayable legacy path; excluded |
| `POST /api/shop/use` | `item_key`, use identity where supported | Existing item/effect/capacity facts | D5B capacity or D5C item-use path | Use only; never acquisition |
| `GET /api/cosmetic-commerce/catalog` | None | Product, wardrobe ownership, active appearance | Read only | Presentation only |

Premium cash routes (`/api/pay/plans`, NewebPay, and PayPal) remain separate
from Coin offers. The Premium V1 claim route is also separate/default-off.

## 6. Current Coin and acquisition authority

```text
COIN_BALANCE_AUTHORITY=user_stats.coins
COIN_GRANT_AUTHORITY=_grant_coins
COIN_SPEND_AUTHORITY=_spend_coins
C019_CURRENT_MASTER_RUNTIME=NO
C021_CURRENT_MASTER_RUNTIME=NO
C023_CURRENT_MASTER_RUNTIME=NO
C019_EXACTLY_ONCE_ROUTE_WIRED=NO
DOUBLE_DEBIT_OR_DOUBLE_GRANT_RISK=YES
CLIENT_PRICE_AUTHORITY_EXISTS=NO
STABLE_OFFER_ID_FACTS_AVAILABLE=NO
OPERATION_ID_READY=NO
```

Current conditional `_spend_coins` protects the balance from going negative,
but it has no durable purchase operation identity. Retrying after a response
loss can repeat a debit/grant. The gacha route is additionally random and
cannot provide deterministic replay under its current contract.

D5A/D5C separation remains a boundary:

- mapped `/api/cosmetic-commerce/purchase` writes a scoped D5A
  `ITEM_ACQUISITION` event for a new mapped wardrobe grant;
- `/api/shop/buy`, fallback `/api/shop/buy_appearance`, and `/api/shop/gacha`
  do not uniformly write D5A acquisition evidence;
- `/api/shop/use` uses the item-use/capacity authorities and is not purchase
  acquisition; D5C is not a valid substitute for purchase lineage.

## 7. Current offer normalization result

The complete 43-identity matrix is in
`c024_current_shop_offer_matrix.json`. Its mutually exclusive primary status
counts are:

| Status | Count | Meaning |
|---|---:|---|
| `READY_FOR_C021_C019` | 14 | 12 direct stackable `shop_inventory` products plus 2 explicit Coin wardrobe products |
| `NEEDS_DESTINATION_ADAPTER` | 4 | Pet-food grants whose destination is `pet_inventory` |
| `NEEDS_MULTI_GRANT_PROFILE` | 5 | Non-pet bundle profiles that must not be flattened |
| `NEEDS_CATALOG_NORMALIZATION` | 16 | Pure-cosmetic daily fallback identities with no product mapping |
| `LEGACY_EFFECT_EXCLUDED` | 4 | `aura_green`, `pet_cat`, `pet_turtle`, `pet_rabbit` |

The nine total bundle products are represented without double-counting: four
are primarily destination-blocked pet grants and five are primarily
multi-grant blocked. No free Coin offer exists. Premium cash, Premium
entitlement, and gacha are outside the Coin denominator.

## 8. Offer identity and price boundary

Current server facts provide static `item_key`, explicit cosmetic `product_id`,
and an internal persisted daily `shop_date`. They do not currently provide a
stable C021 `offer_id` plus `offer_version` in the route contract. Daily
fallback appearance slots may have `product_id=None`.

The future adapter may derive a stable business identity from these server
facts and carry `shop_date` as the daily version, but the client must not
author either value. Until then:

```text
STABLE_OFFER_ID_FACTS_AVAILABLE=NO
OPERATION_ID_READY=NO
CLIENT_PRICE_AUTHORITY_EXISTS=NO
```

Price sources are unchanged and server-owned:

- static item: `SHOP_ITEMS[key].price`;
- daily item: persisted `int(SHOP_ITEMS[key].price * 0.8)`;
- daily appearance: common 200 / uncommon 450;
- explicit Coin cosmetic: `COSMETIC_COMMERCE_PRODUCTS.price` or server daily
  override;
- gacha: `_GACHA_COST=150`;
- cash: `PAY_PLANS` and `PAYPAL_PLANS`.

## 9. C023 and B035 overlay

`C023_OWNER_STATUS=OWNER_ACCEPTED_UNMERGED_CANDIDATE` and
`C023_CURRENT_MASTER_RUNTIME=NO` remain true. The accepted C023 design still
supports:

```text
C023_SLOT_SOURCE_INTEGRATION=APP_BOUNDARY_PROJECTION
```

The future application boundary should derive a resolver/projection from the
live `app.EQUIPMENT_DEFS` and inject it into the Commerce acquisition writer.
Commerce must not import/copy `app.py`, accept a client slot, or let Shop
catalog data become slot authority. A single schema-aware caller can validate
the server slot pre-B033 and populate `canonical_slot` post-B033 once the
separate B033 migration is authorized and present.

B035 is cited only for this equipment-writer/canonical-slot context. It was not
used in the initial C024 recon and does not change Shop counts, price
authority, route risk, or offer classifications.

## 10. C020 historical drift summary

The third JSON artifact records the field-by-field comparison against accepted
C020 evidence. The important current-master differences are:

- C020's 29 Coin offer count is not current; current distinct Coin identities
  are 43.
- C020's 15 ready count is not current; current source-fact-ready count is 14.
- Current fallback daily appearance identities are 20, including four
  effect-bearing entries that must be excluded from a pure cosmetic C019 pool.
- Stable live C021 offer IDs are still absent.
- C020's Premium cash separation and price-duplication findings remain true.

`C020_HISTORICAL_ONLY=YES`.

## 11. Final recommendation

```text
FINAL_RECOMMENDATION=THIN_ADAPTER_OVER_EXISTING_SERVER_CATALOG
NEXT_APP_PY_WIRING_REQUIRED=YES
NEXT_SCHEMA_REQUIRED=NO_FOR_C024
NEXT_DESTINATION_ADAPTERS=pet_inventory;multi_grant_profile;daily_appearance_product_identity;C023_equipment_slot_projection
```

The adapter should consume caller-supplied server facts rather than copy
`SHOP_ITEMS` into a second authority. It should first support the 14
source-fact-ready identities, while keeping the pet destination, bundle,
fallback identity, legacy-effect, daily-version, and C019 operation-identity
gaps explicit.

## 12. Validation and boundaries

```text
JSON_VALIDATION=3/3_PASS
CROSS_ARTIFACT_COUNT_CONSISTENCY=PASS
CURRENT_MASTER_SOURCE_ASSERTIONS=PASS
CHANGED_FILE_SET_EXACT=YES
APP_PY_CHANGED=NO
RUNTIME_CHANGED=NO
FRONTEND_CHANGED=NO
SCHEMA_CHANGED=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
MASTER_MERGE=NO
```

The required candidate file set is exactly the report plus the three JSON
artifacts. No Shop route, purchase transaction, UI, Premium policy, gacha
behavior, migration, or ownership authority is implemented here.

```text
TASK=C024_R1_PUBLICATION_ARTIFACT_COMPLETION_AND_CURRENT_MASTER_OVERLAY_001
REQUIRED_ARTIFACT_COUNT=4
READY_FOR_OWNER_C024_R1_REVIEW=YES
```
