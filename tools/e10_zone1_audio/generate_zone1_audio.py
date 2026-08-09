"""Local (Owner-machine only) ElevenLabs audio tooling for E10 Zone 1 (k26_30).

This tool never runs in the remote Claude Web sandbox — that environment's
egress proxy blocks api.elevenlabs.io by policy. It is meant to be run from
the Owner's local Windows machine, in the canonical repo/worktree, with
ELEVENLABS_API_KEY set only in the current process environment.

For normal Owner use, see Run_Audition_Set_A.cmd / Run_Audition_Set_A.ps1
(double-click launcher covering --check + --audition-set-a). This module is
also usable directly for --list-voices and the single-set --audition mode.

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
                text-to-speech. No paid usage. Exits non-zero if reachability,
                voice access, model access, or model/TTS support fails, so
                callers (e.g. Run_Audition_Set_A.ps1) can gate on it.
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
  --audition-set-a
                Generate AUDITION SET A: a fixed 16-line A/B comparison set
                (2 candidate voices x 8 role/locale slots, defined in
                audition_set_a.json) into _local_review/audition_set_a/,
                using the configured model_id. Each pair reads the SAME
                canonical sample line from casting_candidates.json so the
                two candidates can be compared directly. Does not touch or
                lock casting_candidates.json's voice_id for any slot. Safe to
                re-run: any previous audition_set_a/ output is cleared first,
                so old and new comparison takes never mix. Verifies all 16
                files exist and are non-empty afterward; exits non-zero with
                AUDITION_SET_A_VERIFICATION=FAIL if any are missing/empty.
  --audition-set-b
                Recast pipeline for roles the Owner rejected in Set A
                (audition_set_b_recast_briefs.json), for the account's
                personal voice pool is exhausted for those roles. For each
                pending role: searches the ElevenLabs Voice Library
                (GET /v1/shared-voices) with that role's character-brief
                filters, adds up to candidate_count matches to the account's
                personal voices (POST /v1/voices/add/...), generates one
                sample per candidate into _local_review/audition_set_b/ using
                the SAME canonical sample line as the role's --audition-set-a
                take, and writes the discovered candidates back into
                casting_candidates.json's recast_candidates for that slot
                (never touching voice_id). Refuses to touch any role x locale
                slot marked "locked": true in casting_candidates.json. Safe
                to re-run: any previous audition_set_b/ output is cleared
                first. Verifies PER-ROLE, not just overall: prints
                <ROLE>_GENERATED=<n> for every attempted role and
                AUDITION_SET_B_GENERATED_TOTAL=<n>; if ANY attempted role
                ends up with zero usable (real, non-empty file) candidates,
                exits non-zero with AUDITION_SET_B_VERIFICATION=FAIL and
                AUDITION_SET_B_MISSING_ROLES naming exactly which role(s) --
                a nonzero total across other roles never masks one role's
                failure. Every ElevenLabs call this mode makes (voices,
                models, shared-voices search, add-shared-voice, TTS) goes
                through the single _api_request helper, so auth headers
                cannot diverge between endpoints. A failed search or
                add-to-library call prints a safe, classified diagnostic
                (_describe_elevenlabs_error: HTTP status, ElevenLabs error
                type/message, request_id, and a bucket -- AUTHENTICATION_
                ERROR / AUTHORIZATION_ERROR / VOICE_SLOT_LIMIT / PLAN_
                RESTRICTION / OTHER) instead of a bare status code, and
                never includes the credential. Untested against the live
                Voice Library API from this sandbox (which cannot reach
                it).
  --generate-tts / --generate-sfx / --generate-music
                Reserved for full Zone 1 production once the Owner approves
                casting and BGM direction. Currently print a not-yet-enabled
                notice and take no action (no request is sent).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parent.parent
MANIFEST_PATH = TOOL_DIR / "zone1_beat_manifest.json"
CASTING_PATH = TOOL_DIR / "casting_candidates.json"
AUDITION_SET_A_PATH = TOOL_DIR / "audition_set_a.json"
RECAST_BRIEFS_PATH = TOOL_DIR / "audition_set_b_recast_briefs.json"
REVIEW_DIR = TOOL_DIR / "_local_review"
AUDITION_DIR = REVIEW_DIR / "audition"
AUDITION_SET_A_DIR = REVIEW_DIR / "audition_set_a"
AUDITION_SET_B_DIR = REVIEW_DIR / "audition_set_b"
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


def _try_json(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _api_request(
    method: str,
    path: str,
    api_key: str,
    json_body: dict | None = None,
    accept: str = "application/json",
    timeout: int = 30,
) -> tuple[int, object]:
    """The single authenticated request path for every ElevenLabs call this
    tool makes: /v1/voices, /v1/models, /v1/shared-voices (search),
    /v1/voices/add/... (add a shared voice), /v1/text-to-speech/... . Every
    call goes through this one function so the auth header is provably
    always present and always constructed identically -- there is no
    separate or divergent code path for any endpoint, including the
    "add shared voice" one.

    Returns (http_status, body) where body is parsed JSON when
    accept == "application/json" (or None if parsing failed / on network
    error), or raw bytes for any other accept value (e.g. audio/mpeg).
    Never logs the key, the Authorization/xi-api-key header value, or any
    other request header.
    """
    if not api_key:
        raise ValueError("_api_request called with an empty/None api_key")

    headers = {"xi-api-key": api_key, "Accept": accept}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except urllib.error.URLError as exc:
        print(f"NETWORK_ERROR {method} {path}: {exc.reason}", file=sys.stderr)
        return 0, None

    if accept == "application/json":
        return status, _try_json(raw)
    return status, raw


def _api_get(path: str, api_key: str) -> tuple[int, object]:
    return _api_request("GET", path, api_key)


def _classify_elevenlabs_error(status: int, body: object) -> str:
    """Classify a failed ElevenLabs response into a small set of actionable
    buckets, without ever needing to print the credential to tell them apart.
    Content-based classification (voice-slot-limit, plan) takes priority
    over the blunt HTTP status code, since a 403 that explicitly says
    "upgrade your plan" is more useful classified as PLAN_RESTRICTION than
    as a generic AUTHORIZATION_ERROR.
    """
    detail = body.get("detail") if isinstance(body, dict) else None
    detail_status = detail.get("status") if isinstance(detail, dict) else (detail if isinstance(detail, str) else None)
    detail_message = detail.get("message") if isinstance(detail, dict) else None
    text_blob = " ".join(str(part) for part in (detail_status, detail_message) if part).lower()

    if any(keyword in text_blob for keyword in ("voice_limit", "max_voice", "voice_slot", "voice_add_limit")):
        return "VOICE_SLOT_LIMIT"
    if any(keyword in text_blob for keyword in ("plan", "subscription", "upgrade", "tier")):
        return "PLAN_RESTRICTION"
    if status == 401:
        if any(keyword in text_blob for keyword in ("permission", "scope", "not_allowed", "unauthorized_missing")):
            return "AUTHORIZATION_ERROR"
        return "AUTHENTICATION_ERROR"
    if status == 403:
        return "AUTHORIZATION_ERROR"
    return "OTHER"


def _describe_elevenlabs_error(status: int, body: object) -> str:
    """Build a safe, printable one-line diagnostic for a failed ElevenLabs
    call: HTTP status, ElevenLabs error type/message, request_id if present,
    and a classification bucket. Never includes the API key or any header.
    """
    detail = body.get("detail") if isinstance(body, dict) else None
    error_type = detail.get("status") if isinstance(detail, dict) else (detail if isinstance(detail, str) else None)
    error_message = detail.get("message") if isinstance(detail, dict) else None
    request_id = None
    if isinstance(body, dict):
        request_id = body.get("request_id") or body.get("requestId")
    classification = _classify_elevenlabs_error(status, body)
    return (
        f"http_status={status} classification={classification} "
        f"elevenlabs_error_type={error_type!r} elevenlabs_error_message={error_message!r} "
        f"request_id={request_id!r}"
    )


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

    ok = reachable and voice_access and model_access and model_present and model_supports_tts
    if not ok:
        raise SystemExit(1)


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
    status, body = _api_request(
        "POST",
        f"/v1/text-to-speech/{voice_id}",
        api_key,
        json_body={"text": text, "model_id": model_id},
        accept="audio/mpeg",
        timeout=60,
    )
    if status == 200 and isinstance(body, (bytes, bytearray)):
        output_path.write_bytes(body)
        return True
    if status == 0:
        return False  # network error already logged by _api_request
    # On failure the server sends a JSON error body even though we asked for
    # audio/mpeg; try to decode it for a useful diagnostic.
    error_body = _try_json(body) if isinstance(body, (bytes, bytearray)) else body
    print(f"  FAILED {output_path.name}: {_describe_elevenlabs_error(status, error_body)}", file=sys.stderr)
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


def cmd_audition_set_a() -> None:
    api_key = get_api_key()
    casting = json.loads(CASTING_PATH.read_text(encoding="utf-8"))
    sample_lines = casting["audition_sample_lines"]
    model_id = get_model_id()
    audition_set = json.loads(AUDITION_SET_A_PATH.read_text(encoding="utf-8"))
    items = audition_set["items"]

    print(f"SELECTED_MODEL_ID={model_id}")
    print(f"AUDITION_SET_A_ITEMS={len(items)}")
    print("Run --check first to confirm this model is available and supports text-to-speech.")

    if AUDITION_SET_A_DIR.exists():
        shutil.rmtree(AUDITION_SET_A_DIR)
    AUDITION_SET_A_DIR.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    for item in items:
        role_key = item["role"]
        locale = item["locale"]
        text = sample_lines.get(role_key, {}).get(locale)
        if not text:
            print(f"SKIP {item['output_filename']}: no canonical sample line for {role_key}/{locale}")
            skipped += 1
            continue
        output_path = AUDITION_SET_A_DIR / item["output_filename"]
        print(f"Generating {output_path.name} ({item['candidate_name']}) ...")
        if _text_to_speech(api_key, item["voice_id"], text, model_id, output_path):
            generated += 1

    print(f"AUDITION_SET_A_GENERATED={generated}")
    print(f"AUDITION_SET_A_SKIPPED={skipped}")
    print(f"AUDITION_SET_A_OUTPUT_DIR={AUDITION_SET_A_DIR.resolve()}")

    missing_or_empty = [
        item["output_filename"] for item in items
        if not (AUDITION_SET_A_DIR / item["output_filename"]).is_file()
        or (AUDITION_SET_A_DIR / item["output_filename"]).stat().st_size == 0
    ]
    if missing_or_empty:
        print("AUDITION_SET_A_VERIFICATION=FAIL")
        print(f"AUDITION_SET_A_MISSING_OR_EMPTY={','.join(missing_or_empty)}")
        raise SystemExit(1)
    print("AUDITION_SET_A_VERIFICATION=PASS")

    print("These are local review-only comparison samples. They do not lock casting_candidates.json "
          "and are not canonical production assets until the Owner explicitly approves casting.")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "voice"


def _search_voice_library(api_key: str, params: dict) -> tuple[int, object]:
    query = urllib.parse.urlencode(params, doseq=True)
    return _api_get(f"/v1/shared-voices?{query}", api_key)


def _add_shared_voice(api_key: str, public_owner_id: str, voice_id: str, new_name: str) -> tuple[int, object]:
    return _api_request(
        "POST",
        f"/v1/voices/add/{public_owner_id}/{voice_id}",
        api_key,
        json_body={"new_name": new_name[:100]},
    )


def _pick_library_candidates(api_key: str, role_key: str, brief: dict, exclude_ids: set, count: int) -> list:
    search_params = dict(brief["search"])
    search_params.setdefault("page_size", 30)
    print(f"  Searching Voice Library for {role_key}: {search_params}")
    status, body = _search_voice_library(api_key, search_params)
    voices = body.get("voices", []) if status == 200 and isinstance(body, dict) else []

    if not voices and "fallback_search" in brief:
        fallback_params = dict(brief["fallback_search"])
        fallback_params.setdefault("page_size", 30)
        print(f"  No results, retrying with fallback filters: {fallback_params}")
        status, body = _search_voice_library(api_key, fallback_params)
        voices = body.get("voices", []) if status == 200 and isinstance(body, dict) else []

    if status != 200:
        print(f"  VOICE_LIBRARY_SEARCH_FAILED role={role_key} http_status={status}")
        return []

    candidates = []
    seen = set(exclude_ids)
    for voice in voices:
        if not isinstance(voice, dict):
            continue
        voice_id = voice.get("voice_id")
        if not voice_id or voice_id in seen:
            continue
        candidates.append(voice)
        seen.add(voice_id)
        if len(candidates) >= count:
            break
    return candidates


def cmd_audition_set_b() -> None:
    api_key = get_api_key()
    casting = json.loads(CASTING_PATH.read_text(encoding="utf-8"))
    sample_lines = casting["audition_sample_lines"]
    model_id = get_model_id()
    briefs_doc = json.loads(RECAST_BRIEFS_PATH.read_text(encoding="utf-8"))
    exclude_ids = set(briefs_doc.get("exclude_voice_ids", []))
    briefs = briefs_doc["roles"]

    print(f"SELECTED_MODEL_ID={model_id}")
    print("Run --check first to confirm this model is available and supports text-to-speech.")

    if AUDITION_SET_B_DIR.exists():
        shutil.rmtree(AUDITION_SET_B_DIR)
    AUDITION_SET_B_DIR.mkdir(parents=True, exist_ok=True)

    expected_total = 0
    results_by_role: dict[str, list] = {}

    for role_key, brief in briefs.items():
        role_config_key = brief["role_config_key"]
        locale = brief["locale"]
        role_config = casting["roles"][role_config_key]["voices"][locale]

        if role_config.get("locked"):
            print(f"SKIP role={role_key}: {role_config_key}/{locale} is locked in casting_candidates.json "
                  "(Owner-approved voices are never overwritten by --audition-set-b)")
            continue

        text = sample_lines.get(role_config_key, {}).get(locale)
        if not text:
            print(f"SKIP role={role_key}: no canonical sample line for {role_config_key}/{locale}")
            continue

        count = brief.get("candidate_count", 3)
        expected_total += count
        candidates = _pick_library_candidates(api_key, role_key, brief, exclude_ids, count)
        if not candidates:
            print(f"  NO_CANDIDATES_FOUND role={role_key}")
        results_by_role[role_key] = []

        for voice in candidates:
            public_owner_id = voice.get("public_owner_id")
            shared_voice_id = voice.get("voice_id")
            name = voice.get("name") or shared_voice_id
            slug = _slugify(name)
            output_filename = f"{brief['output_prefix']}_{slug}.mp3"

            if not public_owner_id or not shared_voice_id:
                print(f"    SKIP_CANDIDATE name={name!r}: Voice Library search result is missing "
                      f"public_owner_id or voice_id (public_owner_id={public_owner_id!r}) -- "
                      "cannot construct an add-to-library request for it")
                continue

            print(f"  Adding to library: {name} ({shared_voice_id}) for {role_key} ...")
            add_status, add_body = _add_shared_voice(
                api_key, public_owner_id, shared_voice_id, f"E10Z1_{role_key}_{slug}"
            )
            if add_status not in (200, 201) or not isinstance(add_body, dict) or not add_body.get("voice_id"):
                print(f"    ADD_TO_LIBRARY_FAILED name={name!r} {_describe_elevenlabs_error(add_status, add_body)}")
                continue
            local_voice_id = add_body["voice_id"]

            output_path = AUDITION_SET_B_DIR / output_filename
            print(f"  Generating {output_path.name} ({name}) ...")
            ok = _text_to_speech(api_key, local_voice_id, text, model_id, output_path)

            results_by_role[role_key].append({
                "name": name,
                "shared_voice_id": shared_voice_id,
                "local_voice_id": local_voice_id,
                "output_filename": output_filename,
                "gender": voice.get("gender"),
                "age": voice.get("age"),
                "accent": voice.get("accent"),
                "language": voice.get("language"),
                "description": voice.get("description") or voice.get("descriptive"),
                "generated": ok,
            })

    for role_key, brief in briefs.items():
        role_config_key = brief["role_config_key"]
        locale = brief["locale"]
        role_config = casting["roles"][role_config_key]["voices"][locale]
        if role_config.get("locked"):
            continue
        role_config["recast_candidates"] = results_by_role.get(role_key, [])
    CASTING_PATH.write_text(json.dumps(casting, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CASTING_CANDIDATES_UPDATED={CASTING_PATH.relative_to(REPO_ROOT)} (recast_candidates only; "
          "no voice_id or locked slot was touched)")

    print(f"AUDITION_SET_B_EXPECTED={expected_total}")
    print(f"AUDITION_SET_B_OUTPUT_DIR={AUDITION_SET_B_DIR.resolve()}")

    # Per-role verification: a role counts as usable only if at least one of
    # its candidates actually produced a real, non-empty file on disk. A
    # role-level total of >=1 "usable" candidates across all roles is not
    # sufficient -- each role that was attempted (i.e. not locked/skipped)
    # must individually clear the >=1 bar, or the run is not complete.
    per_role_generated: dict[str, int] = {}
    per_role_requested: dict[str, int] = {}
    missing_or_empty_files: list[str] = []
    failed_roles: list[str] = []

    for role_key, brief in briefs.items():
        if role_key not in results_by_role:
            continue  # locked or missing sample line: not attempted, not gated
        entries = results_by_role[role_key]
        per_role_requested[role_key] = brief.get("candidate_count", 3)
        usable = 0
        for entry in entries:
            output_path = AUDITION_SET_B_DIR / entry["output_filename"]
            is_usable = entry["generated"] and output_path.is_file() and output_path.stat().st_size > 0
            if entry["generated"] and not is_usable:
                missing_or_empty_files.append(entry["output_filename"])
            if is_usable:
                usable += 1
        per_role_generated[role_key] = usable
        if usable == 0:
            failed_roles.append(role_key)

    for role_key in briefs:
        if role_key in per_role_generated:
            print(f"{role_key.upper()}_GENERATED={per_role_generated[role_key]}")
    print(f"AUDITION_SET_B_GENERATED_TOTAL={sum(per_role_generated.values())}")

    for role_key, requested in per_role_requested.items():
        found = per_role_generated[role_key]
        if 0 < found < requested:
            print(f"SHORTAGE role={role_key}: found {found} usable candidate(s), requested {requested} "
                  "-- acceptable since at least 1 exists, but the Owner has fewer options to compare")

    if missing_or_empty_files:
        print(f"AUDITION_SET_B_MISSING_OR_EMPTY={','.join(missing_or_empty_files)}")

    if failed_roles:
        print("AUDITION_SET_B_VERIFICATION=FAIL")
        print(f"AUDITION_SET_B_MISSING_ROLES={','.join(failed_roles)}")
        for role_key in failed_roles:
            print(f"  MISSING: {role_key} has zero usable candidates -- this run is NOT complete, "
                  "do not present it to the Owner as finished")
        raise SystemExit(1)
    print("AUDITION_SET_B_VERIFICATION=PASS")

    print("These are local review-only recast comparison samples. They do not lock casting_candidates.json "
          "and are not canonical production assets until the Owner explicitly approves casting.")


def cmd_not_yet_enabled(flag: str) -> None:
    print(f"{flag}: NOT_YET_ENABLED — awaiting Owner casting/BGM approval. No request was sent.")


def main() -> None:
    parser = argparse.ArgumentParser(description="E10 Zone 1 local ElevenLabs audio tooling (Owner machine only).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Read-only connectivity/voice/model check.")
    group.add_argument("--list-voices", action="store_true", help="Read-only voice discovery list/table.")
    group.add_argument("--audition", action="store_true", help="Generate the minimal casting sample only.")
    group.add_argument("--audition-set-a", action="store_true", help="Generate the fixed 16-line A/B casting comparison set.")
    group.add_argument("--audition-set-b", action="store_true", help="Recast pending roles via a live Voice Library search.")
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
    elif args.audition_set_a:
        cmd_audition_set_a()
    elif args.audition_set_b:
        cmd_audition_set_b()
    elif args.generate_tts:
        cmd_not_yet_enabled("--generate-tts")
    elif args.generate_sfx:
        cmd_not_yet_enabled("--generate-sfx")
    elif args.generate_music:
        cmd_not_yet_enabled("--generate-music")


if __name__ == "__main__":
    main()
