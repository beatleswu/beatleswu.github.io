"""P0 Lane -- Zone4 Owner-final cinematic content recovery regressions."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = ROOT / "tests" / "e9_node_tests" / "run_p0_zone4_new_cinematic_content_recovery_tests.js"


def test_zone4_owner_final_content_adapter_and_closure():
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "6/6 passed" in result.stdout


def test_existing_zone4_wiring_regression_remains_green():
    node_test = ROOT / "tests" / "e9_node_tests" / "run_zone4_intro_cinematic_wiring_tests.js"
    result = subprocess.run(
        ["node", str(node_test)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "6/6 passed" in result.stdout


def test_zone4_failure_boundary_is_explicit_in_host():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "_ensureZone4CinematicContentReady" in source
    assert "_showZone4CinematicUnavailable" in source
    assert "if (zone?.key === 'k11_15' && !(await _ensureZone4CinematicContentReady(zone))) return;" in source
    assert "go_misty_forest_" not in source


def test_zone2_zone3_and_zone5_boundaries_remain_unchanged():
    source = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
    assert "if (zoneKey === 'k21_25') return 'e10_zone2_intro_v1';" in source
    assert "if (zoneKey === 'k16_20') return 'e10_zone3_intro_v1';" in source
    for zone_key in ("k6_10", "k1_5", "d1_2", "d3_4"):
        assert f"if (zoneKey === '{zone_key}') return 'e10_zone" not in source
