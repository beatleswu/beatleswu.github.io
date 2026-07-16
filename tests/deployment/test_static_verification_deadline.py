import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "release" / "ReleaseTooling.psm1"


def budget(files, concurrency, timeout, attempts=1):
    command = (
        f"Import-Module '{MODULE}' -Force; "
        f"Get-StaticPublicVerificationDeadlineSeconds -FileCount {files} "
        f"-Concurrency {concurrency} -RequestTimeoutSeconds {timeout} "
        f"-AttemptCount {attempts}"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return int(result.stdout.strip().splitlines()[-1])


def test_large_bundle_budget_scales_beyond_legacy_deadline():
    assert budget(1390, 8, 15) > 240


def test_small_bundle_has_bounded_minimum():
    assert budget(0, 8, 15) == 120
    assert budget(1, 8, 15) == 135


def test_retries_increase_budget():
    assert budget(100, 8, 15, 2) > budget(100, 8, 15, 1)


def test_concurrency_and_timeout_are_validated():
    with pytest.raises(AssertionError):
        budget(10, 0, 15)
    with pytest.raises(AssertionError):
        budget(10, 8, -1)


def test_large_inputs_are_capped():
    assert budget(10**18, 1, 2**31 - 1, 10**6) == 7200
