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


def test_zone4_owner_approved_dialogue_is_complete_in_both_locales():
    manifest = load_zone4_manifest()
    expected_zh = {
        "adventure.zone4.cinematic.s01.b001": "這裡就是迷霧森林嗎？霧比剛才更濃了。",
        "adventure.zone4.cinematic.s01.b002": "小水，跟緊我，我們不要走散。",
        "adventure.zone4.cinematic.s02.b001": "奇怪……我們剛才，是從哪邊進來的？",
        "adventure.zone4.cinematic.s02.b002": "我明明有記住方向，怎麼四周看起來全都一樣？",
        "adventure.zone4.cinematic.s03.b001": "等等……那邊怎麼有一個我？",
        "adventure.zone4.cinematic.s03.b002": "不對！後面還有……怎麼會有這麼多個我？",
        "adventure.zone4.cinematic.s04.b001": "他們連動作都跟我一模一樣……",
        "adventure.zone4.cinematic.s04.b002": "如果每一個看起來都是真的，我到底該相信哪一個？",
        "adventure.zone4.cinematic.s05.b001": "哪一個……才是你？還是……連你自己也不知道？",
        "adventure.zone4.cinematic.s05.b002": "眼睛看到的，就一定是真的嗎？",
        "adventure.zone4.cinematic.s06.b001": "等等……那些影子一直在變。",
        "adventure.zone4.cinematic.s06.b002": "可是小水沒有。牠一直都在同一個地方。",
        "adventure.zone4.cinematic.s06.b003": "原來我不一定要相信這些影子……我可以相信小水。",
        "adventure.zone4.cinematic.s07.b002": "我不猜了。",
        "adventure.zone4.cinematic.s07.b001": "小水。帶我走。",
        "adventure.zone4.cinematic.s07.b003": "我相信你。",
        "adventure.zone4.cinematic.s08.b001": "霧真的散了……那些假的影子也全部不見了。",
        "adventure.zone4.cinematic.s08.b002": "原來有時候一直靠自己猜，反而會越走越迷糊。",
        "adventure.zone4.cinematic.s09.b001": "咦？黑色和白色的果實？",
        "adventure.zone4.cinematic.s09.b002": "好像圍棋的黑子和白子。",
        "adventure.zone4.cinematic.s09.b003": "這是在提醒我，今天做對的選擇嗎？",
        "adventure.zone4.cinematic.s10.b001": "小水，你聽到了嗎？前面好像有鼓聲。",
        "adventure.zone4.cinematic.s10.b002": "那條路通往森林外面。",
        "adventure.zone4.cinematic.s10.b003": "走吧！看看下一個地方有什麼在等我們。",
    }
    expected_en = {
        "adventure.zone4.cinematic.s01.b001": "Is this the Misty Forest? The fog’s much thicker here.",
        "adventure.zone4.cinematic.s01.b002": "Stay close, Shui. We don’t want to get separated.",
        "adventure.zone4.cinematic.s02.b001": "That’s strange… which way did we come in?",
        "adventure.zone4.cinematic.s02.b002": "I was sure I remembered the way. Why does everything look the same now?",
        "adventure.zone4.cinematic.s03.b001": "Wait… is that me over there?",
        "adventure.zone4.cinematic.s03.b002": "No—there’s another one! Why are there so many of me?",
        "adventure.zone4.cinematic.s04.b001": "They’re even moving exactly like me…",
        "adventure.zone4.cinematic.s04.b002": "If they all look real, how am I supposed to know which one to trust?",
        "adventure.zone4.cinematic.s05.b001": "Which one… is the real you? Or… don’t you even know?",
        "adventure.zone4.cinematic.s05.b002": "Can you always trust what your eyes tell you?",
        "adventure.zone4.cinematic.s06.b001": "Hang on… those copies keep changing.",
        "adventure.zone4.cinematic.s06.b002": "But Shui hasn’t. Shui’s been right there the whole time.",
        "adventure.zone4.cinematic.s06.b003": "I don’t have to trust these shadows. I can trust Shui.",
        "adventure.zone4.cinematic.s07.b002": "I’m done guessing.",
        "adventure.zone4.cinematic.s07.b001": "Shui. Lead the way.",
        "adventure.zone4.cinematic.s07.b003": "I trust you.",
        "adventure.zone4.cinematic.s08.b001": "The fog really is clearing… and all those fake copies are gone.",
        "adventure.zone4.cinematic.s08.b002": "Maybe trying to work everything out on my own just made me more confused.",
        "adventure.zone4.cinematic.s09.b001": "Huh? A black fruit and a white one?",
        "adventure.zone4.cinematic.s09.b002": "They look just like black and white Go stones.",
        "adventure.zone4.cinematic.s09.b003": "Maybe they’re here to remind me that I made the right choice.",
        "adventure.zone4.cinematic.s10.b001": "Shui, can you hear that? I think there are drums up ahead.",
        "adventure.zone4.cinematic.s10.b002": "That path looks like it leads out of the forest.",
        "adventure.zone4.cinematic.s10.b003": "Come on! Let’s see what’s waiting for us next.",
    }
    assert manifest["story"]["ownerApprovedDialogueLineCount"] == 24
    assert manifest["story"]["existingCanonicalZhLineCount"] == 3
    assert manifest["story"]["ownerApprovedNewZhLineCount"] == 21
    assert manifest["locales"]["zh-TW"]["status"] == "OWNER_APPROVED_DIALOGUE_COMPLETE"
    assert manifest["locales"]["en-US"]["status"] == "OWNER_APPROVED_DIALOGUE_COMPLETE"
    assert manifest["locales"]["zh-TW"]["dialogue"] == expected_zh
    assert manifest["locales"]["en-US"]["dialogue"] == expected_en
    for key, value in expected_zh.items():
        assert localized_dialogue("zh-TW", key) == value
    for key, value in expected_en.items():
        assert localized_dialogue("en-US", key) == value
    assert localized_dialogue("fr-FR", next(iter(expected_zh))) is None


def test_zone4_canonical_zh_lines_remain_byte_exact():
    manifest = load_zone4_manifest()
    expected = {
        "adventure.zone4.cinematic.s02.b001": "奇怪……我們剛才，是從哪邊進來的？",
        "adventure.zone4.cinematic.s05.b001": "哪一個……才是你？還是……連你自己也不知道？",
        "adventure.zone4.cinematic.s07.b001": "小水。帶我走。",
    }
    assert {key: manifest["locales"]["zh-TW"]["dialogue"][key] for key in expected} == expected


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
