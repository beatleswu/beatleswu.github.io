from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APPROVED = "a0b2a4de0bd75bf0b221d5c5c2b95c407251f606"
PARENT = "530271be4f3720e15e52e4b1e1796db3cd5df514"
LIVE = "70f7ed5067e8163eb7bc4cf1cfc664baec06f496"


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def git_blob(revision: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", f"{revision}:{path}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def git_json(revision: str, path: str) -> dict:
    raw = subprocess.check_output(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    return json.loads(raw)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def asset_records(matrix: dict) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for beat in matrix["beats"]:
        visual = beat["visual"]
        records[f"visual:{visual['asset_id']}"] = visual
        for line in beat.get("dialogue", []):
            for voice in line["voice_by_locale"].values():
                records[voice["identity_key"]] = voice
        audio = beat.get("audio") or {}
        for key in ("bgm", "ambience", "shui", "transition"):
            asset = audio.get(key)
            if asset:
                records[asset["identity_key"]] = asset
        for binding in audio.get("sfx_event_bindings", []):
            records[binding["asset"]["identity_key"]] = binding["asset"]
    return records


def test_exact_004_blobs_are_reconciled_without_content_drift():
    approved_matrix = git_json(APPROVED, "ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    current_matrix = load("ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    assert current_matrix == approved_matrix

    approved_manifest = git_json(APPROVED, "ZONE4_004_RUNTIME_MANIFEST.json")
    assert load("ZONE4_004_RUNTIME_MANIFEST.json") == approved_manifest

    approved_files = subprocess.check_output(
        ["git", "diff", "--name-only", f"{PARENT}..{APPROVED}"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    assert len(approved_files) == 12
    for path in approved_files:
        assert git_blob(LIVE, path) is None
        assert git_blob(APPROVED, path) == subprocess.check_output(
            ["git", "hash-object", path], cwd=ROOT, text=True
        ).strip()


def test_owner_final_assets_match_approved_blobs_and_manifest_hashes():
    matrix = load("ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    records = asset_records(matrix)
    assert len(records) == 139
    assert sum(1 for key in records if key.startswith("visual:")) == 28
    assert sum(1 for key in records if not key.startswith("visual:")) == 111

    for record in records.values():
        path = record["path"]
        local_path = ROOT / path
        assert local_path.is_file(), path
        assert local_path.stat().st_size == record["byte_size"], path
        assert digest(local_path) == record["sha256"], path
        assert subprocess.check_output(
            ["git", "hash-object", path], cwd=ROOT, text=True
        ).strip() == git_blob(APPROVED, path)
        assert git_blob(LIVE, path) is None


def test_dialogue_and_runtime_semantics_match_approved_candidate():
    approved = git_json(APPROVED, "ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    current = load("ZONE4_004_LORD_STATE_BINDING_MATRIX.json")
    assert current["main_story_order"] == approved["main_story_order"]
    assert current["main_story_order"] == [
        *[f"Z4_S1_{i:02d}" for i in range(1, 9)],
        *[f"Z4_S2_{i:02d}" for i in range(1, 9)],
        *[f"Z4_S3_{i:02d}" for i in range(1, 7)],
    ]
    assert not any(item.startswith("Z4_LORD_") for item in current["main_story_order"])
    assert current["tracks"]["lord_trial"]["linear_order"] is False
    assert current["lord_state_machine"]["linear_story_exclusion"][
        "s3_06_to_lord_01_auto_advance"
    ] is False
    assert current["counts"]["dialogue_line_ids"] == 46
    assert current["counts"]["localized_dialogue_records"] == 92
    assert current["counts"]["audio_assets"] == 111
    assert current["locale_policy"]["cross_locale_fallback"] is False
    assert current["locale_policy"]["en_us_fallback"] is False
    assert current["locale_policy"]["shui_nonverbal"] is True
