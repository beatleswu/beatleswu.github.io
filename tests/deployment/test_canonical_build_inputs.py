"""Verify required build inputs are tracked in the canonical repository.

These tests check the working tree as checked out from Git (via `git
ls-files`), not just filesystem presence, so an accidentally-untracked file
still fails the check.
"""
import subprocess
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return set(out.stdout.splitlines())


TRACKED = tracked_files()

REQUIRED_TRACKED_FILES = [
    "Dockerfile",
    "docker-compose.prod.yml",
    "docker-compose.build.yml",
    "requirements.txt",
    "entrypoint.sh",
    "scheduler.py",
    "nginx/default.conf",
    "app.py",
    "shadow_judging.py",
    "shadow_dashboard.py",
    "shadow_dashboard.html",
    "katago_explain.py",
    "explain_overrides.py",
    "grimoire_api.py",
    "question_taxonomy.py",
    "monster_taxonomy.py",
    "chapter_i18n.py",
    "backend_i18n.py",
    "db.py",
    "community_leaderboard_rewards.py",
    "tools/community_leaderboard_rewards_manual.py",
    "tools/community_leaderboard_rewards_export_entries.py",
    "tools/community_leaderboard_rewards_real_grant_preview.py",
    "tools/community_leaderboard_rewards_real_grant_commit.py",
    "deploy/build-manifest.json",
    "deploy/runtime-source-provenance.json",
    "scripts/build-production-image.ps1",
    "sgf_engine/PROVENANCE_VERIFICATION.md",
    "sgf_engine/VENDORED_FROM.txt",
    ".gitattributes",
    ".env.production.example",
    "index.html",
    "login.html",
    "i18n.js",
    "wgo/wgo.min.js",
    "blog/index.html",
]


@pytest.mark.parametrize("path", REQUIRED_TRACKED_FILES)
def test_required_file_is_tracked(path):
    assert path in TRACKED, f"{path} must be tracked in git, is not"


def test_env_file_not_tracked():
    assert ".env" not in TRACKED, ".env must never be committed"


def test_no_private_key_or_cert_files_tracked():
    import re

    pattern = re.compile(r"\.pem$|\.key$|id_rsa|id_ed25519|oracle_godoyssey")
    matches = [f for f in TRACKED if pattern.search(f)]
    assert not matches, f"tracked files look like secret/key material: {matches}"
