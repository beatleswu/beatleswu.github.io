"""Add the locked Zone 1 Hero identity rendering of the two V2 Zone 2 lines.

This augmentation avoids regenerating the already-created audition candidates.
It remains review-only and writes only inside the existing audition pack.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "tools" / "e10_zone2_audio" / "generate_zone2_audition.py"
PACK = ROOT / "tools" / "e10_zone2_audio" / "_local_review" / "zone2_audio_audition"
HERO_ID = "XXxvxx0YUt8icTEFE3c6"
LINES = [
    {"id": "HERO_SHOT02", "shot": 2, "line": "牠們在發抖。不是想攻擊我們。是在害怕什麼。"},
    {"id": "HERO_SHOT09", "shot": 9, "line": "牠們不是我們的敵人。我們只是，遇到了同一場病。"},
]


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("zone2_generator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    generator = _load(GEN)
    z1 = generator._load_zone1_tool()
    api_key = z1.get_api_key()
    manifest_path = PACK / "audition_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = PACK / "voice" / "protagonist_zone2"
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for item in LINES:
        path = out_dir / f"{item['id'].lower()}.mp3"
        ok = z1._text_to_speech(api_key, HERO_ID, item["line"], manifest["model"], path)
        record = {
            **item,
            "voice_id": HERO_ID,
            "locale": "zh-TW",
            "provider": "ElevenLabs",
            "model": manifest["model"],
            "settings": "NOT_RECORDED_IN_ZONE1_LOCK",
            "generated": bool(ok),
            "file": None,
        }
        if ok:
            record.update(generator._file_meta(path, locale="zh-TW", locked_identity=True, script_line=item["line"]))
            record["file"] = record["relative_path"]
        records.append(record)
    manifest["protagonist_lines"] = records
    manifest["generation_summary"]["protagonist_lines_expected"] = len(LINES)
    manifest["generation_summary"]["protagonist_lines_generated"] = sum(bool(x["generated"]) for x in records)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generator._write_shot_map(manifest)
    generator._write_notes(manifest)
    generator._write_owner_index(manifest)
    print(f"PROTAGONIST_V2_LINES={manifest['generation_summary']['protagonist_lines_generated']}/{len(LINES)}")
    print(f"PROTAGONIST_V2_OUTPUT={out_dir.resolve()}")
    return 0 if all(x["generated"] for x in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
