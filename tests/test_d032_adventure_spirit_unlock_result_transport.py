"""Focused D032 tests for the server-authored Adventure Spirit transport."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spirit_adventure_milestone import ADVENTURE_SPIRIT_MILESTONES
from adventure_spirit_unlock_transport import (
    CONTRACT_VERSION,
    TRANSPORT_FIELD,
    RESULT_STATES,
    AdventureSpiritUnlockTransportError,
    build_adventure_spirit_unlock_result,
    build_adventure_spirit_unlock_results,
    build_adventure_spirit_unlock_transport,
    serialize_adventure_spirit_unlock_transport,
)


D031_MODULE = REPO_ROOT / "js" / "e9" / "adventure_spirit_unlock_presentation.js"
USER_ID = 43102


def _raw_result(zone_key: str, status: str = "UNLOCKED", **overrides):
    milestone = next(item for item in ADVENTURE_SPIRIT_MILESTONES if item.zone_key == zone_key)
    eligible = status != "NOT_ELIGIBLE"
    replayed = status == "REPLAY"
    mutation_count = 1 if status == "UNLOCKED" else 0
    result = {
        "user_id": USER_ID,
        "zone_key": milestone.zone_key,
        "zone_number": milestone.zone_number,
        "spirit_id": milestone.spirit_id,
        "operation_id": f"adventure:spirit_unlock:{USER_ID}:{milestone.zone_key}",
        "source_authority": "ADVENTURE_ZONE_MILESTONE",
        "source_fact": "adventure_boss_progress.cleared=1",
        "source_reference": f"adventure_boss_progress:{USER_ID}:{milestone.zone_key}",
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


def _wire(zone_key: str, status: str = "UNLOCKED", **kwargs):
    return build_adventure_spirit_unlock_transport(
        [_raw_result(zone_key, status, **kwargs)],
        historical_catchup=False,
    )[TRANSPORT_FIELD][0]


def test_contract_field_and_state_vocabulary_are_stable():
    assert TRANSPORT_FIELD == "adventure_spirit_unlock_results"
    assert CONTRACT_VERSION == "ADVENTURE_SPIRIT_UNLOCK_RESULT_TRANSPORT_V1"
    assert RESULT_STATES == ("UNLOCKED", "NO_OP", "NOT_ELIGIBLE")


@pytest.mark.parametrize(
    ("zone_key", "spirit_id"),
    [(item.zone_key, item.spirit_id) for item in ADVENTURE_SPIRIT_MILESTONES],
)
def test_zone_transport_preserves_d030_server_mapping(zone_key, spirit_id):
    result = build_adventure_spirit_unlock_result(
        _raw_result(zone_key), historical_catchup=False
    )
    assert result.result_state == "UNLOCKED"
    assert result.ownership_created is True
    assert result.already_owned is False
    assert result.spirit_id == spirit_id
    assert result.to_dict()["source_reference"].endswith(zone_key)


def test_no_op_transport_is_explicitly_already_owned():
    result = build_adventure_spirit_unlock_result(
        _raw_result("k1_5", "NO_OP"), historical_catchup=False
    )
    assert result.result_state == "NO_OP"
    assert result.ownership_created is False
    assert result.already_owned is True
    assert result.replay is False
    assert result.to_dict()["compensation_count"] == 0
    assert result.to_dict()["replacement_count"] == 0


def test_replay_transport_cannot_look_like_new_unlock():
    result = build_adventure_spirit_unlock_result(
        _raw_result("d3_4", "REPLAY"), historical_catchup=False
    )
    assert result.status == "REPLAY"
    assert result.result_state == "NO_OP"
    assert result.ownership_created is False
    assert result.already_owned is True
    assert result.replay is True
    assert result.to_dict()["new_unlock_count"] == 0


def test_not_eligible_transport_is_neutral_and_does_not_claim_operation_completion():
    wire = _wire("k11_15", "NOT_ELIGIBLE")
    assert wire["result_state"] == "NOT_ELIGIBLE"
    assert wire["ownership_created"] is False
    assert wire["already_owned"] is None
    assert wire["replay"] is False
    assert wire["operation_status"] is None


def test_historical_catchup_requires_explicit_server_context():
    raw = _raw_result("k11_15")
    raw["historical_catchup"] = True
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_result(raw)
    assert exc_info.value.code == "HISTORICAL_CONTEXT_REQUIRED"

    catch_up = build_adventure_spirit_unlock_result(
        raw,
        historical_catchup=True,
    )
    assert catch_up.historical_catchup is True
    assert catch_up.ownership_created is True


def test_exact_replay_and_later_recheck_remain_no_op_states():
    replay = build_adventure_spirit_unlock_result(
        _raw_result("k1_5", "REPLAY"), historical_catchup=False
    )
    later = build_adventure_spirit_unlock_result(
        _raw_result("k1_5", "NO_OP"), historical_catchup=False
    )
    assert replay.to_dict()["new_unlock_count"] == 0
    assert later.to_dict()["new_unlock_count"] == 0
    assert replay.to_dict()["result_state"] == later.to_dict()["result_state"] == "NO_OP"


def test_duplicate_milestone_results_fail_closed():
    raw = _raw_result("k11_15", "REPLAY")
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_results(
            [raw, raw], historical_catchup=False
        )
    assert exc_info.value.code == "DUPLICATE_RESULT_IDENTITY"


def test_unknown_status_fails_closed():
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_result(
            _raw_result("k11_15", "SUCCESS"), historical_catchup=False
        )
    assert exc_info.value.code == "UNKNOWN_RESULT_STATE"


@pytest.mark.parametrize(
    "overrides",
    [
        {"zone_key": "unknown"},
        {"spirit_id": "fatty"},
        {"source_reference": "adventure_boss_progress:43102:k1_5"},
        {"operation_id": "purchase:43102:1"},
        {"client_completion_authority": True},
        {"compensation_count": 1},
        {"ownership_mutation_count": -1},
        {"eligible": True, "cleared": True, "replayed": False, "status": "NOT_ELIGIBLE"},
    ],
)
def test_malformed_or_mismatched_server_state_fails_closed(overrides):
    raw = _raw_result("k11_15")
    raw.update(overrides)
    with pytest.raises(AdventureSpiritUnlockTransportError):
        build_adventure_spirit_unlock_result(
            raw, historical_catchup=False
        )


def test_missing_server_evidence_fails_closed():
    raw = _raw_result("k11_15")
    del raw["source_fact"]
    with pytest.raises(AdventureSpiritUnlockTransportError) as exc_info:
        build_adventure_spirit_unlock_result(raw, historical_catchup=False)
    assert exc_info.value.code == "SOURCE_FACT_MISMATCH"


def test_result_sequence_and_deterministic_serialization():
    results = build_adventure_spirit_unlock_results(
        [_raw_result("d3_4"), _raw_result("k11_15", "NO_OP"), _raw_result("k1_5", "REPLAY")],
        historical_catchup=False,
    )
    serialized = [item.to_dict() for item in results]
    assert [item["zone_key"] for item in serialized] == ["k11_15", "k1_5", "d3_4"]
    assert serialized[0]["source_operation_id"] == serialized[0]["operation_id"]
    response = build_adventure_spirit_unlock_transport(
        [_raw_result("d3_4"), _raw_result("k1_5", "NO_OP")],
        historical_catchup=False,
    )
    encoded = serialize_adventure_spirit_unlock_transport(
        [_raw_result("d3_4"), _raw_result("k1_5", "NO_OP")],
        historical_catchup=False,
    )
    assert json.loads(encoded) == response


def test_sequence_rejects_single_untrusted_mapping():
    with pytest.raises(AdventureSpiritUnlockTransportError):
        build_adventure_spirit_unlock_results(
            _raw_result("k11_15"), historical_catchup=False
        )


def test_d031_consumes_transport_wire_shape_directly():
    node = shutil.which("node")
    if not node:
        pytest.fail("Node.js is required for the D031 consumer compatibility proof")
    payloads = [
        [_wire("k11_15", "UNLOCKED")],
        [_wire("k1_5", "NO_OP")],
        [_wire("d3_4", "REPLAY")],
        [_wire("k11_15", "NOT_ELIGIBLE")],
    ]
    script = f"""
const fs = require('fs');
const presentation = require({json.dumps(str(D031_MODULE))});
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const normalized = input.map(payload => presentation.normalizeResults(payload));
if (normalized.some(items => !items || items.length !== 1)) process.exit(2);
process.stdout.write(JSON.stringify(normalized.map(items => [items[0].status, items[0].state])));
"""
    completed = subprocess.run(
        [node, "-e", script],
        cwd=REPO_ROOT,
        input=json.dumps(payloads),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == [
        ["UNLOCKED", "NEW_SPIRIT_UNLOCK"],
        ["NO_OP", "ALREADY_OWNED_NO_OP"],
        ["REPLAY", "ALREADY_OWNED_NO_OP"],
        ["NOT_ELIGIBLE", "NO_MILESTONE_UNLOCK"],
    ]


def test_transport_omits_internal_sink_and_client_inference_fields():
    raw = _raw_result("d3_4")
    raw.update(
        {
            "sink_result": {"status": "SUCCESS"},
            "selectedZone": "k11_15",
            "client_unlock": True,
            "monster_defeated": True,
            "quest_completed": True,
        }
    )
    wire = build_adventure_spirit_unlock_result(
        raw, historical_catchup=False
    ).to_dict()
    assert "sink_result" not in wire
    assert "selectedZone" not in wire
    assert "client_unlock" not in wire
    assert wire["zone_key"] == "d3_4"
    assert wire["spirit_id"] == "obsidian_bastion"
