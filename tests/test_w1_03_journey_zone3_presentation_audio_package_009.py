"""Bounded contract tests for the Zone 3 presentation-audio package."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "assets" / "e10" / "audio" / "zone3" / "zone3-presentation-audio-manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_zone3_presentation_audio_counts_and_roles_are_complete() -> None:
    manifest = _manifest()
    records = manifest["CUES"]
    new_records = [record for record in records if record["SOURCE_CLASS"] == "AUTHORIZED_NEW_ASSET"]
    reuse_records = [record for record in records if record["SOURCE_CLASS"] == "AUTHORIZED_REUSE"]

    assert len(records) == 18
    assert len(new_records) == 16
    assert len(reuse_records) == 2
    assert Counter(record["CATEGORY"] for record in new_records) == Counter(
        {"ambience": 5, "event_sfx": 7, "transition": 1, "bgm": 3}
    )
    assert manifest["COUNTS"]["NEW_NON_DIALOGUE_AUDIO_COUNT_EXCLUDING_BGM"] == 13
    assert manifest["COUNTS"]["STONE_SHARD_MAGICAL_SFX_COUNT"] == 0
    assert manifest["COUNTS"]["SHUI_HUMAN_VOICE_COUNT"] == 0
    assert {record["ROLE"] for record in new_records} >= {
        "CAVE_ROOM_TONE",
        "DISTANT_CAVE_WIND",
        "FAMILY_ACTIVITY",
        "TRIAL_TENSION",
        "FRAGILE_TRUCE",
        "REFUGEE_FOOTSTEPS",
        "BELONGINGS_MOVEMENT",
        "WATER_DRIP",
        "ROCKFALL",
        "BLOCKED_WATER_FLOW",
        "CENTURION_ARMOR",
        "CENTURION_SPEAR_PLANT",
        "MISTY_FOREST_WIND_TRANSITION",
    }


def test_zone3_presentation_audio_ids_paths_and_hashes_are_unique_and_valid() -> None:
    manifest = _manifest()
    records = manifest["CUES"]
    assert len({record["CUE_ID"] for record in records}) == len(records)
    assert len({record["OUTPUT_PATH"] for record in records}) == len(records)

    for record in records:
        path = ROOT / Path(record["OUTPUT_PATH"])
        assert path.is_file(), record["CUE_ID"]
        data = path.read_bytes()
        audio = MP3(path)
        duration_ms = int(round(float(audio.info.length) * 1000))
        assert len(data) == record["BYTES"]
        assert duration_ms == record["DURATION_MS"]
        assert duration_ms > 0
        assert hashlib.sha256(data).hexdigest() == record["SHA256"]
        assert len(record["SHA256"]) == 64
        assert record["OUTPUT_FORMAT"] == "audio/mpeg"


def test_zone3_presentation_audio_preserves_runtime_and_mute_boundaries() -> None:
    manifest = _manifest()
    assert manifest["AUDIO_SOURCE_AUTHORITY"]["AUTHORIZED_PRESENTATION_AUDIO_PIPELINE_AVAILABLE"] is True
    assert manifest["ARCHITECTURE"]["JOURNEY_RUNTIME_BINDING"] == "NOT_PERFORMED"
    assert manifest["ARCHITECTURE"]["NEW_VOLUME_CONTROL_UI"] is False
    assert manifest["ARCHITECTURE"]["GLOBAL_MUTE_COMPATIBLE"] is True
    assert manifest["ARCHITECTURE"]["SOURCE_ART_MUTATED"] is False

    reuse = {record["ROLE"]: record for record in manifest["CUES"] if record["SOURCE_CLASS"] == "AUTHORIZED_REUSE"}
    assert reuse["SHUI_REACTION"]["OUTPUT_PATH"].endswith("zone2_sfx_shui_reaction_2.mp3")
    assert reuse["STONE_PHYSICAL_HANDOFF"]["OUTPUT_PATH"].endswith("zone1_sfx_shot07_stone_placement.mp3")
    assert reuse["SHUI_REACTION"]["OWNER_AUDIO_LOCK"] is True
    assert reuse["STONE_PHYSICAL_HANDOFF"]["OWNER_AUDIO_LOCK"] is True
