"""Pure-cosmetic runtime consumption contracts for Lane B Wave 2."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "rpg-wave2-lane-b-pure-cosmetic-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")

EXISTING_23 = {
    "hat_cloth", "hat_bamboo", "hat_student", "hat_feather", "hat_scholar",
    "hat_foxmask", "hat_onihorns", "hat_dragon_horn", "hat_celestial_crown",
    "hat_premium", "title_beginner", "title_scholar", "title_wanderer",
    "title_streak", "title_foxwit", "title_master", "title_dragonslayer",
    "title_godshand", "title_celestial", "title_eternity", "title_newbie_voyage",
    "title_claire_recruit", "title_premium",
}
NEW_21 = {
    "robe_plain", "robe_student", "robe_bamboo", "robe_crane", "robe_fox",
    "robe_snow", "robe_dragon", "back_pack", "back_flag", "back_lantern",
    "back_wings", "back_scroll", "back_foxtail", "back_cloak",
    "back_dragon_wings", "acc_bracelet", "acc_fan", "acc_goboard_bag",
    "acc_jade_ring", "acc_goban_seal", "acc_dragon_pendant",
}
PURE_IDS = EXISTING_23 | NEW_21

# These are the approved runtime derivative hashes.  In particular, the jade
# ring hash is from Lane A's final readability revision 423ed676..., not the
# superseded d79f0c8... derivative.
APPROVED_WEBP_SHA256 = {
    "robe_plain": "3a476c5cf9eaae706394e237723f38e3ad7421509e7786a2c7a0eb5b42f17208",
    "robe_student": "3cdf2868cdebfa304e83ceef839973067495305d6a55f059923335c5d3265026",
    "robe_bamboo": "51d83d6f831d073b890b5a1d610907f3540ca212604c26753e194d2d4e77b0b8",
    "robe_crane": "fd14f1d17b915752e1d903594337481d0a0bde6bd135a945717cd228bfb6c7cb",
    "robe_fox": "2e058251942dfd9a5c498f6db3978f10f4ccf0e363b5793912faf2a9145a8f7c",
    "robe_snow": "f503bd8bdca56b41814ec669891d826f39d39f5c5dee785b1b4c706c7fdee929",
    "robe_dragon": "15eadea73a6f9a4d5d5a0cabba22d3d745fc0b128ca2b4177ff580519ee79a79",
    "back_pack": "9626691195d9f63eab267a6f8a772177fe08385604c2bf0037237221cd2a1357",
    "back_flag": "40fbbe8f4e7a99c89526a6690274ab8fb1e242b427dbecaa761cce704816a304",
    "back_lantern": "a4b8e2a56955eb5f401187699bffc7cd5c6ea0e53082e9c5bb47ef3214905c70",
    "back_wings": "e884953b139e13bc4ec825ea410e452c27b2065c5732be96d69dbae58c22b409",
    "back_scroll": "a40ff7f212b225b8c90042466f5fafd5a7e3b0ebd10cb2409694665722df750a",
    "back_foxtail": "6024ca718f8bcd1cda250a2a1da45d8ac78a1413fa041717da3ec71abbba4f7e",
    "back_cloak": "50271f082f232467049d4291d4dfb523573def946ec165c545aff60eaee742e8",
    "back_dragon_wings": "1c5e6a249aec21a9b5c962fa7bafbb894c496698aa7a07f92d6f44db07eeb2f9",
    "acc_bracelet": "733fadc95cd55ecf829acb0cfb574478f7a18681bee8a5c56a0cf978d05f093c",
    "acc_fan": "e65b2a2f4a530f8cf939960d53681f18ac3727d75f53d8405d90075b0b11c8df",
    "acc_goboard_bag": "a90ae96e8677320b2d8b92c1fc77bd0c20b8b6e10f559f007f77eeb71ad1c8ff",
    "acc_jade_ring": "d5a5aa2a82a7c6b7d7765f6638b78dc7a17f3e5a2d84d4301d58e645dd50f25f",
    "acc_goban_seal": "1e360b8a90f8fe9906afb9a47f00e21de0fa2a0fb4dc836193044e94d797be2f",
    "acc_dragon_pendant": "a8441ea82d53006c50c1f16c0c166c54a2440577f3b61cca84733d118a4e0959",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _asset_path(url: str) -> Path:
    assert url.startswith("/assets/")
    return ROOT / url.removeprefix("/")


def test_exact_44_item_pure_presentation_registry():
    registry = app_module.PURE_COSMETIC_PRESENTATION_REGISTRY
    assert set(registry) == PURE_IDS
    assert len(registry) == 44
    assert set(app_module.PURE_COSMETIC_EXISTING_23) == EXISTING_23
    assert set(app_module.PURE_COSMETIC_NEW_21) == NEW_21

    for item_id, presentation in registry.items():
        assert presentation["asset_id"] == item_id
        assert presentation["pure_presentation"] is True
        assert presentation["functional_effect_count"] == 0
        assert presentation["combat_authority"] == "NO"


def test_all_44_assets_are_available_and_id_matched():
    registry = app_module.PURE_COSMETIC_PRESENTATION_REGISTRY
    for item_id in EXISTING_23:
        asset = _asset_path(registry[item_id]["asset"])
        assert asset == ROOT / "assets" / "hero" / "items" / f"{item_id}.svg"
        assert asset.is_file(), item_id
        assert asset.stem == item_id

    for item_id, expected_hash in APPROVED_WEBP_SHA256.items():
        presentation = registry[item_id]
        asset = _asset_path(presentation["asset"])
        assert presentation["mode"] == "FULL_BODY_COSMETIC_REFERENCE"
        assert presentation["asset_format"] == "WEBP"
        assert asset == ROOT / "assets" / "hero" / "items" / "fullbody" / f"{item_id}.webp"
        assert asset.is_file(), item_id
        assert asset.stem == item_id
        assert _sha256(asset) == expected_hash, item_id


def test_pure_cosmetics_have_no_functional_effect_projection():
    appearance_effects = app_module.APPEARANCE_EFFECTS
    for item_id in PURE_IDS:
        assert not appearance_effects.get(item_id, {}), item_id


def test_server_wardrobe_payload_and_client_consumer_keep_state_domains_separate():
    assert "player_wardrobe" in APP
    assert "player_appearance" in APP
    assert "presentation_metadata = _appearance_presentation_metadata(item)" in APP
    assert "wardrobe_item['presentation']" in APP
    assert "'owned': item['id'] in owned_ids" in APP
    assert "'equipped': item['id'] in equipped_ids" in APP
    assert "'selected': item['id'] in equipped_ids" in APP
    assert "'visible': item['id'] in equipped_ids" in APP
    assert "fetch('/api/skills/profile'" in HERO
    assert "_wardrobeItems = res.wardrobe ?? []" in HERO
    assert "item.presentation.pure_presentation === true" in HERO
    assert "'combat_authority': 'NO'" in APP


def test_hero_preview_reload_and_safe_fallback_consume_the_same_mapping():
    assert "function heroItemArtSrc(item)" in HERO
    assert "item.presentation.asset" in HERO
    assert "onerror=\"this.onerror=null;this.src='${HERO_ITEM_ROOT}unknown.svg';\"" in HERO
    assert "function renderCosmeticProjection()" in HERO
    assert "document.getElementById('hero-style-projection')" in HERO
    assert "document.getElementById('pv-style-projection')" in HERO
    assert "data-presentation-mode=\"${presentationMode}\"" in HERO
    assert 'data-owned="true" data-selected="true" data-visible="true"' in HERO
    assert "function openPreview()" in HERO
    assert "renderCosmeticProjection();" in HERO
    assert "_wardrobeItems = res.wardrobe ?? [];" in HERO


def test_responsive_consumer_remains_mobile_safe():
    assert ".hero-functional-projection-icon img { width: 100%; height: 100%; object-fit: contain;" in HERO
    assert ".slot-art {" in HERO
    assert "object-fit: contain;" in HERO
    assert "@media (max-width: 700px)" in HERO
