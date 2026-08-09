"""E10-Z1-AUDIO-PRODUCTION-001 -- ElevenLabs auth consistency + safe diagnostics.

A live Owner run got --check and Voice Library search working (both read-only
GET calls), but every "add a shared voice to my library" POST failed with
HTTP 401 -- 9 out of 9 identical failures. Since the same api_key value
demonstrably worked earlier in the exact same process for the GET calls, the
concern was whether the "add shared voice" code path was somehow using a
different/broken auth mechanism.

Code review found _add_shared_voice already sent the same "xi-api-key"
header via the same api_key value -- but it was a separate, hand-written
urllib.request.Request construction from the GET helper, so there was no
structural guarantee the two could never diverge, and failures only
surfaced a bare HTTP status with no ElevenLabs-provided detail to tell an
auth failure apart from a permissions/plan/voice-slot-limit failure.

Fixes covered by these tests:
  - Every ElevenLabs call (GET voices/models/shared-voices, POST add-shared-
    voice, POST text-to-speech) now goes through one function, _api_request,
    so the auth header is provably always present and identical.
  - Failed add-shared-voice / text-to-speech calls now surface a safe,
    classified diagnostic (HTTP status, ElevenLabs error type/message,
    request_id) without ever printing the credential.
  - A failed add never silently produces a "generated" candidate, and the
    per-role AUDITION SET B gate still catches a role where every add
    attempt failed.

These tests never use a real credential -- DUMMY_KEY below is a clearly
fake, structurally-obvious placeholder -- and they mock urllib.request.urlopen
directly (not the wrapper functions), so the assertions are against the
actual constructed HTTP request, not a mock that could hide a real bug.
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_DIR = REPO_ROOT / "tools" / "e10_zone1_audio"
sys.path.insert(0, str(TOOL_DIR))
import generate_zone1_audio as mod  # noqa: E402

DUMMY_KEY = "dummy_test_value_not_real"


class _FakeHTTPResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _http_error(url: str, status: int, payload: dict) -> urllib.error.HTTPError:
    body = json.dumps(payload).encode("utf-8")
    return urllib.error.HTTPError(url, status, "error", {}, io.BytesIO(body))


@pytest.fixture
def casting_backup():
    original = mod.CASTING_PATH.read_bytes()
    try:
        yield
    finally:
        mod.CASTING_PATH.write_bytes(original)
        if mod.AUDITION_SET_B_DIR.exists():
            shutil.rmtree(mod.AUDITION_SET_B_DIR)


@pytest.fixture
def synthetic_pending_roles(monkeypatch, casting_backup, tmp_path):
    """All 8 role x locale slots are locked in the real, committed
    casting_candidates.json (AUDITION SET B is complete), so
    audition_set_b_recast_briefs.json now has an empty "roles" -- there is
    nothing left for --audition-set-b to actually do against the real repo
    state. These auth/pipeline-mechanism tests need something to process,
    so this fixture temporarily unlocks 3 roles (mirroring the shape Set B
    originally targeted: zh-TW Elder, zh-TW Hero, English Hero) and points
    RECAST_BRIEFS_PATH at a synthetic 3-role brief file for the duration of
    the test. casting_backup restores the real casting_candidates.json
    afterward; monkeypatch restores RECAST_BRIEFS_PATH automatically.
    """
    casting = json.loads(mod.CASTING_PATH.read_text(encoding="utf-8"))
    for role_key, locale in (("elder", "zh-TW"), ("hero", "zh-TW"), ("hero", "en")):
        slot = casting["roles"][role_key]["voices"][locale]
        slot["locked"] = False
        slot["voice_id"] = None
    mod.CASTING_PATH.write_text(json.dumps(casting, ensure_ascii=False, indent=2), encoding="utf-8")

    briefs = {
        "exclude_voice_ids": [],
        "roles": {
            "zh_elder": {
                "role_config_key": "elder", "locale": "zh-TW", "output_prefix": "zh_elder",
                "candidate_count": 1, "search": {"language": "zh", "gender": "male", "age": "old"},
            },
            "zh_hero": {
                "role_config_key": "hero", "locale": "zh-TW", "output_prefix": "zh_hero",
                "candidate_count": 1, "search": {"language": "zh", "gender": "male", "age": "young"},
            },
            "en_hero": {
                "role_config_key": "hero", "locale": "en", "output_prefix": "en_hero",
                "candidate_count": 1, "search": {"language": "en", "gender": "male", "age": "young"},
            },
        },
    }
    briefs_path = tmp_path / "audition_set_b_recast_briefs.json"
    briefs_path.write_text(json.dumps(briefs), encoding="utf-8")
    monkeypatch.setattr(mod, "RECAST_BRIEFS_PATH", briefs_path)


# --- header/auth-path construction -----------------------------------------

def test_add_shared_voice_sends_xi_api_key_header(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["data"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(200, json.dumps({"voice_id": "local_added_1"}).encode("utf-8"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    status, body = mod._add_shared_voice(DUMMY_KEY, "owner1", "sharedVoice1", "TestName")

    assert status == 200
    assert body == {"voice_id": "local_added_1"}
    assert captured["headers"].get("xi-api-key") == DUMMY_KEY
    assert captured["method"] == "POST"
    assert "/v1/voices/add/owner1/sharedVoice1" in captured["url"]
    assert captured["data"] == {"new_name": "TestName"}


def test_all_elevenlabs_calls_share_one_request_function(monkeypatch):
    # _api_get (voices/models/shared-voices search), _add_shared_voice, and
    # _text_to_speech must all route through the same _api_request -- prove
    # it by monkeypatching _api_request itself and confirming every public
    # call goes through it.
    calls = []
    original = mod._api_request

    def spy(method, path, api_key, **kwargs):
        calls.append((method, path))
        return original(method, path, api_key, **kwargs)

    monkeypatch.setattr(mod, "_api_request", spy)

    def fake_urlopen(request, timeout=None):
        if "text-to-speech" in request.full_url:
            return _FakeHTTPResponse(200, b"FAKE_AUDIO")
        return _FakeHTTPResponse(200, json.dumps({"voices": [], "voice_id": "x"}).encode("utf-8"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    mod._api_get("/v1/voices", DUMMY_KEY)
    mod._search_voice_library(DUMMY_KEY, {"language": "en"})
    mod._add_shared_voice(DUMMY_KEY, "owner1", "voice1", "name")
    tmp_path = TOOL_DIR / "_local_review" / "_auth_test_tts.mp3"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mod._text_to_speech(DUMMY_KEY, "voice1", "hello", "eleven_v3", tmp_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    assert len(calls) == 4
    assert {c[0] for c in calls} == {"GET", "POST"}


# --- safe error classification ----------------------------------------------

def test_classify_401_as_authentication_error():
    assert mod._classify_elevenlabs_error(401, {"detail": {"status": "invalid_api_key", "message": "bad key"}}) == (
        "AUTHENTICATION_ERROR"
    )


def test_classify_401_with_permission_wording_as_authorization_error():
    body = {"detail": {"status": "missing_permissions", "message": "This API key does not have permission to add voices"}}
    assert mod._classify_elevenlabs_error(401, body) == "AUTHORIZATION_ERROR"


def test_classify_403_as_authorization_error_distinct_from_401():
    assert mod._classify_elevenlabs_error(403, {"detail": {"status": "forbidden"}}) == "AUTHORIZATION_ERROR"
    assert mod._classify_elevenlabs_error(401, {"detail": {"status": "invalid_api_key"}}) != mod._classify_elevenlabs_error(
        403, {"detail": {"status": "forbidden"}}
    )


def test_classify_voice_slot_limit():
    body = {"detail": {"status": "voice_limit_reached", "message": "You have reached your voice_slot limit"}}
    assert mod._classify_elevenlabs_error(400, body) == "VOICE_SLOT_LIMIT"


def test_classify_plan_restriction_even_when_status_would_suggest_authorization():
    # Content-based classification must win over the blunt 403 status code,
    # since "upgrade your plan" is a much more actionable diagnosis.
    body = {"detail": {"status": "feature_not_available", "message": "Upgrade your subscription plan to use this feature"}}
    assert mod._classify_elevenlabs_error(403, body) == "PLAN_RESTRICTION"


def test_describe_elevenlabs_error_extracts_type_message_and_request_id():
    description = mod._describe_elevenlabs_error(
        401,
        {"detail": {"status": "invalid_api_key", "message": "The API key you provided is invalid"}, "request_id": "req_123"},
    )
    assert "http_status=401" in description
    assert "AUTHENTICATION_ERROR" in description
    assert "invalid_api_key" in description
    assert "req_123" in description
    assert DUMMY_KEY not in description


# --- end-to-end pipeline behavior -------------------------------------------

def _router(add_response, shared_voice_id="shared_v1", owner_id="owner_x"):
    """add_response: (status, payload_dict). status>=400 raises HTTPError."""

    def fake_urlopen(request, timeout=None):
        url = request.full_url
        if "/v1/shared-voices" in url:
            body = json.dumps({
                "voices": [{
                    "voice_id": shared_voice_id,
                    "public_owner_id": owner_id,
                    "name": "Candidate X",
                    "gender": "male",
                    "age": "young",
                    "language": "zh",
                }]
            }).encode("utf-8")
            return _FakeHTTPResponse(200, body)
        if "/v1/voices/add/" in url:
            status, payload = add_response
            if status >= 400:
                raise _http_error(url, status, payload)
            return _FakeHTTPResponse(status, json.dumps(payload).encode("utf-8"))
        if "/v1/text-to-speech/" in url:
            return _FakeHTTPResponse(200, b"FAKE_MP3_AUDIO_BYTES")
        raise AssertionError(f"unexpected URL in test: {url}")

    return fake_urlopen


def test_successful_add_proceeds_to_tts_and_passes_per_role_gate(monkeypatch, synthetic_pending_roles, capsys):
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    monkeypatch.setattr(mod.urllib.request, "urlopen", _router(add_response=(200, {"voice_id": "local_added_1"})))

    mod.cmd_audition_set_b()

    out = capsys.readouterr().out
    assert DUMMY_KEY not in out
    assert "ZH_ELDER_GENERATED=1" in out
    assert "ZH_HERO_GENERATED=1" in out
    assert "EN_HERO_GENERATED=1" in out
    assert "AUDITION_SET_B_VERIFICATION=PASS" in out

    for filename in ("zh_elder_candidate_x.mp3", "zh_hero_candidate_x.mp3", "en_hero_candidate_x.mp3"):
        output_path = mod.AUDITION_SET_B_DIR / filename
        assert output_path.is_file() and output_path.stat().st_size > 0


def test_failed_add_401_never_generates_misleading_success(monkeypatch, synthetic_pending_roles, capsys):
    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    monkeypatch.setattr(
        mod.urllib.request,
        "urlopen",
        _router(add_response=(401, {"detail": {"status": "invalid_api_key", "message": "bad key"}})),
    )

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_audition_set_b()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert DUMMY_KEY not in out
    assert "ZH_ELDER_GENERATED=0" in out
    assert "ZH_HERO_GENERATED=0" in out
    assert "EN_HERO_GENERATED=0" in out
    assert "AUDITION_SET_B_VERIFICATION=FAIL" in out
    assert "AUDITION_SET_B_MISSING_ROLES=zh_elder,zh_hero,en_hero" in out
    assert "AUTHENTICATION_ERROR" in out
    assert "http_status=401" in out
    # No file must exist for any candidate whose add-to-library call failed.
    assert not mod.AUDITION_SET_B_DIR.exists() or not any(mod.AUDITION_SET_B_DIR.iterdir())


def test_one_role_failing_still_fails_the_whole_gate_even_if_others_succeed(monkeypatch, synthetic_pending_roles, capsys):
    # zh_elder search returns a normal candidate that adds successfully;
    # zh_hero and en_hero both get a 401 on add. Confirms the per-role gate
    # (added in the previous hardening round) still works after this
    # refactor, and that it correctly isolates failures per role rather
    # than averaging them out.
    call_state = {"n": 0}

    def fake_urlopen(request, timeout=None):
        url = request.full_url
        if "/v1/shared-voices" in url:
            call_state["n"] += 1
            voice_id = f"shared_v{call_state['n']}"
            body = json.dumps({
                "voices": [{
                    "voice_id": voice_id,
                    "public_owner_id": "owner_x",
                    "name": f"Candidate {call_state['n']}",
                    "gender": "male",
                    "age": "young",
                    "language": "zh",
                }]
            }).encode("utf-8")
            return _FakeHTTPResponse(200, body)
        if "/v1/voices/add/" in url:
            if call_state["n"] == 1:  # zh_elder's search happened first
                return _FakeHTTPResponse(200, json.dumps({"voice_id": "local_ok"}).encode("utf-8"))
            raise _http_error(url, 401, {"detail": {"status": "invalid_api_key"}})
        if "/v1/text-to-speech/" in url:
            return _FakeHTTPResponse(200, b"FAKE_MP3_AUDIO_BYTES")
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit) as exc_info:
        mod.cmd_audition_set_b()

    out = capsys.readouterr().out
    assert exc_info.value.code == 1
    assert "ZH_ELDER_GENERATED=1" in out
    assert "ZH_HERO_GENERATED=0" in out
    assert "EN_HERO_GENERATED=0" in out
    assert "AUDITION_SET_B_MISSING_ROLES=zh_hero,en_hero" in out
    assert "zh_elder" not in out.split("AUDITION_SET_B_MISSING_ROLES=")[1].split("\n")[0]


def test_missing_public_owner_id_is_skipped_not_sent_as_malformed_request(monkeypatch, synthetic_pending_roles, capsys):
    # Defensive guard: if a Voice Library result is missing public_owner_id
    # (e.g. a future API field-name change), the tool must not construct a
    # request with a literal "None" in the URL -- it must skip that
    # candidate with a clear diagnostic instead.
    def fake_urlopen(request, timeout=None):
        url = request.full_url
        if "/v1/shared-voices" in url:
            body = json.dumps({
                "voices": [{"voice_id": "shared_v1", "name": "No Owner Candidate", "gender": "male", "age": "young", "language": "zh"}]
            }).encode("utf-8")
            return _FakeHTTPResponse(200, body)
        raise AssertionError(f"unexpected URL in test (add/tts should never be reached): {url}")

    monkeypatch.setattr(mod, "get_api_key", lambda: DUMMY_KEY)
    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit):
        mod.cmd_audition_set_b()

    out = capsys.readouterr().out
    assert "SKIP_CANDIDATE" in out
    assert "missing public_owner_id" in out
