"""Guard against the image silently packaging administrative tools whose
runtime dependencies are absent. If the Dockerfile ever copies a
tools/community_leaderboard_rewards_*.py script, it must also copy
community_leaderboard_rewards.py -- otherwise the tool is non-functional
inside the built image even though it compiles."""
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"

LEADERBOARD_TOOLS = [
    "tools/community_leaderboard_rewards_manual.py",
    "tools/community_leaderboard_rewards_export_entries.py",
    "tools/community_leaderboard_rewards_real_grant_preview.py",
    "tools/community_leaderboard_rewards_real_grant_commit.py",
    "tools/community_leaderboard_rewards_exact_period.py",
]


def dockerfile_text():
    return DOCKERFILE.read_text(encoding="utf-8")


def test_leaderboard_tools_dependency_copied_if_tools_are_copied():
    content = dockerfile_text()
    any_tool_copied = any(f"COPY {t} " in content for t in LEADERBOARD_TOOLS)
    if any_tool_copied:
        assert "COPY community_leaderboard_rewards.py " in content, (
            "Dockerfile copies community_leaderboard_rewards_*.py tools but not their "
            "community_leaderboard_rewards.py dependency -- this packages non-functional tools"
        )


def test_leaderboard_dependency_is_tracked_and_present():
    dep = REPO_ROOT / "community_leaderboard_rewards.py"
    assert dep.is_file(), (
        "community_leaderboard_rewards.py must exist in the checkout for the "
        "leaderboard tools packaged in the Dockerfile to be functional"
    )


def test_all_copied_tools_importable_with_dependency_present():
    import subprocess
    import sys

    for tool in LEADERBOARD_TOOLS:
        module_name = pathlib.Path(tool).stem
        result = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, 'tools'); sys.path.insert(0, '.'); import {module_name}"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"{tool} failed to import: {result.stderr}"
