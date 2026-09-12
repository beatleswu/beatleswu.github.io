# C045 — New Shop Equipment Final Coin Price Authority

`CONTRACT_ID`: `GO_ODYSSEY_C045_NEW_SHOP_EQUIPMENT_FINAL_COIN_PRICE_AUTHORITY_001`

`CONTRACT_STATUS`: `FINAL_COIN_PRICE_AUTHORITY_LOCKED`

`CANONICAL_BASE_HEAD`: `657d5b368541f593b7bfb16008512de552b5caa2`

`CANONICAL_BASE_TREE`: `a17893a3252f8103cd0f9953cbcb46b5f5be9117`

`OWNER_MODE`: `LOW_BURDEN_OWNER_MODE`

This document locks Coin price authority for exactly six already-approved,
Shop-exclusive functional Equipment products. It does not admit the products
to the live Shop and does not change runtime, `app.py`, the renderer, Zone
rewards, database state, feature flags, or Production.

## Authority inputs

The product identity, slot, rarity, supported effect, exact effect value, and
Shop-exclusive classification are taken from the accepted EQ-D portfolio:

* source commit: `e2cd8c5f30ee757f31cc8b6389697a20412f2636`
* source tree: `a5fa5fa478c09866fae37fdab7e98dd4fc39beeb`
* source artifact: `docs/planning/zone_1_10_first_clear_equipment_reward_contract_002.md`

The existing Shop comparison is the canonical 16-SKU contract at the current
canonical head. Its locked prices are:

* consumables: `30, 50, 60, 60, 70, 80, 100, 120, 130, 150` Coins;
* cosmetics: `200, 220, 450, 480, 750, 950` Coins.

The accepted price bands remain `ENTRY=20-80`, `MID=90-300`, and
`PREMIUM=350-1500`. The active-player balance reference supplied for this
decision is `p25≈30`, `p50≈235`, and `p75≈645` Coins.

## Product and ownership rules

All six products are permanent functional Equipment. The future ownership
destination is `player_inventory`, with `equipped=0` after purchase. Purchase
does not equip the item and does not directly mutate `player_appearance`.
Existing owners do not repurchase.

The six IDs are distinct from all ten EQ-D Zone first-clear Equipment IDs. A
Coin price never changes Zone eligibility, Zone clear progression, or the
guaranteed earned-relic identity.

## Final six-item price matrix

The EQ-D proposed values are ratified here as exact final C045 Coin prices.
Every final price is an integer and is server-authoritative for any future
implementation.

| item_id | zh-TW name | English name | slot | rarity | functional effect | effect magnitude | final Coin price | price band | economy rationale | relative to existing 16-SKU Shop | relative to Zone-exclusive Equipment | progression risk | final authority status |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| `emberline_cutlass` | 赤焰航刃 | Emberline Cutlass | weapon | rare | `dmg_bonus` | `0.11` | **700** | PREMIUM | Rare permanent universal offense is priced near the upper-quartile balance, making the purchase deliberate rather than an early free power skip. | Above every launch consumable (`30-150`) and below the Premium ceiling; it sits in the permanent-value tier alongside, but is not a replacement for, the cosmetic ladder. | Universal `0.11` is a sidegrade to the Zone weapons' situational profiles: `riverstone_sabre` (`0.07` + Dragon `0.06`) and `foxfire_brushblade` (`0.06` + Fox `0.10`). It is not a Zone-reward SKU. | LOW-MEDIUM; premium one-time cost and no Zone unlock effect. | `FINAL_COIN_PRICE_AUTHORITY` |
| `starglass_needle` | 星璃針劍 | Starglass Needle | weapon | epic | `dmg_bonus`; `crit_multiplier` | `0.16`; `1.15` | **1000** | PREMIUM | The top price in the collection reflects an epic two-effect precision sidegrade and keeps it above the supplied p75 balance. | Above the 16-SKU consumable ladder and just above the current `950` cosmetic high point, while remaining below the `1500` Premium cap. | Trades higher general damage for lower critical specialization than Zone `moonstar_rapier` (`0.10` + `1.20`) and does not duplicate a Zone identity. | LOW; high one-time savings threshold and a tradeoff rather than best-in-slot certainty. | `FINAL_COIN_PRICE_AUTHORITY` |
| `weaveguard_vest` | 織衛戰背 | Weaveguard Vest | armor | rare | `player_dmg_reduce` | `0.11` | **650** | PREMIUM | The lowest defensive rare price is still just above the p75 reference, recognizing permanent mitigation without making it an entry purchase. | Above all consumables and within the existing Premium cosmetic span; no existing 16-SKU price is changed or reused as an Equipment offer. | Defensive value is traded against Zone utility: `riverguard_coat` carries `0.10` mitigation plus `sp_bonus=8`, while `foxtail_traveler_mantle` carries `0.08` mitigation plus `xp_bonus=0.05`. | LOW; one-slot defensive sidegrade with a meaningful Coin gate. | `FINAL_COIN_PRICE_AUTHORITY` |
| `mirrorfall_mantle` | 鏡瀑披風 | Mirrorfall Mantle | armor | epic | `player_dmg_reduce`; `xp_bonus` | `0.16`; `0.04` | **950** | PREMIUM | An epic permanent two-effect armor item belongs near the top of the ladder; 950 is material relative to p50/p75 without exceeding the established Premium range. | Matches the existing `hat_dragon_horn` cosmetic price but has a separate functional product identity and ownership store; it remains below the 1500 band ceiling. | Trades higher general mitigation for less quest-specific progression than Zone `cloudstep_star_lamellar` (`0.12` + `quest_xp_bonus=0.08`). No Zone identity is duplicated. | LOW; expensive, non-automatic, and not a guaranteed progression shortcut. | `FINAL_COIN_PRICE_AUTHORITY` |
| `copper_jade_talisman` | 銅玉護符 | Copper-Jade Talisman | accessory | rare | `loot_bonus` | `0.08` | **600** | PREMIUM | The entry point for this permanent collection is still a substantial savings decision: more than 2.5× p50 and just below p75. | Above every consumable and above the MID cosmetic tier; its Premium placement distinguishes durable utility from temporary Shop effects. | It is a later rare utility choice, not a duplicate of Zone `jade_river_bead` (`loot_bonus=0.05`): the Zone relic remains the earned first-clear identity and this product does not alter Zone progression or replace the reward source. | LOW-MEDIUM; the strongest direct utility overlap is guarded by the Premium price and separate acquisition identity. | `FINAL_COIN_PRICE_AUTHORITY` |
| `prism_focus_charm` | 稜晶定心符 | Prism Focus Charm | accessory | epic | `crit_multiplier` | `1.15` | **900** | PREMIUM | The epic single-effect precision item is priced below the two-effect epics but far above temporary utility, preserving a clear rarity ladder. | Above all consumables and within the Premium cosmetic range; it is a new functional identity, not a cosmetic conversion. | It is deliberately below the Zone `constellation_focus_lens` critical value (`1.20`), preserving the earned Zone precision relic as the stronger specialized milestone choice. | LOW; premium cost and lower specialized magnitude than the corresponding Zone relic. | `FINAL_COIN_PRICE_AUTHORITY` |

## Price ladder and compatibility decision

Sorted final prices are `600, 650, 700, 900, 950, 1000` Coins.

* `MIN_PRICE=600`.
* `MAX_PRICE=1000`.
* `MEDIAN_PRICE=800` (the midpoint of the third and fourth ordered prices).
* Rare products form a deliberate `600-700` Premium entry tier.
* Epic products form a deliberate `900-1000` Premium tier.
* The `200`-Coin tier gap recognizes the added durable value of the epic
  products without exceeding the accepted `1500` Premium ceiling.

The ladder is compatible with the existing 16-SKU Shop because all six new
prices are outside the temporary consumable `30-150` ladder, remain inside the
accepted Premium band, and do not modify any existing SKU or price. The prior
accepted C046 starter Equipment authority (`wooden_sword=300`,
`cloth_robe=300`, `lucky_stone=400`) is a separate common/legacy comparison;
these six new rare/epic products are intentionally priced above it.

`EXISTING_SHOP_16_SKU_COMPATIBILITY=PASS`

`ZONE_REWARD_POWER_RELATIONSHIP=PASS`

The relationship passes because there is no Zone reward duplicate SKU, the
products are sidegrades or deliberately lower in the directly comparable
specialization, and every Shop item has a substantial Premium price. No Shop
purchase grants a Zone clear, changes a Zone reward, or bypasses a Zone gate.

## Machine-readable handoff

```json
{
  "contract_id": "GO_ODYSSEY_C045_NEW_SHOP_EQUIPMENT_FINAL_COIN_PRICE_AUTHORITY_001",
  "status": "FINAL_COIN_PRICE_AUTHORITY_LOCKED",
  "currency": "Coins",
  "source": "EQ-D:e2cd8c5f30ee757f31cc8b6389697a20412f2636",
  "shop_exclusive_equipment_count": 6,
  "no_zone_reward_duplicate_sku": true,
  "existing_owner_repurchase_required": false,
  "items": [
    {
      "item_id": "emberline_cutlass",
      "display_name_zh_tw": "赤焰航刃",
      "display_name_en": "Emberline Cutlass",
      "slot": "weapon",
      "rarity": "rare",
      "effects": {"dmg_bonus": 0.11},
      "final_coin_price": 700,
      "price_band": "PREMIUM",
      "ownership_store": "player_inventory",
      "repeat_purchase_allowed": false
    },
    {
      "item_id": "starglass_needle",
      "display_name_zh_tw": "星璃針劍",
      "display_name_en": "Starglass Needle",
      "slot": "weapon",
      "rarity": "epic",
      "effects": {"dmg_bonus": 0.16, "crit_multiplier": 1.15},
      "final_coin_price": 1000,
      "price_band": "PREMIUM",
      "ownership_store": "player_inventory",
      "repeat_purchase_allowed": false
    },
    {
      "item_id": "weaveguard_vest",
      "display_name_zh_tw": "織衛戰背",
      "display_name_en": "Weaveguard Vest",
      "slot": "armor",
      "rarity": "rare",
      "effects": {"player_dmg_reduce": 0.11},
      "final_coin_price": 650,
      "price_band": "PREMIUM",
      "ownership_store": "player_inventory",
      "repeat_purchase_allowed": false
    },
    {
      "item_id": "mirrorfall_mantle",
      "display_name_zh_tw": "鏡瀑披風",
      "display_name_en": "Mirrorfall Mantle",
      "slot": "armor",
      "rarity": "epic",
      "effects": {"player_dmg_reduce": 0.16, "xp_bonus": 0.04},
      "final_coin_price": 950,
      "price_band": "PREMIUM",
      "ownership_store": "player_inventory",
      "repeat_purchase_allowed": false
    },
    {
      "item_id": "copper_jade_talisman",
      "display_name_zh_tw": "銅玉護符",
      "display_name_en": "Copper-Jade Talisman",
      "slot": "accessory",
      "rarity": "rare",
      "effects": {"loot_bonus": 0.08},
      "final_coin_price": 600,
      "price_band": "PREMIUM",
      "ownership_store": "player_inventory",
      "repeat_purchase_allowed": false
    },
    {
      "item_id": "prism_focus_charm",
      "display_name_zh_tw": "稜晶定心符",
      "display_name_en": "Prism Focus Charm",
      "slot": "accessory",
      "rarity": "epic",
      "effects": {"crit_multiplier": 1.15},
      "final_coin_price": 900,
      "price_band": "PREMIUM",
      "ownership_store": "player_inventory",
      "repeat_purchase_allowed": false
    }
  ]
}
```

## Boundary assertions

```text
SHOP_EQUIPMENT_PRICE_COUNT=6
WEAPON_COUNT=2
ARMOR_COUNT=2
ACCESSORY_COUNT=2
NO_ZONE_REWARD_DUPLICATE_SKU=YES
EXISTING_OWNER_REPURCHASE_REQUIRED=NO
NO_NEW_CURRENCY=YES
NO_GACHA=YES
APP_PY_MUTATION=NO
RUNTIME_MUTATION=NO
EQUIPMENT_RENDERER_MUTATION=NO
ZONE_REWARD_MUTATION=NO
DB_MIGRATION=NO
PRODUCTION_MUTATION=NO
SHOP_REOPEN=NO
MERGE=NO
DEPLOY=NO
OWNER_DECISIONS_REQUIRED=NONE
```

This document is the final pricing handoff for SHOP-B, SHOP-C, SHOP-D,
SHOP-E, and SHOP-F. Any future runtime admission must consume these exact
server-owned prices and must not derive a price from request data, UI data, or
the player's current balance.
