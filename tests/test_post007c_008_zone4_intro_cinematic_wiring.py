"""P0 Lane A -- Zone4 intro cinematic wiring regression.

The authoritative behavioral checks live in the Node harness. This pytest
wrapper makes that runtime contract part of the normal regression collection.
"""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = ROOT / "tests" / "e9_node_tests" / "run_zone4_intro_cinematic_wiring_tests.js"


def test_zone4_intro_cinematic_wiring_executes_real_runtime_functions():
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "6/6 passed" in result.stdout


def test_zone4_mapping_is_an_explicit_bounded_extension():
    source = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
    assert "if (zoneKey === 'k11_15') return 'e10_zone4_intro_v1';" in source
    assert "if (zoneKey === 'k11_15') return 'zone4EntryInFlight';" in source
    generic_zone_template = "e10_zone" + "$" + "{n}_intro_v1"
    assert generic_zone_template not in source


def test_zone5_client_mapping_is_not_enabled():
    source = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
    for zone_key in ("k6_10", "k1_5"):
        assert "if (zoneKey === '" + zone_key + "') return 'e10_zone" not in source


def test_server_registry_and_existing_host_contract_remain_unchanged():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    index_source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "E10_CINEMATIC_KEY_REGISTRY = {" in app_source
    assert "for zone_number in range(1, 11)" in app_source
    assert "adventureCinematicKey(zone" in index_source
