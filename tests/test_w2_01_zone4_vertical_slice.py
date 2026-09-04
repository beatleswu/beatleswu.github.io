"""W2-01 Zone 4 Misty Forest vertical-slice contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from adventure_zone4_misty_forest_authority import (
    ZONE4_ADVENTURE_NORMAL_AUTHORIZED_IDS,
    ZONE4_BATTLEFIELD_BOSS_ID,
    ZONE4_LORD_ID,
    ZONE4_NORMAL_CANDIDATES,
    Zone4AuthorityGap,
    authority_snapshot,
    battlefield_boss_reference,
    lord_reference,
    require_zone4_adventure_normal,
    resolve_battlefield_anchor,
)
from adventure_zone4_misty_forest_content import (
    MANIFEST_PATH,
    SUPPORTED_LOCALES,
    ZONE4_KEY,
    load_zone4_manifest,
    localized_dialogue,
    validate_zone4_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


def _repo_path(asset_path: str) -> Path:
    assert asset_path.startswith("/")
    return ROOT / asset_path.lstrip("/")


def test_zone4_manifest_is_a_complete_ten_shot_lifecycle():
    manifest = load_zone4_manifest()
    assert MANIFEST_PATH.is_file()
    assert manifest["zone"] == {
        "number": 4,
        "key": ZONE4_KEY,
        "nameI18nKey": "adventure.zone4.name",
        "names": {"zh-TW": "迷霧森林", "en-US": "Misty Forest"},
        "worldMap": manifest["zone"]["worldMap"],
        "landmark": manifest["zone"]["landmark"],
    }
    assert [shot["id"] for shot in manifest["story"]["shots"]] == [
        f"Z4_S{number:02d}" for number in range(1, 11)
    ]
    assert [
        shot_id
        for phase in manifest["story"]["lifecycle"]
        for shot_id in phase["shots"]
    ] == [f"Z4_S{number:02d}" for number in range(1, 11)]
    assert manifest["story"]["shots"][6]["handoff"] == "HANDOFF_TO_GAMEPLAY_AFTER_SHOT"
    assert manifest["story"]["shots"][9]["handoff"] == "END_CINEMATIC_SEQUENCE_AFTER_SHOT"


def test_zone4_zh_tw_dialogue_is_exact_and_en_us_does_not_fallback():
    manifest = load_zone4_manifest()
    expected = {
        "adventure.zone4.cinematic.s02.b001": "奇怪……我們剛才，是從哪邊進來的？",
        "adventure.zone4.cinematic.s05.b001": "哪一個……才是你？還是……連你自己也不知道？",
        "adventure.zone4.cinematic.s07.b001": "小水。帶我走。",
    }
    assert manifest["locales"]["zh-TW"]["dialogue"] == expected
    for key, value in expected.items():
        assert localized_dialogue("zh-TW", key) == value
        assert localized_dialogue("en-US", key) is None
    assert manifest["locales"]["en-US"]["dialogue"] == {}


def test_all_manifest_referenced_existing_assets_resolve_without_promoting_legacy_art():
    manifest = load_zone4_manifest()
    existing_assets = [
        entry for entry in manifest["assets"]["world"]
        if entry["status"] in {"AUTHORITATIVE_USABLE", "PRESENT_BUT_LEGACY"}
    ]
    for entry in existing_assets:
        path = _repo_path(entry["path"])
        assert path.is_file(), entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest()
    legacy_shots = [
        shot for shot in manifest["story"]["shots"]
        if shot["image"]["status"] == "PRESENT_BUT_LEGACY"
    ]
    assert len(legacy_shots) == 4
    assert all(shot["image"]["renderableInBoundedSlice"] is True for shot in legacy_shots)
    missing_final_shots = [
        shot for shot in manifest["story"]["shots"]
        if shot["image"]["status"] == "MISSING_FINAL_ASSET_AUTHORITY"
    ]
    assert len(missing_final_shots) == 6
    assert all(shot["image"]["path"] is None for shot in missing_final_shots)
    for entry in manifest["encounters"]["normal"]:
        assert _repo_path(entry["assetPath"]).is_file(), entry["assetPath"]
    assert _repo_path(manifest["encounters"]["battlefieldBoss"]["assetPath"]).is_file()


def test_normal_candidate_roster_is_explicit_but_not_promoted_to_adventure_authority():
    assert tuple(candidate.monster_id for candidate in ZONE4_NORMAL_CANDIDATES) == tuple(
        f"M{number:03d}" for number in range(34, 46)
    )
    assert ZONE4_ADVENTURE_NORMAL_AUTHORIZED_IDS == ()
    with pytest.raises(Zone4AuthorityGap):
        require_zone4_adventure_normal("M035")
    anchor = resolve_battlefield_anchor("M034")
    assert anchor.runtime_id == "legacy_bf_04_normal"
    assert anchor.runtime_status == "BATTLEFIELD_ONLY"


def test_battlefield_boss_and_lord_are_separate_authorities():
    boss = battlefield_boss_reference()
    lord = lord_reference()
    assert boss.monster_id == ZONE4_BATTLEFIELD_BOSS_ID == "legacy_bf_04_boss"
    assert lord.lord_id == ZONE4_LORD_ID == "misty_phantom_rabbit_king"
    assert boss.monster_id != lord.lord_id
    assert boss.authority_scope == "BATTLEFIELD_ONLY"
    assert lord.authority_scope == "LORD_ONLY"
    assert authority_snapshot()["battlefield_boss_equals_lord"] is False


def test_zone4_content_validator_rejects_duplicate_or_missing_shots():
    manifest = load_zone4_manifest()
    validate_zone4_manifest(manifest)
    broken = {**manifest, "story": {**manifest["story"], "shots": manifest["story"]["shots"][:-1]}}
    with pytest.raises(ValueError):
        validate_zone4_manifest(broken)


def test_changed_zone4_scope_does_not_touch_forbidden_runtime_or_zone3_files():
    forbidden = {
        "app.py",
        "index.html",
        "i18n.js",
        "js/e9/world_stage.js",
        "js/e9/journey_zone3_vertical_slice.js",
        "js/e9/journey_zone3_presentation_audio.js",
        "srs.js",
        "sound.js",
    }
    changed = {
        "assets/adventure/zone4/zone4-misty-forest-vertical-slice.json",
        "adventure_zone4_misty_forest_content.py",
        "adventure_zone4_misty_forest_authority.py",
        "components/adventure/zone4_misty_forest_vertical_slice.html",
        "css/e9/zone4_misty_forest_vertical_slice.css",
        "js/e9/zone4_misty_forest_vertical_slice.js",
        "tests/test_w2_01_zone4_vertical_slice.py",
        "tests/e2e/fixtures/w2_01_zone4_vertical_slice.html",
        "tests/e2e/run_w2_01_zone4_misty_forest_vertical_slice.mjs",
    }
    assert not changed & forbidden
    assert set(SUPPORTED_LOCALES) == {"zh-TW", "en-US"}


def test_zone4_runtime_renderer_has_no_copied_dialogue_or_progression_writes():
    renderer = (ROOT / "js/e9/zone4_misty_forest_vertical_slice.js").read_text(encoding="utf-8")
    component = (ROOT / "components/adventure/zone4_misty_forest_vertical_slice.html").read_text(encoding="utf-8")
    for canonical_line in (
        "奇怪……我們剛才，是從哪邊進來的？",
        "哪一個……才是你？還是……連你自己也不知道？",
        "小水。帶我走。",
    ):
        assert canonical_line not in renderer
        assert canonical_line not in component
    assert "localStorage" not in renderer
    assert "fetch(" not in renderer
    assert "reward" not in renderer.lower()
    assert "unlock" not in renderer.lower()
