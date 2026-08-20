# Go Odyssey RPG Visual Bible

## Item / Collection Section — Wave 2 Lane C Gate 1

Status: art direction and presentation foundation only. Final artwork is not
generated in this gate.

Canonical implementation data lives in rpg_item_registry.py. This document is
the review-facing visual and product contract; it does not create ownership,
price, drop, payment, or database authority.

## 1. Visual boundary

The non-equipment item taxonomy is:

| Taxonomy | Player surface | Current authority |
|---|---|---|
| ConsumableEffect | Inventory / Item Journal | shop_inventory or pet_inventory |
| Material | Inventory / Item Journal | Existing item store; future source remains server-side |
| QuestItem | Inventory / Item Journal | Contract only; no live dedicated quest item yet |
| TreasureBundle | Shop / Item Journal | Product grants components; bundle product is not necessarily owned |
| Collectible | Collections | badges_earned; Badge is not a Backpack item |

Functional Equipment remains Lane A / Backpack. Cosmetic Appearance remains the
existing player_wardrobe and Appearance Collection authority. Neither is
duplicated here.

## 2. Item art bible

All approved item art must use:

- 256×256 canvas.
- RGBA PNG or WebP with transparent background.
- One canonical art key and one production asset path.
- A silhouette readable at 32px on mobile.
- A single dominant object, two-value contrast, and no microtext.
- No emoji as final art.
- No _ph_* placeholder as production art.
- Chest art may communicate a curated bundle, but never implies chest ownership.

| Family | Visual rule |
|---|---|
| ConsumableEffect | Small usable object: wrapper, fruit, vial, candy, or tool; use cue is immediate. |
| Material | Stable raw component silhouette; stackable and sourceable. |
| QuestItem | Key, insignia, document, or seal; visibly not an ordinary consumable. |
| TreasureBundle | Container or curated package; contents are written in UI. |
| Collectible | Medallion, relic, or achievement seal; not a Backpack consumable. |

## 3. Formal art production pack — eight live items

No final art is included. These are production briefs.

### rare_appearance_fragment

- ITEM_ID: rare_appearance_fragment
- DISPLAY_NAME: 稀有外觀碎片 / Rare Appearance Fragment
- CATEGORY: Material
- CURRENT_OWNERSHIP: shop_inventory.item_key; resulting cosmetic remains player_wardrobe.item_id
- CURRENT_EFFECT: Consume one to unlock one missing common/uncommon appearance; no auto-equip
- CURRENT_SOURCE: Weekly Shop; collector_archive_crate; growth_vault
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.material.appearance-fragment
- ICON_CONCEPT: Faceted wardrobe-glass shard with a silhouette reflection
- SILHOUETTE: Asymmetric shard with a clothing notch
- PRIMARY_MATERIAL: Opalescent glass and paper seal
- WORLD_VISUAL_LANGUAGE: Go-stone geometry translated into wardrobe relic light
- MOBILE_READABILITY: Diagonal shard, two-value contrast, no text
- ART_PRIORITY: P0

### pet_evolution_core

- ITEM_ID: pet_evolution_core
- DISPLAY_NAME: 寵物進化素材 / Pet Evolution Core
- CATEGORY: Material
- CURRENT_OWNERSHIP: shop_inventory.item_key
- CURRENT_EFFECT: Pet XP +35 and existing evolution progress
- CURRENT_SOURCE: Weekly Shop; growth_vault
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.material.pet-evolution-core
- ICON_CONCEPT: Living seed wrapped around a Go stone
- SILHOUETTE: Round core with two leaf horns
- PRIMARY_MATERIAL: Jade seed, sap, woven cord
- WORLD_VISUAL_LANGUAGE: Botanical companion energy, never combat gear
- MOBILE_READABILITY: Circular core and leaves readable at 32px
- ART_PRIORITY: P0

### ai_analysis_pack

- ITEM_ID: ai_analysis_pack
- DISPLAY_NAME: AI 解析包 / AI Analysis Pack
- CATEGORY: TreasureBundle
- CURRENT_OWNERSHIP: Product is not persisted; grants ai_explain_ticket ×5
- CURRENT_EFFECT: Immediate grant; no persistent pack ownership
- CURRENT_SOURCE: Weekly Shop
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.bundle.ai-analysis-pack
- ICON_CONCEPT: Folded analysis folio with a glowing Go diagram
- SILHOUETTE: Horizontal folio with bookmark tab
- PRIMARY_MATERIAL: Ink paper, teal seal, amber lens
- WORLD_VISUAL_LANGUAGE: Scholar field notes; useful, not mystery loot
- MOBILE_READABILITY: Folio, seal, and one bright mark
- ART_PRIORITY: P1

### collector_archive_crate

- ITEM_ID: collector_archive_crate
- DISPLAY_NAME: 收藏典藏箱 / Collector Archive Crate
- CATEGORY: TreasureBundle
- CURRENT_OWNERSHIP: Product is not persisted; grants fragments ×4 and AI tickets ×8
- CURRENT_EFFECT: Immediate curated grant
- CURRENT_SOURCE: Monthly Shop
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.bundle.collector-archive-crate
- ICON_CONCEPT: Sealed archive crate with visible shard and folio corner
- SILHOUETTE: Low box, diagonal seal, inset window
- PRIMARY_MATERIAL: Cedar, brass, archive glass
- WORLD_VISUAL_LANGUAGE: Museum/archive treasure, not mystery loot
- MOBILE_READABILITY: Box, seal, inset shard
- ART_PRIORITY: P0

### growth_vault

- ITEM_ID: growth_vault
- DISPLAY_NAME: 成長寶庫 / Growth Vault
- CATEGORY: TreasureBundle
- CURRENT_OWNERSHIP: Product is not persisted; grants cores ×6 and fragments ×2
- CURRENT_EFFECT: Immediate curated grant
- CURRENT_SOURCE: Monthly Shop
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.bundle.growth-vault
- ICON_CONCEPT: Growth reliquary containing seed and wardrobe shard
- SILHOUETTE: Tall reliquary with split leaf-and-shard window
- PRIMARY_MATERIAL: Green lacquer, jade glass, travel leather
- WORLD_VISUAL_LANGUAGE: Planned supply vault, not combat upgrade
- MOBILE_READABILITY: Tall vessel and two-color symbol
- ART_PRIORITY: P1

### go_spirit_candy

- ITEM_ID: go_spirit_candy
- DISPLAY_NAME: 棋魂糖 / Go Spirit Candy
- CATEGORY: ConsumableEffect
- CURRENT_OWNERSHIP: pet_inventory.item_key
- CURRENT_EFFECT: Fullness +24, affection +4, pet XP +8
- CURRENT_SOURCE: Daily quests; companion grants; pet_snack; Gacha
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.consumable.go-spirit-candy
- ICON_CONCEPT: Black-and-white Go stone candy
- SILHOUETTE: Round candy with stone swirl
- PRIMARY_MATERIAL: Glazed sugar, rice paper, ink seal
- WORLD_VISUAL_LANGUAGE: Friendly companion provisioning with Go-stone heritage
- MOBILE_READABILITY: Round candy and two-tone wrapper
- ART_PRIORITY: P0

### starfruit

- ITEM_ID: starfruit
- DISPLAY_NAME: 星果 / Starfruit
- CATEGORY: ConsumableEffect
- CURRENT_OWNERSHIP: pet_inventory.item_key
- CURRENT_EFFECT: Fullness +38, affection +7, pet XP +15
- CURRENT_SOURCE: Daily completion; pet milestones; starfruit_basket; Gacha
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.consumable.starfruit
- ICON_CONCEPT: Five-point fruit with constellation cut
- SILHOUETTE: Star fruit with central seed window
- PRIMARY_MATERIAL: Golden skin, juice, indigo seed
- WORLD_VISUAL_LANGUAGE: Night-sky nourishment, not premium currency
- MOBILE_READABILITY: Five-point outline and center cut
- ART_PRIORITY: P0

### moon_drop

- ITEM_ID: moon_drop
- DISPLAY_NAME: 月露 / Moon Drop
- CATEGORY: ConsumableEffect
- CURRENT_OWNERSHIP: pet_inventory.item_key
- CURRENT_EFFECT: Fullness +18, affection +10, pet XP +25
- CURRENT_SOURCE: Friend challenge win/draw; moon_dew_vial; Gacha
- CURRENT_ART: Emoji fallback only; no canonical raster asset
- CANONICAL_ART_KEY: item.consumable.moon-drop
- ICON_CONCEPT: Blue dew drop with crescent reflection
- SILHOUETTE: Teardrop and crescent highlight
- PRIMARY_MATERIAL: Glass-like dew, moon silver, blue core
- WORLD_VISUAL_LANGUAGE: Quiet social reward, not currency
- MOBILE_READABILITY: Teardrop and crescent at 32px
- ART_PRIORITY: P0

## 4. Bundle polish pack

The product is a presentation wrapper. The grant is the owned result.

| PRODUCT_ID | GRANTS[] | DISPLAY_COPY |
|---|---|---|
| premium_hint_bundle | hint_ticket ×5 | 立即獲得：小提示卷 ×5 / Contains: Hint Ticket ×5 |
| ai_explain_ticket_bundle | ai_explain_ticket ×3 | 立即獲得：AI 解說券 ×3 / Contains: AI Analysis Ticket ×3 |
| pet_snack | go_spirit_candy ×3 | 立即獲得：棋魂糖 ×3 / Contains: Go Spirit Candy ×3 |
| starfruit_basket | starfruit ×3 | 立即獲得：星果 ×3 / Contains: Starfruit ×3 |
| moon_dew_vial | moon_drop ×3 | 立即獲得：月露 ×3 / Contains: Moon Drop ×3 |
| pet_feast_box | go_spirit_candy ×3, starfruit ×2, moon_drop ×1 | 立即獲得：棋魂糖 ×3、星果 ×2、月露 ×1 / Contains: Go Spirit Candy ×3, Starfruit ×2, Moon Drop ×1 |

Shop cards and purchase confirmation use 立即獲得 / Contains. They do not
imply persistent ownership of the bundle itself.

## 5. Item Journal UX

/item-journal is a read-only projection from /api/item-journal.

Required card fields:

- category filter: Consumables, Materials, Quest, Treasure;
- icon or honest ART SPEC state while art is pending;
- display name and stable item_id;
- owned amount;
- description;
- effect/use;
- source tags;
- where to get more;
- discovered state;
- recently-obtained hint where existing logs provide a timestamp.

Mutation boundary:

    ownership_mutation=0
    purchase_mutation=0
    equip_mutation=0
    journal_write=0

Equipment links to /inventory. Cosmetic rewards link to /hero?tab=appearance.
Badges link to /badges and remain outside the Backpack item list.

## 6. Badge Visual System v1

There are 84 static badges. They use family frames plus tier/symbol treatment,
not 84 unrelated icons. Final art is not generated in this gate.

| Family | FRAME_LANGUAGE | CENTRAL_SYMBOL_LANGUAGE | TIER_TREATMENT | NUMBER_TREATMENT | COLOR_ROLE | MOBILE_READABILITY |
|---|---|---|---|---|---|---|
| Streak | Open ember ring | Flame, linked stones, wind streak | Ember → lightning → storm → comet | Compact threshold | Orange → electric violet | One flame/ring silhouette |
| Correct Answers | Leaf-and-seal frame | Go stone + checkmark / growing tree | Seed → sprout → tree → constellation | Threshold in seal band | Jade/teal, gold mastery | Large check/stone pair |
| Combo | Braided lightning loop | Interlocking stones / bolt | Layered braid and radiance | Centered numeral | Amber/cobalt | One diagonal bolt |
| Mistake Correction | Repaired ink seal | Brush stroke becoming checkmark | Single repair → master seal | Threshold on repair tab | Indigo/teal with restrained red | Before/after stroke |
| Daily | Calendar plaque and sunrise rim | Sun, date mark, repeating moon | Accumulating rim marks | Large day counter | Dawn amber → night blue | Calendar plus one sun |
| Rank | Gate / mountain pass | Stone gate, path marker, summit star | Carved kyu → metal/crystal dan | Rank text primary | Teal kyu, amber/violet dan | Rank text reads alone |
| XP | Growing crystal capsule | Light seed / energy crystal | Facet → constellation | Compact threshold | Cyan → violet | One crystal and bright center |
| Friend Challenge | Two-sided duel medallion | Crossed stones / linked paths | Meeting → rivalry → champion | Win count on ribbon | Balanced blue/red | Two opposing shapes |
| Premium | Faceted jewel frame | Diamond, crown, founder seal | Both legendary; geometry differs | Member/founder ribbon | Violet/champagne gold | One jewel plus seal |
| Community | Leaderboard podium plaque | Medal, podium, laurel | Placement is tier | Placement numeral central | Gold plus community blue | Medal plus large number |

Prototype selection:

streak_3, streak_100, total_10, total_5000, combo_3, combo_50,
mistake_1, mistake_100, daily_first, daily_365, rank_19k, rank_3d,
xp_100, xp_25000, challenge_win_1, challenge_win_30,
premium_member, premium_founder, badge_lb_weekly_1.

## 7. Zone Material Design Contract

Previous candidate material names are not canonized by this gate. A future Zone
Material must provide:

    ITEM_ID
    DISPLAY_NAME
    ZONE_ID
    MONSTER_FAMILY
    RARITY_IF_NEEDED
    SOURCE_TYPE
    QUEST_ROLE
    COLLECTION_ROLE
    SHOP_ALLOWED
    COMBAT_POWER
    ASSET_KEY

Rules:

- COMBAT_POWER=NONE.
- SHOP_ALLOWED=NO by default until explicitly approved.
- Acquisition is server-authoritative.
- Use canonical monster family/source tags, not unstable display aliases.
- Do not imply a recipe, salvage, or large crafting system.
- Initial uses should be quest turn-in or collection set completion.

## 8. Shop Product → Grant registry

All 21 current Shop products are represented by
SHOP_PRODUCT_GRANT_REGISTRY_21 in rpg_item_registry.py.

| PRODUCT_ID | GRANT_TYPE | GRANTED_IDS | PERSISTENT_PRODUCT_OWNERSHIP | PRICE_AUTHORITY | SHOP_CADENCE | CURRENT_ASSET / ART_STATUS |
|---|---|---|---|---|---|---|
| hint_ticket | ITEM | hint_ticket ×1 | YES | Server SHOP_ITEMS.price | Daily; Gacha yes | small_hint_scroll.webp / dedicated |
| premium_hint_bundle | BUNDLE | hint_ticket ×5 | NO | Server | Daily; Gacha yes | premium_hint_bundle.webp / dedicated |
| ai_explain_ticket | ITEM | ai_explain_ticket ×1 | YES | Server | Daily; Gacha yes | icon_ai_ticket.webp / dedicated |
| ai_explain_ticket_bundle | BUNDLE | ai_explain_ticket ×3 | NO | Server | Daily; Gacha yes | ai_explain_ticket_bundle.webp / dedicated |
| extra_questions_small | ITEM | extra_questions_small ×1 | YES | Server | Daily; Gacha yes | small_training_pass.webp / dedicated |
| extra_questions | ITEM | extra_questions ×1 | YES | Server | Daily; Gacha yes | shared small_training_pass.webp |
| grand_training_pass | ITEM | grand_training_pass ×1 | YES | Server | Daily; Gacha yes | grand_training_pass.webp / dedicated |
| small_xp_potion | ITEM | small_xp_potion ×1 | YES | Server | Daily; Gacha yes | small_xp_potion.webp / dedicated |
| xp_potion | ITEM | xp_potion ×1 | YES | Server | Daily; Gacha yes | icon_xp_potion.webp / dedicated |
| grand_xp_potion | ITEM | grand_xp_potion ×1 | YES | Server | Daily; Gacha yes | grand_xp_potion.webp / dedicated |
| streak_shield | ITEM | streak_shield ×1 | YES | Server | Daily; Gacha yes | icon_shield.webp / dedicated |
| double_streak_shield | ITEM | double_streak_shield ×1 | YES | Server | Daily; Gacha yes | double_streak_shield.webp / dedicated |
| pet_snack | BUNDLE | go_spirit_candy ×3 | NO | Server | Daily; Gacha yes | pet_candy_pouch.webp / dedicated |
| starfruit_basket | BUNDLE | starfruit ×3 | NO | Server | Daily; Gacha yes | star_fruit_basket.webp / dedicated |
| moon_dew_vial | BUNDLE | moon_drop ×3 | NO | Server | Daily; Gacha yes | moon_dew_vial.webp / dedicated |
| pet_feast_box | BUNDLE | candy ×3, starfruit ×2, moon drop ×1 | NO | Server | Daily; Gacha yes | pet_feast_box.webp / dedicated |
| rare_appearance_fragment | ITEM | rare_appearance_fragment ×1 | YES | Server | Weekly; Gacha no | no asset / art spec |
| pet_evolution_core | ITEM | pet_evolution_core ×1 | YES | Server | Weekly; Gacha no | no asset / art spec |
| ai_analysis_pack | BUNDLE | ai_explain_ticket ×5 | NO | Server | Weekly; Gacha no | no asset / art spec |
| collector_archive_crate | BUNDLE | fragment ×4, AI ticket ×8 | NO | Server | Monthly; Gacha no | no asset / art spec |
| growth_vault | BUNDLE | core ×6, fragment ×2 | NO | Server | Monthly; Gacha no | no asset / art spec |

No price is copied into the registry as a second authority. Prices remain in
SHOP_ITEMS and server-side daily rotation logic.

## 9. Cross-domain fragment contract

rare_appearance_fragment:

    Item ownership / quantity:
        shop_inventory.item_key

    Consumption intent:
        server-side /api/shop/use item intent

    Resulting appearance ownership:
        existing player_wardrobe.item_id authority

    Second cosmetic ownership table:
        NO

The Item Journal explains and links to Appearance Collection after unlock, but
does not own or equip the resulting appearance.

## 10. Non-equipment drop interface

This gate defines the interface only; it does not implement monster drops:

    server settlement
        → drop result
        → item_id
        → quantity
        → source tag
        → journal discovery
        → inventory projection

Client input has no drop authority. Lane B continues to own equipment loot
presentation and settlement. No drop rate or battle reward is changed here.

## 11. Authority locks

    COIN_SPEND_AUTHORITY=existing server-side atomic _spend_coins
    DROP_AUTHORITY=existing server-side settlement; client presentation only
    PAYMENT_AUTHORITY=existing server payment/subscription entitlement
    PRICE_CHANGED=NO
    DROP_RATE_CHANGED=NO
    PAYMENT_CHANGED=NO
    DB_MIGRATION=NO
