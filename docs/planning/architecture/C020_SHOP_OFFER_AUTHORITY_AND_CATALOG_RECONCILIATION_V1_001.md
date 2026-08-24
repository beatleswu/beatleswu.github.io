# C020 — Shop Offer Authority and Catalog Reconciliation V1

Status: read-only reconciliation candidate; owner review required.

This artifact answers which Shop/Coin products exist on the current canonical
runtime line, where prices are resolved, where acquisition lands, and which
products can later be adapted to the accepted C019 CoinShopOffer contract. It
does not integrate C019, change app.py, change schema, or mutate any database.

## Provenance and boundaries

| Field | Value |
|---|---|
| Repository | D:\go-website |
| Start origin/master | 58d9b7047f285751a048fc551c955909c87984ac |
| C020 base | 58d9b7047f285751a048fc551c955909c87984ac |
| Branch | codex/c020-shop-offer-authority-reconciliation |
| C019 architectural reference | cb8f7e07350edb873c6300bfae3680819b0329f6 |
| Recon date | 2026-08-25 |
| Runtime behavior | unchanged |
| Production / schema / deployment | untouched |

The canonical checkout had an unrelated staged planning file before this work.
It was not modified. The C019 modules were read from their isolated candidate
worktree as a contract reference only; they were not copied into this
fresh-master branch.

C019 remains the future transaction boundary:

    server-owned offer
    -> authoritative price
    -> eligibility
    -> exactly-once operation
    -> atomic Coin debit
    -> canonical acquisition destination
    -> D5A ITEM_ACQUISITION
    -> deterministic replay

The Shop remains an acquisition source, never an ownership authority.

## Executive result

The current catalog is split across multiple layers:

1. app.py:SHOP_ITEMS is the live server product and base-price authority for
   21 item/bundle keys.
2. app.py:_daily_shop_slots creates three discounted item instances and two
   appearance instances per date. It is a second offer surface, not a second
   item-definition authority.
3. app.py:COSMETIC_COMMERCE_PRODUCTS defines three outfit products: two Coin
   products and one Premium-entitlement unlock. The two Coin outfits also
   appear in the daily appearance route, so their current price and offer
   surface are duplicated.
4. app.py:PAY_PLANS and PAYPAL_PLANS define four direct Premium cash plan
   variants. They are not Coin offers and must not enter C019.
5. rpg_item_registry.py and shop.html are projections/presentation. They do
   not own price, balance, or ownership mutation.

The legacy /api/shop/buy accepts an item_key and a client quantity rather than
a stable server-owned offer_id. It resolves price on the server, but it is not
an exactly-once C019 transaction and does not itself provide a C019
purchase-operation identity or C019 D5A purchase event.

## Counts and counting convention

TOTAL_SHOP_PRODUCT_DEFINITIONS counts static/route definitions, not every
date-generated slot.

| Count | Result |
|---|---:|
| app.py:SHOP_ITEMS product definitions | 21 |
| app.py:COSMETIC_COMMERCE_PRODUCTS | 3 |
| Gacha route definition | 1 |
| Premium cash plan variants | 4 |
| TOTAL_SHOP_PRODUCT_DEFINITIONS | 29 |
| Dynamic daily item instances per date | 3 |
| Dynamic daily appearance instances per date | 2 |
| TOTAL_ACTIVE_PURCHASABLE_OFFERS | 34 |

The 34 active instances are 29 static/route definitions plus the five
date-generated daily instances. The two display-only visual candidates are
not included in that total. On the deterministic recon date 2026-08-25, the
source-derived daily projection is:

- item discounts: premium_hint_bundle 130 to 104, extra_questions 100 to 80,
  grand_xp_potion 220 to 176;
- appearance slots: hat_cloth 200 and back_pack 200.

Offer classification is:

| Classification | Count | Meaning |
|---|---:|---|
| COIN_ITEM_PURCHASE | 29 | 24 static Coin routes/definitions plus five daily Coin instances; gacha is counted here but excluded from C019 support |
| PREMIUM_CASH_SUBSCRIPTION | 4 | NewebPay/PayPal times monthly/annual |
| LEGACY_NON_COIN_SHOP | 0 | No separate active non-Coin Shop family was found |
| ADMIN_ONLY | 0 | Admin grants are not Shop offers |
| DISABLED_OR_DISPLAY_ONLY | 2 | back_pack and acc_dragon_pendant visual candidate projections |
| UNKNOWN_REQUIRES_OWNER_REVIEW | 1 | cosmetic.outfit.robe_premium entitlement-gated unlock |

The complete machine-readable matrix is
c020_shop_offer_normalization_matrix.json in this directory.

## Source-of-truth matrix

| ID | File / symbol | Product scope | Currency / price | Destination / ownership | Runtime consumer | Reconciliation result |
|---|---|---|---|---|---|---|
| S01 | app.py:SHOP_ITEMS | 21 item/bundle definitions | Coins; SHOP_ITEMS.price, with daily override | shop_inventory for item grants; pet_inventory for Spirit-food grants | /api/shop/catalog, /api/shop/buy, _grant_shop_purchase, /api/shop/use | Primary current Coin product source; no C019 offer IDs |
| S02 | app.py:_daily_shop_slots | Three item discounts plus two appearance slots per date | Server date-seeded 80% item prices; common 200 / uncommon 450 | shop_inventory or player_wardrobe | /api/shop/catalog, /api/shop/buy, /api/shop/buy_appearance | Dynamic offer surface; no stable IDs; exposes four legacy-effect appearances |
| S03 | app.py:COSMETIC_COMMERCE_PRODUCTS | robe_plain, robe_bamboo, robe_premium | Coins 200/450 or Premium entitlement with no Coin price | player_wardrobe; equipped state in player_appearance | /api/cosmetic-commerce/* and daily compatibility route | Valid wardrobe source, but direct/daily price and route duplication exists |
| S04 | app.py:/api/shop/buy | Any of the 21 SHOP_ITEMS keys | Server resolves price; client cannot set it | _grant_shop_purchase chooses destination | shop.html buyItem | Legacy mutation path; no C019 operation or C019 D5A event |
| S05 | app.py:/api/shop/buy_appearance | Two daily appearance slots selected from 22 candidates | Server daily slot price | player_wardrobe | shop.html buyAppearance | Mapped and unmapped branches; legacy-effect quarantine gap |
| S06 | app.py:PAY_PLANS, PAYPAL_PLANS | Four Premium cash variants | TWD 299/2490; USD 9.9/84 | Premium entitlement/payment tables | Provider payment routes | Direct cash Premium only; outside C019 |
| S07 | premium_v1_revenue.py:C013_* | Premium projection plus five-cosmetic credit pool | Projection only; payment tables remain authoritative | D5B/D5F/player_wardrobe | Premium offer/claim routes | Benefit/credit surface, not Coin commerce |
| S08 | rpg_item_registry.py:build_*_registry | 21 Shop products plus three Spirit foods | No numeric authority; descriptive price-source text | Descriptive projection of existing stores | /api/item-journal, /api/shop/catalog | Presentation registry; must not become a second catalog authority |
| S09 | shop.html:ZH_ITEM, EN_ITEM, art map | 21 fallback presentation entries | Server values render cards; gacha label displays 150 | No ownership authority | Shop page | Static validation: 21/21 language keys and 21/21 art mappings |
| S10 | app.py:PET_FOOD_CATALOG | go_spirit_candy, starfruit, moon_drop | No direct price | pet_inventory | Pet status/feed APIs and _grant_pet_food | Real Spirit authority; C019 needs an adapter |
| S11 | app.py:_GACHA_COST, /api/shop/gacha | One random Coin draw operation | Coins 150 | Result-dependent | Shop gacha action | Existing route accounted for, but not deterministic and excluded from C019 |

## Item and destination reconciliation

The current 21 SHOP_ITEMS entries map as follows:

| Current products | C019 class | Current destination | Duplicate behavior | C019 status |
|---|---|---|---|---|
| hint_ticket, premium_hint_bundle, ai_explain_ticket, ai_explain_ticket_bundle | CONSUMABLE | shop_inventory | Stack | Ready after offer resolution |
| extra_questions_small, extra_questions, grand_training_pass | XP_CONSUMABLE | shop_inventory | Stack | Ready; D5B remains use authority |
| small_xp_potion, xp_potion, grand_xp_potion | XP_CONSUMABLE | shop_inventory | Stack | Ready; D5C remains use authority |
| streak_shield, double_streak_shield | CONSUMABLE | shop_inventory | Stack | Ready |
| rare_appearance_fragment, pet_evolution_core | MATERIAL | shop_inventory | Stack | Ready for acquisition; use remains external |
| ai_analysis_pack | CONSUMABLE grant ai_explain_ticket x5 | shop_inventory | Component quantity stacks; product row is not persisted | Ready as a single-grant bundle mapping |
| pet_snack, starfruit_basket, moon_dew_vial | SPIRIT_CONSUMABLE | pet_inventory | Stack | Needs pet_inventory destination adapter |
| pet_feast_box | SPIRIT_CONSUMABLE multi-grant | pet_inventory | Component quantities stack | Needs Spirit destination and multi-grant adapter |
| collector_archive_crate | Mixed Material/Consumable multi-grant | shop_inventory components | Component quantities stack | C019 single-result shape cannot represent both grants |
| growth_vault | Mixed Material multi-grant | shop_inventory components | Component quantities stack | C019 single-result shape cannot represent both grants |

Current effective ownership is not a generic item ledger. A future adapter
must write directly to shop_inventory, pet_inventory, or player_wardrobe.
xp_amulet is not exposed as a Coin product and remains HOLD_FOR_AUTHORITY.
go_stone_black is not exposed as a Coin product and remains TROPHY /
INVENTORY_ONLY / NO_COMBAT_POWER.

## Cosmetic and Premium separation

COSMETIC_COMMERCE_PRODUCTS contains:

| Product | Current price / eligibility | Ownership | Status |
|---|---|---|---|
| cosmetic.outfit.robe_plain | Coins 200 | player_wardrobe.item_id=robe_plain | Coin-shaped but duplicated by daily route; normalize before C019 |
| cosmetic.outfit.robe_bamboo | Coins 450 | player_wardrobe.item_id=robe_bamboo | Coin-shaped but duplicated by daily route; normalize before C019 |
| cosmetic.outfit.robe_premium | No Coin price; live Premium required | player_wardrobe.item_id=robe_premium | Owner decision: Premium benefit/unlock, not a C019 Coin offer |

The five locked Premium collection IDs remain:

    robe_plain
    robe_bamboo
    robe_fox
    back_pack
    acc_dragon_pendant

The C013 collection credit is a benefit/redemption right, not Coins. Direct
cash remains Premium only:

- NewebPay monthly: TWD 299
- NewebPay annual: TWD 2490
- PayPal monthly: USD 9.9
- PayPal annual: USD 84

C013_PLAN_PRICES repeats these values for projection, while payment mutation
uses PAY_PLANS and PAYPAL_PLANS. This is a duplicated representation, not a
second payment authority. PREMIUM_CASH_SEPARATION_PRESERVED=YES.

## Price authority and offer identity

SERVER_PRICE_AUTHORITY is currently server-side:

- fixed item price: app.py:SHOP_ITEMS[key].price;
- daily item price: _daily_shop_slots computes int(base_price * 0.8);
- daily appearance price: _daily_shop_slots computes common 200 or uncommon
  450;
- direct cosmetic price: COSMETIC_COMMERCE_PRODUCTS.price, with the daily
  compatibility route supplying a server price_override;
- gacha price: _GACHA_COST=150;
- Premium cash: PAY_PLANS / PAYPAL_PLANS.

PRICE_AUTHORITY_DUPLICATED=YES for two concrete reasons:

1. robe_plain and robe_bamboo have a direct product price and a second daily
   route price policy, even though current numeric values agree.
2. Premium prices are projected in premium_v1_revenue.C013_PLAN_PRICES and
   separately used by payment tables. The payment tables remain the mutation
   authority.

The client cannot authoritatively choose the price in the legacy item or
cosmetic routes, but the current client submits item_key/item_id instead of a
stable offer identity. The current identifiers are:

- SHOP_ITEMS.key: item/product identity, not an offer identity;
- COSMETIC_COMMERCE_PRODUCTS.product_id: stable product identity, but not
  versioned as a unified ShopOffer;
- PAY_PLANS/PAYPAL_PLANS plan keys: provider plan identity, not C019;
- daily slots: date-row identity only; no stable offer ID.

Therefore:

    STABLE_SERVER_OFFER_IDS=0
    MISSING_STABLE_OFFER_IDS=34 active instances

The proposed future IDs in the candidate JSON use shop.<product>.v1 for fixed
products and shop.daily.appearance.<item_id>.v1 for date-eligible appearance
candidates. They are recommendations only and are not activated.

## C019 normalization support

The accepted C019 destination contract supports player_inventory,
shop_inventory, player_wardrobe, entitlement, capacity, and credit; its SQL
acquisition adapter currently supports the first three ownership destinations
only. C020 does not add adapters.

The 46 normalized Coin candidate rows are classified disjointly as follows:

| Support class | Count | Rows |
|---|---:|---|
| READY_FOR_C019_WIRING | 15 | The 15 single-destination SHOP_ITEMS rows whose result is one stackable shop_inventory item/grant |
| NEEDS_DESTINATION_ADAPTER | 4 | Three Spirit-food bundles plus pet_feast_box targeting pet_inventory |
| NEEDS_ELIGIBILITY_AUTHORITY | 0 | Existing source eligibility exists; it is not yet adapted into C019 |
| NEEDS_CATALOG_NORMALIZATION | 22 | Two multi-grant Shop bundles, two direct Coin cosmetics, and 18 pure daily appearance candidates |
| UNSUPPORTED_BY_V1_POLICY | 5 | Gacha plus four daily legacy-effect appearances |

The five unsupported appearance identities are:

    pet_cat       APPEARANCE_EFFECTS.drop_bonus +5%
    pet_turtle    APPEARANCE_EFFECTS.drop_bonus +5%
    pet_rabbit    APPEARANCE_EFFECTS.drop_bonus +8%
    aura_green    APPEARANCE_EFFECTS.xp_bonus   +5%

They are currently eligible for the common/uncommon daily pool because
_daily_shop_slots filters rarity and hidden IDs but does not filter
APPEARANCE_EFFECTS. They must not be normalized as pure cosmetic C019
offers without a separate policy decision; no runtime correction is made in
C020.

DUPLICATE_POLICY is current-source derived, not invented here:

- shop_inventory and pet_inventory use quantity upserts: STACK;
- player_wardrobe uses unique (user_id,item_id) behavior:
  REJECT_IF_OWNED;
- existing gacha duplicate appearance handling can return Coins, but that is
  an existing gacha rule and is not imported into C019.

The exact per-row mapping, prices, eligibility sources, destinations,
blockers, and proposed IDs are in the JSON artifact. No runtime dictionary
was created from that JSON.

## Static validation

Validation was source/static only; no application import was required and no
database was opened or mutated.

    SHOP_ITEMS accounted for                         21/21 PASS
    shop.html ZH_ITEM keys                          21/21 PASS
    shop.html EN_ITEM keys                          21/21 PASS
    SHOP_PRODUCT_ART_ASSETS entries                21/21 PASS
    Referenced Shop asset files missing             0 PASS
    Grant component IDs resolve                     PASS
    Server Coin prices positive integers            21/21 PASS
    Direct cosmetic Coin prices positive integers   2/2 PASS
    Premium price variants numeric                  4/4 PASS
    Duplicate literal product IDs                  0 PASS
    Duplicate proposed normalized offer IDs         0 PASS
    Duplicate current offer surfaces                YES (reported gap)
    xp_amulet exposed as Coin offer                NO PASS
    go_stone_black exposed as Coin offer           NO PASS
    Premium cash in C019 Coin matrix               NO PASS
    Legacy-effect appearance daily exposure        YES (4 reported gaps)

## Owner packet and next implementation boundary

    RECOMMENDATION_A=THIN_ADAPTER_OVER_EXISTING_SERVER_CATALOG
    NEXT_APP_PY_WIRING_REQUIRED=YES
    NEXT_SCHEMA_REQUIRED=NO

The next implementation should resolve existing server symbols directly:

1. SHOP_ITEMS remains the base item/product source.
2. COSMETIC_COMMERCE_PRODUCTS remains the direct cosmetic source only after
   the duplicate daily surface is given one canonical adapter path.
3. _daily_shop_slots remains the server eligibility/price policy for dynamic
   offers, not a client catalog.
4. rpg_item_registry.py remains a read-only presentation projection.
5. shop.html remains a presentation consumer.

Destination/shape work still required:

    pet_inventory destination adapter for Spirit consumables
    multi-grant acquisition profile/result for pet_feast_box
    multi-grant acquisition profile/result for collector_archive_crate
    multi-grant acquisition profile/result for growth_vault

OWNER_DECISION_REQUIRED_COUNT=1: classify
cosmetic.outfit.robe_premium as a Premium benefit redemption outside ShopOffer,
or define a separate entitlement redemption contract. It must not be sent
through C019 as a Coin purchase.

Before app.py wiring, the adapter must also exclude the four legacy-effect
appearance identities from a pure-cosmetic Coin pool and keep gacha outside
C019. No Coin debit, purchase execution, route change, UI change, migration,
Premium redesign, or production action belongs in C020.

## C020 gate result

    APP_PY_CHANGED=NO
    RUNTIME_CHANGED=NO
    SCHEMA_CHANGED=NO
    PRODUCTION_MUTATION=NO
    PRODUCTION_MIGRATION=NO
    DEPLOY=NO
    MASTER_MERGE=NO
    ALL_ACTIVE_OFFERS_ACCOUNTED_FOR=YES
    READY_FOR_OWNER_C020_REVIEW=YES
