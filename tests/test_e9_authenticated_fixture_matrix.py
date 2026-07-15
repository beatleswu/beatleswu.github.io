import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "e9_authenticated_fixture_matrix.json"
ALLOWED_IDS = {
    "full_happy_path", "ordinary_legacy_user", "partial_optional_data",
    "empty_new_player", "malformed_payload", "unauthenticated",
    "session_switch", "api_failure_retry",
}


def load_matrix():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_matrix_is_sanitized_deterministic_and_complete():
    data = load_matrix()
    assert data["schema_version"] == "e9-authenticated-fixtures-v1"
    assert data["identity_policy"] == "synthetic-only"
    scenarios = data["scenarios"]
    assert {item["id"] for item in scenarios} == ALLOWED_IDS
    assert len(scenarios) == len(ALLOWED_IDS)
    serialized = json.dumps(data, sort_keys=True)
    for forbidden in ("@", "token", "cookie", "password", "secret", "production"):
        assert forbidden not in serialized.casefold()


def test_fixture_matrix_covers_authenticated_data_contract():
    data = load_matrix()
    happy = next(x for x in data["scenarios"] if x["id"] == "full_happy_path")
    for key in ("profile", "adventure", "daily", "srs", "mistakes", "expected"):
        assert key in happy
    assert {z["status"] for z in happy["adventure"]["zones"]} == {"completed", "unlocked"}
    assert happy["daily"]["available"] is True
    assert happy["srs"]["due_count"] == 3
    assert happy["mistakes"]["count"] == 2
    assert happy["auth"]["e9_eligible"] is True


def test_partial_empty_malformed_auth_and_retry_contracts_are_explicit():
    data = load_matrix()
    by_id = {x["id"]: x for x in data["scenarios"]}
    assert by_id["partial_optional_data"]["expected"]["fallback"] == "component-local"
    assert by_id["empty_new_player"]["expected"]["empty_states"] is True
    assert by_id["malformed_payload"]["expected"]["fail_closed"] is True
    assert by_id["unauthenticated"]["auth"]["status"] == 401
    assert by_id["session_switch"]["expected"]["no_cross_user_cache"] is True
    assert by_id["api_failure_retry"]["expected"]["retry"] is True
