"""W29 scheduler import and deployment-safety contracts.

The Production scheduler starts in /app with only the application root on the
normal module path.  Tests must not add /app/tools as a second top-level module
root because that masks incorrect imports that fail in the built image.
"""

import datetime
import os
import pathlib
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
EXACT_PERIOD = ROOT / "tools" / "community_leaderboard_rewards_exact_period.py"
DOCKERFILE = ROOT / "Dockerfile"
REQUIRED_MODULES = (
    "tools.community_leaderboard_rewards_real_grant_preview",
    "tools.community_leaderboard_rewards_real_grant_commit",
)


def test_exact_period_uses_packaged_tools_module_contract():
    source = EXACT_PERIOD.read_text(encoding="utf-8")
    for module in REQUIRED_MODULES:
        assert f"from {module} import" in source
    assert "from community_leaderboard_rewards_real_grant_preview import" not in source
    assert "from community_leaderboard_rewards_real_grant_commit import" not in source


def test_required_modules_resolve_from_scheduler_runtime_working_directory():
    script = "; ".join(f"import {module}" for module in REQUIRED_MODULES)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_dockerfile_packages_required_modules_at_matching_paths():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    for module in REQUIRED_MODULES:
        relative = module.replace(".", "/") + ".py"
        assert f"COPY {relative} /app/{relative}" in dockerfile


def test_built_scheduler_image_resolves_required_modules():
    image = os.environ.get("GO_ODYSSEY_W29_TEST_IMAGE", "").strip()
    if not image:
        pytest.skip("GO_ODYSSEY_W29_TEST_IMAGE is required for built-image verification")
    script = "; ".join(f"import {module}" for module in REQUIRED_MODULES)
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "python",
            image,
            "-c",
            script,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_overdue_enabled_target_remains_immediately_eligible_for_catchup(monkeypatch):
    monkeypatch.setenv("COMMUNITY_LEADERBOARD_REWARDS_ENABLED", "true")
    import community_leaderboard_rewards_scheduler as scheduler

    now = datetime.datetime(2026, 7, 20, 7, 53, 56, tzinfo=ZoneInfo("Asia/Taipei"))
    target = scheduler.get_weekly_scheduler_target(now=now)
    assert target["period_key"] == "2026-W29"
    assert target["due_at"] == datetime.datetime(
        2026, 7, 20, 0, 10, tzinfo=ZoneInfo("Asia/Taipei")
    )
    assert target["is_due"] is True
    assert scheduler.next_scheduler_check_at(now=now) <= now + datetime.timedelta(seconds=60)
