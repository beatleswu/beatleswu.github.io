from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def test_exact_story_order_and_lord_exclusion():
    matrix = load("ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    expected = (
        [f"Z4_S1_{i:02d}" for i in range(1, 9)]
        + [f"Z4_S2_{i:02d}" for i in range(1, 9)]
        + [f"Z4_S3_{i:02d}" for i in range(1, 7)]
    )
    assert matrix["main_story_order"] == expected
    assert len(matrix["main_story_order"]) == 22
    assert not any(beat_id.startswith("Z4_LORD_") for beat_id in matrix["main_story_order"])
    assert matrix["tracks"]["lord_trial"]["linear_order"] is False
    assert matrix["lord_state_machine"]["linear_story_exclusion"]["s3_06_to_lord_01_auto_advance"] is False


def test_state_bindings_and_authoritative_line_coverage():
    matrix = load("ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    states = matrix["lord_state_machine"]["lord_states"]
    assert states["challenge_entry"]["visual_id"] == "Z4-LORD-01"
    assert states["challenge_domain"]["visual_id"] == "Z4-LORD-02"
    assert states["challenge_active"]["visual_id"] == "Z4-LORD-06"
    assert states["failure_retraining"]["visual_id"] == "Z4-LORD-03"
    assert states["success_background"]["visual_id"] == "Z4-LORD-04"
    assert states["success_portrait"]["visual_id"] == "Z4-LORD-05"
    assert states["challenge_domain"]["dialogue_context"] == "LORD_PRE"
    assert states["failure_retraining"]["dialogue_context"] == "LORD_FAIL"
    assert matrix["counts"] == {
        "visual_assets": 28,
        "main_story_visuals": 22,
        "lord_state_visuals": 6,
        "dialogue_line_ids": 46,
        "localized_dialogue_records": 92,
        "audio_assets": 111,
        "main_story_beats": 22,
        "lord_state_bindings": 6,
        "story_beats_total": 28,
        "missing_bindings": 0,
        "duplicate_bindings": 0,
    }
    lines = [line_id for beat in matrix["beats"] for line_id in beat["dialogue_line_ids"]]
    assert len(lines) == 46
    assert len(set(lines)) == 46
    localized_records = [
        (line["line_id"], locale)
        for beat in matrix["beats"]
        for line in beat["dialogue"]
        for locale in ("zh-TW", "en-GB")
        if locale in line["text"] and locale in line["voice_by_locale"]
    ]
    assert len(localized_records) == 92


def test_visual_and_audio_hashes_are_unchanged_from_003():
    old = load("ZONE4_STORY_BEAT_BINDING_MATRIX.json")
    new = load("ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    old_beats = {beat["beat_id"]: beat for beat in old["beats"]}
    new_beats = {beat["beat_id"]: beat for beat in new["beats"]}
    assert set(old_beats) == set(new_beats)
    assert {
        beat_id: old_beats[beat_id]["dialogue"] for beat_id in old_beats
    } == {
        beat_id: new_beats[beat_id]["dialogue"] for beat_id in new_beats
    }
    old_visuals = {beat["visual"]["asset_id"]: beat["visual"] for beat in old["beats"]}
    new_visuals = {beat["visual"]["asset_id"]: beat["visual"] for beat in new["beats"]}
    assert set(old_visuals) == set(new_visuals)
    for asset_id, old_asset in old_visuals.items():
        new_asset = new_visuals[asset_id]
        assert new_asset["sha256"] == old_asset["sha256"]
        path = ROOT / new_asset["path"]
        assert path.stat().st_size == new_asset["byte_size"]
        assert digest(path) == new_asset["sha256"]

    old_audio = {}
    for beat in old["beats"]:
        for line in beat.get("dialogue", []):
            for voice in line["voice_by_locale"].values():
                old_audio[voice["identity_key"]] = voice
        audio = beat.get("audio") or {}
        for asset in [audio.get("bgm"), audio.get("ambience"), audio.get("shui"), audio.get("transition")]:
            if asset:
                old_audio[asset["identity_key"]] = asset
        for binding in audio.get("sfx_event_bindings", []):
            old_audio[binding["asset"]["identity_key"]] = binding["asset"]
    new_audio = {}
    for beat in new["beats"]:
        for line in beat.get("dialogue", []):
            for voice in line["voice_by_locale"].values():
                new_audio[voice["identity_key"]] = voice
        audio = beat.get("audio") or {}
        for asset in [audio.get("bgm"), audio.get("ambience"), audio.get("shui"), audio.get("transition")]:
            if asset:
                new_audio[asset["identity_key"]] = asset
        for binding in audio.get("sfx_event_bindings", []):
            new_audio[binding["asset"]["identity_key"]] = binding["asset"]
    assert len(old_audio) == len(new_audio) == 111
    assert {key: asset["sha256"] for key, asset in old_audio.items()} == {key: asset["sha256"] for key, asset in new_audio.items()}
    for asset in new_audio.values():
        path = ROOT / asset["path"]
        assert path.stat().st_size == asset["byte_size"]
        assert digest(path) == asset["sha256"]


def test_runtime_manifest_and_preview_use_004_contract():
    manifest = load("ZONE4_004_RUNTIME_MANIFEST.json")
    assert manifest["counts"]["main_story_visuals"] == 22
    assert manifest["counts"]["lord_state_visuals"] == 6
    assert manifest["controls"]["auto_play_stops_at_lord_entry"] is True
    assert manifest["controls"]["lord_state_assets_never_flattened"] is True
    source = (ROOT / "zone4_owner_story_runtime.html").read_text(encoding="utf-8")
    assert "ZONE4_004_LORD_STATE_BINDING_MATRIX.json" in source
    assert "ZONE4_004_RUNTIME_MANIFEST.json" in source
    assert "SIMULATE FAIL" in source
    assert "SIMULATE PASS" in source
    runtime = (ROOT / "js/e10/zone4_owner_story_runtime.js").read_text(encoding="utf-8")
    assert "enterLordTrial" in runtime
    assert "simulateFail" in runtime
    assert "simulatePass" in runtime
    assert "autoplay_enter_lord_trial" in runtime
    assert "S3_06" not in runtime
    assert "en-US" not in runtime


def test_node_lord_state_playback_acceptance():
    script = ROOT / "tests/e2e/run_zone4_004_lord_state_binding.mjs"
    result = subprocess.run(["node", str(script)], cwd=ROOT, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "PASS"
    assert payload["main_story_order_exact"] is True
    assert payload["lord_assets_in_linear_main"] is False
    assert payload["s2_08_enters_lord"] is True
    assert payload["fail_visual"] == "Z4-LORD-03"
    assert payload["pass_visuals"] == ["Z4-LORD-04", "Z4-LORD-05"]
    assert payload["pass_to"] == "Z4_S3_01"
    assert payload["s3_06_to_lord_auto_advance"] is False
    assert payload["auto_play_stops_at"] == "Z4-LORD-01"
    assert payload["max_voice_overlap"] <= 1
    assert payload["max_sfx_overlap"] <= 1
