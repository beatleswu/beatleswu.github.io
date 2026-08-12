"""Promote the Owner-locked Zone 2 audition bytes into canonical assets.

This is intentionally a byte-preserving, allowlisted promotion.  It consumes
only the selected V5/A3/B3/C3/current-SFX records from the local audition pack;
rejected Herder candidates and rejected Shui reaction A remain review-only.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "tools" / "e10_zone2_audio" / "_local_review" / "zone2_audio_audition"
AUDITION_EVIDENCE = "docs/planning/e10_zone2_audio_audition_gate_20260812.md"
REAUDITION = PACK / "herder_reaudition" / "reaudition_manifest.json"
SOURCE_MANIFEST = PACK / "audition_manifest.json"
DEST = ROOT / "assets" / "e10" / "audio" / "zone2"

CANONICAL_HERDER_LINE = "以前這片草原不是這樣的。自從蜂巢那邊出了問題，牠們就沒睡過一天安穩覺。"
TTS_HERDER_LINE_JIAO4 = CANONICAL_HERDER_LINE.replace("安穩覺", "安穩叫")

SELECTED_BGM = {"A3": "bgm/zone2_bgm_discovery.mp3", "B3": "bgm/zone2_bgm_escalation.mp3", "C3": "bgm/zone2_bgm_recovery.mp3"}
SELECTED_SFX = {
    "AMBIENT_GRASSLAND": "ambience/zone2_ambience_slime_plains.mp3",
    "AMBIENT_HIVE_CAVE": "ambience/zone2_ambience_hive_cave.mp3",
    "AMBIENT_PLAINS_RECOVERY": "ambience/zone2_ambience_plains_recovery.mp3",
    "SFX_FRIGHTENED_SLIME": "sfx/zone2_sfx_frightened_slime.mp3",
    "SFX_SLIME_MOVEMENT": "sfx/zone2_sfx_slime_movement.mp3",
    "AMBIENT_BEE_DISTANT": "sfx/zone2_ambient_bee_distant.mp3",
    "SFX_BEE_CLOSE": "sfx/zone2_sfx_bee_close.mp3",
    "SFX_LORD_EMERGENCE": "sfx/zone2_sfx_lord_emergence.mp3",
    "SFX_LORD_MOVEMENT": "sfx/zone2_sfx_lord_movement.mp3",
    "SFX_LORD_RUMBLE": "sfx/zone2_sfx_lord_rumble.mp3",
    "SFX_LORD_DEFEAT": "sfx/zone2_sfx_lord_defeat.mp3",
    "SFX_CROWN_IMPACT": "sfx/zone2_sfx_crown_impact.mp3",
    "SFX_ROUTE_REVEAL": "sfx/zone2_sfx_route_reveal.mp3",
    "SFX_SHUI_REACTION_B": "sfx/zone2_sfx_shui_reaction_2.mp3",
}

# English dialogue is generated with the Owner-locked Zone 1 identities and
# promoted alongside the already-locked zh-TW files.  Keeping the source in
# the review pack makes the same-byte provenance check reproducible without
# regenerating any approved Chinese audio.
EN_DIALOGUE = [
    {
        "source": "voice/english_zone2/zone2_final_shot02_beat01_en_hero.mp3",
        "output": "dialogue/zone2_final_shot02_beat01_en_hero.mp3",
        "asset_id": "ZONE2_SHOT02_HERO_EN",
        "shot": 2,
        "speaker": "hero",
        "locale": "en",
        "script_line": "They are trembling. They are not trying to attack us. They are afraid of something.",
        "voice_id": "6aOpkucJD6a4vTXyUKon",
        "provider": "ElevenLabs",
        "model": "eleven_v3",
    },
    {
        "source": "voice/english_zone2/zone2_final_shot04_beat01_en_herder.mp3",
        "output": "dialogue/zone2_final_shot04_beat01_en_herder.mp3",
        "asset_id": "ZONE2_SHOT04_HERDER_V5_EN",
        "shot": 4,
        "speaker": "herder",
        "locale": "en",
        "script_line": "This plain was not like this before. Since something went wrong at the hive, they have not slept peacefully for a single day.",
        "voice_id": "UwT0JPexcCbH107hq7i5",
        "provider": "ElevenLabs",
        "model": "eleven_v3",
    },
    {
        "source": "voice/english_zone2/zone2_final_shot09_beat01_en_hero.mp3",
        "output": "dialogue/zone2_final_shot09_beat01_en_hero.mp3",
        "asset_id": "ZONE2_SHOT09_HERO_EN",
        "shot": 9,
        "speaker": "hero",
        "locale": "en",
        "script_line": "They are not our enemies. We only encountered the same sickness.",
        "voice_id": "6aOpkucJD6a4vTXyUKon",
        "provider": "ElevenLabs",
        "model": "eleven_v3",
    },
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_records() -> tuple[dict, dict, dict]:
    source = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    reaudition = json.loads(REAUDITION.read_text(encoding="utf-8"))
    bgm = {item["id"]: item for item in source["bgm"] if item.get("generated")}
    sfx = {item["id"]: item for item in source["sfx_ambient"] if item.get("generated")}
    herder = next(item for item in reaudition["candidates"] if item["id"] == "HERDER_V5")
    return bgm, sfx, herder


def promote(source: Path, destination: Path, record: dict, **extra: object) -> dict:
    expected = record.get("sha256") or record.get("context_audio_meta", {}).get("sha256")
    if not expected:
        raise RuntimeError(f"missing source hash for {source}")
    if not source.is_file():
        raise RuntimeError(f"missing audition source {source}")
    if sha256(source) != expected:
        raise RuntimeError(f"source hash mismatch {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    actual = sha256(destination)
    if actual != expected:
        raise RuntimeError(f"promoted hash mismatch {destination}")
    result = {
        "path": destination.relative_to(ROOT).as_posix(),
        # Candidate files remain outside the runtime PR.  Keep a stable,
        # reviewable evidence reference instead of serializing a local
        # _local_review path that is intentionally not shipped.
        "source_review_path": AUDITION_EVIDENCE,
        "sha256": actual,
        "bytes": destination.stat().st_size,
    }
    result.update(extra)
    return result


def main() -> int:
    bgm, sfx, herder = load_records()
    DEST.mkdir(parents=True, exist_ok=True)
    assets: list[dict] = []

    for candidate_id, output_rel in SELECTED_BGM.items():
        record = bgm[candidate_id]
        source = PACK / record["relative_path"]
        assets.append(promote(source, DEST / output_rel, record, asset_id=candidate_id, category="bgm", phase={"A3": "FIRST_ENTRY", "B3": "BOSS_READY", "C3": "POST_CLEAR"}[candidate_id]))

    # Promote the V5 Herder context only.  The separate phrase-check sample
    # remains audition evidence and is never a runtime asset.
    herder_source = PACK / herder["context_audio_meta"]["file"]
    assets.append(promote(
        herder_source,
        DEST / "dialogue" / "zone2_final_shot04_beat01_zh_herder.mp3",
        herder,
        asset_id="ZONE2_SHOT04_HERDER_V5",
        category="dialogue",
        shot=4,
        speaker="herder",
        locale="zh-TW",
        script_line=CANONICAL_HERDER_LINE,
        tts_input=TTS_HERDER_LINE_JIAO4,
        pronunciation="jiào / ㄐㄧㄠˋ (TTS-only 覺→叫)",
        voice_id=herder["voice_id"],
        provider="ElevenLabs",
        model="eleven_v3",
    ))

    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    protagonist = {item["id"]: item for item in source_manifest.get("protagonist_lines", [])}
    for item_id, output_name, shot in (
        ("HERO_SHOT02", "zone2_final_shot02_beat01_zh_hero.mp3", 2),
        ("HERO_SHOT09", "zone2_final_shot09_beat01_zh_hero.mp3", 9),
    ):
        record = protagonist[item_id]
        source = PACK / record["relative_path"]
        assets.append(promote(source, DEST / "dialogue" / output_name, record, asset_id=f"ZONE2_SHOT{shot:02d}_HERO", category="dialogue", shot=shot, speaker="hero", locale="zh-TW", script_line=record["line"], voice_id=record["voice_id"], provider="ElevenLabs", model="eleven_v3"))

    for item in EN_DIALOGUE:
        source = PACK / item["source"]
        extra = {key: value for key, value in item.items() if key not in {"source", "output"}}
        assets.append(promote(source, DEST / item["output"], {"sha256": sha256(source)}, category="dialogue", **extra))

    for asset_id, output_rel in SELECTED_SFX.items():
        record = sfx[asset_id]
        source = PACK / record["relative_path"]
        category = "ambience" if asset_id.startswith("AMBIENT_") else "sfx"
        assets.append(promote(source, DEST / output_rel, record, asset_id=asset_id, category=category))

    package = {
        "schema_version": 1,
        "status": "OWNER_APPROVED_INTEGRATED_PENDING_REVIEW",
        "zone_key": "k21_25",
        "zone_name": "史萊姆平原",
        "script_version": "OWNER_APPROVED_V2",
        "owner_audio_lock": True,
        "audio_lock": {
            "herder_voice": "HERDER_V5_JAMES",
            "bgm_a": "A3",
            "bgm_b": "B3",
            "bgm_c": "C3",
            "shui_reaction": "SFX_SHUI_REACTION_B",
            "other_ambient_sfx": "APPROVED_AS_CURRENT",
            "sleep_phrase_pronunciation": "jiào / ㄐㄧㄠˋ",
        },
        "runtime_integrated": True,
        "source_review_pack": AUDITION_EVIDENCE,
        "assets": assets,
        "excluded_review_only": [
            "HERDER_V1",
            "HERDER_V2",
            "HERDER_V3",
            "HERDER_V4",
            "HERDER_V6",
            "SFX_SHUI_REACTION_A",
            "HERDER_V5_phrase_jiao4",
        ],
    }
    package["asset_count"] = len(assets)
    package["asset_sha256_set"] = sorted(item["sha256"] for item in assets)
    (DEST / "zone2-audio-package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dialogue = {
        "schema_version": 1,
        "status": package["status"],
        "zone_key": "k21_25",
        "script_version": "OWNER_APPROVED_V2",
        "owner_audio_lock": True,
        "assets": [item for item in assets if item["category"] == "dialogue"],
    }
    (DEST / "zone2-dialogue-assets.json").write_text(json.dumps(dialogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ZONE2_AUDIO_ASSETS_PROMOTED={len(assets)}")
    print("ZONE2_AUDIO_PACKAGE=assets/e10/audio/zone2/zone2-audio-package.json")
    print("OWNER_APPROVED_AUDIO_BYTES_PRESERVED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
