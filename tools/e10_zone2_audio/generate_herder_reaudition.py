"""Generate the narrow Zone 2 Herder/pronunciation re-audition pack.

This script deliberately augments the existing Owner review pack.  It does
not rerun the Phase 3 generator and therefore never regenerates the already
approved A3/B3/C3 music, Shui reaction 2, or the other ambient/SFX files.
The written Owner-locked dialogue remains unchanged; ``叫`` is used only as
a TTS-input homophone for the final ``覺`` (jiào) where the provider otherwise
misreads it.  The resulting files remain audition-only and are not runtime
assets.
"""

from __future__ import annotations

import hashlib
import html
import importlib.util
import json
from pathlib import Path

from mutagen.mp3 import MP3


ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = ROOT / "tools" / "e10_zone2_audio" / "generate_zone2_audition.py"
PACK = ROOT / "tools" / "e10_zone2_audio" / "_local_review" / "zone2_audio_audition"
OUT = PACK / "herder_reaudition"
MANIFEST_PATH = PACK / "audition_manifest.json"

# This is the exact written, Owner-approved line.  It is intentionally kept
# separate from the TTS-only workaround below.
CANONICAL_HERDER_LINE = "以前這片草原不是這樣的。自從蜂巢那邊出了問題，牠們就沒睡過一天安穩覺。"
TTS_HERDER_LINE_JIAO4 = CANONICAL_HERDER_LINE.replace("安穩覺", "安穩叫")
CANONICAL_PHRASE = "睡個安穩覺"
TTS_PHRASE_JIAO4 = CANONICAL_PHRASE.replace("覺", "叫")

APPROVED_FILES = {
    "BGM_A3": PACK / "bgm" / "A" / "a3.mp3",
    "BGM_B3": PACK / "bgm" / "B" / "b3.mp3",
    "BGM_C3": PACK / "bgm" / "C" / "c3.mp3",
    "SHUI_REACTION_2": PACK / "sfx_ambient" / "sfx_shui_reaction_b.mp3",
}

# Public shared-voice records selected for this re-audition.  These are all
# young male Mandarin voices and do not overlap the locked Zone 1 Hero,
# Elder, or Messenger identities.
CANDIDATES = [
    {
        "id": "HERDER_V4",
        "label": "Chen",
        "shared_voice_id": "4aW8bNY2tSD8eaHmuXZ0",
        "public_owner_id": "2b639961b8881065ef148f39374c2543923ea7598a67f0ad7a5b326eff45a09d",
        "locale": "zh-TW",
        "gender": "male",
        "age": "young",
        "description": "23-year-old Taiwan Mandarin; fresh, warm young-adult read.",
    },
    {
        "id": "HERDER_V5",
        "label": "James",
        "shared_voice_id": "UwT0JPexcCbH107hq7i5",
        "public_owner_id": "fcfda4732d40ae6389dd3e58326fec47312afb2640e44339c3ba53f0a0d41b3b",
        "locale": "zh-TW",
        "gender": "male",
        "age": "young",
        "description": "Young Taiwan Mandarin; friendly and positive without announcer weight.",
    },
    {
        "id": "HERDER_V6",
        "label": "Yao Yuan Wu",
        "shared_voice_id": "R55vTH9XmVSyAcM6YvtV",
        "public_owner_id": "a88ae5146bec8305070e1c0afc7f909caa0f21a1cfd4b0170506789b2e550dc3",
        "locale": "zh-TW",
        "gender": "male",
        "age": "young",
        "description": "Young Taiwan Mandarin; warm, sweet, trustworthy and clearly distinct.",
    },
]


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("zone2_generator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audio_meta(path: Path, **extra: object) -> dict:
    stat = path.stat()
    meta = {
        "file": path.relative_to(PACK).as_posix(),
        "bytes": stat.st_size,
        "sha256": _sha256(path),
        "duration_seconds": round(float(MP3(path).info.length), 3),
    }
    meta.update(extra)
    return meta


def _existing_voice_id(z1, api_key: str, shared_voice_id: str) -> str | None:
    status, body = z1._api_get("/v1/voices", api_key)
    if status != 200 or not isinstance(body, dict):
        raise RuntimeError(f"VOICE_LIBRARY_READ_FAILED status={status}")
    for voice in body.get("voices", []):
        if isinstance(voice, dict) and voice.get("voice_id") == shared_voice_id:
            return shared_voice_id
    return None


def _ensure_voice(z1, api_key: str, candidate: dict) -> tuple[str, str]:
    existing = _existing_voice_id(z1, api_key, candidate["shared_voice_id"])
    if existing:
        return existing, "ALREADY_IN_ACCOUNT"
    status, body = z1._add_shared_voice(
        api_key,
        candidate["public_owner_id"],
        candidate["shared_voice_id"],
        f"E10 Zone2 Herder {candidate['id']} {candidate['label']}",
    )
    if status not in (200, 201) or not isinstance(body, dict):
        raise RuntimeError(z1._describe_elevenlabs_error(status, body))
    voice_id = body.get("voice_id") or candidate["shared_voice_id"]
    return str(voice_id), "ADDED_FOR_REAUDITION"


def _generate(z1, api_key: str, voice_id: str, text: str, model_id: str, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not z1._text_to_speech(api_key, voice_id, text, model_id, path):
        raise RuntimeError(f"TTS_FAILED file={path.name}")
    return _audio_meta(path)


def _write_owner_page(records: list[dict], frozen: dict, model_id: str) -> None:
    rows: list[str] = []
    for record in records:
        rows.append(
            "<section class='card'>"
            f"<h2>{html.escape(record['id'])} — {html.escape(record['label'])}</h2>"
            f"<p>{html.escape(record['description'])}</p>"
            f"<p><b>Herder context (canonical written line):</b> {html.escape(record['written_dialogue'])}</p>"
            f"<audio controls preload='metadata' src='{html.escape(record['context_audio'])}'></audio>"
            f"<p><b>Exact pronunciation check:</b> {html.escape(record['written_phrase'])} → expected <code>jiào / ㄐㄧㄠˋ</code></p>"
            f"<audio controls preload='metadata' src='{html.escape(record['phrase_audio'])}'></audio>"
            f"<p class='note'>TTS input only: final 覺 was replaced by the homophone 叫. Written dialogue is unchanged.</p>"
            "</section>"
        )
    frozen_rows = "".join(
        f"<li>{html.escape(name)} — {_sha256(path)} (preserved)</li>"
        for name, path in ((name, Path(item["path"])) for name, item in frozen.items())
    )
    page = """<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>Zone 2 Herder re-audition</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;line-height:1.55;margin:0;background:#fbf8f0;color:#26231f}main{max-width:760px;margin:auto;padding:18px}.card{background:#fff;border-radius:14px;padding:16px;margin:14px 0;box-shadow:0 2px 12px #0001}audio{width:100%;margin:8px 0}.note{font-size:.9em;color:#6a6258}code{font-size:1.05em}</style></head><body><main>
<h1>Zone 2 牧者 re-audition</h1><p>V4–V6 are new male candidates. Approved A3/B3/C3, Shui reaction 2, and other SFX remain frozen.</p>
<h2>Frozen approved bytes</h2><ul>__FROZEN__</ul>__ROWS__
<p class='note'>Provider model: __MODEL__. This remains audition-only; Owner selection and pronunciation listening are still required.</p>
</main></body></html>"""
    page = page.replace("__FROZEN__", frozen_rows).replace("__ROWS__", "".join(rows)).replace("__MODEL__", html.escape(model_id))
    (OUT / "herder_reaudition.html").write_text(page, encoding="utf-8")


def main() -> int:
    if not MANIFEST_PATH.is_file():
        raise SystemExit(f"missing existing audition manifest: {MANIFEST_PATH}")
    for name, path in APPROVED_FILES.items():
        if not path.is_file():
            raise SystemExit(f"missing approved audition file {name}: {path}")
    frozen = {
        name: {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
        for name, path in APPROVED_FILES.items()
    }

    generator = _load(GENERATOR_PATH)
    z1 = generator._load_zone1_tool()
    api_key = z1.get_api_key()
    model_id = z1.get_model_id()
    OUT.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    for candidate in CANDIDATES:
        voice_id, library_action = _ensure_voice(z1, api_key, candidate)
        context_path = OUT / f"{candidate['id'].lower()}_context_jiao4.mp3"
        phrase_path = OUT / f"{candidate['id'].lower()}_phrase_jiao4.mp3"
        context_meta = _generate(z1, api_key, voice_id, TTS_HERDER_LINE_JIAO4, model_id, context_path)
        phrase_meta = _generate(z1, api_key, voice_id, TTS_PHRASE_JIAO4, model_id, phrase_path)
        records.append(
            {
                **candidate,
                "voice_id": voice_id,
                "library_action": library_action,
                "written_dialogue": CANONICAL_HERDER_LINE,
                "tts_input_dialogue": TTS_HERDER_LINE_JIAO4,
                "written_phrase": CANONICAL_PHRASE,
                "tts_input_phrase": TTS_PHRASE_JIAO4,
                "pronunciation_expected": "jiào / ㄐㄧㄠˋ",
                "pronunciation_workaround": "TTS-only homophone substitution 覺→叫; written dialogue remains unchanged",
                "context_audio": context_meta["file"],
                "phrase_audio": phrase_meta["file"],
                "context_audio_meta": context_meta,
                "phrase_audio_meta": phrase_meta,
                "generated": True,
            }
        )

    after_frozen = {
        name: {"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size}
        for name, path in APPROVED_FILES.items()
    }
    preservation = all(frozen[name] == after_frozen[name] for name in frozen)
    if not preservation:
        raise SystemExit("APPROVED_AUDIO_PRESERVATION=FAIL")

    result = {
        "status": "AUDITION_ONLY_OWNER_REVIEW_REQUIRED",
        "scope": "HERDER_V4_V6_AND_JIAO4_PRONUNCIATION_ONLY",
        "script_version": "OWNER_APPROVED_V2",
        "provider": "ElevenLabs",
        "model": model_id,
        "written_dialogue_unchanged": True,
        "pronunciation_phrase": {
            "written": CANONICAL_PHRASE,
            "expected": "jiào / ㄐㄧㄠˋ",
            "incorrect": "jué / ㄐㄩㄝˊ",
            "tts_only_input": TTS_PHRASE_JIAO4,
            "verification": "OWNER_LISTEN_PENDING",
        },
        "candidates": records,
        "frozen_approved_assets": after_frozen,
        "approved_audio_preservation": "PASS",
        "runtime_integrated": False,
        "canonical_manifest_created": False,
        "owner_audio_lock": False,
    }
    (OUT / "reaudition_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_owner_page(records, after_frozen, model_id)
    print("HERDER_V4_V5_V6_GENERATED=3/3")
    print("HERDER_ALL_NEW_CANDIDATES_MALE=YES")
    print("APPROVED_AUDIO_PRESERVATION=PASS")
    print("SLEEP_PHRASE_TTS_WORKAROUND=覺→叫 (TTS-only)")
    print("EXPECTED_JIAO_PRONUNCIATION_VERIFIED=OWNER_LISTEN_PENDING")
    print(f"IPAD_REAUDITION_PACK={(OUT / 'herder_reaudition.html').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
