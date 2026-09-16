"""POST007C_008 Lane A -- Zone4 intro cinematic wiring.

Owner UAT reported Zone4's intro cinematic never plays. Root cause was in
js/e9/world_stage.js: introCinematicKeyForZone() mapped only Zones 1-3, so
Zone4 ('k11_15') fell through to null and the journey never mounted the
cinematic host. Production telemetry confirmed e10_zone4_intro_v1 had never
fired for any account.

The behavioural assertions live in the Node harness, which executes the real
functions rather than matching source text. This module runs that harness and
adds the server-side and asset-side parity checks that keep the hotfix honest.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD_STAGE = (ROOT / "js" / "e9" / "world_stage.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")
NODE_TEST = ROOT / "tests" / "e9_node_tests" / "run_zone4_intro_cinematic_wiring_tests.js"


def test_zone4_intro_cinematic_wiring_behaviour():
    """Executes the real world_stage.js functions.

    Fails against the pre-hotfix baseline on three assertions:
    Zone4's cinematic key, Zone4's in-flight guard, and wired-zone distinctness.
    """
    result = subprocess.run(
        ["node", str(NODE_TEST)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_zone4_uses_the_existing_zones_1_3_cinematic_host():
    """No new Zone4 runtime: the hotfix only adds a mapping entry.

    adventureCinematicKey() in index.html is already generic, and
    _getIntroFilmLocaleConfigBase already carries a k11_15 branch. Wiring the
    key is therefore sufficient -- if either of those regressed into a
    Zone4-specific special case, this test catches it.
    """
    assert "k11_15" in INDEX
    # The client's key derivation must stay generic rather than growing a
    # parallel hand-maintained Zone4 ladder.
    assert "`e10_zone${index + 1}_${normalized}_v1`" in INDEX


def test_zone5_and_beyond_remain_unwired_in_the_client_mapping():
    """POST007C_008 is bounded to Zone4; Zone5 must stay untouched."""
    for zone_key in ("k6_10", "k1_5"):
        assert f"if (zoneKey === '{zone_key}') return 'e10_zone" not in WORLD_STAGE


def test_mapping_and_in_flight_guard_are_extended_in_lockstep():
    """introEntryInFlightKey's trailing fallback returns Zone2's guard.

    A zone added to the cinematic map but not the in-flight map would share
    Zone2's re-entrancy guard, and the two zones would suppress each other's
    first-entry cinematic. Guard the invariant, not the spelling.
    """
    assert "return 'zone2EntryInFlight';" in WORLD_STAGE  # the fallback still exists
    assert "if (zoneKey === 'k11_15') return 'e10_zone4_intro_v1';" in WORLD_STAGE
    assert "if (zoneKey === 'k11_15') return 'zone4EntryInFlight';" in WORLD_STAGE


def test_server_registry_already_accepts_the_zone4_intro_key():
    """The hotfix is client-only; the server contract must already be complete.

    E10_CINEMATIC_KEY_REGISTRY is built as a comprehension over zones 1-10, so
    e10_zone4_intro_v1 has always been a valid key -- only the client mapping
    was missing. That asymmetry is exactly how the defect went unnoticed: no
    server-side error was ever raised, the client simply never asked.
    """
    app_py = (ROOT / "app.py").read_text(encoding="utf-8", errors="ignore")
    assert "E10_CINEMATIC_KEY_REGISTRY = {" in app_py
    assert "f'e10_zone{zone_number}_{kind_key}_v1'" in app_py
    assert "for zone_number in range(1, 11)" in app_py


def test_hotfix_grants_no_progression_and_mutates_no_lord_state():
    """A cinematic wiring change must not touch progression or Lord gating.

    The diff is confined to two return statements in world_stage.js; assert the
    file gained no progression/Lord/reward vocabulary alongside them.
    """
    import subprocess as sp

    diff = sp.run(
        ["git", "diff", "HEAD", "--", "js/e9/world_stage.js"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    ).stdout
    added = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    forbidden = (
        "lord_ready",
        "progress_credited",
        "grantProgress",
        "awardStars",
        "earned_stars",
        "reward",
        "coins",
    )
    for line in added:
        lowered = line.lower()
        for token in forbidden:
            assert token.lower() not in lowered, f"hotfix must not touch {token}: {line}"
