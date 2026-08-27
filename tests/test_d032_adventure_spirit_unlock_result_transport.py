"""D032 server-authored Adventure Spirit result transport tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from adventure_spirit_unlock_transport import (
    AdventureSpiritUnlockTransportError,
    RESULT_STATES,
    TRANSPORT_CONTRACT_VERSION,
    TRANSPORT_FIELD,
    TRANSPORT_RESULT_STATES,
    build_adventure_spirit_unlock_result,
    build_adventure_spirit_unlock_results,
    build_adventure_spirit_unlock_transport,
    serialize_adventure_spirit_unlock_results,
    serialize_adventure_spirit_unlock_results_json,
)


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
        "user_id": 43102,
        "zone_key": zone_key,
        "zone_number": zone_number,
        "spirit_id": spirit_id,
        "operation_id": f"adventure:spirit_unlock:43102:{zone_key}",
        "source_authority": "ADVENTURE_ZONE_MILESTONE",
        "source_fact": "adventure_boss_progress.cleared=1",
        "source_reference": f"adventure_boss_progress:43102:{zone_key}",
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


def _transport(zone_index: int, status: str = "UNLOCKED", **overrides):
    return build_adventure_spirit_unlock_result(
        _raw_result(zone_index, status, **overrides),
    )


def test_contract_field_and_state_vocabulary_are_stable():
    assert TRANSPORT_FIELD == "adventure_spirit_unlock_results"
    assert TRANSPORT_CONTRACT_VERSION == "ADVENTURE_SPIRIT_UNLOCK_RESULT_TRANSPORT_V1"
    assert TRANSPORT_RESULT_STATES == RESULT_STATES == ("UNLOCKED", "NO_OP", "NOT_ELIGIBLE")


@pytest.mark.parametrize("zone_index", range(3))
def test_locked_zone_transport_preserves_d030_mapping(zone_index):
    result = _transport(zone_index)
    assert result.result_state == "UNLOCKED"
    assert result.ownership_created is True
    assert result.already_owned is False
    assert result.spirit_id == MILESTONES[zone_index][2]
    assert result.zone_number == MILESTONES[zone_index][1]


def test_no_op_transport_is_explicitly_already_owned():
    result = _transport(1, "NO_OP")
    assert result.result_state == "NO_OP"
    assert result.ownership_created is False
    assert result.already_owned is True
    assert result.replay is False
    assert result.compensation_count == result.replacement_count == 0


def test_replay_transport_is_a_no_op_and_never_new_unlock():
    result = _transport(2, "REPLAY")
    assert result.status == "REPLAY"
    assert result.result_state == "NO_OP"
    assert result.ownership_created is False
    assert result.already_owned is True
    assert result.replay is True
    assert result.new_unlock_count == 0


def test_not_eligible_transport_does_not_claim_ownership_state():
    result = _transport(2, "NOT_ELIGIBLE")
    assert result.result_state == "NOT_ELIGIBLE"
    assert result.ownership_created is False
    # D030 does not read pet_collection on this branch, so ownership remains
    # unknown rather than being fabricated as false.
    assert result.already_owned is None
    assert result.replay is False
    assert result.operation_status is None
    assert "operation_status" not in result.to_wire()


def test_historical_catchup_is_explicit_and_nullable_when_d030_does_not_emit_it():
    raw = _raw_result(0)
    direct = build_adventure_spirit_unlock_result(raw)
    assert direct.historical_catchup is None
    catch_up = build_adventure_spirit_unlock_result(raw, historical_catchup=True)
    assert catch_up.historical_catchup is True
    assert catch_up.ownership_created is True
    normal = build_adventure_spirit_unlock_result(raw, historical_catchup=False)
    assert normal.historical_catchup is False


def test_embedded_historical_marker_must_agree_with_server_context():
    raw = _raw_result(0, historical_catchup=True)
    assert build_adventure_spirit_unlock_result(raw).historical_catchup is None
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_result(raw, historical_catchup=False)
    assert exc_info.value.code == "RESULT_FIELD_CONFLICT"


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"status": "SUCCESS"}, "UNKNOWN_RESULT_STATE"),
        ({"status": "REJECTED"}, "UNKNOWN_RESULT_STATE"),
        ({"zone_key": "selectedZone"}, "UNKNOWN_MILESTONE"),
        ({"spirit_id": "ink_drop_kelpie"}, "SPIRIT_IDENTITY_MISMATCH"),
        ({"source_fact": "monster_defeated"}, "SOURCE_FACT_MISMATCH"),
        ({"operation_id": "client-operation"}, "OPERATION_ID_MISMATCH"),
        ({"client_completion_authority": True}, "CLIENT_AUTHORITY_PRESENT"),
        ({"compensation_count": 1}, "UNAUTHORIZED_COMPENSATION"),
        ({"replayed": "true"}, "INVALID_BOOLEAN"),
    ],
)
def test_unknown_or_malformed_state_fails_closed(overrides, code):
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_result(_raw_result(0, **overrides))
    assert exc_info.value.code == code


def test_missing_required_server_fact_fails_closed():
    raw = _raw_result(0)
    del raw["source_fact"]
    with pytest.raises(AdventureSpiritUnlockTransportError):
        build_adventure_spirit_unlock_result(raw)


def test_eligible_result_requires_completed_d030_operation():
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_result(_raw_result(0, operation_status="PENDING"))
    assert exc_info.value.code == "NON_TERMINAL_RESULT"


def test_conflicting_normalized_fields_fail_closed():
    raw = _raw_result(0, result_state="NO_OP")
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_result(raw)
    assert exc_info.value.code == "RESULT_FIELD_CONFLICT"


def test_list_transport_is_sorted_and_rejects_duplicate_zone_identity():
    outcomes = [_raw_result(2), _raw_result(0), _raw_result(1, "REPLAY")]
    results = build_adventure_spirit_unlock_results(outcomes)
    assert [result.zone_number for result in results] == [4, 6, 8]
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_results([_raw_result(0), _raw_result(0)])
    assert exc_info.value.code == "DUPLICATE_RESULT_IDENTITY"


def test_response_fragment_contains_only_the_transport_field_and_is_deterministic():
    first = build_adventure_spirit_unlock_transport([_raw_result(2), _raw_result(0)])
    second = build_adventure_spirit_unlock_transport([_raw_result(0), _raw_result(2)])
    assert first == second
    assert list(first) == [TRANSPORT_FIELD]
    assert [item["zone_number"] for item in first[TRANSPORT_FIELD]] == [4, 8]


def test_serialization_is_deterministic_and_does_not_forward_untrusted_fields():
    raw = _raw_result(
        2,
        sink_result={"status": "SUCCESS"},
        selectedZone="k11_15",
        client_unlock=True,
        monster_defeated=True,
        quest_completed=True,
    )
    typed = _transport(2, sink_result={"status": "SUCCESS"})
    wire = typed.to_wire()
    assert "sink_result" not in wire
    assert "selectedZone" not in wire
    assert "client_unlock" not in wire
    assert wire["zone_key"] == "d3_4"
    json_a = serialize_adventure_spirit_unlock_results_json([typed])
    json_b = serialize_adventure_spirit_unlock_results_json([typed])
    assert json_a == json_b
    assert json.loads(json_a) == serialize_adventure_spirit_unlock_results([typed])
    # The raw client-shaped fields above never participate in construction.
    assert build_adventure_spirit_unlock_transport([raw])[TRANSPORT_FIELD][0]["spirit_id"] == "obsidian_bastion"


@pytest.mark.parametrize("status", ["UNLOCKED", "NO_OP", "REPLAY", "NOT_ELIGIBLE"])
def test_d031_consumer_accepts_each_transport_state(status):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for D031 consumer compatibility")
    typed = _transport(0, status)
    script = (
        "const fs=require('fs');"
        "const p=require(process.argv[1]);"
        "const input=JSON.parse(fs.readFileSync(0,'utf8'));"
        "const normalized=p.normalizeResult(input);"
        "if (!normalized) process.exit(2);"
        "process.stdout.write(normalized.state);"
    )
    completed = subprocess.run(
        [node, "-e", script, str(D031_PRESENTATION)],
        cwd=ROOT,
        input=json.dumps(typed.to_wire()),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout in RESULT_STATES or completed.stdout in {
        "NEW_SPIRIT_UNLOCK",
        "ALREADY_OWNED_NO_OP",
        "NO_MILESTONE_UNLOCK",
    }


def test_module_is_pure_and_does_not_import_app_or_mutate_authority():
    source = (ROOT / "adventure_spirit_unlock_transport.py").read_text(encoding="utf-8")
    assert "import app" not in source
    assert "INSERT" not in source.upper()
    assert "UPDATE" not in source.upper()
    assert "DELETE" not in source.upper()
    assert "commit(" not in source
    assert "rollback(" not in source
