"""Executable safety contract for the Docker build-context boundary.

The production build runs from an exact-SHA detached worktree.  This test
uses a synthetic repository with representative untracked canaries to verify
the same Git worktree mechanism: only committed source appears in the context
and the source identity remains the requested commit.
"""
from __future__ import annotations

import pathlib
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "scripts" / "build-production-image.ps1"
DOCKERIGNORE = ROOT / ".dockerignore"


def git(cwd: pathlib.Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_detached_exact_commit_context_excludes_synthetic_untracked_canaries(tmp_path):
    """A detached worktree exposes only the selected commit's tracked tree."""
    source = tmp_path / "canonical"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "context-test@example.invalid")
    git(source, "config", "user.name", "context-test")
    for relative_path in ("Dockerfile", "app.py", "requirements.txt"):
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("tracked\n", encoding="utf-8")
    git(source, "add", "Dockerfile", "app.py", "requirements.txt")
    git(source, "commit", "-m", "tracked context fixture")
    expected_sha = git(source, "rev-parse", "HEAD")

    canaries = (
        "untracked-secret-canary.txt",
        "secret_key.txt",
        ".env.test",
        "local-test.db",
        "venv_test/marker.txt",
        "node_modules/example/marker.txt",
        "katago/local-marker.txt",
        "ordinary-untracked.txt",
    )
    for relative_path in canaries:
        path = source / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("TEST CANARY -- NOT A SECRET\n", encoding="utf-8")

    context = tmp_path / "tracked-context"
    try:
        git(source, "worktree", "add", "--detach", str(context), expected_sha)
        assert git(context, "rev-parse", "HEAD") == expected_sha
        assert git(context, "branch", "--show-current") == ""
        assert {
            path.relative_to(context).as_posix()
            for path in context.rglob("*")
            if path.is_file() and ".git" not in path.parts
        } == {"Dockerfile", "app.py", "requirements.txt"}
        for relative_path in canaries:
            assert not (context / relative_path).exists()
    finally:
        if context.exists():
            git(source, "worktree", "remove", str(context))


def test_build_uses_validated_exact_worktree_as_docker_context_not_ambient_dot():
    content = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "$dockerBuildContext = Assert-DetachedWorktreeIdentity" in content
    assert "-Path $validatedWorktreeRoot" in content
    assert "-ExpectedGitSha $GitSha" in content
    assert "$dockerBuildContext" in content
    build_arguments = content[content.index("'buildx', 'build'") :]
    assert "        $dockerBuildContext" in build_arguments
    assert "        '.'" not in build_arguments


def test_dockerignore_is_present_as_defense_in_depth_for_representative_local_files():
    patterns = set(DOCKERIGNORE.read_text(encoding="utf-8").splitlines())
    for required in (
        ".git",
        ".env",
        ".env.*",
        "secret_key.txt",
        "*.db",
        "venv*/",
        "node_modules/",
        "katago/",
        "*.log",
    ):
        assert required in patterns


def test_required_build_inputs_remain_tracked():
    tracked = set(git(ROOT, "ls-files").splitlines())
    assert {"Dockerfile", "app.py", "requirements.txt"} <= tracked
