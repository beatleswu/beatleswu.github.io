"""Local (Owner-machine only) ElevenLabs audio tooling for E10 Zone 1 (k26_30).

This tool never runs in the remote Claude Web sandbox — that environment's
egress proxy blocks api.elevenlabs.io by policy. It is meant to be run from
the Owner's local Windows machine, in the canonical repo/worktree, with
ELEVENLABS_API_KEY set only in the current process environment.

Credential handling contract (do not weaken this):
  - The API key is read once via os.environ.get("ELEVENLABS_API_KEY").
  - The key is never printed, logged, written to disk, or included in any
    generated file, error message, or exception traceback text we control.
  - No request header dump, no "here is what I sent" debug output.
  - This file must not read secret_key.txt, .env, or any other credential
    file — the environment variable is the only accepted source.

Modes:
  --check       Read-only: GET /v1/voices and /v1/models, and verifies the
                configured model (casting_candidates.json audio_config.
                model_id, default "eleven_v3") is present and supports
                text-to-speech. No paid usage.
  --list-voices Read-only: GET /v1/voices and print a compact table of
                name/voice_id/category/language/accent/gender/age/
                description for casting reference. Add --json to also write
                a local review artifact (_local_review/voices.json). Add
                --quiet (requires --json) to suppress the table/counts and
                print only the resulting artifact path — for a minimal
                one-command Owner workflow. No audio is generated and
                casting_candidates.json is not touched by this mode.
  --audition    Generate the 8-line casting sample (4 roles x 2 locales)
                from casting_candidates.json into _local_review/audition/,
                using the configured model_id. Reports the selected model
                before generating. Skips any role/locale left with
                voice_id = null.
  --generate-tts / --generate-sfx / --generate-music
                Reserved for full Zone 1 production once the Owner approves
                casting and BGM direction. Currently print a not-yet-enabled
                notice and take no action (no request is sent).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parent.parent
MANIFEST_PATH = TOOL_DIR / "zone1_beat_manifest.json"
CASTING_PATH = TOOL_DIR / "casting_candidates.json"
REVIEW_DIR = TOOL_DIR / "_local_review"
AUDITION_DIR = REVIEW_DIR / "audition"
VOICES_JSON_PATH = REVIEW_DIR / "voices.json"

API_BASE = "https://api.elevenlabs.io"
ENV_VAR = "ELEVENLABS_API_KEY"
DEFAULT_MODEL_ID = "eleven_v3"


def get_api_key() -> str:
    key = os.environ.get(ENV_VAR)
    if not key:
        print(
            f"ERROR: {ENV_VAR} is not set in this process environment. "
            "See README.md for the PowerShell commands to set it before running this tool.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return key


def get_model_id() -> str:
    casting = json.loads(CASTING_PATH.read_text(encoding="utf-8"))
    return casting.get("audio_config", {}).get("model_id") or DEFAULT_MODEL_ID


def _api_get(path: str, api_key: str) -> tuple[int, object]:
    request = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={"xi-api-key": api_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except urllib.error.URLError as exc:
        print(f"NETWORK_ERROR reaching {API_BASE}{path}: {exc.reason}", file=sys.stderr)
        return 0, None


def cmd_check() -> None:
    api_key = get_api_key()
    selected_model_id = get_model_id()

    voices_status, voices_body = _api_get("/v1/voices", api_key)
    voice_access = voices_status == 200
    voice_count = len(voices_body.get("voices", [])) if voice_access and isinstance(voices_body, dict) else 0

    models_status, models_body = _api_get("/v1/models", api_key)
    model_access = models_status == 200
    model_count = len(models_body) if model_access and isinstance(models_body, list) else 0

    selected_model = None
    if model_access and isinstance(models_body, list):
        for model in models_body:
            if isinstance(model, dict) and model.get("model_id") == selected_model_id:
                selected_model = model
                break
    model_present = selected_model is not None
    model_supports_tts = bool(selected_model and selected_model.get("can_do_text_to_speech"))

    reachable = voices_status != 0 or models_status != 0

    print(f"SELECTED_MODEL_ID={selected_model_id}")
    print(f"ELEVENLABS_API_REACHABLE={'YES' if reachable else 'NO'}")
    print(f"VOICE_API_ACCESS={'YES' if voice_access else 'NO'}")
    print(f"MODEL_API_ACCESS={'YES' if model_access else 'NO'}")
    print(f"AVAILABLE_VOICE_COUNT={voice_count}")
    print(f"AVAILABLE_MODEL_COUNT={model_count}")
    print(f"SELECTED_MODEL_PRESENT={'YES' if model_present else 'NO'}")
    print(f"SELECTED_MODEL_SUPPORTS_TTS={'YES' if model_supports_tts else 'NO'}")
    if not voice_access:
        print(f"VOICE_API_HTTP_STATUS={voices_status}")
    if not model_access:
        print(f"MODEL_API_HTTP_STATUS={models_status}")


def _extract_voice_summary(voice: dict) -> dict:
    labels = voice.get("labels") or {}
    return {
        "name": voice.get("name") or "",
        "voice_id": voice.get("voice_id") or "",
        "category": voice.get("category") or "",
        "language_accent": labels.get("language") or labels.get("accent") or "",
        "gender": labels.get("gender") or "",
        "age": labels.get("age") or "",
        "description": labels.get("description") or labels.get("use_case") or "",
    }


def cmd_list_voices(as_json: bool, quiet: bool = False) -> None:
    api_key = get_api_key()

    voices_status, voices_body = _api_get("/v1/voices", api_key)
    if voices_status != 200 or not isinstance(voices_body, dict):
        print("VOICE_API_ACCESS=NO")
        print(f"VOICE_API_HTTP_STATUS={voices_status}")
        raise SystemExit(1)

    raw_voices = voices_body.get("voices", [])
    summaries = [_extract_voice_summary(voice) for voice in raw_voices if isinstance(voice, dict)]

    if not quiet:
        print("VOICE_API_ACCESS=YES")
        print(f"AVAILABLE_VOICE_COUNT={len(summaries)}")
        print()

        columns = ("name", "voice_id", "category", "language_accent", "gender", "age", "description")
        headers = ("NAME", "VOICE_ID", "CATEGORY", "LANGUAGE/ACCENT", "GENDER", "AGE", "DESCRIPTION")
        widths = [len(header) for header in headers]
        for summary in summaries:
            for index, column in enumerate(columns):
                widths[index] = max(widths[index], len(str(summary[column])[:40]))

        def format_row(values: tuple[str, ...]) -> str:
            return "  ".join(str(value)[:40].ljust(widths[index]) for index, value in enumerate(values))

        print(format_row(headers))
        print(format_row(tuple("-" * width for width in widths)))
        for summary in summaries:
            print(format_row(tuple(summary[column] for column in columns)))

    if as_json:
        REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        VOICES_JSON_PATH.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
        if quiet:
            print(str(VOICES_JSON_PATH.resolve()))
        else:
            print()
            print(f"VOICES_JSON_WRITTEN={VOICES_JSON_PATH.relative_to(REPO_ROOT)}")


def _text_to_speech(api_key: str, voice_id: str, text: str, model_id: str, output_path: Path) -> bool:
    payload = json.dumps({
        "text": text,
        "model_id": model_id,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}/v1/text-to-speech/{voice_id}",
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            output_path.write_bytes(response.read())
        return True
    except urllib.error.HTTPError as exc:
        print(f"  FAILED ({exc.code}): {output_path.name}", file=sys.stderr)
        return False
    except urllib.error.URLError as exc:
        print(f"  NETWORK_ERROR: {output_path.name}: {exc.reason}", file=sys.stderr)
        return False


def cmd_audition() -> None:
    api_key = get_api_key()
    casting = json.loads(CASTING_PATH.read_text(encoding="utf-8"))
    roles = casting["roles"]
    sample_lines = casting["audition_sample_lines"]
    model_id = get_model_id()

    print(f"SELECTED_MODEL_ID={model_id}")
    print("Run --check first to confirm this model is available and supports text-to-speech.")

    AUDITION_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    for role_key, role in roles.items():
        for locale, voice_cfg in role["voices"].items():
            voice_id = voice_cfg.get("voice_id")
            text = sample_lines.get(role_key, {}).get(locale)
            if not voice_id or not text:
                print(f"SKIP {role_key}/{locale}: no voice_id set in casting_candidates.json")
                skipped += 1
                continue
            output_path = AUDITION_DIR / f"audition_{role_key}_{locale}.mp3"
            print(f"Generating {output_path.name} (model={model_id}) ...")
            if _text_to_speech(api_key, voice_id, text, model_id, output_path):
                generated += 1

    print(f"AUDITION_GENERATED={generated}")
    print(f"AUDITION_SKIPPED={skipped}")
    print(f"AUDITION_OUTPUT_DIR={AUDITION_DIR.relative_to(REPO_ROOT)}")
    print("These are local review-only samples. They are not canonical production assets "
          "until the Owner explicitly approves casting.")


def cmd_not_yet_enabled(flag: str) -> None:
    print(f"{flag}: NOT_YET_ENABLED — awaiting Owner casting/BGM approval. No request was sent.")


def main() -> None:
    parser = argparse.ArgumentParser(description="E10 Zone 1 local ElevenLabs audio tooling (Owner machine only).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Read-only connectivity/voice/model check.")
    group.add_argument("--list-voices", action="store_true", help="Read-only voice discovery list/table.")
    group.add_argument("--audition", action="store_true", help="Generate the minimal casting sample only.")
    group.add_argument("--generate-tts", action="store_true", help="Reserved; not yet enabled.")
    group.add_argument("--generate-sfx", action="store_true", help="Reserved; not yet enabled.")
    group.add_argument("--generate-music", action="store_true", help="Reserved; not yet enabled.")
    parser.add_argument("--json", action="store_true", help="With --list-voices, also write _local_review/voices.json.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="With --list-voices --json, suppress the table/counts and print only the resulting artifact path.",
    )
    args = parser.parse_args()

    if args.json and not args.list_voices:
        parser.error("--json is only valid together with --list-voices")
    if args.quiet and not (args.list_voices and args.json):
        parser.error("--quiet is only valid together with --list-voices --json")

    if args.check:
        cmd_check()
    elif args.list_voices:
        cmd_list_voices(as_json=args.json, quiet=args.quiet)
    elif args.audition:
        cmd_audition()
    elif args.generate_tts:
        cmd_not_yet_enabled("--generate-tts")
    elif args.generate_sfx:
        cmd_not_yet_enabled("--generate-sfx")
    elif args.generate_music:
        cmd_not_yet_enabled("--generate-music")


if __name__ == "__main__":
    main()
