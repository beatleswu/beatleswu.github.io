# EQ-D — Canonical Equipment Merchandise and Zone Reward Portfolio

**Task:** `GO_ODYSSEY_EQ_D_CANONICAL_NEW_EQUIPMENT_AND_ZONE_REWARD_PORTFOLIO_001`
**Portfolio status:** `LOCKED_PRODUCT_DESIGN`
**Canonical design base:** `0762cd2517901eba7ed103105cb48f797ce71ba1`
**Canonical base tree:** `f67f3ba57801dbbde486f932478b1ce1aa7b7a9e`
**Runtime implementation:** `FORBIDDEN_IN_THIS_TASK`
**Production / database mutation:** `FORBIDDEN_IN_THIS_TASK`

## 1. Provenance and scope

This is a clean canonical-based successor planning artifact. The accepted
EQ-D0 product-design evidence is commit
`9540822a7ce231d60f3d59fb73e94d850c96eb52`, tree
`4b956a657e1e82a2edcce1a2a9cccd4e49096e64`, whose parent is the canonical base
`0762cd2517901eba7ed103105cb48f797ce71ba1`. It is used for the supported
functional slots, effect keys, existing Equipment pool, and renderer contract.

The earlier planning candidate `7134d20807eebdd2ce564475c7c4e7a74ecc4328`
and its markdown are product-design input only. Its parent lineage at
`872fcbb501ba7b7818c3b85ba99f7c45ec64f076` is not propagated, merged, or
reconstructed here. The candidate's useful Zone distribution was re-reviewed;
its blanket `HANDHELD_REQUIRED=NO` decision was rejected for wieldable weapons.

This artifact locks product identities and acceptance contracts only. It does
not add item definitions, routes, database columns, migrations, prices to the
live Shop, feature flags, art, renderer code, loadout behavior, or
`app.py` changes.

## 2. Canonical authority boundaries

Functional Equipment remains server-owned by the existing `EQUIPMENT_DEFS`
contract and `player_inventory` ownership/equipped state. The only functional
slots in this portfolio are `weapon`, `armor`, and `accessory`; rarity remains
`common`, `rare`, `epic`, or `legendary`.

The supported effect allowlist used by this portfolio is:

| Effect key | Value form | Portfolio use |
| --- | --- | --- |
| `dmg_bonus` | decimal fraction | flat player damage increase |
| `dragon_dmg_bonus` | decimal fraction | Dragon-target damage increase |
| `player_dmg_reduce` | decimal fraction | incoming player damage reduction |
| `crit_multiplier` | positive decimal | critical multiplier |
| `xp_bonus` | decimal fraction | general experience increase |
| `quest_xp_bonus` | decimal fraction | quest experience increase |
| `loot_bonus` | decimal fraction | loot increase |
| `sp_bonus` | positive integer | Spirit-point increase |

No portfolio row uses the inactive or unsupported candidates
`first_question_ace`, `negate_counter`, or `combo_multiplier_double`. No new
effect field is invented. Existing `fox_dmg_bonus` remains supported by the
runtime allowlist but is not needed by this locked 16-item portfolio.

Functional ownership is not cosmetic ownership:

* Functional Equipment is granted to `player_inventory` with `equipped=0`.
* The F028 cosmetic reward remains in `player_wardrobe` and is projected by
  the existing appearance flow.
* `player_appearance` is changed only by the existing equip/appearance flow;
  buying or granting a functional item does not write it.
* `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` stays unchanged and off.

## 3. F028 cosmetic mapping preserved

The new functional reward is additive. These existing cosmetic first-clear
rewards remain unchanged, keep combat power `0`, have no repeat reward, and do
not auto-equip:

| Zone | Canonical zone key | Existing F028 cosmetic | Store | Slot | New functional reward interaction |
| --- | --- | --- | --- | --- | --- |
| 1 | `k26_30` | `back_pack` | `player_wardrobe` | `back` | additive, independent |
| 2 | `k21_25` | `hat_cloth` | `player_wardrobe` | `hat` | additive, independent |
| 3 | `k16_20` | `hat_bamboo` | `player_wardrobe` | `hat` | additive, independent |
| 4 | `k11_15` | `robe_crane` | `player_wardrobe` | `outfit` | additive, independent |
| 5 | `k6_10` | `hat_onihorns` | `player_wardrobe` | `hat` | additive, independent |
| 6 | `k1_5` | `robe_dragon` | `player_wardrobe` | `outfit` | additive, independent |
| 7 | `d1_2` | `acc_dragon_pendant` | `player_wardrobe` | `accessory` | additive, independent |
| 8 | `d3_4` | `back_cloak` | `player_wardrobe` | `back` | additive, independent |
| 9 | `d5_6` | `hat_dragon_horn` | `player_wardrobe` | `hat` | additive, independent |
| 10 | `d7_plus` | `hat_celestial_crown` | `player_wardrobe` | `hat` | additive, independent |

The cosmetic operation remains the existing first-clear operation. It must not
be replaced by the functional Equipment operation below.

## 4. Portfolio summary

The portfolio deliberately has two distinct sources and no identity overlap.
The ten Zone items are exclusive first-clear functional rewards. The six Shop
items are new Coin Shop-exclusive functional products. Existing drop/admin
identities such as `wooden_sword`, `cloth_robe`, and `lucky_stone` are not
relabelled as new Shop products.

| Source | Count | Weapon | Armor | Accessory | Rarity mix |
| --- | ---: | ---: | ---: | ---: | --- |
| Zone 1–10 first clear | 10 | 3 | 4 | 3 | common 3, rare 3, epic 3, legendary 1 |
| New Shop-exclusive Equipment | 6 | 2 | 2 | 2 | rare 3, epic 3 |
| **Total new portfolio identities** | **16** | **5** | **6** | **5** | **no Zone/Shop overlap** |

The Shop prices below are exact proposed design values in Coins, not live
authority. C045 must receive stable Owner-approved price references before any
future implementation can expose or charge them. This task does not mutate
the current Shop V2 16-SKU catalog.

## 5. Zone first-clear functional reward matrix

`ZONE` means the item is not an ordinary Coin Shop SKU. `HANDHELD_REQUIRED=YES`
means that a real answer-screen handheld pose is part of acceptance; a sheath,
waist, or back mount is not an acceptable substitute for that item.

| item_id | zh-TW name | English name | source | zone | slot | rarity | gameplay role | supported stat/effect | exact proposed value | renderer family | HANDHELD_REQUIRED | EQ-C dependency | art requirement | runtime proof requirement | price if Shop | implementation readiness |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `bamboo_shadow_blade` | 竹影短刃 | Bamboo Shadow Blade | ZONE | 1 (`k26_30`) | weapon | common | early offensive baseline | `dmg_bonus` | `0.06` | `functional_handheld_one_hand_weapon` | YES | C1 hand/grip/occlusion renderer; C2 equipment registry binding | Transparent 1056x1408 RGBA overlay plus SVG icon; one-hand grip with visible blade and wrist/palm clearance | Granted owner equips it; answer screen renders blade in hand; damage calculation applies `0.06`; unequipped state has no weapon overlay | — | `DESIGN_LOCKED_EQ-C_HANDHELD` |
| `jade_river_bead` | 玉河珠 | Jade River Bead | ZONE | 2 (`k21_25`) | accessory | common | entry loot utility | `loot_bonus` | `0.05` | `functional_front_accessory` | NO | C2 functional accessory registry and slot binding | Transparent 1056x1408 RGBA front accessory overlay plus SVG icon; no face/hand occlusion | Ownership required before equip; accessory pointer changes; equipped hero/avatar resolves the overlay; loot result applies `0.05` | — | `DESIGN_LOCKED_EQ-C_STAT_ART` |
| `bamboo_scale_vest` | 竹鱗甲 | Bamboo Scale Vest | ZONE | 3 (`k16_20`) | armor | common | early survivability | `player_dmg_reduce` | `0.06` | `functional_torso_armor` | NO | C2 torso armor registry and stat binding | Transparent 1056x1408 RGBA torso overlay plus SVG icon; preserve head, back, and accessory layers | Ownership required before equip; torso pointer changes; render resolves; incoming damage reduction applies `0.06` | — | `DESIGN_LOCKED_EQ-C_STAT_ART` |
| `foxtail_traveler_mantle` | 狐尾行旅披風 | Foxtail Traveler Mantle | ZONE | 4 (`k11_15`) | armor | rare | mobility/progression hybrid | `player_dmg_reduce`; `xp_bonus` | `0.08`; `0.05` | `functional_torso_armor` | NO | C2 two-effect armor binding and stat proof | Transparent 1056x1408 RGBA mantle overlay plus SVG icon; no back-slot collision with F028 projection | Equip render shows mantle without changing unrelated slots; damage and XP proofs each match exact values | — | `DESIGN_LOCKED_EQ-C_STAT_ART` |
| `riverguard_coat` | 河守長衣 | Riverguard Coat | ZONE | 5 (`k6_10`) | armor | rare | defense plus Spirit progression | `player_dmg_reduce`; `sp_bonus` | `0.10`; `8` | `functional_torso_armor` | NO | C2 two-effect armor binding and stat proof | Transparent 1056x1408 RGBA coat overlay plus SVG icon; stable torso silhouette across answer poses | Equip/unequip preserves other pointers; incoming damage and Spirit-point settlement each prove exact values | — | `DESIGN_LOCKED_EQ-C_STAT_ART` |
| `riverstone_sabre` | 河石軍刀 | Riverstone Sabre | ZONE | 6 (`k1_5`) | weapon | rare | general offense plus Dragon specialization | `dmg_bonus`; `dragon_dmg_bonus` | `0.07`; `0.06` | `functional_handheld_one_hand_weapon` | YES | C1 real one-hand answer-screen pose; C2 two-effect weapon binding | Transparent 1056x1408 RGBA handheld blade overlay plus SVG icon; grip-axis, wrist, face, and torso occlusion proof | Owner-only equip renders the sabre in hand; general and Dragon damage tests match; no waist/back fallback accepted | — | `DESIGN_LOCKED_EQ-C_HANDHELD` |
| `cloudstep_star_lamellar` | 雲步星札 | Cloudstep Star Lamellar | ZONE | 7 (`d1_2`) | armor | epic | high-tier defense plus quest progression | `player_dmg_reduce`; `quest_xp_bonus` | `0.12`; `0.08` | `functional_torso_armor` | NO | C2 two-effect armor binding; C4 high-tier stat proof | Transparent 1056x1408 RGBA lamellar overlay plus SVG icon; mobile crop and layer-order proof | Equip render resolves; unrelated head/accessory/back pointers stay unchanged; damage and quest XP each prove exact values | — | `DESIGN_LOCKED_EQ-C_STAT_ART` |
| `constellation_focus_lens` | 星座聚焦鏡 | Constellation Focus Lens | ZONE | 8 (`d3_4`) | accessory | epic | critical-hit specialization | `crit_multiplier` | `1.20` | `functional_front_accessory` | NO | C2 accessory binding; C4 critical-stat proof | Transparent 1056x1408 RGBA lens overlay plus SVG icon; no face readability loss and no hat replacement | Equip writes only the accessory pointer; hero/avatar render resolves; critical calculation proves `1.20` | — | `DESIGN_LOCKED_EQ-C_STAT_ART` |
| `moonstar_rapier` | 月星細劍 | Moonstar Rapier | ZONE | 9 (`d5_6`) | weapon | epic | precision offense | `dmg_bonus`; `crit_multiplier` | `0.10`; `1.20` | `functional_handheld_one_hand_weapon` | YES | C1 real rapier-in-hand answer-screen pose; C2 two-effect binding; C4 high-tier stat proof | Transparent 1056x1408 RGBA handheld rapier overlay plus SVG icon; narrow blade, grip axis, palm/wrist, and opponent/board clearance | Ownership/equip/render proves the rapier is held in the answer screen; damage and critical tests match; no sheath-only presentation | — | `DESIGN_LOCKED_EQ-C_HANDHELD` |
| `odyssey_star_compass` | 奧德賽星羅盤 | Odyssey Star Compass | ZONE | 10 (`d7_plus`) | accessory | legendary | endgame exploration plus Spirit progression | `loot_bonus`; `sp_bonus` | `0.06`; `12` | `functional_front_accessory` | NO | C2 two-effect accessory binding; C4 legendary stat proof | Transparent 1056x1408 RGBA compass overlay plus SVG icon; clear silhouette at mobile scale and no front-accessory collision | Equip changes only accessory state; render resolves; loot and Spirit-point proofs match exact values; no auto-equip | — | `DESIGN_LOCKED_EQ-C_STAT_ART` |

### Zone distribution decision

The reviewed Zone distribution is retained because it is coherent with the
first-clear progression curve and the supported effect allowlist:

* Weapons: Zones 1, 6, and 9.
* Armor: Zones 3, 4, 5, and 7.
* Accessories: Zones 2, 8, and 10.
* Rarities: common 3, rare 3, epic 3, legendary 1.

All three Zone weapons are genuinely wieldable and therefore require the
handheld proof. None was converted to a sheath-only or back-mounted concept
to avoid EQ-C work.

## 6. New Shop-exclusive functional Equipment matrix

These six IDs are new product identities: they are absent from the canonical
15-item Equipment pool, absent from the ten Zone rows above, and absent from
the F028 cosmetic mapping. They are ordinary Coin Shop candidates only after
C045 price authority and the C043 purchase path are separately admitted.

| item_id | zh-TW name | English name | source | zone | slot | rarity | gameplay role | supported stat/effect | exact proposed value | renderer family | HANDHELD_REQUIRED | EQ-C dependency | art requirement | runtime proof requirement | price if Shop | implementation readiness |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- |
| `emberline_cutlass` | 赤焰航刃 | Emberline Cutlass | SHOP | — | weapon | rare | accessible offensive sidegrade | `dmg_bonus` | `0.11` | `functional_handheld_one_hand_weapon` | YES | C1 real cutlass-in-hand answer-screen pose; C2 weapon binding; C045 price authority | Transparent 1056x1408 RGBA handheld cutlass overlay plus SVG icon; grip axis and arm/board clearance | Coin purchase creates `player_inventory` ownership only; owner equips; answer-screen renders in hand; damage proves `0.11`; no auto-equip | 700 Coins (proposed) | `DESIGN_LOCKED_EQ-C_HANDHELD-C045` |
| `starglass_needle` | 星璃針劍 | Starglass Needle | SHOP | — | weapon | epic | precision offensive sidegrade | `dmg_bonus`; `crit_multiplier` | `0.16`; `1.15` | `functional_handheld_one_hand_weapon` | YES | C1 real needle-sword handheld pose; C2 two-effect binding; C4 stat proof; C045 price authority | Transparent 1056x1408 RGBA handheld narrow-blade overlay plus SVG icon; fine-grip and mobile silhouette proof | Purchase/equip/render path proves held presentation; damage and critical tests prove exact values; no sheath/back fallback | 1000 Coins (proposed) | `DESIGN_LOCKED_EQ-C_HANDHELD-C045` |
| `weaveguard_vest` | 織衛戰背 | Weaveguard Vest | SHOP | — | armor | rare | defensive sidegrade | `player_dmg_reduce` | `0.11` | `functional_torso_armor` | NO | C2 armor binding and stat proof; C045 price authority | Transparent 1056x1408 RGBA torso overlay plus SVG icon; no collision with hat/back/accessory | Purchase does not equip; explicit equip changes armor state only; render and damage proof match `0.11`; unequip restores prior state | 650 Coins (proposed) | `DESIGN_LOCKED_EQ-C045_STAT_ART` |
| `mirrorfall_mantle` | 鏡瀑披風 | Mirrorfall Mantle | SHOP | — | armor | epic | defense plus general progression | `player_dmg_reduce`; `xp_bonus` | `0.16`; `0.04` | `functional_torso_armor` | NO | C2 two-effect armor binding; C4 stat proof; C045 price authority | Transparent 1056x1408 RGBA mantle overlay plus SVG icon; layer order and mobile crop proof | Purchase/own/equip/render is explicit; defense and XP proofs match; unrelated cosmetic pointers remain unchanged | 950 Coins (proposed) | `DESIGN_LOCKED_EQ-C045_STAT_ART` |
| `copper_jade_talisman` | 銅玉護符 | Copper-Jade Talisman | SHOP | — | accessory | rare | accessible exploration utility | `loot_bonus` | `0.08` | `functional_front_accessory` | NO | C2 accessory binding and stat proof; C045 price authority | Transparent 1056x1408 RGBA accessory overlay plus SVG icon; face/hand readability and mobile-size proof | Purchase ownership is in `player_inventory`; explicit accessory equip renders; loot proof matches `0.08`; no wardrobe or appearance-row mutation at purchase | 600 Coins (proposed) | `DESIGN_LOCKED_EQ-C045_STAT_ART` |
| `prism_focus_charm` | 稜晶定心符 | Prism Focus Charm | SHOP | — | accessory | epic | critical-hit sidegrade | `crit_multiplier` | `1.15` | `functional_front_accessory` | NO | C2 accessory binding; C4 critical proof; C045 price authority | Transparent 1056x1408 RGBA charm overlay plus SVG icon; no overlap with lens/hat and readable mobile silhouette | Purchase/own/equip/render proves the correct accessory pointer and `1.15` critical value; switching accessory leaves armor/weapon unchanged | 900 Coins (proposed) | `DESIGN_LOCKED_EQ-C045_STAT_ART` |

The six Shop products are intentionally not the Zone reward identities. The
Shop collection has two weapons, two armor items, and two accessories, so the
portfolio does not put all new Equipment in either one source.

## 7. Acquisition, past-clear backfill, and exactly-once contract

The functional first-clear operation identity is deterministic:

```text
adventure:first_clear_equipment:{uid}:{zone_key}
```

`uid` and `zone_key` are server-derived from the authenticated player and the
persisted canonical Zone mapping. The client cannot select a Zone, item, or
reward identity.

Eligibility is the authoritative persisted first-clear state in
`adventure_boss_progress(user_id, zone_key).cleared=1`. UI labels, scores,
cosmetic ownership, replay count, and client-provided reward keys are not
eligibility authorities.

The future implementation must use the caller's open transaction and must not
commit or roll back inside a domain service:

1. Lock the exact `adventure_boss_progress` row for the authenticated user and
   canonical Zone.
2. Recheck `cleared=1` and resolve the immutable Zone-to-item mapping on the
   server.
3. Check the exact `player_inventory` ownership for that `item_id`.
4. If already owned, return the typed already-owned/no-reward result without
   inserting a duplicate.
5. Otherwise insert one row into `player_inventory` with `equipped=0`.
6. Record the deterministic operation through the existing Adventure
   first-clear settlement/convergence receipt authority, in the same caller
   transaction as the F028 cosmetic settlement.

The current `adventure_first_clear_convergence.py` evidence establishes the
deployed Adventure receipt pattern in the D5A outbox and explicitly avoids a
second redundant receipt table. The Shop-specific C019/C043 purchase operation
ledger remains Shop purchase authority and must not be overloaded as a Zone
reward ledger merely because both flows need idempotency. The durable Zone
reward is the `player_inventory` ownership row plus the existing Adventure
settlement/convergence receipt under the new functional operation namespace.

Required outcomes:

| Scenario | Required result |
| --- | --- |
| Past clear, no functional owner | Grant the new functional item once; preserve the existing F028 cosmetic result. |
| Past clear, already owns item | No repurchase and no new row; no re-clear required. |
| First-clear replay | No duplicate functional row and no repeat cosmetic reward. |
| Different replay with same client reward key | Ignore client key; server mapping and operation identity prevail. |
| Grant response interrupted after commit | Receipt/ownership convergence makes retry idempotent. |
| Successful grant | `equipped=0`; no automatic appearance/loadout mutation. |
| Invalid or unknown Zone mapping | Fail closed; do not grant an invented item. |

Backfill is a one-time future implementation operation over already-cleared
canonical Zones. It uses the same lock, server mapping, ownership check, and
operation identity. It grants only the additional functional item, never
reissues the F028 cosmetic, never requires a Zone re-clear, and never requires
an existing owner to repurchase.

## 8. EQ-C handheld and render dependency contract

EQ-C must treat the five weapon rows as answer-screen wieldable Equipment:
three Zone weapons and two Shop weapons. Static `WAIST_SHEATHED` or
`BACK_MOUNTED` is not sufficient acceptance for these rows. The required
handheld proof is narrow and shared:

1. Bind a functional weapon overlay to the existing 1056x1408 RGBA canvas and
   SVG item icon registry.
2. Provide a stable one-hand grip transform with visible palm/wrist relation,
   blade/guard clearance, and deterministic layer order.
3. Prove the held pose in the real answer-screen hero/avatar renderer at the
   supported responsive sizes; do not accept a Shop-card-only image.
4. Prove switching between two handheld weapons updates only the weapon
   presentation and leaves armor, accessory, and cosmetic wardrobe pointers
   unchanged.
5. Keep equip authority in the existing wardrobe/appearance flow and
   functional ownership authority in `player_inventory`; EQ-C adds no second
   ownership or equip authority.

For all non-weapon rows, EQ-C still must prove the appropriate torso or front
accessory renderer family, slot collision behavior, mobile readability, and
that a functional equip does not silently replace unrelated F028 cosmetic
slots.

## 9. Acceptance and regression gates for future implementation

This planning task does not run runtime or browser acceptance. The following
are the required future proofs before any implementation or Shop admission is
considered ready:

* Every matrix item exists in the server Equipment definition authority with
  only the listed supported effect keys and exact values.
* Every Zone reward is granted to `player_inventory`, never
  `player_wardrobe` or `player_appearance`.
* Every Shop purchase uses the existing C043 purchase authority and C019
  idempotency contract after C045 approves stable prices; buying never
  directly equips or writes `player_appearance`.
* Each item passes own -> equip -> render -> stat/effect proof.
* All five handheld weapons pass the real answer-screen held-pose proof.
* Switching in one slot leaves all unrelated functional and cosmetic slots
  unchanged.
* Existing Equipment identities and their acquisition roles remain intact.
* Existing F028 cosmetics, premium cosmetic bundles, onboarding/achievement
  titles, hidden unreleased cosmetics, and other wardrobe slots remain
  unchanged and unexposed.
* `EQUIPMENT_CANONICAL_LOADOUT_ENABLED` remains off and no auto-equip is
  introduced.

## 10. Locked task boundaries

```text
OLD_7134D_USED_AS_DESIGN_INPUT_ONLY=YES
INVALID_872FCBB_LINEAGE_PROPAGATED=NO
F028_MAPPING_PRESERVED=YES
ZONE_REWARD_COUNT=10
ZONE_WEAPON_COUNT=3
ZONE_ARMOR_COUNT=4
ZONE_ACCESSORY_COUNT=3
NEW_SHOP_EQUIPMENT_COUNT=6
NEW_SHOP_WEAPON_COUNT=2
NEW_SHOP_ARMOR_COUNT=2
NEW_SHOP_ACCESSORY_COUNT=2
HANDHELD_REQUIREMENTS_RECONCILED=YES
PAST_CLEAR_BACKFILL=YES
NO_REPURCHASE=YES
NO_RECLEAR=YES
NO_REPLAY_DUPLICATE=YES
OWNER_DECISIONS_REQUIRED=NONE_TO_LOCK_PORTFOLIO
FUTURE_C045_PRICE_AUTHORITY=REQUIRED_BEFORE_SHOP_IMPLEMENTATION
APP_PY_MUTATION=NO
RUNTIME_MUTATION=NO
PRODUCTION_MUTATION=NO
SHOP_V2_CURRENT_16_SKU_MUTATION=NO
LOADOUT_ENABLEMENT=UNCHANGED_OFF
```

No current Shop catalog, price, feature flag, migration, runtime authority,
or production state is changed by this artifact.
