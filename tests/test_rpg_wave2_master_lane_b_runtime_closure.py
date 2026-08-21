"""Wave 2 Master Lane B runtime-closure contracts.

These checks cover the presentation bridge only.  They intentionally do not
create a new authority, alter combat formulas, or require a production DB.
"""

from pathlib import Path

import os

os.environ.setdefault("SECRET_KEY", "rpg-wave2-master-lane-b-test-secret")
import app as app_module  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
HERO = (ROOT / "hero.html").read_text(encoding="utf-8")
PROFILE = (ROOT / "profile.html").read_text(encoding="utf-8")
GAMES = (ROOT / "games.html").read_text(encoding="utf-8")
MANAGE = (ROOT / "manage.html").read_text(encoding="utf-8")
STONE = (ROOT / "wgo" / "stone_skin.js").read_text(encoding="utf-8")
INVENTORY = (ROOT / "inventory.html").read_text(encoding="utf-8")


FUNCTIONAL_IDS = {
    "wooden_sword",
    "iron_sword",
    "fox_fang",
    "dragon_claw",
    "celestial_blade",
    "cloth_robe",
    "leather_armor",
    "fox_pelt",
    "dragon_scale",
    "void_mantle",
    "lucky_stone",
    "xp_amulet",
    "fox_mask",
    "dragon_eye",
    "go_stone_black",
}


def test_character_presentation_fails_closed_to_server_default():
    assert app_module._presentation_character_key("sage") == "sage"
    assert app_module._presentation_character_key("hero_male") == "apprentice"
    assert app_module._presentation_character_key("unknown") == "apprentice"
    assert app_module._presentation_character_key(None) == "apprentice"

    assert "character_key_source" in APP
    assert "player_appearance.character_key" in APP
    assert "authoritative hero presentation unavailable" in HERO
    assert "fetch('/api/player/appearance'" in HERO
    assert "charKeySynced" not in HERO


def test_functional_registry_has_fourteen_full_body_items_and_inventory_only_stone():
    assert set(app_module.FUNCTIONAL_EQUIPMENT_ART) == FUNCTIONAL_IDS
    assert len(app_module.FUNCTIONAL_EQUIPMENT_ART) == 15
    assert set(app_module.FUNCTIONAL_EQUIPMENT_PRESENTATION_REGISTRY) == FUNCTIONAL_IDS

    full_body_ids = FUNCTIONAL_IDS - {"go_stone_black"}
    assert len(full_body_ids) == 14

    for item_id in FUNCTIONAL_IDS:
        equip = app_module._EQUIP_MAP[item_id]
        art = app_module.FUNCTIONAL_EQUIPMENT_ART[item_id]
        payload = app_module._functional_equipment_payload(equip)
        presentation = payload["presentation"]
        assert presentation["fallback"] == "NEUTRAL_FUNCTIONAL_ICON"
        assert presentation["presentation_only"] is True
        assert art["presentation_only"] is True
        if item_id in full_body_ids:
            assert art["presentation_mode"] == "FULL_BODY_OVERLAY"
            assert art["full_body_required"] is True
            assert presentation["mode"] == "FULL_BODY_OVERLAY"
            assert presentation["full_body_required"] is True
            assert presentation["asset"] == (
                f"/assets/hero/equipment/wearables/overlays/{item_id}.png"
            )
            assert presentation["layer"]
        else:
            assert item_id == "go_stone_black"
            assert art["presentation_mode"] == "ICON_ONLY"
            assert art["full_body_required"] is False
            assert presentation["mode"] == "ICON_ONLY"
            assert presentation["full_body_required"] is False
            assert presentation["family"] == "INVENTORY_ONLY"
            assert presentation["asset"] is None
        assert payload["functional_equipment"] is True
        assert payload["style_equipment"] is False

    assert "fetch('/api/player/inventory'" in HERO
    assert "item.functional_equipment === true" in HERO
    assert "server state · icon + full-body projection" in HERO
    assert "data-presentation-mode" in HERO
    assert "damage" not in HERO[HERO.index("function functionalProjectionItemHTML"):HERO.index("function combatGearButtonHTML")]


def test_functional_and_style_projections_are_explicitly_separate():
    assert "戰鬥裝備 / Functional Equipment" in HERO
    assert "外觀裝備 / Hero Style Gear" in HERO
    assert "visual only · no combat authority" in HERO
    assert "wardrobeHasGameplayEffect(item)" in HERO
    assert "item.owned === true && item.equipped === true" in HERO
    assert 'data-owned="true" data-selected="true" data-visible="true"' in HERO
    assert "data-item-domain=\"style\"" in HERO
    assert "data-item-domain=\"equipment\"" in HERO


def test_stone_board_renderer_covers_private_and_replay_routes():
    assert "configureStoneBoardSelection" in STONE
    assert "__GO_STONE_BOARD_SELECTION__" in STONE
    assert "__stoneSkinRedraw" in STONE
    assert "stone_skin.js?v=4" in PROFILE
    assert "stone_skin.js?v=4" in GAMES
    assert 'src="/wgo/stone_skin.js?v=4"' in MANAGE
    assert "window.__GO_STONE_BOARD_SELECTION__" in PROFILE


def test_responsive_runtime_contracts_cover_tablet_orientations():
    assert "@media (min-width: 701px) and (max-width: 1180px)" in HERO
    assert "orientation: portrait" in HERO
    assert "@media (min-width:701px) and (max-width:1180px)" in INVENTORY
    assert "@media (min-width:701px) and (max-width:1024px) and (orientation:portrait)" in INVENTORY
