# GO ODYSSEY RPG VISUAL BIBLE

Canonical authority: `docs/planning/GO_ODYSSEY_RPG_VISUAL_BIBLE.md`

This single document combines the Wave 2 character/body-frame contract with the Item, Badge, and
Bundle presentation contract. Repository-root copies are non-canonical and must not be maintained.

## Character System Section v1

Status: PROPOSAL_FOR_OWNER_GATE1
Scope: Wave 2 Lane A character production foundation
Base: origin/master a82b0d99e0b413d9cd55dac4e86ef5c5140351e6

This section establishes the shared character-art contract for player appearances and world
characters. It is a specification only. It does not change runtime assets, renderers, APIs, combat,
ownership, Premium, database schema, or Production.

## 1. Precedence and relationship to existing bibles

1. The E10 Newbie Village Art Direction Bible remains authoritative for Zone 1-specific Hero,
   Village Elder, Water Spirit Horse, village, and scene decisions.
2. Any separately approved E10 cross-zone visual identity document remains authoritative for shared
   cross-zone Go visual language and energy behavior.
3. This section owns the Wave 2 character production contract: player appearance identity, world NPC
   identity, base-art export, character anchors, and collection presentation.
4. The screenplay owns story canon. A production concept cannot rewrite a story role.
5. Lane B owns functional equipment and Backpack. Lane C owns item, collection, and shop economy
   presentation. Character artwork cannot cross those authority boundaries.

## 2. Character categories

The following categories are separate:

| Category | Meaning | Selectable by player | Gameplay authority |
|---|---|---:|---|
| PLAYER_CHARACTER_APPEARANCE | Player-selected body, face, hair, and base visual identity | Yes | None |
| WORLD_CHARACTER_NPC | Elder, messenger, guide, merchant, companion, or Zone story character | No | Story/presentation only |
| MONSTER_ENEMY | Battlefield enemy or boss encounter entity | No | Server encounter authority, never character collection authority |
| OUTFIT_COSMETIC | Visual layer worn by a player appearance | No, equipped visually | No attack/defense authority |
| FUNCTIONAL_EQUIPMENT | Weapon, armor, accessory, or other gameplay item | Equipped separately | Server-owned functional authority |

Names such as Warrior, Mage, Knight, and Sage are collection families or visual roles. They are
not combat classes unless a future product decision explicitly authorizes a separate class system.

## 3. Master canvas and export contract

~~~
MASTER_CANVAS=1056x1408
SOURCE_FORMAT=PNG master
RUNTIME_FORMAT=WebP
COLOR_MODE=RGBA
ALPHA_POLICY=true alpha; no chroma-key matte
~~~

- The visible body uses a shared target frame of x=.20–.80 and y=.02–.98.
- The visible foot contact is aligned to y=.975; a soft shadow may extend to y=.99.
- Transparent pixels must use neutral RGB values. Green-key RGB residue is rejected even when alpha
  is zero.
- Runtime WebP is derived from the accepted PNG master. No hand-edited runtime-only variant becomes
  the source of truth.
- Profile/card derivatives are generated from the accepted master and retain the same identity key.

## 4. Camera, pose, and body system

- Camera: frontal or near-frontal, eye-level, orthographic-feeling, with no perspective stretch.
- Default pose: stable standing pose with relaxed/open hands and clear feet.
- Base body: full-body image, consistent baseline, readable shoulder and head placement.
- Allowed variation: age, body width, height impression, skin tone, hair, and facial expression may
  vary intentionally, but not through accidental crop or scale drift.
- The artist must record any intentional silhouette exception, especially for older bodies, broader
  guardian silhouettes, or flowing robe shapes.

~~~
PLAYER_FRAME_A_STANDARD_CHIBI=apprentice,mage,paladin,trail_apprentice,night_runner,constellation_apprentice
WEARABLE_PROTOTYPE_READY=YES
UNIVERSAL_WEARABLE_FIT_PROVEN=NO
~~~

The six P1 player bodies share normalized frame and anchor geometry suitable for a future wearable
prototype. This is not proof that every present or future character can accept universal wearable
armor, and this Gate 2 integration does not implement wearable armor.

## 5. Face grid

- Use a shared eye, brow, nose, mouth, ear, and chin alignment guide.
- Face scale may vary for age and body identity, but eye placement and expression direction must
  remain readable at card size.
- Avoid oversized generic anime eyes, photorealistic pores, and tiny facial detail that disappears
  on mobile.
- Preserve the existing ten characters' identities during polish. A face-grid correction is not a
  license to replace a character.

## 6. Outline, shading, and lighting

### Outline

- Use a consistent dark blue-brown outline family rather than pure black.
- The contour should remain readable on both light and dark UI surfaces.
- Avoid green, white, or saturated colored edge halos.

### Shading

- Use a shared three-value cel/soft-render structure: base, controlled shadow, restrained highlight.
- Large material planes are preferred over many sub-pixel folds.
- Hair, robe, armor, skin, and cloth should remain distinguishable at mobile card size.

### Lighting

- Default key light is soft upper-left with a restrained fill.
- Face readability takes priority over costume sparkle.
- Gold, white, and magical highlights are accents, not full-image bloom.
- The Go Odyssey world can use warm village light, cool forest light, or zone-specific ambience, but
  the character's face and silhouette must remain in the common lighting family.

## 7. Palette logic

The palette is role-coded but not power-coded:

- Beginner: teal, off-white, clay beige, leather brown, muted brass.
- Warrior: slate, blue, rust, charcoal, leather brown.
- Knight/Guardian: blue-charcoal, stone grey, ivory, restrained gold.
- Ranger: forest green, bark brown, mist violet, ivory.
- Rogue: charcoal, muted violet/teal, warm grey.
- Mage: deep navy, lavender, ivory, muted brass.
- Scholar/Sage: umber, slate, parchment ivory, muted teal.

Color must not imply attack strength, defense strength, rarity, Premium entitlement, or item
ownership.

## 8. Mobile and card safe area

- Keep the face, torso, primary silhouette cue, and feet inside the default card safe area.
- Use at least 10% outer margin on the master unless a recorded silhouette exception is approved.
- At approximately 72–96px card height, the character must remain identifiable by silhouette and one
  primary palette block.
- Do not rely on tiny text, tiny weapons, tiny jewelry, or micro-patterns to identify a character.
- Selected and locked state belong to the UI layer, not inside the artwork.

## 9. Base art and visual layer contract

The canonical visual stack is:

~~~
Base Character
  → Outfit Cosmetic
  → Functional Equipment projection if supported
  → Cosmetic Style Gear
  → Aura / FX
~~~

### Base Character

Contains body, face, hair, hands, base clothing, and identity silhouette. Preferred policy is
empty/open hands. No authoritative functional weapon, armor, accessory, stat, or combat effect is
embedded in the base artwork.

### Outfit Cosmetic

Changes appearance only. Outfit art may be layered over a compatible base character and must declare
its frame/anchor compatibility. It does not grant attack or defense.

### Functional Equipment projection

May show the visual projection of an owned/equipped functional item. Its identity and effect come
from the server-owned functional equipment path, not from pixels or client-submitted display data.

### Cosmetic Style Gear

Includes visual hats, capes, accessories, pets, and other style layers. Visual presence is not
ownership or gameplay authority.

### Aura / FX

Presentation-only effects. They must not look like hidden weapon damage, defense, XP, loot, coin, or
Premium mechanics.

## 10. Weapon and prop policy

- Functional weapons are separate from player-character base art.
- Empty/open hands are the default.
- A decorative prop may appear only when it is clearly non-authoritative, documented in the asset
  record, and approved as a visual prop.
- A decorative sword, staff, shield, or book must never silently map to player_inventory.
- A functional-equipment projection must use a separate item identity and a compatible anchor.

## 11. Player character art direction

The current ten remain:

~~~
apprentice
apprentice_girl
swordsman
rogue
ranger
berserker
guardian
paladin
mage
sage
~~~

Their concepts are preserved and polished, not replaced. The first expansion adds ten candidate
identities:

~~~
trail_apprentice
river_wayfinder
stone_caretaker
duelist_scout
bastion_warden
forest_pathfinder
night_runner
constellation_apprentice
archive_scholar
worldkeeper
~~~

These IDs are candidates pending Owner display-name approval. None is a combat class.

## 12. NPC, companion, and monster relationship

### World NPCs

NPCs share the same world materials, lighting discipline, alpha cleanliness, and line-family logic,
but may use more age, body, pose, and personality variation than the player roster. They are not
registered as player character appearances.

### Water Spirit Horse

Water Spirit Horse / 小水 remains a story companion and pet-system entity, not a player body
appearance, mount, weapon, or combat class. Its canonical identity is governed by the existing
Newbie Village bible.

### Monsters and enemy bosses

Monsters may use stronger scale, motion, asymmetry, gloss, or environmental effects. They remain in
the monster/enemy asset namespace and are excluded from the character collection. A boss portrait
must not become an NPC registry entry merely because it is a humanoid or story-relevant encounter.

## 13. Shared character anchors

All coordinates are normalized to the master canvas unless marked body-relative:

| Anchor | Contract |
|---|---|
| BODY_FRAME | x=.20–.80, y=.02–.98 target visible body box |
| FOOT_BASELINE | y=.975 visible contact; shadow may reach y=.99 |
| HAND_ANCHOR | primary body-relative point x=.82,y=.58; secondary x=.18,y=.58; safe boxes ±.12 x and ±.15 y |
| HEAD_ANCHOR | center x=.50,y=.16; safe box x=.28–.72,y=.02–.32 |
| BACK_ANCHOR | behind-body safe box x=.05–.95,y=.20–.86 |
| ACCESSORY_ANCHOR | chest/waist center x=.50,y=.55; safe box x=.36–.64,y=.40–.68 |
| AURA_SAFE_AREA | x=.04–.96,y=.02–.98, with face and labels clear |

The anchors are a shared production contract. Adopting them in runtime is a separate Lane B/C
implementation decision.

## 14. Collection presentation

The future Hero → 外觀 → 角色造型 surface is a Character Collection:

- show 10 / 20 progress;
- show large preview, selected state, locked state, unlock requirement, family, short lore, Zone,
  and acquisition source;
- provide All, Beginner, Warrior, Knight, Ranger, Rogue, Mage, and Scholar filters;
- provide desktop two-panel and mobile single-preview/two-column-card layouts;
- never show Attack, Defense, Power, class stats, equipment effects, or functional weapon claims;
- do not add rarity at Gate 1 because family and acquisition information better serve a non-power
  appearance collection.

## 15. Acceptance gates

Every accepted character asset must pass:

1. identity continuity;
2. canvas, alpha, and transparent-pixel checks;
3. shared body and footline checks;
4. face, outline, lighting, and palette checks;
5. desktop, tablet, and mobile crop checks;
6. empty/open-hands and no-authoritative-weapon check;
7. player/NPC/monster category check;
8. Owner approval before runtime connection.

~~~
CHARACTER_COMBAT_AUTHORITY=NO
FUNCTIONAL_WEAPON_BAKED_IN_BASE_ART=NO
OUTFIT_COMBAT_AUTHORITY=NO
MONSTER_AS_PLAYER_APPEARANCE=NO
~~~

---

## Item / Collection Section — Wave 2 Lane C Gate 2 P1

Status: first vertical slice with eight dedicated live-item assets, six bundle
presentation mappings, a read-only Item Journal, and ten badge family
prototypes. Future Zone Materials remain contract-only.

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

Functional Equipment remains Lane B / Backpack. Cosmetic Appearance remains the
existing player_wardrobe and Appearance Collection authority. Neither is
duplicated here.

## 2. Item art bible

All approved item art must use:

- 256×256 canvas.
- Transparent SVG vector with a 256×256 render target, or RGBA PNG/WebP.
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

The following eight identities now have dedicated canonical SVG assets. The
brief fields remain the source-of-truth for art review; the asset paths are
the integrated P1 presentation assets.

| ITEM_ID | CANONICAL_ART_KEY | ASSET_PATH | ART_STATUS |
|---|---|---|---|
| rare_appearance_fragment | item.material.appearance-fragment | /assets/items/rare_appearance_fragment.svg | dedicated transparent SVG |
| pet_evolution_core | item.material.pet-evolution-core | /assets/items/pet_evolution_core.svg | dedicated transparent SVG |
| ai_analysis_pack | item.bundle.ai-analysis-pack | /assets/items/ai_analysis_pack.svg | dedicated transparent SVG |
| collector_archive_crate | item.bundle.collector-archive-crate | /assets/items/collector_archive_crate.svg | dedicated transparent SVG |
| growth_vault | item.bundle.growth-vault | /assets/items/growth_vault.svg | dedicated transparent SVG |
| go_spirit_candy | item.consumable.go-spirit-candy | /assets/items/go_spirit_candy.svg | dedicated transparent SVG |
| starfruit | item.consumable.starfruit | /assets/items/starfruit.svg | dedicated transparent SVG |
| moon_drop | item.consumable.moon-drop | /assets/items/moon_drop.svg | dedicated transparent SVG |

### rare_appearance_fragment

- ITEM_ID: rare_appearance_fragment
- DISPLAY_NAME: 稀有外觀碎片 / Rare Appearance Fragment
- CATEGORY: Material
- CURRENT_OWNERSHIP: shop_inventory.item_key; resulting cosmetic remains player_wardrobe.item_id
- CURRENT_EFFECT: Consume one to unlock one missing common/uncommon appearance; no auto-equip
- CURRENT_SOURCE: Weekly Shop; collector_archive_crate; growth_vault
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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
- CURRENT_ART: Dedicated transparent 256×256 SVG asset
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

- category filter: Consumables, Materials, Quest, Treasure, Collectibles;
- canonical icon; honest ART SPEC is retained only for future entries whose art is pending;
- display name and stable item_id;
- owned amount;
- description;
- effect/use;
- source tags;
- where to get more;
- catalog-visible definition state;
- owned state and amount from the authoritative item store;
- recently-obtained hint where existing logs provide a timestamp.

P1 does not expose or persist player discovery history. Catalog visibility is
metadata truth only; `discovery_semantics=NOT_TRACKED`.

Mutation boundary:

    ownership_mutation=0
    purchase_mutation=0
    equip_mutation=0
    journal_write=0

Equipment links to /inventory. Cosmetic rewards link to /hero?tab=appearance.
Badges link to /badges and remain outside the Backpack item list.

## 6. Badge Visual System v1

There are 84 static badges. They use family frames plus tier/symbol treatment,
not 84 unrelated icons. This P1 produces exactly one representative art
prototype per family; the remaining badge IDs keep their existing metadata and
legacy presentation until a later art gate.

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

Prototype selection (exactly 10, one per family):

| FAMILY | BADGE_ID | PROTOTYPE_ASSET |
|---|---|---|
| Streak | streak_3 | /assets/badges/prototypes/streak.svg |
| Correct Answers | total_10 | /assets/badges/prototypes/correct-answers.svg |
| Combo | combo_3 | /assets/badges/prototypes/combo.svg |
| Mistake Correction | mistake_1 | /assets/badges/prototypes/mistake-correction.svg |
| Daily | daily_first | /assets/badges/prototypes/daily.svg |
| Rank | rank_19k | /assets/badges/prototypes/rank.svg |
| XP | xp_100 | /assets/badges/prototypes/xp.svg |
| Friend Challenge | challenge_win_1 | /assets/badges/prototypes/friend-challenge.svg |
| Premium | premium_member | /assets/badges/prototypes/premium.svg |
| Community | badge_lb_weekly_1 | /assets/badges/prototypes/community.svg |

The Community badge definition remains unawarded unless the existing
server-side award behavior is later authorized; this prototype does not
activate it.

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
| rare_appearance_fragment | ITEM | rare_appearance_fragment ×1 | YES | Server | Weekly; Gacha no | rare_appearance_fragment.svg / dedicated |
| pet_evolution_core | ITEM | pet_evolution_core ×1 | YES | Server | Weekly; Gacha no | pet_evolution_core.svg / dedicated |
| ai_analysis_pack | BUNDLE | ai_explain_ticket ×5 | NO | Server | Weekly; Gacha no | ai_analysis_pack.svg / dedicated |
| collector_archive_crate | BUNDLE | fragment ×4, AI ticket ×8 | NO | Server | Monthly; Gacha no | collector_archive_crate.svg / dedicated |
| growth_vault | BUNDLE | core ×6, fragment ×2 | NO | Server | Monthly; Gacha no | growth_vault.svg / dedicated |

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

    PLAYER_APPEARANCE_AUTHORITY=player_appearance.character_key
    FUNCTIONAL_EQUIPMENT_OWNERSHIP=player_inventory
    FUNCTIONAL_EQUIPMENT_EQUIPPED=player_inventory.equipped
    FUNCTIONAL_EFFECT_AUTHORITY=server EQUIPMENT_DEFS
    ITEM_JOURNAL=projection only
    SHOP_PURCHASE_AUTHORITY=existing purchase settlement only
    COIN_SPEND_AUTHORITY=existing server-side atomic _spend_coins
    DROP_AUTHORITY=existing server-side settlement; client presentation only
    BADGE_EARNING_AUTHORITY=existing badge earning authority
    PAYMENT_AUTHORITY=existing server payment/subscription entitlement
    CLIENT_COMBAT_AUTHORITY=NO
    PRICE_CHANGED=NO
    DROP_RATE_CHANGED=NO
    PAYMENT_CHANGED=NO
    DB_MIGRATION=NO
