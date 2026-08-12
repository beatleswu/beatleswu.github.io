"""Promote the Owner-locked Zone 2 V3 dialogue bytes and manifests.

This narrow helper copies only the approved Hero and Herder dialogue clips
from the retained audition worktrees.  BGM, ambience, SFX, art, and gameplay
assets are read from the current package and are never regenerated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ZH_HERO = "XXxvxx0YUt8icTEFE3c6"
EN_HERO = "6aOpkucJD6a4vTXyUKon"
ZH_HERDER = "BrbEfHMQu0fyclQR7lfh"
EN_HERDER = "dqdOhmL2BvMSx2KtSAtN"

LINES = {
    (2, 1): ("hero", "咦？別怕，我不會傷害你。", "Oh? Don't be afraid. I won't hurt you."),
    (2, 2): ("hero", "……水靈，你看。牠不是想攻擊，牠是在發抖。", "...Shui, look. It isn't trying to attack us. It's trembling."),
    (3, 1): ("herder", "等等！別再往前了！", "Wait! Don't go any farther!"),
    (3, 2): ("hero", "發生什麼事了？", "What happened?"),
    (3, 3): ("herder", "這幾天史萊姆一直往外逃……以前從沒看過牠們這麼害怕。", "The slimes have been fleeing outward for days... I've never seen them this afraid."),
    (3, 4): ("hero", "是因為那些蜂群嗎？", "Is it because of those swarms?"),
    (3, 5): ("herder", "不只。蜂群也越來越多……像是有什麼東西，把牠們全都趕了出來。", "Not just that. The swarms keep growing too... It's as if something drove them all out."),
    (4, 1): ("hero", "那是……蜂巢？", "Is that... a hive?"),
    (4, 2): ("herder", "嗯。異常好像就是從那個洞穴開始的。", "Yes. It seems the trouble began in that cave."),
    (4, 3): ("herder", "那裡以前不是這個樣子。蜂巢是最近才突然擴散出來的。", "It wasn't like this before. The honeycomb spread there only recently."),
    (4, 4): ("hero", "所以史萊姆和蜂群的異常，都可能跟那裡有關……", "So whatever is affecting the slimes and the swarms could be connected to that place..."),
    (4, 5): ("herder", "如果你要過去調查，一定要小心。", "If you're going to investigate, be careful."),
    (7, 1): ("hero", "原來……就是你讓這裡變成這樣的。", "So... you're the one who did this to this place."),
    (7, 2): ("hero", "史萊姆也好，蜂群也好，牠們都不該變成現在這個樣子。", "The slimes and the swarms... neither of them should have ended up like this."),
    (7, 3): ("hero", "我不能讓你再這樣下去了。", "I can't let you keep doing this."),
    (9, 1): ("hero", "風……平靜下來了。", "The wind... it's calm again."),
    (9, 2): ("hero", "原來牠們不是敵人，只是受到了影響。", "They weren't our enemies. They were caught in this too."),
    (10, 1): ("hero", "走吧。", "Let's go."),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_for(source_root: Path, shot: int, beat: int, locale: str, speaker: str) -> Path:
    stem = f"shot{shot:02d}_line{beat:02d}"
    if speaker == "hero":
        return source_root / "tools" / "e10_zone2_dialogue_v3_reaudition" / "audio" / locale / f"{stem}_{locale}.mp3"
    if locale == "zh-TW":
        return source_root / "tools" / "e10_zone2_herder_voice_replacement_audition" / "audio" / "zh-TW" / f"{stem}_zh-TW_brbEfHMQu0fyclQR7lfh.mp3"
    return source_root / "tools" / "e10_zone2_herder_en_v2_clean_retake" / "audio" / f"{stem}_en_v2_clean_retake.mp3"


def canonical_name(shot: int, beat: int, locale: str, speaker: str) -> str:
    locale_name = "zh" if locale == "zh-TW" else "en"
    return f"zone2_final_shot{shot:02d}_beat{beat:02d}_{locale_name}_{speaker}.mp3"


def dialogue_record(repo_root: Path, source_root: Path, shot: int, beat: int, locale: str, speaker: str, zh: str, en: str) -> dict:
    destination = repo_root / "assets" / "e10" / "audio" / "zone2" / "dialogue" / canonical_name(shot, beat, locale, speaker)
    source = source_for(source_root, shot, beat, locale, speaker)
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    voice_id = (ZH_HERO if locale == "zh-TW" else EN_HERO) if speaker == "hero" else (ZH_HERDER if locale == "zh-TW" else EN_HERDER)
    voice_name = {
        ("hero", "zh-TW"): "Roy",
        ("hero", "en"): "Anvay",
        ("herder", "zh-TW"): "BrbEfHMQu0fyclQR7lfh",
        ("herder", "en"): "Ali - Everyday British (London) Male",
    }[(speaker, locale)]
    rel = destination.relative_to(repo_root).as_posix()
    return {
        "path": rel,
        "source_review_path": str(source.relative_to(source_root)).replace("\\", "/"),
        "sha256": sha256(destination),
        "bytes": destination.stat().st_size,
        "asset_id": f"ZONE2_SHOT{shot:02d}_BEAT{beat:02d}_{speaker.upper()}_{'ZH_TW' if locale == 'zh-TW' else 'EN'}",
        "category": "dialogue",
        "shot": shot,
        "beat": beat,
        "speaker": speaker,
        "locale": locale,
        "script_line": zh if locale == "zh-TW" else en,
        "voice_id": voice_id,
        "voice_name": voice_name,
        "provider": "ElevenLabs",
        "model": "eleven_v3",
        "audio_source": "CLEAN_RETAKE" if speaker == "herder" and locale == "en" else "OWNER_APPROVED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    source_root = args.source_root.resolve()
    package_path = repo_root / "assets" / "e10" / "audio" / "zone2" / "zone2-audio-package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    non_dialogue = [item for item in package["assets"] if item.get("category") != "dialogue"]
    dialogue = []
    for locale in ("zh-TW", "en"):
        for (shot, beat), (speaker, zh, en) in sorted(LINES.items()):
            dialogue.append(dialogue_record(repo_root, source_root, shot, beat, locale, speaker, zh, en))
    assets = sorted(non_dialogue + dialogue, key=lambda item: item["path"])
    package["script_version"] = "OWNER_DIALOGUE_V3"
    package["owner_audio_lock"] = True
    package["runtime_integrated"] = True
    package["audio_lock"] = {
        **package.get("audio_lock", {}),
        "herder_voice": "HERDER_BILINGUAL_V3",
        "herder_voice_zh_tw": ZH_HERDER,
        "herder_voice_en": EN_HERDER,
        "herder_en_audio_source": "CLEAN_RETAKE",
        "hero_voice_zh_tw": ZH_HERO,
        "hero_voice_en": EN_HERO,
        "speaking_shots": [2, 3, 4, 7, 9, 10],
        "silent_shots": [1, 5, 6, 8],
    }
    package["superseded_dialogue_assets"] = [
        "ZONE2_SHOT02_HERO",
        "ZONE2_SHOT04_HERDER_V5",
        "ZONE2_SHOT09_HERO",
        "ZONE2_SHOT02_HERO_EN",
        "ZONE2_SHOT04_HERDER_V5_EN",
        "ZONE2_SHOT09_HERO_EN",
    ]
    package["assets"] = assets
    package["asset_count"] = len(assets)
    package["asset_sha256_set"] = sorted(item["sha256"] for item in assets)
    package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dialogue_path = package_path.with_name("zone2-dialogue-assets.json")
    dialogue_path.write_text(json.dumps({
        "schema_version": "1.1.0",
        "status": "owner-approved-runtime-dialogue-v3",
        "zone_key": "k21_25",
        "script_version": "OWNER_DIALOGUE_V3",
        "speaking_shots": [2, 3, 4, 7, 9, 10],
        "silent_shots": [1, 5, 6, 8],
        "owner_audio_lock": True,
        "assets": dialogue,
        "asset_count": len(dialogue),
        "asset_sha256_set": sorted(item["sha256"] for item in dialogue),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_path = repo_root / "deploy" / "canonical-e10-zone2-audio-pack-manifest.json"
    old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = []
    for item in assets:
        path = repo_root / item["path"]
        files.append({
            "path": item["path"],
            "size": path.stat().st_size,
            "sha256": sha256(path),
            "mime": "audio/mpeg",
            "provenance": "owner-approved-project-created",
            "source_evidence": "Owner-locked Zone 2 V3 bilingual dialogue and unchanged approved BGM/ambient/SFX package.",
        })
    manifest = {
        **old_manifest,
        "$schema_note": "Canonical governed E10 Zone 2 bilingual audio closure with Owner-locked V3 dialogue and unchanged shared music/SFX.",
        "total_files": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "provenance_summary": {"owner-approved-project-created": len(files)},
        "files": sorted(files, key=lambda item: item["path"]),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dialogue_files": len(dialogue), "package_files": len(assets), "manifest_files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
