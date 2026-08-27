"""D033 additive Adventure boss-finish response adapter tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from dataclasses import replace

import pytest

from adventure_boss_finish_response import (
    AdventureBossFinishResponseError,
    RESPONSE_FIELD,
    build_adventure_boss_finish_spirit_result_fragment,
    compose_adventure_boss_finish_response,
)
from adventure_spirit_unlock_transport import build_adventure_spirit_unlock_result


ROOT = Path(__file__).resolve().parents[1]
D031_PRESENTATION = ROOT / "js" / "e9" / "adventure_spirit_unlock_presentation.js"

MILESTONES = (
    ("k11_15", 4, "starpath_antlerling"),
    ("k1_5", 6, "fatty"),
    ("d3_4", 8, "obsidian_bastion"),
)


def _raw_result(zone_index: int, status: str = "UNLOCKED", **overrides):
    zone_key, zone_number, spirit_id = MILESTONES[zone_index]
    eligible = status != "NOT_ELIGIBLE"
    replayed = status == "REPLAY"
    mutation_count = 1 if status == "UNLOCKED" else 0
    result = {
        "user_id": 53101,
        "zone_key": zone_key,
        "zone_number": zone_number,
        "spirit_id": spirit_id,
        "operation_id": f"adventure:spirit_unlock:53101:{zone_key}",
        "source_authority": "ADVENTURE_ZONE_MILESTONE",
        "source_fact": "adventure_boss_progress.cleared=1",
        "source_reference": f"adventure_boss_progress:53101:{zone_key}",
        "cleared": eligible,
        "eligible": eligible,
        "operation_type": "SPIRIT_UNLOCK",
        "ownership_store": "pet_collection",
        "compensation_count": 0,
        "replacement_count": 0,
        "client_completion_authority": False,
        "status": status,
        "replayed": replayed,
        "ownership_mutation_count": mutation_count,
        "new_unlock_count": mutation_count,
    }
    if eligible:
        result["operation_status"] = "COMPLETED"
    result.update(overrides)
    return result


def _typed(zone_index: int, status: str = "UNLOCKED", **overrides):
    return build_adventure_spirit_unlock_result(
        _raw_result(zone_index, status, **overrides)
    )


def _existing_response():
    return {
        "ok": True,
        "passed": True,
        "correct": 20,
        "total": 20,
        "pass_score": 15,
        "cooldown_left": 0,
        "attempt_mode": "first_clear",
        "replay": False,
        "reward": {"coins": 50, "first_clear": True},
        "map": {"zone_key": "k11_15", "stars": 1},
    }


@pytest.mark.parametrize("zone_index", range(3))
def test_locked_zone_results_are_additive_and_preserve_existing_response(zone_index):
    existing = _existing_response()
    composed = compose_adventure_boss_finish_response(existing, _typed(zone_index))

    assert composed[RESPONSE_FIELD][0]["result_state"] == "UNLOCKED"
    assert composed[RESPONSE_FIELD][0]["zone_number"] == MILESTONES[zone_index][1]
    assert composed[RESPONSE_FIELD][0]["spirit_id"] == MILESTONES[zone_index][2]
    assert set(composed) == set(existing) | {RESPONSE_FIELD}
    assert {key: composed[key] for key in existing} == existing
    assert existing.get(RESPONSE_FIELD) is None


def test_no_result_is_neutral_empty_d032_list_without_fabricated_unlock():
    existing = _existing_response()
    composed = compose_adventure_boss_finish_response(existing, None)
    assert composed[RESPONSE_FIELD] == []
    assert "spirit_id" not in json.dumps(composed[RESPONSE_FIELD])
    assert {key: composed[key] for key in existing} == existing


def test_explicit_not_eligible_is_preserved_as_d032_neutral_state():
    result = _typed(2, "NOT_ELIGIBLE")
    composed = compose_adventure_boss_finish_response(_existing_response(), result)
    item = composed[RESPONSE_FIELD][0]
    assert item["status"] == "NOT_ELIGIBLE"
    assert item["result_state"] == "NOT_ELIGIBLE"
    assert item["ownership_created"] is False
    assert item["already_owned"] is None


def test_already_owned_serializes_as_no_op_without_new_ownership():
    item = compose_adventure_boss_finish_response(
        _existing_response(), _typed(1, "NO_OP")
    )[RESPONSE_FIELD][0]
    assert item["status"] == "NO_OP"
    assert item["result_state"] == "NO_OP"
    assert item["ownership_created"] is False
    assert item["already_owned"] is True
    assert item["new_unlock_count"] == 0
    assert item["compensation_count"] == 0
    assert item["replacement_count"] == 0


def test_replay_serializes_as_no_op_and_never_as_new_unlock():
    item = compose_adventure_boss_finish_response(
        _existing_response(), _typed(0, "REPLAY")
    )[RESPONSE_FIELD][0]
    assert item["status"] == "REPLAY"
    assert item["result_state"] == "NO_OP"
    assert item["replay"] is True
    assert item["replayed"] is True
    assert item["ownership_created"] is False
    assert item["new_unlock_count"] == 0


def test_historical_catchup_is_serialized_only_when_explicitly_server_marked():
    result = _typed(0)
    historical_wire = result.to_wire()
    historical_wire.pop("historical_catchup", None)
    historical = build_adventure_spirit_unlock_result(
        historical_wire, historical_catchup=True
    )
    item = compose_adventure_boss_finish_response(
        _existing_response(), historical
    )[RESPONSE_FIELD][0]
    assert item["status"] == "UNLOCKED"
    assert item["historical_catchup"] is True
    assert item["ownership_created"] is True


@pytest.mark.parametrize(
    "bad_value",
    [
        {"status": "UNLOCKED"},
        object(),
        {"selectedZone": "k11_15", "spirit_id": "fatty"},
    ],
)
def test_raw_or_client_shaped_result_is_rejected(bad_value):
    with pytest.raises(AdventureBossFinishResponseError) as exc_info:
        compose_adventure_boss_finish_response(_existing_response(), bad_value)
    assert exc_info.value.code == "MALFORMED_TRANSPORT"


def test_unknown_d032_state_fails_closed_without_partial_response():
    malformed = replace(_typed(0), status="UNKNOWN")
    with pytest.raises(AdventureBossFinishResponseError) as exc_info:
        compose_adventure_boss_finish_response(_existing_response(), malformed)
    assert exc_info.value.code == "MALFORMED_TRANSPORT"


def test_malformed_typed_transport_fails_closed():
    malformed = replace(_typed(0), source_fact="monster_defeated")
    with pytest.raises(AdventureBossFinishResponseError) as exc_info:
        build_adventure_boss_finish_spirit_result_fragment(malformed)
    assert exc_info.value.code == "MALFORMED_TRANSPORT"


def test_duplicate_results_fail_closed_and_no_second_response_authority():
    with pytest.raises(AdventureBossFinishResponseError) as exc_info:
        compose_adventure_boss_finish_response(
            _existing_response(), [_typed(0), _typed(0, "REPLAY")]
        )
    assert exc_info.value.code == "DUPLICATE_RESULT_IDENTITY"


def test_result_order_is_deterministic_and_response_field_is_attached_once():
    response = compose_adventure_boss_finish_response(
        _existing_response(), [_typed(2), _typed(0), _typed(1, "REPLAY")]
    )
    assert [item["zone_number"] for item in response[RESPONSE_FIELD]] == [4, 6, 8]
    with pytest.raises(AdventureBossFinishResponseError) as exc_info:
        compose_adventure_boss_finish_response(response, _typed(0))
    assert exc_info.value.code == "RESPONSE_FIELD_ALREADY_PRESENT"


def test_d031_consumes_composed_payload_directly_for_all_states():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for D031 compatibility")
    cases = (
        (_typed(0), "NEW_SPIRIT_UNLOCK"),
        (_typed(1, "NO_OP"), "ALREADY_OWNED_NO_OP"),
        (_typed(2, "REPLAY"), "ALREADY_OWNED_NO_OP"),
        (_typed(2, "NOT_ELIGIBLE"), "NO_MILESTONE_UNLOCK"),
    )
    script = (
        "const fs=require('fs');"
        "const p=require(process.argv[1]);"
        "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
        "const normalized=p.normalizeResults(input);"
        "if (!normalized || normalized.length !== 1) process.exit(2);"
        "process.stdout.write(normalized[0].state);"
    )
    for typed, expected in cases:
        response = compose_adventure_boss_finish_response(
            _existing_response(), typed
        )
        completed = subprocess.run(
            [node, "-e", script, str(D031_PRESENTATION)],
            cwd=ROOT,
            input=json.dumps(response[RESPONSE_FIELD]),
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout == expected


def test_d031_consumes_neutral_no_result_without_client_inference():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for D031 compatibility")
    response = compose_adventure_boss_finish_response(_existing_response(), None)
    script = (
        "const p=require(process.argv[1]);"
        "const normalized=p.normalizeResults(JSON.parse(process.argv[2]));"
        "if (!Array.isArray(normalized) || normalized.length !== 0) process.exit(2);"
    )
    completed = subprocess.run(
        [node, "-e", script, str(D031_PRESENTATION), json.dumps(response[RESPONSE_FIELD])],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_response_adapter_is_pure_and_does_not_import_or_mutate_authority():
    source = (ROOT / "adventure_boss_finish_response.py").read_text(encoding="utf-8")
    assert "import app" not in source
    assert "INSERT" not in source.upper()
    assert "execute(" not in source
    assert "DELETE" not in source.upper()
    assert "commit(" not in source
    assert "rollback(" not in source
    assert "selectedZone" not in source
