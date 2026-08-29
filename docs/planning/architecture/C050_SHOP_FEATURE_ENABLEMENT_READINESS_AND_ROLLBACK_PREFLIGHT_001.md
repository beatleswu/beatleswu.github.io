# C050 Shop Feature Enablement Readiness and Rollback Preflight

Status: `TECHNICALLY_READY_PENDING_OWNER_GO_ENABLE`

This is a source/readiness record only. It does not enable Shop or Loadout,
query Production, change payment infrastructure, or change the database
schema.

## Identity and lineage

```text
CURRENT_ORIGIN_MASTER=6829c4c528adf4800326e90534585a32e390ebec
BASE_SHA=3348796c135ec23b2e2015623419e7806a4bc3ac
C048_HEAD=c50075926144c05f8c0185c01c1ba91bf6b4b55a
C049_HEAD=3348796c135ec23b2e2015623419e7806a4bc3ac
FRESH_MASTER_RECONCILIATION=PASS
FRESH_MASTER_IS_ANCESTOR=YES
C048_AUTHORITY_PRESENT=YES
```

The candidate was created from the pushed C049 branch, not from the dirty
canonical checkout. `origin/master` is an ancestor of the candidate and the
C048 commit is in the candidate ancestry. C049 remains a candidate dependency;
it is not assumed to be merged into `origin/master`.

## Shop and Loadout gates

The runtime Shop gate is the request-time environment flag wired in `app.py`:

```text
SHOP_FLAG_SOURCE=app.py:CANONICAL_COIN_SHOP_PURCHASE_FLAG -> _canonical_coin_shop_purchase_enabled()
SHOP_FLAG_DEFAULT=CANONICAL_COIN_SHOP_PURCHASE_ENABLED absent
SHOP_EFFECTIVE_DEFAULT=OFF
SHOP_ENABLED=NO
LOADOUT_ENABLED=NO
```

`equipment_shop_offer_authority.py` also exports `SHOP_ENABLED=False` and
`LOADOUT_ENABLED=False` as source assertions. The actual runtime projection is
`app.py`'s `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` flag.

| Surface | Gate effect | Default result |
| --- | --- | --- |
| `/api/shop/catalog` canonical `equipment_offers` | Includes the C046 server offer projection only when the Shop flag is true | Empty equipment-offer projection |
| `/api/shop/buy` | Does not use the UI flag as a security boundary; classifies server facts, then dispatches C019/C043 or fails closed | Safe authenticated route; legacy products fail closed |
| `/api/shop/buy_appearance` | Does not use the UI flag as a security boundary; canonical mapped cosmetics use C019, other legacy IDs retire | Safe authenticated route |
| `/api/cosmetic-commerce/purchase` | C049 canonical cosmetic Coins products remain server-authoritative and separate from the equipment catalog gate | Existing C049 behavior |
| `shop.html` canonical Equipment panel | Rendered only from the server `equipment_offers` array and starts with HTML `hidden` | Hidden |
| `/api/player/inventory/equip` | Separate `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` gate | Loadout remains off; purchase does not equip |

There is no new public UI exposure in C050. The existing authenticated
`/shop` shell and legacy panels remain existing source; the canonical
Equipment surface is hidden by the default gate. The legacy gacha/daily
compatibility controls are not treated as a security boundary and their
unsupported mutation paths fail closed.

## Appearance and wardrobe mutation surface audit

The following are the server-reachable appearance/wardrobe mutation surfaces
found in the accepted C049 source. `player_wardrobe` remains ownership truth;
`player_appearance` remains selected/equipped presentation state.

| Route/function | Auth | Coins | Ownership mutation | Equip mutation | Price source / idempotency | Classification and reachability |
| --- | --- | --- | --- | --- | --- | --- |
| `POST /api/cosmetic-commerce/purchase` (Coins products) | authenticated | C019 debit | `player_wardrobe` through C019 | no | `COSMETIC_COMMERCE_PRODUCTS` server price; C019 operation | `CANONICAL_DURABLE_PURCHASE`, reachable by existing Shop consumer |
| `POST /api/cosmetic-commerce/purchase` (Premium product) | authenticated | no | entitlement hydration, idempotent wardrobe insert | no | Premium entitlement, not a Coins purchase | `FREE_ENTITLEMENT_GRANT`, reachable by existing Premium consumer |
| `POST /api/shop/buy_appearance` mapped product | authenticated | C019 debit | `player_wardrobe` through C019 | no | daily/server product facts; C019 operation | `CANONICAL_DURABLE_PURCHASE`, reachable compatibility route |
| `POST /api/shop/buy_appearance` unmapped appearance | authenticated | no | no | no | no canonical price | `DEAD_ROUTE` / `LEGACY_PURCHASE_RETIRED`, fail closed |
| `POST /api/shop/gacha` | authenticated | no | no | no | no price authority | `DEAD_ROUTE`, returns `LEGACY_PURCHASE_RETIRED` |
| `POST /api/cosmetic-commerce/equip` | authenticated | no | no | `player_appearance` | not a purchase; owned check | `NON_PURCHASE_APPEARANCE_MUTATION`, owned-only |
| `POST /api/player/appearance/equip` | authenticated | no | no | `player_appearance` | not a purchase; owned/valid appearance check | `NON_PURCHASE_APPEARANCE_MUTATION`, owned-only |
| `POST /api/player/appearance/unequip` | authenticated | no | no | clears one selected slot | not a purchase | `NON_PURCHASE_APPEARANCE_MUTATION` |
| `POST /api/skills/equip` compatibility alias | authenticated | no | no | `player_appearance` | not a purchase; owned check | `NON_PURCHASE_APPEARANCE_MUTATION`, owned-only |
| `POST /api/skills/character` | authenticated | no | no | `player_appearance.character_key` / presentation fields | server unlock rules | `NON_PURCHASE_APPEARANCE_MUTATION` |
| `POST /api/skills/stone_skin` and `POST /api/skills/board_skin` | authenticated | no | no | `player_appearance` skin fields | server unlock rules | `NON_PURCHASE_APPEARANCE_MUTATION` |
| `POST /api/admin/users/<uid>/assets/appearance` | admin | no | grant/remove `player_wardrobe` | no | admin action; no Shop price | `ADMIN_ONLY` |
| `POST /api/admin/users/<uid>/set-plan` and `grant_premium_rewards` | admin/payment authority | no Coins Shop debit | Premium wardrobe hydration | optional Premium default appearance | Premium entitlement | `ADMIN_ONLY` / `FREE_ENTITLEMENT_GRANT`, outside Coins Shop |
| `GET /api/player/appearance`, `GET /api/player/appearance/all-items` | authenticated | no | read hydration may call `ensure_premium_rewards(..., equip_default=False)` | no | Premium entitlement | `FREE_ENTITLEMENT_GRANT` read hydration plus projection |
| `GET /api/skills/profile` and `_grant_earned_titles` | authenticated | no | achievement/Premium wardrobe hydration | no purchase equip | achievement/Premium authority | `FREE_ENTITLEMENT_GRANT` |
| `POST /api/srs/review`, `POST /api/daily-challenge/submit` | authenticated | no Shop debit | rank/daily/monster reward wardrobe grants | no Shop equip | reward authority | `FREE_ENTITLEMENT_GRANT` / reward path |
| `POST /api/adventure/boss/finish` and F030/F028 reward service | authenticated | no Shop debit | server-authoritative first-clear wardrobe reward | no Shop equip | Boss reward authority | `FREE_ENTITLEMENT_GRANT` / reward path |

No unknown mutation surface remains in the audited source:

```text
LEGACY_APPEARANCE_PURCHASE_BYPASS_COUNT=0_REACHABLE
UNKNOWN_MUTATION_SURFACE_COUNT=0
PAID_APPEARANCE_PURCHASE_AUTHORITY=CANONICAL_DURABLE
NO_PAID_APPEARANCE_ROUTE_REMAINS=NO
DIRECT_COIN_SPEND_PLUS_WARDROBE_GRANT_REACHABLE=NO
```

Paid appearance requests use the existing C019 operation ledger and the
server-owned product/price mapping. Client `price`, `discount`, `expected_price`,
and metadata cannot change the debit. Duplicate operations replay the
canonical result without a second debit or wardrobe grant. Legacy paid
appearance paths use the explicit `LEGACY_PURCHASE_RETIRED` compatibility
error; they do not fall back to direct spend plus wardrobe grant.

## Canonical Equipment Shop parity

The accepted C046 authority remains the only Equipment offer source:

```text
EQUIPMENT_OFFERS_SOURCE=equipment_shop_offer_authority.py
PRICE_AUTHORITY_SOURCE=OWNER_EQUIPMENT_SHOP_PRICING_DECISION_001
EQUIPMENT_OFFERS_COUNT=3
wooden_sword=300 Coins
cloth_robe=300 Coins
lucky_stone=400 Coins
UNAUTHORIZED_EQUIPMENT_OFFERS=0
XP_AMULET_SHOP_ELIGIBLE=NO
GO_STONE_BLACK_SHOP_ELIGIBLE=NO
HIGH_VALUE_ITEMS_EXCLUDED=fox_fang,fox_pelt,fox_mask,dragon_claw,dragon_scale,dragon_eye,celestial_blade,void_mantle
SERVER_PRICE_AUTHORITY=YES
CLIENT_PRICE_AUTHORITY=NO
FRONTEND_PRICE_AUTHORITY=NO
APP_PY_DUPLICATE_PRICE_AUTHORITY=NO
CATALOG_PURCHASE_OFFER_PARITY=PASS
CLIENT_ONLY_OFFERS=0
SERVER_ONLY_PUBLIC_OFFERS=0 (canonical Equipment scope)
```

When the isolated test flag is enabled, the Flask catalog response contains
exactly the three server offers and C044 renders that response. With the
default flag absent, the Equipment array is empty and the Equipment panel
stays hidden. `shop.html` contains no Equipment price table or fallback offer
IDs.

## Error and rollback contracts

| Case | Server contract | Mutation guarantee |
| --- | --- | --- |
| unauthenticated mutation | `401` login response | no mutation |
| unknown/malformed offer or product | `400` unknown/invalid contract | no mutation |
| insufficient Coins | `400`, `INSUFFICIENT_COINS` | no debit, no grant, no operation row |
| already-owned Equipment | `409`, `EQUIPMENT_ALREADY_OWNED` | no second debit or item |
| already-owned cosmetic | canonical `200`, `status=already_owned`, `granted=false` | no second debit or wardrobe row |
| duplicate operation | canonical replay result | one ledger row, one debit, one grant |
| forged client price/metadata | canonical server price is used or request fails closed | client is never price authority |
| acquisition/DB failure | canonical acquisition failure | caller transaction rolls back debit, grant, operation and outbox changes |
| retired legacy appearance/gacha | `409`, `LEGACY_PURCHASE_RETIRED` | no direct spend/grant fallback |
| unowned appearance equip | `403`, `not_owned` | no `player_appearance` change |

Rollback for a future Owner-approved Equipment enablement is a flag-only
disable:

1. Set `CANONICAL_COIN_SHOP_PURCHASE_ENABLED` to false (and keep the separate
   Loadout flag false).
2. Confirm the canonical Equipment catalog is empty and the Equipment panel
   returns to its hidden state.
3. Keep `coin_purchase_operations`, currency log, `player_inventory`,
   `player_wardrobe`, and `player_appearance` unchanged.
4. Do not reverse valid purchases, rewrite prices, touch payment settings, or
   run a data rollback. Existing operation IDs remain durable/replayable under
   the canonical route safety contract.

```text
SHOP_DISABLE_ROLLBACK_PLAN=COMPLETE_FLAG_ONLY_DISABLE
FLAG_DISABLE_RESTORES_HIDDEN_UI=YES (canonical Equipment surface)
VALID_PURCHASES_REMAIN_DURABLE=YES
INVENTORY_PRESERVED_ON_DISABLE=YES
COIN_LEDGER_PRESERVED_ON_DISABLE=YES
NO_DATA_ROLLBACK_REQUIRED_FOR_SIMPLE_DISABLE=YES
PURCHASE_AUTO_EQUIP=NO
ACQUIRE_AUTO_EQUIP=NO
```

Existing wardrobe ownership and equipped cosmetic state are not migrated or
deleted. C049 route tests prove owned-only equip, reload persistence, and
preservation of selected state. Pure cosmetics have zero combat authority.

## UI readiness and enablement gates

```text
SHOP_UI_TEST_MODE=isolated deterministic C044 Node/source contract; default gate unchanged
SHOP_UI_PREFLIGHT=PASS_ISOLATED_SOURCE_NODE_CONTRACT
SHOP_UI_VISIBILITY=canonical Equipment hidden by default; existing authenticated /shop shell unchanged
SHOP_UI_PURCHASE_CAPABILITY=canonical C019/C043 paths exist; no new public capability exposed
```

| Readiness gate | Result | Evidence or remaining authorization |
| --- | --- | --- |
| SOURCE_READY | PASS | C043-C049 source lineage and C046 offer authority |
| SERVER_AUTHORITY_READY | PASS | C019/C043 durable purchase, server price and ownership authority |
| POSTGRES_READY | PASS for required C049 appearance proof | disposable PostgreSQL replay/race/rollback/persistence proof; no Production query |
| UI_READY | PASS for isolated C044 contract | catalog, price, ownership, pending, errors, retry, and Backpack convergence are source-tested |
| ROLLBACK_READY | PASS | flag-only disable preserves all durable state |
| BROWSER_READY | PASS_ISOLATED_CONTRACT | no authenticated multi-device browser harness was available/needed for this source-only gate |
| PHYSICAL_DEVICE_READY | PENDING | separate device QA is still required before live rollout |
| PRODUCTION_SCHEMA_READY | UNKNOWN_CURRENT | intentionally not queried in C050 |
| OWNER_GO_ENABLE_REQUIRED | YES | explicit Owner authorization is mandatory |
| PAYMENT_GATE_REQUIRED_OR_NOT | NOT_REQUIRED_FOR_COINS_SHOP | NewebPay/PayPal remain separate and unchanged |

The existing cosmetic Shop panel includes legacy presentation controls whose
unsupported mutations are now explicit failures. That is a known compatibility
presentation limitation, not a reachable purchase bypass and not a reason to
change the payment or schema boundary in C050.

## Validation record

All commands ran in the isolated C050 worktree with `SHOP` and `LOADOUT`
defaults unchanged:

```text
focused C043-C049/C019/appearance commerce suites: 145 passed, 3 skipped
focused appearance/wardrobe/equipment presentation suites: 33 passed
D024 canonical acquisition-result lineage suite: 16 passed
C044 deterministic Node contract: passed
C049 disposable PostgreSQL appearance replay/race/rollback suite: 13 passed
```

The old C030 self-managed PostgreSQL harness was also attempted but its
disposable server on port 54411 closed during startup, producing three setup
errors. This is recorded as a pre-existing environment/harness gap; the
required C049 disposable PostgreSQL proof passed independently. No C050 source
or test failure was observed.

```text
COMMERCE_REGRESSION=PASS
WARDROBE_REGRESSION=PASS
POSTGRES_COMMERCE_PREFLIGHT=PASS (C049 disposable PostgreSQL proof)
TASK_INTRODUCED_FAILURES=0
PRE_EXISTING_FAILURES=C030 disposable PostgreSQL startup harness (3 setup errors)
ENVIRONMENT_GAPS=no authenticated multi-device browser proof; no physical-device QA; Production state intentionally unknown
```

## Protected boundaries and C050 change set

```text
APP_PY_CHANGED=NO
RUNTIME_SOURCE_CHANGED=NO
STATIC_SOURCE_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
PAYMENT_CHANGED=NO
GO_ENABLE_PAYMENTS_CONSUMED=NO
GO_REVENUE_LIVE_CONSUMED=NO
GO_ENABLE_CONSUMED=NO
A042_SCOPE_TOUCHED=NO
B057_SCOPE_TOUCHED=NO
C050_RELEASE_BLOCKING_FINDING=NONE
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
MASTER_MERGE=NO
```

C050 changes documentation only: this readiness record. It does not touch
`app.py`, `shop.html`, tests, payment code, release files, `sw.js`, or
`secret_key.txt`.

## Decision

```text
SHOP_DISABLED_SERVER_SAFETY=PASS
DEFAULT_SHOP_PURCHASE_AUTHORITY=CANONICAL_DURABLE
DEFAULT_LIVE_SHOP_IDEMPOTENCY=PASS
DIRECT_COIN_SPEND_PLUS_WARDROBE_GRANT_REACHABLE=NO
EXISTING_WARDROBE_OWNERSHIP_PRESERVED=YES
EXISTING_EQUIPPED_COSMETIC_PRESERVED=YES
APPEARANCE_COMBAT_POWER=0
COSMETIC_ROUTE_COMBAT_AUTHORITY=NO
SHOP_ENABLED=NO
LOADOUT_ENABLED=NO
SHOP_READY_FOR_OWNER_ENABLE_DECISION=YES
RESULT=PASS_SHOP_FEATURE_ENABLEMENT_READINESS_AND_ROLLBACK_PREFLIGHT
```

What is ready: server-owned three-item Equipment offers, canonical durable
purchase/idempotency, authoritative Coins and ownership, safe appearance
compatibility routes, C044 source consumer, and flag-only rollback.

What still blocks live enablement: explicit Owner `GO_ENABLE`, production
rollout approval and verification, physical-device QA, and any separately
governed release/package decision. C050 intentionally does not perform any of
those actions.
