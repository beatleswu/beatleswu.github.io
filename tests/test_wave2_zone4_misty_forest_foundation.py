"""Deterministic non-app.py contracts for the Wave 2 Zone 4 foundation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from adventure_zone3_monster_authority import (
    ZONE3_AUTHORITY,
    ZONE3_BINDING_COUNT,
    ZONE3_NORMAL_IDS,
)
from adventure_zone4_misty_forest_authority import (
    ZONE4_AUTHORITY,
    ZONE4_BINDING_COUNT,
    ZONE4_BINDING_SOURCE,
    ZONE4_BINDING_VERSION,
    ZONE4_KEY,
    ZONE4_LORD_CLASSIFICATION,
    ZONE4_LORD_ID,
    ZONE4_MONSTER_PROFILE_REGISTRY,
    ZONE4_NORMAL_ATTACK,
    ZONE4_NORMAL_IDS,
    ZONE4_NORMAL_MAX_HP,
    ZONE4_NORMAL_SPECS,
    ZONE4_PRESENTATION_ASSETS,
    ZONE4_PROFILE_VERSION,
    Zone4MonsterAuthorityError,
    decode_zone4_binding,
    encode_zone4_binding,
    get_zone4_binding,
    select_zone4_binding,
    zone4_combat_profile,
    zone4_presentation_for_battle,
)
from adventure_zone4_misty_forest_content import (
    ZONE4_BOOKS,
    ZONE4_CANONICAL_ROW_SOURCE,
    ZONE4_CANONICAL_ROW_STATUS,
    ZONE4_LORD_METADATA,
    ZONE4_NEW_ART_REQUIRED_COUNT,
    ZONE4_NEW_AUDIO_REQUIRED_COUNT,
    ZONE4_REUSED_AMBIENCE_PATHS,
    ZONE4_REUSED_BGM_PATHS,
    ZONE4_STORYBOARD_AVAILABLE,
    ZONE4_STORYBOARD_SCENE_PATHS,
    ZONE4_STORYBOARD_VOICE_PATHS,
    ZONE4_VO_AVAILABLE,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_IDS = tuple(f"M{number:03d}" for number in range(34, 46))
EXPECTED_ASSETS = {
    "M034": ("assets/monsters/forest_spirit_chibi.png", "AEA102378AAB74F0A217B66F2B41A6C2C4BCBAD230F943C4AA2E28058C77D529"),
    "M035": ("art/monsters/M035_mist_tail_fox.png", "2139DD735189B7EE620470A0ADAB1A8B3171617CB9FF518310B4B85C4EF06B48"),
    "M036": ("art/monsters/M036_moonleaf_moth.png", "1EEED20F6A18F602364DC62AB457920050B364EAA5760D789659D49E365F277A"),
    "M037": ("art/monsters/M037_vineclaw_beast.png", "2B0FA587B9C1469AB4239E955D646B9635C8DC7C141E1B9E84D19757C70071F2"),
    "M038": ("art/monsters/M038_mossback_turtle.png", "8DBF1A3B3AC64159F42E1B3C1B27C67437A4B964254C9D96D3F4C320BDD896EF"),
    "M039": ("art/monsters/M039_dewdrop_spider.png", "43AF530C228551E9F91E430A4159D0ECB91716DE356D41A1762AEC9A8AF36C2E"),
    "M040": ("art/monsters/M040_twig_deer.png", "0ADEE00D4858DFE66FFB28F7FA6DB70EBA3C91743513CE1168C3D1ABB73BC379"),
    "M041": ("art/monsters/M041_fogwhistle_frog.png", "418F3240A9F0E50DCAFEE11485B4471EFFC744C293963BFA397A916E2563C635"),
    "M042": ("art/monsters/M042_bloomcrown_caterpillar.png", "1F054B4CF4B66758BC72A38713F92FB16F4ABF64D94114DAF657E2694D4EB4A2"),
    "M043": ("art/monsters/M043_shadowstep_cat.png", "FC92B7D3A9FD343BDCF6AC065342913D1E8D596FC7E852B8627E036717695181"),
    "M044": ("art/monsters/M044_hollowtree_cub.png", "920159D38C2A3C72575CD9B227D959FFF6C4F76E4E635CF95E061EB1956D736E"),
    "M045": ("art/monsters/M045_mosscap_sapling.png", "F6C892BEB99EFE739C07B3211C9FDFB76E22286A4A29939AB5E3B43E13CAE23D"),
}


def test_zone3_template_extraction_preserves_established_contract():
    assert ZONE3_BINDING_COUNT == 13
    assert len(ZONE3_AUTHORITY.profile_registry.profiles) == 13
    assert ZONE3_NORMAL_IDS == (
        "M022", "M023", "M024", "M025", "M026", "M027", "M028",
        "M029", "M030", "M031", "M032", "M033", "M060",
    )


def test_zone4_roster_is_exactly_existing_m034_to_m045_and_normal_only():
    assert ZONE4_NORMAL_IDS == EXPECTED_IDS
    assert ZONE4_BINDING_COUNT == 12
    assert len(ZONE4_NORMAL_SPECS) == 12
    assert not any(int(monster_id[1:]) > 120 for monster_id in ZONE4_NORMAL_IDS)
    assert ZONE4_LORD_ID not in ZONE4_NORMAL_IDS
    assert ZONE4_LORD_CLASSIFICATION == "LORD_ONLY"
    assert all(
        profile.encounter_class == "NORMAL" and profile.boss_role is None
        for profile in ZONE4_MONSTER_PROFILE_REGISTRY.profiles
    )


def test_zone4_each_binding_is_explicit_and_reuses_existing_asset_bytes():
    for roster_slot, monster_id in enumerate(EXPECTED_IDS, start=1):
        binding = get_zone4_binding(monster_id)
        assert binding is not None
        assert binding.monster_id == monster_id
        assert binding.roster_slot == roster_slot
        assert binding.zone_key == ZONE4_KEY
        assert binding.encounter_class == "NORMAL"
        assert binding.profile_id == f"adventure_z4_normal_{monster_id}"
        assert binding.profile_version == ZONE4_PROFILE_VERSION
        assert binding.max_hp == ZONE4_NORMAL_MAX_HP
        assert binding.attack == ZONE4_NORMAL_ATTACK
        asset_path, expected_hash = EXPECTED_ASSETS[monster_id]
        assert binding.presentation_asset == f"/{asset_path}"
        actual_hash = hashlib.sha256((ROOT / asset_path).read_bytes()).hexdigest().upper()
        assert actual_hash == expected_hash
        assert ZONE4_PRESENTATION_ASSETS[monster_id] == binding.presentation_asset
        profile = ZONE4_MONSTER_PROFILE_REGISTRY.by_id[monster_id]
        assert profile.zone_key == ZONE4_KEY
        assert profile.drop_profile_id == "drop_legacy_rabbit"
        assert profile.reward_profile_id == "reward_battlefield_legacy"


def test_zone4_selection_is_deterministic_and_fail_closed():
    selected = [select_zone4_binding(question_id).monster_id for question_id in range(1, 301)]
    assert selected == [select_zone4_binding(question_id).monster_id for question_id in range(1, 301)]
    assert set(selected).issubset(set(EXPECTED_IDS))
    assert get_zone4_binding("M121") is None
    assert get_zone4_binding(ZONE4_LORD_ID) is None
    with pytest.raises(Zone4MonsterAuthorityError):
        select_zone4_binding(0)


def test_zone4_persisted_binding_round_trip_and_tamper_rejection():
    binding = get_zone4_binding("M039")
    assert binding is not None
    encoded = encode_zone4_binding(binding)
    row = {
        "zone_key": ZONE4_KEY,
        "migration_source": ZONE4_BINDING_SOURCE,
        "migration_version": encoded,
    }
    assert decode_zone4_binding(row) == binding
    with pytest.raises(Zone4MonsterAuthorityError):
        decode_zone4_binding({**row, "zone_key": "k16_20"})
    with pytest.raises(Zone4MonsterAuthorityError):
        decode_zone4_binding({**row, "migration_source": "client-choice"})
    with pytest.raises(Zone4MonsterAuthorityError):
        decode_zone4_binding({**row, "migration_version": encoded.replace("M039", "M121")})
    with pytest.raises(Zone4MonsterAuthorityError):
        decode_zone4_binding({**row, "migration_version": encoded.replace(ZONE4_PROFILE_VERSION, "wave2.zone4.normal.v2")})


def test_zone4_combat_and_presentation_are_projections_not_authority():
    binding = get_zone4_binding("M034")
    assert binding is not None
    profile = zone4_combat_profile(binding)
    assert profile.canonical_monster_id == "M034"
    assert profile.zone_key == ZONE4_KEY
    assert profile.encounter_class == "NORMAL"
    assert profile.max_hp == ZONE4_NORMAL_MAX_HP
    assert profile.stat_source == "WAVE2_ADVENTURE_ZONE4_MONSTER_CATALOG"
    assert profile.compatibility_mode == "ADVENTURE_ZONE4_EXPLICIT_PROFILE"
    row = {
        "zone_key": ZONE4_KEY,
        "migration_source": ZONE4_BINDING_SOURCE,
        "migration_version": encode_zone4_binding(binding),
        "monster_hp": 37,
        "state": "OPEN",
    }
    presentation = zone4_presentation_for_battle(row)
    assert presentation["monster_id"] == "M034"
    assert presentation["hp"] == 37
    assert presentation["max_hp"] == 100
    assert "drop_profile_id" not in presentation
    assert "reward_profile_id" not in presentation
    assert "progression" not in presentation


def test_zone4_canonical_story_content_and_lean_reuse_are_available():
    assert ZONE4_BOOKS == ("7迷霧森林", "8迷霧森林深處")
    assert ZONE4_CANONICAL_ROW_SOURCE == "app.ADVENTURE_ZONES[k11_15].books"
    assert ZONE4_CANONICAL_ROW_STATUS == "BOOK_BINDING_CANONICAL_QUESTION_DATA_NOT_TRACKED"
    assert ZONE4_STORYBOARD_AVAILABLE is True
    assert ZONE4_VO_AVAILABLE is True
    assert len(ZONE4_STORYBOARD_SCENE_PATHS) == 4
    assert all((ROOT / path).is_file() for path in ZONE4_STORYBOARD_SCENE_PATHS)
    assert all(
        len(paths) == 4 and all((ROOT / path).is_file() for path in paths)
        for paths in ZONE4_STORYBOARD_VOICE_PATHS.values()
    )
    assert len(ZONE4_REUSED_BGM_PATHS) == 2
    assert len(ZONE4_REUSED_AMBIENCE_PATHS) == 1
    assert all((ROOT / path).is_file() for path in ZONE4_REUSED_BGM_PATHS)
    assert all((ROOT / path).is_file() for path in ZONE4_REUSED_AMBIENCE_PATHS)
    assert ZONE4_NEW_ART_REQUIRED_COUNT == 0
    assert ZONE4_NEW_AUDIO_REQUIRED_COUNT == 0
    assert ZONE4_LORD_METADATA == {
        "zone_key": "k11_15",
        "lord_id": "misty_phantom_rabbit_king",
        "classification": "LORD_ONLY",
        "source": "app.ADVENTURE_BOSS_META[k11_15]",
        "normal_defeat_does_not_clear_zone": True,
    }


def test_manifest_is_valid_and_keeps_app_integration_deferred():
    manifest = json.loads(
        (ROOT / "docs/planning/wave2_zone3_zone4_integration_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["app_py_integration_deferred"] is True
    assert manifest["schema_change_required"] is False
    assert manifest["zone4"]["monster_binding_count"] == 12
    assert manifest["zone4"]["new_art_required_count"] == 0
    assert manifest["zone4"]["new_audio_required_count"] == 0
    assert "app.py" not in manifest["implementation_files"]
    assert all("incident019b" not in path.lower() for path in manifest["implementation_files"])
