"""Verify every recovered runtime dependency (outside sgf_engine) has recorded
Git provenance, matches its recorded source SHA, uses LF, and that the
Dockerfile no longer copies arbitrary Python files by wildcard."""
import json
import hashlib
import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "deploy" / "runtime-source-provenance.json"
DOCKERFILE = REPO_ROOT / "Dockerfile"


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_exists_and_valid():
    data = load_manifest()
    assert isinstance(data["files"], list)
    assert len(data["files"]) == 13


def test_manifest_covers_every_recovered_runtime_file():
    data = load_manifest()
    paths = {entry["path"] for entry in data["files"]}
    expected = {
        "backend_i18n.py", "chapter_i18n.py", "explain_overrides.py", "grimoire_api.py",
        "katago_explain.py", "monster_taxonomy.py", "question_taxonomy.py", "scheduler.py",
        "community_leaderboard_rewards.py",
        "tools/community_leaderboard_rewards_export_entries.py",
        "tools/community_leaderboard_rewards_manual.py",
        "tools/community_leaderboard_rewards_real_grant_commit.py",
        "tools/community_leaderboard_rewards_real_grant_preview.py",
    }
    assert paths == expected


def test_every_entry_has_required_fields():
    data = load_manifest()
    required = {"path", "source_commit", "source_branch_or_local_ref", "source_commit_subject",
                "source_date", "content_sha256", "line_ending_policy", "runtime_role", "source_status"}
    for entry in data["files"]:
        assert required.issubset(entry.keys()), f"{entry['path']} missing fields: {required - entry.keys()}"
        assert entry["line_ending_policy"] == "LF"
        assert len(entry["source_commit"]) == 40, f"{entry['path']} source_commit must be a full 40-char SHA"


def test_source_status_does_not_overclaim_review():
    data = load_manifest()
    for entry in data["files"]:
        status = entry["source_status"]
        assert "not previously pushed to canonical origin" in status
        assert "reviewed" not in status.lower() or "not" in status.lower()


def test_working_tree_matches_recorded_content_sha256():
    data = load_manifest()
    for entry in data["files"]:
        p = REPO_ROOT / entry["path"]
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == entry["content_sha256"], f"{entry['path']} content drifted from recorded provenance"


def test_working_tree_matches_recorded_source_commit_blob():
    data = load_manifest()
    for entry in data["files"]:
        out = subprocess.run(
            ["git", "cat-file", "blob", f"{entry['source_commit']}:{entry['path']}"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        )
        src_norm = out.stdout.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        actual = (REPO_ROOT / entry["path"]).read_bytes()
        assert actual == src_norm, f"{entry['path']} does not match its recorded source commit"


def test_no_cr_bytes_in_recovered_files():
    data = load_manifest()
    for entry in data["files"]:
        p = REPO_ROOT / entry["path"]
        assert b"\r" not in p.read_bytes(), f"{entry['path']} must be LF-only"


def test_dockerfile_has_no_python_wildcard_copy():
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    copy_lines = [ln for ln in lines if ln.strip().startswith("COPY ")]
    wildcard_py = [ln for ln in copy_lines if "*.py" in ln]
    assert not wildcard_py, f"Dockerfile must not wildcard-copy arbitrary Python files: {wildcard_py}"


def test_dockerfile_explicitly_copies_every_provenance_tracked_file():
    content = DOCKERFILE.read_text(encoding="utf-8")
    data = load_manifest()
    for entry in data["files"]:
        path = entry["path"]
        filename = path.rsplit("/", 1)[-1]
        assert f"COPY {path} " in content or f"COPY {filename} " in content, (
            f"Dockerfile must explicitly COPY {path}"
        )
