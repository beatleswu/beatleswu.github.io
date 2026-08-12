"""Owner-locked Zone 2 V3 bilingual audio integration contracts."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
PACKAGE_PATH = ROOT / "assets" / "e10" / "audio" / "zone2" / "zone2-audio-package.json"
PACKAGE = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slots() -> str:
    return INDEX[INDEX.index("function _zone2CinematicPhaseSlots") : INDEX.index("\nfunction getIntroFilmLocaleConfig")]


def test_owner_v3_audio_lock_and_selected_identity_are_recorded():
    lock = PACKAGE["audio_lock"]
    assert PACKAGE["owner_audio_lock"] is True
    assert PACKAGE["script_version"] == "OWNER_DIALOGUE_V3"
    assert lock["herder_voice_zh_tw"] == "BrbEfHMQu0fyclQR7lfh"
    assert lock["herder_voice_en"] == "dqdOhmL2BvMSx2KtSAtN"
    assert lock["herder_en_audio_source"] == "CLEAN_RETAKE"
    assert lock["hero_voice_zh_tw"] == "XXxvxx0YUt8icTEFE3c6"
    assert lock["hero_voice_en"] == "6aOpkucJD6a4vTXyUKon"
    assert lock["bgm_a"] == "A3"
    assert lock["bgm_b"] == "B3"
    assert lock["bgm_c"] == "C3"
    assert lock["shui_reaction"] == "SFX_SHUI_REACTION_B"
    assert lock["sleep_phrase_pronunciation"] == "jiào / ㄐㄧㄠˋ"
    assert PACKAGE["runtime_integrated"] is True


def test_all_ten_final_shots_and_phase_order_are_wired():
    for shot in range(1, 11):
        assert (ROOT / "assets" / "storyboards" / f"e10_z2_shot{shot:02d}.webp").is_file()
    slots = _slots()
    assert "const image = (shot)" in slots
    assert "timeline" in slots and "bossReadyTimeline" in slots and "postClearTimeline" in slots
    for shot in range(1, 11):
        assert f"shot({shot}," in slots
    assert slots.index("shot(4,") < slots.index("bossReadyTimeline")
    assert slots.index("shot(7,") < slots.index("postClearTimeline")


def test_owner_v3_dialogue_and_silence_contract_are_integrated():
    slots = _slots()
    for key in (
        "e10.zone2.shot02.line01", "e10.zone2.shot02.line02",
        "e10.zone2.shot03.line01", "e10.zone2.shot03.line05",
        "e10.zone2.shot04.line01", "e10.zone2.shot04.line05",
        "e10.zone2.shot07.line01", "e10.zone2.shot07.line03",
        "e10.zone2.shot09.line01", "e10.zone2.shot09.line02",
        "e10.zone2.shot10.line01",
    ):
        assert key in slots
    assert "e10.zone2.shot02.dialogue" not in slots
    assert "e10.zone2.shot04.dialogue" not in slots
    assert "e10.zone2.shot09.dialogue" not in slots
    assert "shot(5," in slots and "shot(6," in slots
    assert "lordRumble" in slots


def test_every_promoted_audio_asset_exists_and_matches_manifest():
    assets = PACKAGE["assets"]
    assert len(assets) == 53
    assert all((ROOT / item["path"]).is_file() for item in assets)
    assert all(_sha(ROOT / item["path"]) == item["sha256"] for item in assets)
    assert len({item["sha256"] for item in assets}) == len(assets)


def test_bilingual_dialogue_uses_locked_voice_identities_and_exact_locales():
    dialogue = [item for item in PACKAGE["assets"] if item["category"] == "dialogue"]
    assert len(dialogue) == 36
    assert {item["locale"] for item in dialogue} == {"zh-TW", "en"}
    assert sum(item["locale"] == "zh-TW" for item in dialogue) == 18
    assert sum(item["locale"] == "en" for item in dialogue) == 18
    assert {item["voice_id"] for item in dialogue if item["locale"] == "zh-TW" and item["speaker"] == "hero"} == {"XXxvxx0YUt8icTEFE3c6"}
    assert {item["voice_id"] for item in dialogue if item["locale"] == "en" and item["speaker"] == "hero"} == {"6aOpkucJD6a4vTXyUKon"}
    assert {item["voice_id"] for item in dialogue if item["locale"] == "zh-TW" and item["speaker"] == "herder"} == {"BrbEfHMQu0fyclQR7lfh"}
    assert {item["voice_id"] for item in dialogue if item["locale"] == "en" and item["speaker"] == "herder"} == {"dqdOhmL2BvMSx2KtSAtN"}
    assert all(item["model"] == "eleven_v3" for item in dialogue)


def test_rejected_candidates_and_shui_reaction_a_stay_out_of_runtime_package():
    excluded = set(PACKAGE["excluded_review_only"])
    assert {"HERDER_V1", "HERDER_V2", "HERDER_V3", "HERDER_V4", "HERDER_V6"} <= excluded
    assert "SFX_SHUI_REACTION_A" in excluded
    runtime_ids = {item["asset_id"] for item in PACKAGE["assets"]}
    assert not runtime_ids & {"HERDER_V1", "HERDER_V2", "HERDER_V3", "HERDER_V4", "HERDER_V6", "SFX_SHUI_REACTION_A"}


def test_zone2_audio_runtime_uses_package_phase_cues_and_ducking():
    assert "const ZONE2_AUDIO = Object.freeze" in INDEX
    assert "ZONE2_AUDIO.dialogue.zh" in INDEX
    assert "ZONE2_AUDIO.dialogue.en" in INDEX
    assert "bgmBossReady" in INDEX and "bgmPostClear" in INDEX
    assert "ambienceBossReady" in INDEX and "ambiencePostClear" in INDEX
    assert "ZONE2_AUDIO.sfx.routeReveal" in INDEX
    assert "ZONE2_AUDIO.sfx.lordEmergence" in INDEX
    assert "ZONE2_AUDIO.sfx.lordDefeat" in INDEX
    assert "_setIntroBgmDucked" in INDEX


def test_superseded_sparse_script_is_not_in_runtime_or_governance_records():
    runtime = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("index.html", "i18n.js"))
    package = PACKAGE_PATH.read_text(encoding="utf-8")
    assert "same sickness" not in runtime.lower()
    assert "同一場病" not in runtime
    assert "same sickness" not in package.lower()
    assert "同一場病" not in package
