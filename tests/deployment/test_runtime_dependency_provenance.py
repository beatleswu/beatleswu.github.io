"""Verify every governed runtime dependency (outside sgf_engine) has recorded
Git provenance, matches its recorded source SHA, uses LF, and that the
Dockerfile no longer copies arbitrary Python files by wildcard."""
import json
import hashlib
import pathlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "deploy" / "runtime-source-provenance.json"
DOCKERFILE = REPO_ROOT / "Dockerfile"


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_exists_and_valid():
    data = load_manifest()
    assert isinstance(data["files"], list)
    assert len(data["files"]) == 78


def test_manifest_covers_every_governed_runtime_file():
    data = load_manifest()
    paths = {entry["path"] for entry in data["files"]}
    expected = {
        "js/e9/feature_flags.js", "js/e9/world_stage.js",
        "css/e9/world_stage.css", "components/adventure/world_stage.html",
        "backend_i18n.py", "chapter_i18n.py", "explain_overrides.py", "grimoire_api.py",
        "katago_explain.py", "monster_taxonomy.py", "question_taxonomy.py", "scheduler.py",
        "shadow_event_storage.py",
        "community_leaderboard_rewards_scheduler.py",
        "community_leaderboard_rewards.py", "db.py",
        "newebpay.py", "paypal_api.py",
        "tools/community_leaderboard_rewards_export_entries.py",
        "tools/community_leaderboard_rewards_manual.py",
        "tools/community_leaderboard_rewards_exact_period.py",
        "tools/community_leaderboard_rewards_real_grant_commit.py",
        "tools/community_leaderboard_rewards_real_grant_preview.py",
        "login.html", "landing.html", "index.html", "terms.html", "manage.html",
        "admin.html", "bot.html", "daily_challenge.html", "community.html",
        "messages.html", "share_view.html", "mistakes.html", "curriculum.html",
        "hero.html", "rating_test.html", "shop.html", "profile.html",
        "premium_weekly.html", "stats.html", "upgrade.html", "play.html",
        "inventory.html", "badges.html", "games.html",
        "i18n.js", "sw.js", "srs.js", "monster_trash.js", "sound.js",
        "mobile-nav.js", "site-nav.js", "community_reward_notifications.js",
        "community_reward_rules.js", "pwa.js",
        "manifest.json", "robots.txt", "sitemap.xml", "og-image.jpg",
        "icon-192.png", "icon-512.png",
        "wgo/stone_skin.js", "wgo/wgo.min.js", "wgo/wgo.player.css",
        "wgo/wgo.player.min.js", "wgo/wood1.jpg",
        "blog/go-ai-improve.html", "blog/go-rules-for-beginners.html",
        "blog/go-scoring-counting.html", "blog/go-vs-chess.html",
        "blog/how-to-improve-at-go.html", "blog/how-to-play-go.html",
        "blog/index.html", "blog/kids-learn-go-age.html",
        "blog/what-is-life-and-death.html", "blog/what-is-tsumego.html",
    }
    assert paths == expected


BINARY_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _is_binary(path):
    return path.endswith(BINARY_EXTENSIONS)


def _recorded_blob(entry, repo_root=REPO_ROOT):
    return subprocess.run(
        ["git", "cat-file", "blob", f"{entry['source_commit']}:{entry['path']}"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    ).stdout


def _assert_working_tree_matches_recorded_blob(entry, repo_root=REPO_ROOT):
    source = _recorded_blob(entry, repo_root=repo_root)
    actual = (repo_root / entry["path"]).read_bytes()
    if _is_binary(entry["path"]):
        assert actual == source, f"{entry['path']} does not match its recorded source commit"
    else:
        source = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        assert actual == source, f"{entry['path']} does not match its recorded source commit"


def test_every_entry_has_required_fields():
    data = load_manifest()
    required = {"path", "source_commit", "source_branch_or_local_ref", "source_commit_subject",
                "source_date", "content_sha256", "line_ending_policy", "runtime_role", "source_status"}
    for entry in data["files"]:
        assert required.issubset(entry.keys()), f"{entry['path']} missing fields: {required - entry.keys()}"
        if _is_binary(entry["path"]):
            assert entry["line_ending_policy"] == "N/A (binary)"
        else:
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
        _assert_working_tree_matches_recorded_blob(entry)


def test_origin_master_provenance_commits_exist_and_are_reachable():
    entries = [
        entry for entry in load_manifest()["files"]
        if entry["source_branch_or_local_ref"] == "origin/master"
    ]
    assert entries
    for entry in entries:
        subprocess.run(
            ["git", "cat-file", "-e", f"{entry['source_commit']}^{{commit}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", entry["source_commit"], "origin/master"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )


def _synthetic_provenance_repository(tmp_path):
    repo = tmp_path / "provenance-repository"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Provenance Test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "provenance@example.invalid"], cwd=repo, check=True)
    source = repo / "governed.txt"
    source.write_bytes(b"recorded\n")
    subprocess.run(["git", "add", "governed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "record governed blob"], cwd=repo, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    return repo, source, commit


def test_missing_provenance_commit_fails_closed(tmp_path):
    repo, _source, _commit = _synthetic_provenance_repository(tmp_path)
    entry = {"path": "governed.txt", "source_commit": "0" * 40}
    with pytest.raises(subprocess.CalledProcessError):
        _assert_working_tree_matches_recorded_blob(entry, repo_root=repo)


def test_wrong_provenance_blob_fails_closed(tmp_path):
    repo, source, commit = _synthetic_provenance_repository(tmp_path)
    source.write_bytes(b"different\n")
    entry = {"path": "governed.txt", "source_commit": commit}
    with pytest.raises(AssertionError, match="does not match"):
        _assert_working_tree_matches_recorded_blob(entry, repo_root=repo)


def test_no_cr_bytes_in_recovered_text_files():
    data = load_manifest()
    for entry in data["files"]:
        if _is_binary(entry["path"]):
            continue
        p = REPO_ROOT / entry["path"]
        assert b"\r" not in p.read_bytes(), f"{entry['path']} must be LF-only"


def test_dockerfile_has_no_python_wildcard_copy():
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    copy_lines = [ln for ln in lines if ln.strip().startswith("COPY ")]
    wildcard_py = [ln for ln in copy_lines if "*.py" in ln]
    assert not wildcard_py, f"Dockerfile must not wildcard-copy arbitrary Python files: {wildcard_py}"


def _copy_line_tokens(content):
    """Tokens (source-side arguments) from every multi-line-aware COPY
    instruction, so files listed on a shared `COPY a b c ./` line (or
    continued with a trailing backslash) are still recognized as
    explicitly enumerated, not just the first token on the line."""
    tokens = []
    lines = content.replace("\\\n", " ").splitlines()
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("COPY "):
            parts = stripped.split()[1:-1]  # drop 'COPY' and the destination
            tokens.extend(parts)
    return tokens


def test_dockerfile_explicitly_copies_every_provenance_tracked_file():
    content = DOCKERFILE.read_text(encoding="utf-8")
    tokens = _copy_line_tokens(content)
    data = load_manifest()
    for entry in data["files"]:
        path = entry["path"]
        filename = path.rsplit("/", 1)[-1]
        # a directory-level COPY (e.g. `COPY wgo ./wgo`) covers every file
        # inside it; a flat-file COPY lists the filename directly.
        directories = [
            "/".join(path.split("/")[:index])
            for index in range(1, len(path.split("/")))
        ]
        assert path in tokens or filename in tokens or any(directory in tokens for directory in directories), (
            f"Dockerfile must explicitly COPY {path}"
        )
