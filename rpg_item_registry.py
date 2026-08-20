"""Wave 2 Lane C non-equipment item presentation registry.

This module is deliberately descriptive.  It owns no balances, grants no
items, and does not write to a database.  Runtime ownership remains in the
existing domain stores:

* ``shop_inventory`` for Shop item quantities;
* ``pet_inventory`` for companion food quantities;
* ``badges_earned`` for badges;
* ``player_wardrobe`` for cosmetics (outside this registry's ownership).

The registry makes the product-to-grant relationship and the visual contract
explicit without moving Coins, payment, drop, equipment, or cosmetic
authority into Lane C's item presentation surface.
"""

from copy import deepcopy


ITEM_REGISTRY_VERSION = "rpg-wave2-item-registry-v1"

ITEM_TAXONOMY = (
    "ConsumableEffect",
    "Material",
    "QuestItem",
    "TreasureBundle",
    "Collectible",
)

ITEM_REGISTRY_V1 = {
    "version": ITEM_REGISTRY_VERSION,
    "taxonomy": ITEM_TAXONOMY,
    "ownership_model": "runtime projection over existing domain stores; no new ownership table",
    "final_art_generated": False,
}

JOURNAL_SECTIONS = (
    {"key": "ConsumableEffect", "label": "消耗品", "label_en": "Consumables"},
    {"key": "Material", "label": "素材", "label_en": "Materials"},
    {"key": "QuestItem", "label": "任務", "label_en": "Quest"},
    {"key": "TreasureBundle", "label": "寶物", "label_en": "Treasure"},
)

COLLECTION_SECTIONS = (
    {"key": "RelicsZone", "label": "遺物／區域", "label_en": "Relics / Zone"},
    {"key": "AchievementsBadges", "label": "成就／徽章", "label_en": "Achievements / Badges"},
)


# The first eight items have no final raster art yet.  These are production
# art briefs only; ``asset_path`` intentionally remains None until approved
# artwork is delivered.
LIVE_ITEM_ART_PACK_8 = {
    "rare_appearance_fragment": {
        "item_id": "rare_appearance_fragment",
        "name": "稀有外觀碎片",
        "name_en": "Rare Appearance Fragment",
        "category": "Material",
        "current_ownership": "shop_inventory.item_key quantity; resulting cosmetic remains player_wardrobe.item_id",
        "current_effect": "Consume one to unlock one missing common/uncommon appearance; no auto-equip",
        "current_source": "Weekly Shop; collector_archive_crate; growth_vault",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.material.appearance-fragment",
        "icon_concept": "A faceted shard of wardrobe glass with a small silhouette reflection",
        "silhouette": "Asymmetric crystal shard with one readable clothing notch",
        "primary_material": "Opalescent glass over warm paper seal",
        "world_visual_language": "Go stones translated into wardrobe relic geometry; teal and violet light",
        "mobile_readability": "One large diagonal shard, two-value contrast, no microtext",
        "art_priority": "P0",
        "stackable": True,
        "source_tags": ["Shop:weekly", "Bundle:collector_archive_crate", "Bundle:growth_vault"],
        "where_to_get_more": ["Weekly Shop", "Collector Archive Crate", "Growth Vault"],
        "effect_use": "Appearance unlock intent is server-side; resulting cosmetic uses existing Cosmetic authority",
    },
    "pet_evolution_core": {
        "item_id": "pet_evolution_core",
        "name": "寵物進化素材",
        "name_en": "Pet Evolution Core",
        "category": "Material",
        "current_ownership": "shop_inventory.item_key quantity",
        "current_effect": "Consume one for pet XP +35 and existing evolution progress",
        "current_source": "Weekly Shop; growth_vault",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.material.pet-evolution-core",
        "icon_concept": "A living seed wrapped around a small Go stone",
        "silhouette": "Round seed nucleus with two upward leaf horns",
        "primary_material": "Jade seed, translucent sap, woven cord",
        "world_visual_language": "Companion growth expressed as botanical spirit energy, not combat gear",
        "mobile_readability": "Circular core and two leaves remain legible at 32px",
        "art_priority": "P0",
        "stackable": True,
        "source_tags": ["Shop:weekly", "Bundle:growth_vault"],
        "where_to_get_more": ["Weekly Shop", "Growth Vault"],
        "effect_use": "Pet-growth intent is server-side and remains outside combat power",
    },
    "ai_analysis_pack": {
        "item_id": "ai_analysis_pack",
        "name": "AI 解析包",
        "name_en": "AI Analysis Pack",
        "category": "TreasureBundle",
        "current_ownership": "Product is not persisted; grants ai_explain_ticket x5 into shop_inventory",
        "current_effect": "Immediate grant of five AI analysis tickets; no persistent pack ownership",
        "current_source": "Weekly Shop",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.bundle.ai-analysis-pack",
        "icon_concept": "A folded analysis folio with one glowing eye-shaped Go diagram",
        "silhouette": "Horizontal folio with a visible bookmark tab",
        "primary_material": "Ink-black paper, teal seal, small amber lens",
        "world_visual_language": "Scholar's field notes; intelligent and useful, never magical loot-box mystery",
        "mobile_readability": "Folio rectangle plus one bright seal; no tiny board lines",
        "art_priority": "P1",
        "stackable": False,
        "source_tags": ["Shop:weekly"],
        "where_to_get_more": ["Weekly Shop"],
        "effect_use": "Show Contains: AI Analysis Ticket ×5, then navigate to Backpack",
    },
    "collector_archive_crate": {
        "item_id": "collector_archive_crate",
        "name": "收藏典藏箱",
        "name_en": "Collector Archive Crate",
        "category": "TreasureBundle",
        "current_ownership": "Product is not persisted; grants fragments x4 and AI tickets x8",
        "current_effect": "Immediate grant of four appearance fragments and eight AI analysis tickets",
        "current_source": "Monthly Shop",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.bundle.collector-archive-crate",
        "icon_concept": "A sealed archive crate with a visible shard and folio corner",
        "silhouette": "Low wooden archive box, diagonal seal band, one inset window",
        "primary_material": "Dark cedar, brass corners, violet archive glass",
        "world_visual_language": "Museum/archive treasure; contents are explicit, not random mystery",
        "mobile_readability": "Box, seal, and one inset shard survive thumbnail size",
        "art_priority": "P0",
        "stackable": False,
        "source_tags": ["Shop:monthly"],
        "where_to_get_more": ["Monthly Shop"],
        "effect_use": "Show Contains: Appearance Fragment ×4; AI Analysis Ticket ×8",
    },
    "growth_vault": {
        "item_id": "growth_vault",
        "name": "成長寶庫",
        "name_en": "Growth Vault",
        "category": "TreasureBundle",
        "current_ownership": "Product is not persisted; grants pet cores x6 and fragments x2",
        "current_effect": "Immediate grant of six pet evolution cores and two appearance fragments",
        "current_source": "Monthly Shop",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.bundle.growth-vault",
        "icon_concept": "A compact growth reliquary containing a seed and wardrobe shard",
        "silhouette": "Tall reliquary with split leaf-and-shard window",
        "primary_material": "Green lacquer, jade glass, stitched travel leather",
        "world_visual_language": "A planned supply vault, not a combat upgrade chest",
        "mobile_readability": "Tall vessel with one two-color symbol and strong top cap",
        "art_priority": "P1",
        "stackable": False,
        "source_tags": ["Shop:monthly"],
        "where_to_get_more": ["Monthly Shop"],
        "effect_use": "Show Contains: Pet Evolution Core ×6; Appearance Fragment ×2",
    },
    "go_spirit_candy": {
        "item_id": "go_spirit_candy",
        "name": "棋魂糖",
        "name_en": "Go Spirit Candy",
        "category": "ConsumableEffect",
        "current_ownership": "pet_inventory.item_key quantity",
        "current_effect": "Feed companion: fullness +24, affection +4, pet XP +8",
        "current_source": "Daily quest completion; companion grants; pet_snack; Gacha",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.consumable.go-spirit-candy",
        "icon_concept": "A small black-and-white Go stone candy wrapped like a travel sweet",
        "silhouette": "Round candy with a two-tone stone swirl",
        "primary_material": "Glazed sugar, rice paper, dark ink seal",
        "world_visual_language": "Friendly companion provisioning with Go-stone heritage",
        "mobile_readability": "Single round candy and two-tone wrapper at 32px",
        "art_priority": "P0",
        "stackable": True,
        "source_tags": ["Daily quest", "Companion grant", "Shop:daily", "Gacha:pet_food"],
        "where_to_get_more": ["Daily quests", "Pet Candy Pouch", "Gacha", "Companion progression"],
        "effect_use": "Use from the existing Spirit feeding contract; no combat effect",
    },
    "starfruit": {
        "item_id": "starfruit",
        "name": "星果",
        "name_en": "Starfruit",
        "category": "ConsumableEffect",
        "current_ownership": "pet_inventory.item_key quantity",
        "current_effect": "Feed companion: fullness +38, affection +7, pet XP +15",
        "current_source": "Daily completion; pet milestones; starfruit_basket; Gacha",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.consumable.starfruit",
        "icon_concept": "A five-point fruit with a small constellation cut through its center",
        "silhouette": "Five-point star fruit, one bright seed window",
        "primary_material": "Golden fruit skin, translucent juice, indigo seed",
        "world_visual_language": "Night-sky nourishment; bright but natural, not premium currency",
        "mobile_readability": "Five-point outline and single central cut remain readable at 32px",
        "art_priority": "P0",
        "stackable": True,
        "source_tags": ["Daily quest", "Pet milestone", "Shop:daily", "Gacha:pet_food"],
        "where_to_get_more": ["Daily quests", "Pet milestones", "Star Fruit Basket", "Gacha"],
        "effect_use": "Use from the existing Spirit feeding contract; no combat effect",
    },
    "moon_drop": {
        "item_id": "moon_drop",
        "name": "月露",
        "name_en": "Moon Drop",
        "category": "ConsumableEffect",
        "current_ownership": "pet_inventory.item_key quantity",
        "current_effect": "Feed companion: fullness +18, affection +10, pet XP +25",
        "current_source": "Friend challenge win/draw; moon_dew_vial; Gacha",
        "current_art": "Emoji fallback only; no canonical raster asset",
        "asset_path": None,
        "canonical_art_key": "item.consumable.moon-drop",
        "icon_concept": "A suspended blue dew drop holding a crescent reflection",
        "silhouette": "Single teardrop with a crescent highlight",
        "primary_material": "Glass-like dew, moon-silver rim, deep blue core",
        "world_visual_language": "Quiet night reward from social play; precious without becoming currency",
        "mobile_readability": "Teardrop outline and crescent highlight at 32px",
        "art_priority": "P0",
        "stackable": True,
        "source_tags": ["Friend challenge", "Shop:daily", "Gacha:pet_food"],
        "where_to_get_more": ["Friend challenges", "Moon Dew Vial", "Gacha"],
        "effect_use": "Use from the existing Spirit feeding contract; no combat effect",
    },
}


BUNDLE_POLISH_PACK_6 = {
    "premium_hint_bundle": {
        "product_id": "premium_hint_bundle",
        "display_name": "高級提示包",
        "display_name_en": "Premium Hint Bundle",
        "grants": [{"item_id": "hint_ticket", "quantity": 5}],
        "display_copy": "立即獲得：小提示卷 ×5",
        "display_copy_en": "Contains: Hint Ticket ×5",
        "current_asset": "/assets/shop/premium_hint_bundle.webp",
        "art_status": "dedicated_asset",
    },
    "ai_explain_ticket_bundle": {
        "product_id": "ai_explain_ticket_bundle",
        "display_name": "AI 解說券包",
        "display_name_en": "AI Analysis Bundle",
        "grants": [{"item_id": "ai_explain_ticket", "quantity": 3}],
        "display_copy": "立即獲得：AI 解說券 ×3",
        "display_copy_en": "Contains: AI Analysis Ticket ×3",
        "current_asset": "/assets/shop/ai_explain_ticket_bundle.webp",
        "art_status": "dedicated_asset",
    },
    "pet_snack": {
        "product_id": "pet_snack",
        "display_name": "寵物糖果包",
        "display_name_en": "Pet Candy Pouch",
        "grants": [{"item_id": "go_spirit_candy", "quantity": 3}],
        "display_copy": "立即獲得：棋魂糖 ×3",
        "display_copy_en": "Contains: Go Spirit Candy ×3",
        "current_asset": "/assets/shop/pet_candy_pouch.webp",
        "art_status": "dedicated_asset",
    },
    "starfruit_basket": {
        "product_id": "starfruit_basket",
        "display_name": "星果籃",
        "display_name_en": "Star Fruit Basket",
        "grants": [{"item_id": "starfruit", "quantity": 3}],
        "display_copy": "立即獲得：星果 ×3",
        "display_copy_en": "Contains: Starfruit ×3",
        "current_asset": "/assets/shop/star_fruit_basket.webp",
        "art_status": "dedicated_asset",
    },
    "moon_dew_vial": {
        "product_id": "moon_dew_vial",
        "display_name": "月露瓶",
        "display_name_en": "Moon Dew Vial",
        "grants": [{"item_id": "moon_drop", "quantity": 3}],
        "display_copy": "立即獲得：月露 ×3",
        "display_copy_en": "Contains: Moon Drop ×3",
        "current_asset": "/assets/shop/moon_dew_vial.webp",
        "art_status": "dedicated_asset",
    },
    "pet_feast_box": {
        "product_id": "pet_feast_box",
        "display_name": "寵物豪華餐盒",
        "display_name_en": "Pet Feast Box",
        "grants": [
            {"item_id": "go_spirit_candy", "quantity": 3},
            {"item_id": "starfruit", "quantity": 2},
            {"item_id": "moon_drop", "quantity": 1},
        ],
        "display_copy": "立即獲得：棋魂糖 ×3、星果 ×2、月露 ×1",
        "display_copy_en": "Contains: Go Spirit Candy ×3, Starfruit ×2, Moon Drop ×1",
        "current_asset": "/assets/shop/pet_feast_box.webp",
        "art_status": "dedicated_asset",
    },
}


# Existing Shop art is kept as a presentation mapping only.  It does not
# become price or ownership authority.
SHOP_PRODUCT_ART_ASSETS = {
    "hint_ticket": "/assets/shop/small_hint_scroll.webp",
    "premium_hint_bundle": "/assets/shop/premium_hint_bundle.webp",
    "ai_explain_ticket": "/assets/shop/icon_ai_ticket.webp",
    "ai_explain_ticket_bundle": "/assets/shop/ai_explain_ticket_bundle.webp",
    "pet_snack": "/assets/shop/pet_candy_pouch.webp",
    "starfruit_basket": "/assets/shop/star_fruit_basket.webp",
    "moon_dew_vial": "/assets/shop/moon_dew_vial.webp",
    "pet_feast_box": "/assets/shop/pet_feast_box.webp",
    "streak_shield": "/assets/shop/icon_shield.webp",
    "double_streak_shield": "/assets/shop/double_streak_shield.webp",
    "extra_questions_small": "/assets/shop/small_training_pass.webp",
    "extra_questions": "/assets/shop/small_training_pass.webp",
    "grand_training_pass": "/assets/shop/grand_training_pass.webp",
    "small_xp_potion": "/assets/shop/small_xp_potion.webp",
    "xp_potion": "/assets/shop/icon_xp_potion.webp",
    "grand_xp_potion": "/assets/shop/grand_xp_potion.webp",
}


NEWBIE_ITEM_SOURCE_TAGS = {
    "hint_ticket": ["Newbie stage 2"],
    "ai_explain_ticket": ["Newbie stage 4"],
    "extra_questions_small": ["Newbie stage 6"],
    "extra_questions": ["Newbie stage 7"],
    "small_xp_potion": ["Newbie stage 5"],
    "xp_potion": ["Newbie stage 7"],
    "streak_shield": ["Newbie stage 3"],
    "double_streak_shield": ["Newbie stage 7"],
    "pet_snack": ["Newbie stage 1"],
    "starfruit_basket": ["Newbie stage 7"],
}


PET_FOOD_SOURCE_TAGS = {
    "go_spirit_candy": ["Daily quest", "Companion grant", "Shop bundle", "Gacha"],
    "starfruit": ["Daily quest", "Pet milestone", "Shop bundle", "Gacha"],
    "moon_drop": ["Friend challenge", "Shop bundle", "Gacha"],
}


def _semantic_category(product):
    if product.get("grants_items") or product.get("grants_food"):
        return "TreasureBundle"
    if product.get("category") == "collection":
        return "Material"
    if product.get("category") == "pet" and product.get("effect", {}).get("key") == "pet_xp":
        return "Material"
    return "ConsumableEffect"


def _product_grants(product):
    grants = []
    for item_id, quantity in (product.get("grants_items") or {}).items():
        grants.append({"item_id": item_id, "quantity": int(quantity), "grant_type": "ITEM"})
    for item_id, quantity in (product.get("grants_food") or {}).items():
        grants.append({"item_id": item_id, "quantity": int(quantity), "grant_type": "ITEM"})
    if not grants:
        grants.append({"item_id": product["key"], "quantity": 1, "grant_type": "ITEM"})
    return grants


def build_shop_product_grant_registry(shop_items, pet_food_catalog=None):
    """Return a read-only product/grant projection for all current products."""

    registry = []
    pet_food_catalog = pet_food_catalog or {}
    for product_id, product in shop_items.items():
        grants = _product_grants(product)
        bundle = bool(product.get("grants_items") or product.get("grants_food"))
        asset = SHOP_PRODUCT_ART_ASSETS.get(product_id)
        status = "shared_asset" if product_id == "extra_questions" else (
            "dedicated_asset" if asset else "emoji_fallback_no_canonical_asset"
        )
        cadence = product.get("shop_pool", "daily")
        source_tags = [f"Shop:{cadence}"]
        if product.get("gacha_drop", True):
            source_tags.append("Gacha")
        source_tags.extend(NEWBIE_ITEM_SOURCE_TAGS.get(product_id, []))
        granted_display_names = {}
        granted_display_names_en = {}
        for grant in grants:
            grant_id = grant["item_id"]
            definition = shop_items.get(grant_id) or pet_food_catalog.get(grant_id) or {}
            granted_display_names[grant_id] = definition.get("name", grant_id)
            granted_display_names_en[grant_id] = definition.get("name_en", grant_id)
        registry.append({
            "product_id": product_id,
            "display_name": product.get("name", product_id),
            "display_name_en": product.get("name_en", product_id),
            "grant_type": "BUNDLE" if bundle else "ITEM",
            "granted_ids": [grant["item_id"] for grant in grants],
            "grants": grants,
            "quantities": {grant["item_id"]: grant["quantity"] for grant in grants},
            "granted_display_names": granted_display_names,
            "granted_display_names_en": granted_display_names_en,
            "persistent_product_ownership": not bundle,
            "price_authority": "server: SHOP_ITEMS.price plus server daily rotation price",
            "shop_cadence": cadence,
            "gacha_enabled": bool(product.get("gacha_drop", True)),
            "source_tags": source_tags,
            "current_asset": asset,
            "art_status": status,
            "category": _semantic_category(product),
            "current_shop_category": product.get("category"),
            "current_effect": deepcopy(product.get("effect") or {}),
            "description": product.get("desc", ""),
            "description_en": product.get("desc_en", ""),
            "ownership_authority": "shop_inventory.item_key" if not bundle else "grant_components_only",
        })
    return registry


def _base_item_entry(item_id, name, name_en, category, *, ownership, stackable,
                     source_tags, where_to_get_more, effect_use, asset_path=None,
                     product_id=None, product_registry=None):
    return {
        "item_id": item_id,
        "name": name,
        "name_en": name_en,
        "category": category,
        "ownership_authority": ownership,
        "stackable": bool(stackable),
        "source_tags": list(source_tags),
        "where_to_get_more": list(where_to_get_more),
        "effect_use": effect_use,
        "asset_path": asset_path,
        "canonical_art_key": f"item.{category.lower()}.{item_id}",
        "art_status": "dedicated_asset" if asset_path else "spec_only_no_final_art",
        "product_id": product_id,
        "product": product_registry,
        "player_visible": True,
        "journal_read_only": True,
    }


def build_item_registry(shop_items, pet_food_catalog):
    """Build the current non-equipment item projection without ownership writes."""

    products = build_shop_product_grant_registry(shop_items, pet_food_catalog)
    by_product = {entry["product_id"]: entry for entry in products}
    items = []

    for product_id, product in shop_items.items():
        product_view = by_product[product_id]
        art_pack = LIVE_ITEM_ART_PACK_8.get(product_id)
        grants = product_view["grants"]
        # A bundle is a product presentation, not a persistent item row.
        if product_view["grant_type"] == "BUNDLE":
            item_id = product_id
            ownership = "grant_components_only"
            stackable = False
        else:
            item_id = product_id
            ownership = "shop_inventory.item_key"
            stackable = True
        if art_pack:
            entry = deepcopy(art_pack)
            entry.update({
                "product_id": product_id,
                "product": product_view,
                "ownership_authority": ownership,
                "stackable": stackable,
                "source_tags": product_view["source_tags"],
                "where_to_get_more": product_view["source_tags"],
                "art_status": "spec_only_no_final_art",
                "player_visible": True,
                "journal_read_only": True,
            })
        else:
            effect = product.get("effect") or {}
            effect_use = product.get("desc", "")
            if product_view["grant_type"] == "BUNDLE":
                effect_use = product.get("desc", "")
            entry = _base_item_entry(
                item_id,
                product.get("name", item_id),
                product.get("name_en", item_id),
                product_view["category"],
                ownership=ownership,
                stackable=stackable,
                source_tags=product_view["source_tags"],
                where_to_get_more=product_view["source_tags"],
                effect_use=effect_use,
                asset_path=product_view["current_asset"],
                product_id=product_id,
                product_registry=product_view,
            )
            entry["current_effect"] = deepcopy(effect)
            entry["current_shop_category"] = product.get("category")
            entry["current_art"] = product_view["art_status"]
            entry["stackable"] = stackable
        items.append(entry)

    for item_id, food in pet_food_catalog.items():
        art_pack = LIVE_ITEM_ART_PACK_8.get(item_id)
        if art_pack:
            entry = deepcopy(art_pack)
            entry.update({
                "product_id": None,
                "product": None,
                "ownership_authority": "pet_inventory.item_key",
                "player_visible": True,
                "journal_read_only": True,
            })
        else:
            entry = _base_item_entry(
                item_id,
                food.get("name", item_id),
                food.get("name_en", item_id),
                "ConsumableEffect",
                ownership="pet_inventory.item_key",
                stackable=True,
                source_tags=PET_FOOD_SOURCE_TAGS.get(item_id, []),
                where_to_get_more=PET_FOOD_SOURCE_TAGS.get(item_id, []),
                effect_use=(
                    f"Feed companion: fullness +{food.get('fullness', 0)}, "
                    f"affection +{food.get('affection', 0)}, pet XP +{food.get('xp', 0)}"
                ),
            )
            entry["current_effect"] = {
                "fullness": food.get("fullness", 0),
                "affection": food.get("affection", 0),
                "pet_xp": food.get("xp", 0),
            }
            entry["current_art"] = "emoji_fallback_no_canonical_asset"
        items.append(entry)

    return items


BADGE_FAMILY_BY_TYPE = {
    "streak": "Streak",
    "max_streak": "Streak",
    "total_correct": "Correct Answers",
    "combo": "Combo",
    "mistake_corrected": "Mistake Correction",
    "daily_challenge": "Daily",
    "rank": "Rank",
    "xp": "XP",
    "challenge_win": "Friend Challenge",
    "challenge_win_streak": "Friend Challenge",
    "premium": "Premium",
    "community_leaderboard": "Community",
    "newbie_quest": "Correct Answers",
    "unit_complete": "Correct Answers",
}


BADGE_VISUAL_SYSTEM_V1 = {
    "version": "badge-visual-system-v1",
    "final_art": False,
    "shared_rule": "One family frame plus one central symbol language; threshold is carried by tier and number treatment, not 84 unrelated silhouettes.",
    "families": {
        "Streak": {
            "frame_language": "Open ember ring with forward motion notch",
            "central_symbol_language": "Flame, linked stones, or wind streak",
            "tier_treatment": "Bronze ember, silver lightning, gold storm, legendary comet",
            "number_treatment": "Threshold as compact lower-right numeral or Roman-style mark",
            "color_role": "Warm orange to electric violet signals sustained momentum",
            "mobile_readability": "One flame/ring silhouette; no more than two interior marks",
        },
        "Correct Answers": {
            "frame_language": "Leaf-and-seal frame, opening upward",
            "central_symbol_language": "Go stone plus checkmark or growing tree",
            "tier_treatment": "Seed, sprout, tree, constellation",
            "number_treatment": "Small threshold numeral in seal band",
            "color_role": "Jade and teal for learning growth; gold for mastery",
            "mobile_readability": "Large check/stone pair with a clean outer leaf silhouette",
        },
        "Combo": {
            "frame_language": "Braided lightning loop",
            "central_symbol_language": "Interlocking stones or bolt",
            "tier_treatment": "One, two, three, then radiant braid layers",
            "number_treatment": "Centered numeral inside the loop",
            "color_role": "Amber and cobalt contrast; legendary adds white spark",
            "mobile_readability": "One high-contrast diagonal bolt; avoid thin braid strands",
        },
        "Mistake Correction": {
            "frame_language": "Repaired ink seal with visible stitch or correction stroke",
            "central_symbol_language": "Brush stroke turning into a checkmark",
            "tier_treatment": "Single repair, double repair, polished seal, master seal",
            "number_treatment": "Threshold sits on the repair tab",
            "color_role": "Indigo/teal with restrained red correction accent",
            "mobile_readability": "Before/after stroke remains visible at thumbnail size",
        },
        "Daily": {
            "frame_language": "Calendar plaque with sunrise rim",
            "central_symbol_language": "Sun, date mark, or repeating moon",
            "tier_treatment": "Short streak marks accumulate around the rim",
            "number_treatment": "Days displayed as large two/three-digit counter",
            "color_role": "Dawn amber to night blue shows continuity",
            "mobile_readability": "Calendar square plus one sun mark; no tiny date grid",
        },
        "Rank": {
            "frame_language": "Gate or mountain pass frame",
            "central_symbol_language": "Stone gate, path marker, or summit star",
            "tier_treatment": "Kyu uses carved wood/stone; dan uses metal and crystal",
            "number_treatment": "Rank text is the primary readable content",
            "color_role": "Teal for kyu progression; amber/violet for dan prestige",
            "mobile_readability": "Rank text must remain legible without relying on symbol",
        },
        "XP": {
            "frame_language": "Growing crystal capsule",
            "central_symbol_language": "Light seed, energy crystal, or orbit",
            "tier_treatment": "One facet through a full constellation",
            "number_treatment": "Compact XP threshold under central crystal",
            "color_role": "Cool cyan to violet with a warm learning core",
            "mobile_readability": "One crystal silhouette and one bright center",
        },
        "Friend Challenge": {
            "frame_language": "Two-sided duel medallion",
            "central_symbol_language": "Crossed stones, paired hands, or linked paths",
            "tier_treatment": "Bronze meeting, silver rivalry, gold champion, legendary legend",
            "number_treatment": "Win count on the lower ribbon",
            "color_role": "Balanced blue/red accents, never a combat damage signal",
            "mobile_readability": "Two opposing shapes read as social contest",
        },
        "Premium": {
            "frame_language": "Faceted jewel frame with restrained crown edge",
            "central_symbol_language": "Diamond, crown, or founder seal",
            "tier_treatment": "Both remain legendary; distinction comes from seal geometry",
            "number_treatment": "No numeric threshold; use member/founder ribbon",
            "color_role": "Deep violet and champagne gold; avoid pay-to-win visual language",
            "mobile_readability": "Single jewel plus one crown/seal mark",
        },
        "Community": {
            "frame_language": "Leaderboard podium plaque",
            "central_symbol_language": "Medal, podium, or laurel",
            "tier_treatment": "Placement is the tier; first place gets a single clear numeral",
            "number_treatment": "Placement numeral is central and large",
            "color_role": "Gold with community blue accent",
            "mobile_readability": "Medal and placement numeral must read at 32px",
        },
    },
}


BADGE_PROTOTYPE_SELECTION = (
    {"badge_id": "streak_3", "family": "Streak", "role": "entry tier"},
    {"badge_id": "streak_100", "family": "Streak", "role": "legendary tier"},
    {"badge_id": "total_10", "family": "Correct Answers", "role": "entry tier"},
    {"badge_id": "total_5000", "family": "Correct Answers", "role": "legendary tier"},
    {"badge_id": "combo_3", "family": "Combo", "role": "entry tier"},
    {"badge_id": "combo_50", "family": "Combo", "role": "legendary tier"},
    {"badge_id": "mistake_1", "family": "Mistake Correction", "role": "entry tier"},
    {"badge_id": "mistake_100", "family": "Mistake Correction", "role": "legendary tier"},
    {"badge_id": "daily_first", "family": "Daily", "role": "entry state"},
    {"badge_id": "daily_365", "family": "Daily", "role": "legendary tier"},
    {"badge_id": "rank_19k", "family": "Rank", "role": "kyu entry"},
    {"badge_id": "rank_3d", "family": "Rank", "role": "dan apex"},
    {"badge_id": "xp_100", "family": "XP", "role": "entry tier"},
    {"badge_id": "xp_25000", "family": "XP", "role": "legendary tier"},
    {"badge_id": "challenge_win_1", "family": "Friend Challenge", "role": "entry tier"},
    {"badge_id": "challenge_win_30", "family": "Friend Challenge", "role": "legendary tier"},
    {"badge_id": "premium_member", "family": "Premium", "role": "member seal"},
    {"badge_id": "premium_founder", "family": "Premium", "role": "founder seal"},
    {"badge_id": "badge_lb_weekly_1", "family": "Community", "role": "placement prototype"},
)


ZONE_MATERIAL_DESIGN_CONTRACT = {
    "version": "zone-material-design-contract-v1",
    "identity_fields": (
        "ITEM_ID",
        "DISPLAY_NAME",
        "ZONE_ID",
        "MONSTER_FAMILY",
        "RARITY_IF_NEEDED",
        "SOURCE_TYPE",
        "QUEST_ROLE",
        "COLLECTION_ROLE",
        "SHOP_ALLOWED",
        "COMBAT_POWER",
        "ASSET_KEY",
    ),
    "rules": {
        "COMBAT_POWER": "NONE",
        "SHOP_ALLOWED_DEFAULT": "NO",
        "DROP_AUTHORITY": "server settlement only",
        "CLIENT_ROLE": "presentation of a server-returned item_id and quantity",
        "CRAFTING_SCOPE": "No recipe/salvage system implied; first use is quest turn-in or collection set",
        "MONSTER_IDENTITY": "Use canonical monster family/source tag, not an unstable display alias",
    },
}


NON_EQUIPMENT_DROP_INTERFACE = {
    "version": "non-equipment-drop-interface-v1",
    "owner": "Lane C defines item identity/presentation; Lane B owns equipment loot settlement",
    "server_sequence": (
        "server settlement",
        "drop result",
        "item_id",
        "quantity",
        "source tag",
        "journal discovery",
        "inventory projection",
    ),
    "client_authority": "none",
    "drop_rate_authority": "unchanged and server-side",
    "equipment_boundary": "Equipment loot remains player_inventory and Lane B/A surfaces",
}


CROSS_DOMAIN_FRAGMENT_CONTRACT = {
    "item_id": "rare_appearance_fragment",
    "item_ownership_authority": "shop_inventory.item_key quantity",
    "consumption_intent": "server-side /api/shop/use item intent",
    "resulting_appearance_authority": "existing player_wardrobe.item_id authority",
    "second_cosmetic_ownership_table": "NO",
    "journal_projection": "show the item quantity and link to /hero?tab=appearance after unlock",
}


ITEM_ART_BIBLE_V1 = {
    "version": "item-art-bible-v1",
    "final_art_generated": False,
    "canvas": "256x256",
    "format": "RGBA PNG or WebP with transparent background",
    "asset_key_rule": "one canonical asset key per item/product visual",
    "mobile_rule": "silhouette and primary contrast must survive 32px display",
    "families": {
        "ConsumableEffect": "small usable object; readable cap, wrapper, fruit, or vial",
        "Material": "raw, stackable component with a stable center silhouette",
        "QuestItem": "key/insignia/document silhouette with clear non-consumable intent",
        "TreasureBundle": "container or curated package; contents must be explicit in UI",
        "Collectible": "medallion/relic seal; not a Backpack consumable",
    },
    "prohibitions": (
        "No emoji as final art",
        "No _ph_* placeholder as production art",
        "Chest art does not imply chest ownership",
        "No combat-power iconography for non-combat items",
        "No live asset key before art review approves the specification",
    ),
}


def badge_visual_metadata(badge):
    """Return visual-system metadata without replacing legacy badge fields."""

    badge_type = badge.get("type", "")
    family = BADGE_FAMILY_BY_TYPE.get(badge_type, "Correct Answers")
    family_spec = BADGE_VISUAL_SYSTEM_V1["families"][family]
    rarity = badge.get("rarity", "bronze")
    return {
        "visual_family": family,
        "visual_art_status": "system_spec_only",
        "canonical_art_key": f"badge.family.{family.lower().replace(' ', '-')}.tier.{rarity}",
        "frame_language": family_spec["frame_language"],
        "central_symbol_language": family_spec["central_symbol_language"],
        "tier": rarity,
        "tier_treatment": family_spec["tier_treatment"],
        "number_treatment": family_spec["number_treatment"],
        "color_role": family_spec["color_role"],
        "mobile_readability": family_spec["mobile_readability"],
    }
