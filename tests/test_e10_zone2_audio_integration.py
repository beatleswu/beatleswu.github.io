"""Owner-locked Zone 2 final art/audio integration contracts."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
PACKAGE_PATH = ROOT / "assets" / "e10" / "audio" / "zone2" / "zone2-audio-package.json"
PACKAGE = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_owner_audio_lock_and_selected_identity_are_recorded():
    lock = PACKAGE["audio_lock"]
    assert PACKAGE["owner_audio_lock"] is True
    assert lock["herder_voice"] == "HERDER_V5_JAMES"
    assert lock["bgm_a"] == "A3"
    assert lock["bgm_b"] == "B3"
    assert lock["bgm_c"] == "C3"
    assert lock["shui_reaction"] == "SFX_SHUI_REACTION_B"
    assert lock["sleep_phrase_pronunciation"] == "jiào / ㄐㄧㄠˋ"
    assert PACKAGE["runtime_integrated"] is True


def test_all_ten_final_shots_are_wired_in_attachment_order():
    for shot in range(1, 11):
        assert (ROOT / "assets" / "storyboards" / f"e10_z2_shot{shot:02d}.webp").is_file()
    slots = INDEX[INDEX.index("function _zone2CinematicPhaseSlots"):INDEX.index("\nfunction getIntroFilmLocaleConfig")]
    assert "const image = (shot)" in slots
    assert "bossReadyTimeline" in slots
    assert "postClearTimeline" in slots
    assert "shot(5," in slots and "shot(6," in slots and "shot(7," in slots
    assert "shot(8," in slots and "shot(9," in slots and "shot(10," in slots


def test_owner_v2_dialogue_and_silence_contract_are_integrated():
    slots = INDEX[INDEX.index("function _zone2CinematicPhaseSlots"):INDEX.index("\nfunction getIntroFilmLocaleConfig")]
    assert "e10.zone2.shot02.dialogue" in slots
    assert "e10.zone2.shot04.dialogue" in slots
    assert "e10.zone2.shot09.dialogue" in slots
    # Shot 6/7 remain visual/creature-vocal beats; the Swarm Lord has no
    # human dialogue in the locked audio treatment.
    assert "e10.zone2.shot06.alt" in slots
    assert "lordRumble" in slots


def test_every_promoted_audio_asset_exists_and_matches_manifest():
    assets = PACKAGE["assets"]
    assert len(assets) == 23
    assert all((ROOT / item["path"]).is_file() for item in assets)
    assert all(_sha(ROOT / item["path"]) == item["sha256"] for item in assets)
    assert len({item["sha256"] for item in assets}) == len(assets)


def test_bilingual_dialogue_uses_locked_voice_identities_and_exact_locales():
    dialogue = [item for item in PACKAGE["assets"] if item["category"] == "dialogue"]
    assert {item["locale"] for item in dialogue} == {"zh-TW", "en"}
    english = {item["asset_id"]: item for item in dialogue if item["locale"] == "en"}
    assert set(english) == {"ZONE2_SHOT02_HERO_EN", "ZONE2_SHOT04_HERDER_V5_EN", "ZONE2_SHOT09_HERO_EN"}
    assert english["ZONE2_SHOT02_HERO_EN"]["voice_id"] == "6aOpkucJD6a4vTXyUKon"
    assert english["ZONE2_SHOT09_HERO_EN"]["voice_id"] == "6aOpkucJD6a4vTXyUKon"
    assert english["ZONE2_SHOT04_HERDER_V5_EN"]["voice_id"] == "UwT0JPexcCbH107hq7i5"
    assert all(item["model"] == "eleven_v3" for item in english.values())


def test_rejected_candidates_and_shui_reaction_a_stay_out_of_runtime_package():
    excluded = set(PACKAGE["excluded_review_only"])
    assert {"HERDER_V1", "HERDER_V2", "HERDER_V3", "HERDER_V4", "HERDER_V6"} <= excluded
    assert "SFX_SHUI_REACTION_A" in excluded
    runtime_ids = {item["asset_id"] for item in PACKAGE["assets"]}
    assert not runtime_ids & {"HERDER_V1", "HERDER_V2", "HERDER_V3", "HERDER_V4", "HERDER_V6", "SFX_SHUI_REACTION_A"}


def test_zone2_audio_runtime_uses_zone2_package_and_phase_specific_cues():
    assert "const ZONE2_AUDIO = Object.freeze" in INDEX
    assert "bgmBossReady" in INDEX
    assert "bgmPostClear" in INDEX
    assert "ambienceBossReady" in INDEX
    assert "ambiencePostClear" in INDEX
    assert "ZONE2_AUDIO.sfx.routeReveal" in INDEX
    assert "ZONE2_AUDIO.sfx.lordEmergence" in INDEX
    assert "ZONE2_AUDIO.sfx.lordDefeat" in INDEX
    assert "dialogueHeroShot02En" in INDEX
    assert "dialogueHerderShot04En" in INDEX
    assert "dialogueHeroShot09En" in INDEX
