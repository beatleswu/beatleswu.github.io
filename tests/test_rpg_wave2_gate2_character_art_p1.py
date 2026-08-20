"""Focused contract checks for the Wave 2 Lane A Gate 2 P1 art slice."""

import json
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/planning/rpg_wave2_gate2_character_art_p1_manifest.json"
REVIEW = ROOT / "docs/planning/rpg_wave2_gate2_character_art_p1_review.html"
CONTACT_SHEET = ROOT / "docs/planning/rpg_wave2_gate2_character_art_p1_contact_sheet.png"
APP = ROOT / "app.py"
HERO = ROOT / "hero.html"

CURRENT_IDS = {
    "apprentice",
    "apprentice_girl",
    "swordsman",
    "rogue",
    "ranger",
    "berserker",
    "guardian",
    "paladin",
    "mage",
    "sage",
}
P1_PLAYER_IDS = {"apprentice", "mage", "paladin", "trail_apprentice", "night_runner", "constellation_apprentice"}
P1_NPC_IDS = {"world.village_elder", "world.messenger"}


def _manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_p1_manifest_has_exact_production_scope_and_authority_guards():
    manifest = _manifest()
    assert manifest["scope"] == {
        "existing_character_polish_count": 3,
        "new_character_count": 3,
        "world_npc_count": 2,
        "runtime_roster_changed": False,
        "runtime_selection_api_changed": False,
    }
    assert manifest["art_contract"]["master_canvas"] == "1056x1408"
    assert manifest["art_contract"]["source_master"] == "PNG"
    assert manifest["art_contract"]["runtime_derivative"] == "WebP"
    assert manifest["art_contract"]["functional_weapon_baked_in_base_art"] is False
    assert manifest["authority"] == {
        "player_character_appearance": "player_appearance.character_key",
        "functional_equipment": "player_inventory",
        "character_combat_authority": False,
        "collection_prototype_writes_api": False,
        "collection_prototype_writes_db": False,
        "new_candidate_ids_registered_in_runtime": False,
    }

    player_assets = manifest["player_assets"]
    npc_assets = manifest["world_npc_assets"]
    assert {entry["character_id"] for entry in player_assets} == P1_PLAYER_IDS
    assert {entry["canonical_id"] for entry in npc_assets} == P1_NPC_IDS
    assert sum(entry["kind"] == "existing_polish" for entry in player_assets) == 3
    assert sum(entry["kind"] == "new_candidate" for entry in player_assets) == 3
    assert all(entry["functional_weapon_baked_in"] is False for entry in player_assets)
    assert all(entry["functional_weapon_baked_in"] is False for entry in npc_assets)


def test_p1_png_masters_and_webp_derivatives_meet_export_contract():
    manifest = _manifest()
    entries = manifest["player_assets"] + manifest["world_npc_assets"]
    for entry in entries:
        master = ROOT / entry["master"]
        runtime = ROOT / entry["runtime_derivative"]
        assert master.is_file(), master
        assert runtime.is_file(), runtime
        with Image.open(master) as image:
            rgba = image.convert("RGBA")
            assert rgba.size == (1056, 1408), master
            assert rgba.getchannel("A").getextrema()[0] == 0, master
            assert rgba.getbbox() is not None, master
            # Fully transparent pixels cannot carry a keyed RGB matte forward.
            for red, green, blue, alpha in rgba.get_flattened_data():
                if alpha == 0:
                    assert (red, green, blue) == (0, 0, 0), master
        with Image.open(runtime) as image:
            assert image.size == (1056, 1408), runtime
            assert image.mode in {"RGBA", "RGB"}, runtime


def test_visual_revision_locks_shared_player_family_and_review_artifact():
    manifest = _manifest()
    revision = manifest["visual_revision"]
    assert revision["revision_id"] == "RPG_WAVE2_GATE2_CHARACTER_ART_P1_VISUAL_REVISION_002"
    assert revision["player_visual_family_coherence"].startswith("PASS")
    assert revision["classifications"] == {
        "trail_apprentice": "POLISH — identity, scarf, pack, travel silhouette, and teal/brown family preserved",
        "night_runner": "REVISE — rogue hood, dark asymmetric silhouette, and teal/violet accents preserved while moving into the player proportion family",
        "constellation_apprentice": "REVISE — mage/scholar identity, constellation motif, asymmetric layers, and navy/gold family preserved",
        "world.village_elder": "KEEP — canonical E10 identity preserved",
        "world.messenger": "POLISH — Zone 1 Shot 10 courier identity and story role preserved",
    }
    assert set(revision["player_body_frame_families"]["PLAYER_FRAME_A_STANDARD_CHIBI"]["members"]) == P1_PLAYER_IDS
    assert revision["player_body_frame_families"]["NPC_FRAME_B_WORLD_BROAD"]["members"] == [
        "world.village_elder",
        "world.messenger",
    ]
    assert "no functional weapon" in revision["functional_weapon_policy"].lower()
    assert CONTACT_SHEET.is_file()
    with Image.open(CONTACT_SHEET) as sheet:
        assert sheet.width >= 1500
        assert sheet.height >= 1200


def test_collection_review_prototype_is_review_only_and_contains_required_states():
    html = REVIEW.read_text(encoding="utf-8")
    assert "P1 Visual Revision 002" in html
    assert "rpg_wave2_gate2_character_art_p1_contact_sheet.png" in html
    assert "10 / 20" in html
    assert "player_appearance.character_key" in html
    assert "player_inventory" in html
    assert "SELECTED" in html
    assert "UNLOCKED" in html
    assert "LOCKED" in html
    assert "Attack, Defense, Power, or rarity" in html
    for forbidden_runtime_field in ("name=\"attack\"", "name=\"defense\"", "name=\"power\"", "data-rarity="):
        assert forbidden_runtime_field not in html

    manifest = _manifest()
    for entry in manifest["player_assets"] + manifest["world_npc_assets"]:
        rel = entry["master"]
        assert (ROOT / rel).is_file(), rel
        assert f"../../{rel}" in html, rel


def test_current_character_ids_and_authority_paths_are_unchanged():
    app = APP.read_text(encoding="utf-8")
    hero = HERO.read_text(encoding="utf-8")

    valid_block = re.search(r"VALID_CHARACTER_KEYS\s*=\s*\{(?P<body>.*?)\n\}", app, re.S)
    assert valid_block, "VALID_CHARACTER_KEYS block is missing"
    runtime_key_literals = set(re.findall(r"['\"]([a-z_]+)['\"]", valid_block.group("body")))
    assert CURRENT_IDS <= runtime_key_literals
    for new_id in ("trail_apprentice", "night_runner", "constellation_apprentice"):
        assert new_id not in runtime_key_literals

    assert "const CHARACTER_KEYS = COMBAT_GEAR.character.map(c => c.key);" in hero
    assert all(re.search(rf"key\s*:\s*'{re.escape(current_id)}'", hero) for current_id in CURRENT_IDS)
    assert all(not re.search(rf"key\s*:\s*'{re.escape(new_id)}'", hero) for new_id in ("trail_apprentice", "night_runner", "constellation_apprentice"))
    assert "fetch('/api/skills/character'" in hero
    assert "player_appearance" in app
    assert "player_inventory" in app
    assert "def _get_authoritative_combat_stats" in app
