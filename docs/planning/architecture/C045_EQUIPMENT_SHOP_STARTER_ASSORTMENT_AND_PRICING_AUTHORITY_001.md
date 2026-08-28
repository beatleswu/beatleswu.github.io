# C045 — Equipment Shop Starter Assortment and Pricing Authority

Status: `READY_FOR_OWNER_PRICING_DECISION`

This candidate is based on the accepted C044 dependency
`28e7a0cb1b2df575b35794145578599786500572`. C044 is not merged into
`origin/master`; this report does not change that fact.

## Decision

The current source has fifteen canonical functional Equipment definitions but
zero authoritative functional Equipment Shop offers. The definitions have no
price field, `SHOP_ITEMS` contains no functional Equipment identity, and no
reachable repository history provides an Equipment Shop price. C045 therefore
does not publish guessed offers.

The proposed starter assortment is three common, early-slot alternatives:

| item_id | slot | status | reason |
| --- | --- | --- | --- |
| `wooden_sword` | Weapon | proposed, Owner decision required | common entry weapon; Goblin drop overlap is explicit |
| `cloth_robe` | Armor | proposed, Owner decision required | common entry armor; Goblin drop overlap is explicit |
| `lucky_stone` | Accessory | proposed, Owner decision required | common entry accessory; Goblin drop overlap is explicit |

This is a product recommendation, not an active catalog listing. `iron_sword`
and `leather_armor` remain evaluation-only alternatives. The remaining
regional, dragon-pool, locked, or inventory-only items are excluded by
default.

## 15-item acquisition audit

The matrix is derived from the current server-owned `app.py:EQUIPMENT_DEFS`
snapshot by `build_equipment_acquisition_audit()`. The C045 module does not
import `app.py` or become an alternate ownership/equipment authority.
`ADMIN/LEGACY` is listed because the existing authenticated admin grant path
can write any canonical Equipment definition. No row currently has a Shop
source, Quest source, Premium source, or starter/default grant in the source
snapshot.

| item_id | slot | current acquisition sources | current rarity/progression role | Shop overlap risk | recommended Shop eligibility | reason |
| --- | --- | --- | --- | --- | --- | --- |
| `wooden_sword` | Weapon | `MONSTER_DROP`, `ADMIN/LEGACY` | common; separate progression authority not defined | Monster drop overlap | Proposed starter candidate | Common entry weapon; preserve the existing Goblin drop identity. |
| `iron_sword` | Weapon | `MONSTER_DROP`, `ADMIN/LEGACY` | common; separate progression authority not defined | Monster drop overlap | Evaluate-only starter candidate | Common weapon, but the three-item proposal already covers Weapon. |
| `fox_fang` | Weapon | `MONSTER_DROP`, `ADMIN/LEGACY` | rare; separate progression authority not defined | Monster drop overlap | Default do not list | Fox-pool rare equipment should retain regional drop value. |
| `dragon_claw` | Weapon | `MONSTER_DROP`, `ADMIN/LEGACY` | epic; separate progression authority not defined | Monster drop overlap | Default do not list | Dragon-pool epic equipment should not fill an empty Shop. |
| `celestial_blade` | Weapon | `MONSTER_DROP`, `ADMIN/LEGACY` | legendary; separate progression authority not defined | Monster drop overlap | Default do not list | Dragon-pool legendary equipment should retain high-value identity. |
| `cloth_robe` | Armor | `MONSTER_DROP`, `ADMIN/LEGACY` | common; separate progression authority not defined | Monster drop overlap | Proposed starter candidate | Common entry armor; preserve the existing Goblin drop identity. |
| `leather_armor` | Armor | `MONSTER_DROP`, `ADMIN/LEGACY` | common; separate progression authority not defined | Monster drop overlap | Evaluate-only starter candidate | Common armor, but the three-item proposal already covers Armor. |
| `fox_pelt` | Armor | `MONSTER_DROP`, `ADMIN/LEGACY` | rare; separate progression authority not defined | Monster drop overlap | Default do not list | Fox-pool rare equipment should retain regional drop value. |
| `dragon_scale` | Armor | `MONSTER_DROP`, `ADMIN/LEGACY` | epic; separate progression authority not defined | Monster drop overlap | Default do not list | Dragon-pool epic equipment should not fill an empty Shop. |
| `void_mantle` | Armor | `MONSTER_DROP`, `ADMIN/LEGACY` | legendary; separate progression authority not defined | Monster drop overlap | Default do not list | Dragon-pool legendary equipment should retain high-value identity. |
| `lucky_stone` | Accessory | `MONSTER_DROP`, `ADMIN/LEGACY` | common; separate progression authority not defined | Monster drop overlap | Proposed starter candidate | Common entry accessory; preserve the existing Goblin drop identity. |
| `xp_amulet` | Accessory | `MONSTER_DROP`, `ADMIN/LEGACY` | rare; separate progression authority not defined | Monster drop overlap | Default do not list | New Equip is `HOLD`; a Shop sale must not bypass that authority. |
| `fox_mask` | Accessory | `MONSTER_DROP`, `ADMIN/LEGACY` | rare; separate progression authority not defined | Monster drop overlap | Default do not list | Fox-pool rare equipment should retain regional drop value. |
| `dragon_eye` | Accessory | `MONSTER_DROP`, `ADMIN/LEGACY` | epic; separate progression authority not defined | Monster drop overlap | Default do not list | Dragon-pool epic equipment should not fill an empty Shop. |
| `go_stone_black` | Accessory | `MONSTER_DROP`, `ADMIN/LEGACY` | legendary; separate progression authority not defined | Monster drop overlap | Default do not list | Trophy/inventory-only; no combat-equipment Shop authority. |

`EQUIPMENT_ACQUISITION_AUDIT_COUNT=15`.

## Coins economy and price authority

The current Coins rules traced from source are:

| source | current authoritative behavior |
| --- | --- |
| `user_stats.coins` | authoritative balance and debit row |
| global daily earning cap | 500 Coins |
| Monster defeat | 2 Coins each, Monster income capped at 40/day |
| daily quests | 15 Coins per each of the three ordinary quests |
| all daily quests complete | 50 Coins bonus |
| Adventure first clear | 200 Coins, one-time per zone and bypasses the ordinary cap |
| existing Shop | prices belong to non-equipment `SHOP_ITEMS`; they are comparables only |

The existing non-equipment Shop has 21 valid positive price entries spanning
30–6000 Coins. That range is an economy comparison, not an Equipment price
authority. `EQUIPMENT_DEFS` has no `price`, `currency`, or Shop product field.
No canonical Equipment price was found in reachable Git history.
`COIN_ECONOMY_AUTHORITY_TRACED=YES`, but
`ECONOMY_BALANCE_CONFIDENCE=LOW` for a new persistent Equipment price.

### Owner pricing decision matrix

No numeric range or default is supplied because that would be an unsupported
guess. The existing Shop price range is recorded only as context. The Owner
must decide whether the proposed items should be priced at all and, if so,
provide a stable price authority/reference for each accepted item.

| item_id | current acquisition role | estimated player earning context | existing comparable price | recommended price range | recommended default | confidence | evidence | Owner decision required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `wooden_sword` | common Weapon; Goblin drop; admin/legacy | cap 500; Monster 2 each/cap 40; quests 15×3 + 50; first clear 200 | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | no Equipment price field or historical price | YES |
| `iron_sword` | common Weapon; Goblin/Fox drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | no Equipment price field or historical price | YES |
| `fox_fang` | rare Weapon; Fox drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `dragon_claw` | epic Weapon; Dragon drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `celestial_blade` | legendary Weapon; Dragon drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `cloth_robe` | common Armor; Goblin drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | no Equipment price field or historical price | YES |
| `leather_armor` | common Armor; Goblin/Fox drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | no Equipment price field or historical price | YES |
| `fox_pelt` | rare Armor; Fox drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `dragon_scale` | epic Armor; Dragon drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `void_mantle` | legendary Armor; Dragon drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `lucky_stone` | common Accessory; Goblin drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | no Equipment price field or historical price | YES |
| `xp_amulet` | rare Accessory; Goblin/Fox drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | new Equip is HOLD_FOR_AUTHORITY | YES |
| `fox_mask` | rare Accessory; Fox drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `dragon_eye` | epic Accessory; Dragon drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | high-value drop identity must be protected | YES |
| `go_stone_black` | legendary Accessory; Dragon drop; admin/legacy | same current earning rules | non-equipment Shop range only; no equipment comparable | unresolved | none | LOW | inventory/trophy-only, no combat power | YES |

## Offer authority and implementation state

`equipment_shop_starter_catalog.py` provides the source-level C045 boundary:

- derives the 15-item audit from caller-supplied canonical definitions;
- keeps the recommended three-item assortment explicit;
- records the two permanent exclusions (`xp_amulet`, `go_stone_black`);
- accepts no client/display price; and
- can construct C025/C029 `ServerShopOfferFacts` only when a future caller
  supplies Owner-accepted positive prices plus stable price references.

With the current unresolved pricing state:

```text
EQUIPMENT_OFFERS_AUTHORITY_TRACED=YES
EQUIPMENT_OFFERS_SOURCE_IMPLEMENTED=NO
EQUIPMENT_OFFERS_COUNT_AFTER_SOURCE_CANDIDATE=0
ALL_OFFER_PRICES_AUTHORITATIVE=NO
ASSORTMENT_AUTHORITY_READY=YES
PRICING_AUTHORITY_READY=NO
OFFERS_ACTIVATABLE=NO
FRONTEND_OFFER_DUPLICATION=NO
```

No frontend change is required. C044 already consumes server-projected
`equipment_offers`; the C045 factory emits the same C025/C029 shape when
explicit accepted prices exist, and no C044 Shop constants are copied.

The C043 purchase service remains the only purchase path. Its existing
C019 operation/idempotency, Coins transaction, B040 `player_inventory`
acquisition, already-owned behavior, exact ownership reference, and
`equipped=0` contract remain unchanged. `C043_PURCHASE_SERVICE_COMPATIBLE=YES`
and `C044_SHOP_CONSUMER_COMPATIBLE=YES` mean the candidate offer shape was
validated against those contracts with explicit test fixtures; they do not
mean the Shop is enabled.

## app.py and runtime boundaries

`app.py` is owned by B051 and was not changed. The current C043 patch remains
queued and was not applied. Once an Owner pricing decision exists, a future
B051-authorized patch is required to bind
`build_authoritative_starter_offer_facts(equipment_defs=EQUIPMENT_DEFS, ...)`
into `_canonical_shop_offer_facts()` before the existing C043 route/catalog
adapter. That proposal must use only source-owned accepted prices and must
remain default-off. C045 does not apply or duplicate the C043 patch.

```text
APP_PY_CHANGED=NO
APP_PY_PATCH_REQUIRED=YES (future price-authority binding)
C043_APP_PY_PATCH_APPLIED=NO
SHOP_ENABLED=NO
LOADOUT_ENABLED=NO
AUTO_EQUIP_AFTER_PURCHASE=NO
PAYMENT_CHANGED=NO
SCHEMA_CHANGED=NO
MIGRATION_CHANGED=NO
PRODUCTION_QUERY=NO
PRODUCTION_MUTATION=NO
DEPLOY=NO
MASTER_MERGE=NO
```

## Gate result

```text
EQUIPMENT_ACQUISITION_AUDIT_COUNT=15
STARTER_ASSORTMENT_COUNT=3
STARTER_ASSORTMENT_IDS=wooden_sword,cloth_robe,lucky_stone
XP_AMULET_SHOP_ELIGIBLE=NO
GO_STONE_BLACK_SHOP_ELIGIBLE=NO
HIGH_VALUE_ITEM_LISTING_JUSTIFICATION=COMPLETE_PER_ITEM
COIN_ECONOMY_AUTHORITY_TRACED=YES
EQUIPMENT_OFFERS_AUTHORITY_TRACED=YES
C043_PURCHASE_SERVICE_COMPATIBLE=YES
C044_SHOP_CONSUMER_COMPATIBLE=YES
TASK_INTRODUCED_FAILURES=0
RESULT=READY_FOR_OWNER_PRICING_DECISION
```
