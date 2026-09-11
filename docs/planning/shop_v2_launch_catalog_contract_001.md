# Shop V2 R1 Launch Catalog and Product Contract

`CONTRACT_ID`: `GO_ODYSSEY_SHOP_A_LAUNCH_CATALOG_AND_PRODUCT_CONTRACT_001`
`OWNER_LANE`: `SHOP-A`
`BASE_HEAD`: `0762cd2517901eba7ed103105cb48f797ce71ba1`
`BASE_TREE`: `f67f3ba57801dbbde486f932478b1ce1aa7b7a9e`
`CONTRACT_STATUS`: `R1_LAUNCH_CATALOG_LOCKED`

This document is the durable Shop V2 R1 product-data, copy, price, SKU, and
asset contract. It is the exact handoff input for SHOP-B, SHOP-C, SHOP-D,
SHOP-E, and SHOP-F.

SHOP-A does not own purchase authority, app routing, database migrations,
feature flags, presentation rollout, or Production mutation. A catalog entry
being marked `R1_LAUNCH_DEFAULT` does not reopen the Shop or authorize a
runtime rollout.

## Launch boundaries

The launch catalog contains exactly 16 SKUs: 10 consumables and 6 cosmetics.
Equipment, premium-entitlement cosmetics, achievement or milestone titles,
hidden or unreleased appearance IDs, new currencies, gacha products, and
real-money products are excluded. Equipment remains excluded because priced
canonical offers do not exist and canonical loadout remains disabled.

The locked evidence-based price bands are:

| PRICE_BAND | PRICE_RANGE |
| --- | --- |
| `ENTRY` | `20-80` |
| `MID` | `90-300` |
| `PREMIUM` | `350-1500` |

`PURCHASE` and `USE` are separate lifecycle events. In particular, buying an
effect-bearing consumable stores or stacks the item; the existing use or
activation flow applies its effect later.

## Machine-readable exact 16-SKU contract

```json
{
  "CONTRACT_ID": "GO_ODYSSEY_SHOP_A_LAUNCH_CATALOG_AND_PRODUCT_CONTRACT_001",
  "CONTRACT_STATUS": "R1_LAUNCH_CATALOG_LOCKED",
  "SOURCE_BASE": {
    "HEAD": "0762cd2517901eba7ed103105cb48f797ce71ba1",
    "TREE": "f67f3ba57801dbbde486f932478b1ce1aa7b7a9e"
  },
  "CATALOG": {
    "LAUNCH_SKU_COUNT": 16,
    "CONSUMABLE_COUNT": 10,
    "COSMETIC_COUNT": 6,
    "AVAILABILITY_POLICY": "R1_LAUNCH_DEFAULT; runtime rollout and Shop reopen remain separately gated",
    "PRICE_BANDS": {
      "ENTRY": "20-80",
      "MID": "90-300",
      "PREMIUM": "350-1500"
    },
    "SKUS": [
      {
        "SKU_ID": "hint_ticket",
        "DISPLAY_NAME_ZH_TW": "小提示卷",
        "DISPLAY_NAME_EN": "Hint Ticket",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 30,
        "PRICE_BAND": "ENTRY",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the ticket and does not use a hint.",
        "USE_SEMANTICS": "Existing in-question hint flow consumes one stored hint_ticket later to reveal the next correct move.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/small_hint_scroll.webp",
        "SHOP_CARD_COPY_ZH_TW": "購買後存入提示卷；作答時使用可顯示下一手正解位置。",
        "SHOP_CARD_COPY_EN": "Store a ticket now; use it during a question to reveal the next correct move.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "ai_explain_ticket",
        "DISPLAY_NAME_ZH_TW": "AI 解說券",
        "DISPLAY_NAME_EN": "AI Analysis Ticket",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 50,
        "PRICE_BAND": "ENTRY",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the ticket and does not run an AI analysis.",
        "USE_SEMANTICS": "Existing post-answer AI analysis flow consumes one stored ai_explain_ticket later when the eligible analysis is requested or auto-used.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/icon_ai_ticket.webp",
        "SHOP_CARD_COPY_ZH_TW": "先存下一張 AI 解說券；符合條件時再使用一次棋力解析。",
        "SHOP_CARD_COPY_EN": "Store one AI analysis ticket for a later eligible KataGo analysis.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "small_xp_potion",
        "DISPLAY_NAME_ZH_TW": "小 XP 藥水",
        "DISPLAY_NAME_EN": "Small XP Potion",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 70,
        "PRICE_BAND": "ENTRY",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the potion; it does not activate the XP boost.",
        "USE_SEMANTICS": "Existing activation flow consumes one stored small_xp_potion later and applies XP x1.25 for 20 minutes.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/small_xp_potion.webp",
        "SHOP_CARD_COPY_ZH_TW": "存入小 XP 藥水；使用後 20 分鐘內答題 XP x1.25。購買不會立即啟用。",
        "SHOP_CARD_COPY_EN": "Store a potion; use it later for XP x1.25 for 20 minutes. Buying does not activate it.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "streak_shield",
        "DISPLAY_NAME_ZH_TW": "連勝護盾",
        "DISPLAY_NAME_EN": "Streak Shield",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 80,
        "PRICE_BAND": "ENTRY",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the shield; it does not protect an answer until used.",
        "USE_SEMANTICS": "Existing activation flow consumes one stored streak_shield later and protects the next wrong answer from breaking the combo.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/icon_shield.webp",
        "SHOP_CARD_COPY_ZH_TW": "存入連勝護盾；使用後下一次答錯不中斷連擊。購買不會立即啟用。",
        "SHOP_CARD_COPY_EN": "Store a shield; use it later so the next wrong answer will not break your combo.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "pet_snack",
        "DISPLAY_NAME_ZH_TW": "寵物糖果包",
        "DISPLAY_NAME_EN": "Pet Candy Pouch",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 60,
        "PRICE_BAND": "ENTRY",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; SHOP-B canonical grant destination pending",
        "PURCHASE_SEMANTICS": "Intended product result: grant 3 Go Spirit Candies. Purchase is not feeding or activation; SHOP-B must prove the canonical physical grant destination.",
        "USE_SEMANTICS": "Existing Go Spirit Candy feeding flow consumes the granted candy units later; purchase itself does not feed the Spirit.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "GRANT_TARGET_UNITS; canonical storage destination pending SHOP-B",
        "ASSET_PATH": "/assets/shop/pet_candy_pouch.webp",
        "SHOP_CARD_COPY_ZH_TW": "購買預計獲得棋魂糖 x3；之後到寵物頁餵食。",
        "SHOP_CARD_COPY_EN": "Intended result: 3 Go Spirit Candies to feed later from the pet flow.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "extra_questions_small",
        "DISPLAY_NAME_ZH_TW": "小型修行令",
        "DISPLAY_NAME_EN": "Small Training Pass",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 60,
        "PRICE_BAND": "ENTRY",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the pass; it does not change today's question limit.",
        "USE_SEMANTICS": "Existing activation flow consumes one stored extra_questions_small later and adds 5 to today's free-question limit.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/small_training_pass.webp",
        "SHOP_CARD_COPY_ZH_TW": "存入小型修行令；使用後今日免費題數上限 +5。購買不會立即生效。",
        "SHOP_CARD_COPY_EN": "Store a pass; use it later for +5 to today's free-question limit. Buying does not apply it.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "extra_questions",
        "DISPLAY_NAME_ZH_TW": "加題券",
        "DISPLAY_NAME_EN": "Extra Questions Ticket",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 100,
        "PRICE_BAND": "MID",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the ticket; it does not change today's question limit.",
        "USE_SEMANTICS": "Existing activation flow consumes one stored extra_questions later and adds 10 to today's free-question limit.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/small_training_pass.webp",
        "SHOP_CARD_COPY_ZH_TW": "存入加題券；使用後今日免費題數上限 +10。購買不會立即生效。",
        "SHOP_CARD_COPY_EN": "Store a ticket; use it later for +10 to today's free-question limit. Buying does not apply it.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "xp_potion",
        "DISPLAY_NAME_ZH_TW": "XP 藥水",
        "DISPLAY_NAME_EN": "XP Potion",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 120,
        "PRICE_BAND": "MID",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the potion; it does not activate the XP boost.",
        "USE_SEMANTICS": "Existing activation flow consumes one stored xp_potion later and applies XP x1.5 for 30 minutes.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/icon_xp_potion.webp",
        "SHOP_CARD_COPY_ZH_TW": "存入 XP 藥水；使用後 30 分鐘內答題 XP x1.5。購買不會立即啟用。",
        "SHOP_CARD_COPY_EN": "Store a potion; use it later for XP x1.5 for 30 minutes. Buying does not activate it.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "premium_hint_bundle",
        "DISPLAY_NAME_ZH_TW": "高級提示包",
        "DISPLAY_NAME_EN": "Premium Hint Bundle",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 130,
        "PRICE_BAND": "MID",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; SHOP-B canonical grant destination pending",
        "PURCHASE_SEMANTICS": "Intended product result: grant 5 hint_ticket units. Purchase does not consume a hint; SHOP-B must prove the canonical physical grant destination.",
        "USE_SEMANTICS": "The resulting hint_ticket units use the existing in-question hint flow later, one unit per hint use.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "GRANT_TARGET_UNITS; canonical storage destination pending SHOP-B",
        "ASSET_PATH": "/assets/shop/premium_hint_bundle.webp",
        "SHOP_CARD_COPY_ZH_TW": "購買預計獲得小提示卷 x5；作答時再逐張使用。",
        "SHOP_CARD_COPY_EN": "Intended result: 5 Hint Tickets, stored for use one hint at a time.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "double_streak_shield",
        "DISPLAY_NAME_ZH_TW": "雙層護盾",
        "DISPLAY_NAME_EN": "Double Streak Shield",
        "CATEGORY": "CONSUMABLE",
        "PRICE": 150,
        "PRICE_BAND": "MID",
        "STORE_OF_RECORD": "app.SHOP_ITEMS product definition; shop_inventory item quantity",
        "PURCHASE_SEMANTICS": "Grant and stack one item unit in shop_inventory. Purchase stores the shield; it does not protect answers until used.",
        "USE_SEMANTICS": "Existing activation flow consumes one stored double_streak_shield later and protects the next two wrong answers from breaking the combo.",
        "REPEAT_PURCHASE_ALLOWED": true,
        "OWNERSHIP_POLICY": "STACK_BY_ITEM_KEY",
        "ASSET_PATH": "/assets/shop/double_streak_shield.webp",
        "SHOP_CARD_COPY_ZH_TW": "存入雙層護盾；使用後接下來兩次答錯不中斷連擊。購買不會立即啟用。",
        "SHOP_CARD_COPY_EN": "Store a double shield; use it later to protect the next two wrong answers.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "robe_bamboo",
        "DISPLAY_NAME_ZH_TW": "竹林道袍",
        "DISPLAY_NAME_EN": "Bamboo Grove Robe",
        "CATEGORY": "COSMETIC",
        "PRICE": 450,
        "PRICE_BAND": "PREMIUM",
        "STORE_OF_RECORD": "SHOP-A launch contract; player_wardrobe.item_id ownership",
        "PURCHASE_SEMANTICS": "Purchase grants permanent ownership of robe_bamboo in player_wardrobe. It must not mutate player_appearance and must not auto-equip.",
        "USE_SEMANTICS": "After ownership, the existing appearance selection/equip flow may select the robe and update the outfit slot; purchase itself does not equip it.",
        "REPEAT_PURCHASE_ALLOWED": false,
        "OWNERSHIP_POLICY": "PERMANENT; REJECT_IF_OWNED; player_wardrobe.item_id; no auto-equip",
        "ASSET_PATH": "/assets/hero/items/robe_bamboo.svg",
        "SHOP_CARD_COPY_ZH_TW": "永久外觀：竹影掃棋，不動一子。購買後存入衣櫥，不會自動換裝。",
        "SHOP_CARD_COPY_EN": "Permanent cosmetic: Bamboo shadows sweep the board; not a stone is moved. Stored in your wardrobe, never auto-equipped.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "back_pack",
        "DISPLAY_NAME_ZH_TW": "棋具布包",
        "DISPLAY_NAME_EN": "Go Kit Pack",
        "CATEGORY": "COSMETIC",
        "PRICE": 220,
        "PRICE_BAND": "MID",
        "STORE_OF_RECORD": "SHOP-A launch contract; player_wardrobe.item_id ownership",
        "PURCHASE_SEMANTICS": "Purchase grants permanent ownership of back_pack in player_wardrobe. It must not mutate player_appearance and must not auto-equip.",
        "USE_SEMANTICS": "After ownership, the existing appearance selection/equip flow may select the pack and update the back slot; purchase itself does not equip it.",
        "REPEAT_PURCHASE_ALLOWED": false,
        "OWNERSHIP_POLICY": "PERMANENT; REJECT_IF_OWNED; player_wardrobe.item_id; no auto-equip",
        "ASSET_PATH": "/assets/hero/items/back_pack.svg",
        "SHOP_CARD_COPY_ZH_TW": "永久外觀：棋盤、棋石，皆在此中。購買後存入衣櫥，不會自動換裝。",
        "SHOP_CARD_COPY_EN": "Permanent cosmetic: A board and stones for every journey. Stored in your wardrobe, never auto-equipped.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "robe_student",
        "DISPLAY_NAME_ZH_TW": "學子短衫",
        "DISPLAY_NAME_EN": "Student Robe",
        "CATEGORY": "COSMETIC",
        "PRICE": 200,
        "PRICE_BAND": "MID",
        "STORE_OF_RECORD": "SHOP-A launch contract; player_wardrobe.item_id ownership",
        "PURCHASE_SEMANTICS": "Purchase grants permanent ownership of robe_student in player_wardrobe. It must not mutate player_appearance and must not auto-equip.",
        "USE_SEMANTICS": "After ownership, the existing appearance selection/equip flow may select the robe and update the outfit slot; purchase itself does not equip it.",
        "REPEAT_PURCHASE_ALLOWED": false,
        "OWNERSHIP_POLICY": "PERMANENT; REJECT_IF_OWNED; player_wardrobe.item_id; no auto-equip",
        "ASSET_PATH": "/assets/hero/items/robe_student.svg",
        "SHOP_CARD_COPY_ZH_TW": "永久外觀：求學之路，始於布衣。購買後存入衣櫥，不會自動換裝。",
        "SHOP_CARD_COPY_EN": "Permanent cosmetic: The road of learning begins in plain cloth. Stored in your wardrobe, never auto-equipped.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "acc_fan",
        "DISPLAY_NAME_ZH_TW": "折扇",
        "DISPLAY_NAME_EN": "Folding Fan",
        "CATEGORY": "COSMETIC",
        "PRICE": 480,
        "PRICE_BAND": "PREMIUM",
        "STORE_OF_RECORD": "SHOP-A launch contract; player_wardrobe.item_id ownership",
        "PURCHASE_SEMANTICS": "Purchase grants permanent ownership of acc_fan in player_wardrobe. It must not mutate player_appearance and must not auto-equip.",
        "USE_SEMANTICS": "After ownership, the existing appearance selection/equip flow may select the fan and update the accessory slot; purchase itself does not equip it.",
        "REPEAT_PURCHASE_ALLOWED": false,
        "OWNERSHIP_POLICY": "PERMANENT; REJECT_IF_OWNED; player_wardrobe.item_id; no auto-equip",
        "ASSET_PATH": "/assets/hero/items/acc_fan.svg",
        "SHOP_CARD_COPY_ZH_TW": "永久外觀：扇風落子，氣定神閒。購買後存入衣櫥，不會自動換裝。",
        "SHOP_CARD_COPY_EN": "Permanent cosmetic: A fan for calm, deliberate moves. Stored in your wardrobe, never auto-equipped.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "acc_jade_ring",
        "DISPLAY_NAME_ZH_TW": "翡翠扳指",
        "DISPLAY_NAME_EN": "Jade Thumb Ring",
        "CATEGORY": "COSMETIC",
        "PRICE": 750,
        "PRICE_BAND": "PREMIUM",
        "STORE_OF_RECORD": "SHOP-A launch contract; player_wardrobe.item_id ownership",
        "PURCHASE_SEMANTICS": "Purchase grants permanent ownership of acc_jade_ring in player_wardrobe. It must not mutate player_appearance and must not auto-equip.",
        "USE_SEMANTICS": "After ownership, the existing appearance selection/equip flow may select the ring and update the accessory slot; purchase itself does not equip it.",
        "REPEAT_PURCHASE_ALLOWED": false,
        "OWNERSHIP_POLICY": "PERMANENT; REJECT_IF_OWNED; player_wardrobe.item_id; no auto-equip",
        "ASSET_PATH": "/assets/hero/items/acc_jade_ring.svg",
        "SHOP_CARD_COPY_ZH_TW": "永久外觀：翡翠護指，落子有聲。購買後存入衣櫥，不會自動換裝。",
        "SHOP_CARD_COPY_EN": "Permanent cosmetic: Jade guards the hand that places every stone. Stored in your wardrobe, never auto-equipped.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      },
      {
        "SKU_ID": "hat_dragon_horn",
        "DISPLAY_NAME_ZH_TW": "龍角冠",
        "DISPLAY_NAME_EN": "Dragon Horn Crown",
        "CATEGORY": "COSMETIC",
        "PRICE": 950,
        "PRICE_BAND": "PREMIUM",
        "STORE_OF_RECORD": "SHOP-A launch contract; player_wardrobe.item_id ownership",
        "PURCHASE_SEMANTICS": "Purchase grants permanent ownership of hat_dragon_horn in player_wardrobe. It must not mutate player_appearance and must not auto-equip.",
        "USE_SEMANTICS": "After ownership, the existing appearance selection/equip flow may select the crown and update the hat slot; purchase itself does not equip it.",
        "REPEAT_PURCHASE_ALLOWED": false,
        "OWNERSHIP_POLICY": "PERMANENT; REJECT_IF_OWNED; player_wardrobe.item_id; no auto-equip",
        "ASSET_PATH": "/assets/hero/items/hat_dragon_horn.svg",
        "SHOP_CARD_COPY_ZH_TW": "永久外觀：龍角加冕，棋盤稱王。購買後存入衣櫥，不會自動換裝。",
        "SHOP_CARD_COPY_EN": "Permanent cosmetic: Crowned with dragon horns, ruler of the board. Stored in your wardrobe, never auto-equipped.",
        "AVAILABILITY": "R1_LAUNCH_DEFAULT"
      }
    ]
  }
}
```

## Product invariants for integration lanes

### Consumable purchase and use

The following six SKUs are explicitly stored or stacked at purchase and only
apply an effect on a later use or activation: `small_xp_potion`,
`streak_shield`, `extra_questions_small`, `extra_questions`, `xp_potion`, and
`double_streak_shield`. No implementation may convert their purchase into
immediate activation.

`hint_ticket` and `ai_explain_ticket` follow the same purchase-before-use
separation. The ticket is stored first; the existing question or analysis flow
consumes it later.

### Bundle result boundary

`premium_hint_bundle` has the intended product result of 5 `hint_ticket` units.
`pet_snack` has the intended product result of 3 Go Spirit Candies. These are
product results only in this SHOP-A contract. SHOP-A does not specify a new
table, column, write path, or storage adapter. SHOP-B must prove the exact
canonical grant destination before implementation is treated as complete.

### Cosmetic ownership boundary

All six cosmetics are permanent, have `REPEAT_PURCHASE_ALLOWED=false`, and use
`REJECT_IF_OWNED`. Purchase ownership is recorded against
`player_wardrobe.item_id`; purchase must not directly mutate
`player_appearance` or auto-equip. The existing appearance selection flow owns
the later equip action.

## Existing verified asset paths

The 16 SKUs use 15 unique existing assets because both training-pass SKUs
intentionally share `small_training_pass.webp`. The paths below were checked
against the exact source base and the canonical image-pack manifest.

| ASSET_PATH | USED_BY | BASE_FILE_EXISTS | MANIFEST_SHA256 |
| --- | --- | --- | --- |
| `/assets/shop/small_hint_scroll.webp` | `hint_ticket` | `YES` | `47e400835cbb8a0c1270411e8fb4eae981096a46cbbf6c0dc056a7609a34e5a3` |
| `/assets/shop/icon_ai_ticket.webp` | `ai_explain_ticket` | `YES` | `f2ad9bfdcef85c6a5f8ce561374dbb91b8b7f11a8f5c910d55dcc3a70cc51de8` |
| `/assets/shop/small_xp_potion.webp` | `small_xp_potion` | `YES` | `2b84f9ccb18a9af7efd8cc2fc1651afc2fd765a782262b0aa417ba166007684e` |
| `/assets/shop/icon_shield.webp` | `streak_shield` | `YES` | `2f6de1583029d1ecf3331c4ae2ce10f0f16348088011a8fe5b21d5e59442ada5` |
| `/assets/shop/pet_candy_pouch.webp` | `pet_snack` | `YES` | `6a0343da91eecc967f43155c3e308180e9455a74d7f8b749a5990305853a1f8c` |
| `/assets/shop/small_training_pass.webp` | `extra_questions_small`, `extra_questions` | `YES` | `07ad61b4c736e058ae5e51545342cb9e45d6736823345b1b3fcd1a5241ecbc70` |
| `/assets/shop/icon_xp_potion.webp` | `xp_potion` | `YES` | `6ecc5703919ad390ff268ea29140781867ce58ba4c935bca5835dec517e274e1` |
| `/assets/shop/premium_hint_bundle.webp` | `premium_hint_bundle` | `YES` | `f05b3aa04cb445683056d83f42d0a6dafa3941fd1d30f3a98a5c0abab434ffa9` |
| `/assets/shop/double_streak_shield.webp` | `double_streak_shield` | `YES` | `46bdaef1b7ca4652632c669336976314baa6b1c19778cb2e52e88569d8bfcb7f` |
| `/assets/hero/items/robe_bamboo.svg` | `robe_bamboo` | `YES` | `86a6f34307db1816a84556fda7c3dd9b088923c41aa3ca08f786d7c902cc2e5e` |
| `/assets/hero/items/back_pack.svg` | `back_pack` | `YES` | `b4c90cf1a4956da7d8f98cb0be5ee31ce35c755b9bac3a614747e5ab730cfc3a` |
| `/assets/hero/items/robe_student.svg` | `robe_student` | `YES` | `f6e7591017945ef880177d38b385b5e1ab9ed7eaf7ee106f6eed48ca34a7e2e6` |
| `/assets/hero/items/acc_fan.svg` | `acc_fan` | `YES` | `cd7be3fbb26224de98bc6c74ab6994fa54385491e155272803cbf55815630e34` |
| `/assets/hero/items/acc_jade_ring.svg` | `acc_jade_ring` | `YES` | `20ef512a7ee9c47359068665299fbde55301518782fd532fe8873129d3f9885b` |
| `/assets/hero/items/hat_dragon_horn.svg` | `hat_dragon_horn` | `YES` | `95cfd55c6f221df2b0112073e8e7daa391d85c57940aa338c7e93c535dbff761` |

`NEW_ART_REQUIRED_FOR_R1=NO`. No asset is redrawn, replaced, or introduced by
this contract.

## Source evidence and handoff rules

The locked prices, item names, descriptions, and intended item effects are
grounded in the exact-base `app.py` Shop item definitions (`app.py` lines
24304-24396). Existing Shop art bindings are recorded in
`rpg_item_registry.py` (`rpg_item_registry.py` lines 327-342), and the bundle
result definitions are recorded in its bundle registry (lines 252-276).
Cosmetic display names, ownership authority, and verified current art paths are
recorded in the exact-base appearance definitions and the Wave 2 cosmetic
inventory (`docs/planning/go_odyssey_wave2_cosmetic_inventory.json`). Asset
existence and hashes are backed by
`deploy/canonical-image-pack-manifest.json`.

These references are evidence for the product contract, not permission to edit
their owning runtime files. SHOP-B owns canonical grant-storage proof for the
two bundle products. SHOP-C owns coin/economy authority. SHOP-D owns inventory
mutation authority. SHOP-E owns any onboarding or eligibility authority.
SHOP-F owns app.py wiring. No downstream lane may invent alternate SKU IDs,
prices, names, categories, asset paths, or purchase/use semantics.

`PRODUCTION_MUTATION=NO`
`SHOP_REOPEN=NOT_AUTHORIZED`
`FEATURE_FLAG_CHANGE=NOT_AUTHORIZED`
`DB_MIGRATION=NOT_AUTHORIZED`
