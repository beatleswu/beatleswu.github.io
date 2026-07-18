"""Verify every governed runtime dependency (outside sgf_engine) has recorded
Git provenance, matches its recorded source SHA, uses LF, and that the
Dockerfile no longer copies arbitrary Python files by wildcard."""
import json
import hashlib
import pathlib
import re
import subprocess
from collections import Counter

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
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _is_binary(path):
    return path.endswith(BINARY_EXTENSIONS)


def _run_git(repo_root, *arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )


def _assert_normalized_manifest_path(path):
    assert isinstance(path, str) and path, "provenance path must be nonblank"
    assert SAFE_PATH_RE.fullmatch(path), f"unsafe or malformed provenance path: {path!r}"
    parsed = pathlib.PurePosixPath(path)
    assert not parsed.is_absolute(), f"absolute provenance path is forbidden: {path!r}"
    assert "." not in parsed.parts and ".." not in parsed.parts
    assert str(parsed) == path, f"provenance path is not normalized: {path!r}"


def _assert_entry_metadata(entry):
    _assert_normalized_manifest_path(entry["path"])
    assert COMMIT_RE.fullmatch(entry["source_commit"]), (
        f"{entry['path']} source_commit must be a lowercase full SHA"
    )
    label = entry["source_branch_or_local_ref"]
    assert isinstance(label, str) and label.strip(), (
        f"{entry['path']} source_branch_or_local_ref must be nonblank"
    )


def _assert_provenance_entry(entry, repo_root=REPO_ROOT, master_ref="origin/master"):
    """Fail closed on metadata, object, ancestry, path, and raw blob identity."""
    _assert_entry_metadata(entry)
    commit = entry["source_commit"]
    path = entry["path"]
    _run_git(repo_root, "cat-file", "-e", f"{commit}^{{commit}}")
    _run_git(repo_root, "merge-base", "--is-ancestor", commit, master_ref)
    _run_git(repo_root, "cat-file", "-e", f"{commit}:{path}")
    source = _run_git(repo_root, "cat-file", "blob", f"{commit}:{path}").stdout
    governed_path = repo_root / pathlib.PurePosixPath(path)
    assert governed_path.is_file(), f"governed path is missing: {path}"
    assert governed_path.read_bytes() == source, (
        f"{path} does not raw-byte-match its recorded source commit"
    )
    subject = _run_git(repo_root, "show", "-s", "--format=%s", commit).stdout.decode(
        "utf-8"
    ).rstrip("\r\n")
    source_date = _run_git(repo_root, "show", "-s", "--format=%cs", commit).stdout.decode(
        "ascii"
    ).strip()
    assert entry["source_commit_subject"] == subject, f"{path} source subject metadata drifted"
    assert entry["source_date"] == source_date, f"{path} source date metadata drifted"
    return path


def _assert_all_provenance_entries(entries, repo_root=REPO_ROOT, master_ref="origin/master"):
    return [
        _assert_provenance_entry(entry, repo_root=repo_root, master_ref=master_ref)
        for entry in entries
    ]


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
        _assert_entry_metadata(entry)


def test_source_status_does_not_overclaim_review():
    data = load_manifest()
    for entry in data["files"]:
        status = entry["source_status"]
        assert isinstance(status, str) and status.strip()
        assert "reviewed" not in status.lower() or "not" in status.lower()


def test_working_tree_matches_recorded_content_sha256():
    data = load_manifest()
    for entry in data["files"]:
        p = REPO_ROOT / entry["path"]
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == entry["content_sha256"], f"{entry['path']} content drifted from recorded provenance"


def test_working_tree_matches_recorded_source_commit_blob():
    data = load_manifest()
    examined = _assert_all_provenance_entries(data["files"])
    expected = [entry["path"] for entry in data["files"]]
    assert examined == expected
    assert Counter(examined) == Counter(expected)
    assert all(count == 1 for count in Counter(examined).values())


def test_every_recorded_commit_exists_and_is_reachable_from_origin_master():
    entries = load_manifest()["files"]
    assert entries
    for entry in entries:
        _assert_entry_metadata(entry)
        _run_git(REPO_ROOT, "cat-file", "-e", f"{entry['source_commit']}^{{commit}}")
        _run_git(
            REPO_ROOT,
            "merge-base",
            "--is-ancestor",
            entry["source_commit"],
            "origin/master",
        )


def _synthetic_provenance_repository(tmp_path):
    repo = tmp_path / "provenance-repository"
    repo.mkdir()
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.name", "Provenance Test")
    _run_git(repo, "config", "user.email", "provenance@example.invalid")
    source = repo / "governed.txt"
    source.write_bytes(b"recorded\n")
    binary = repo / "governed.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-recorded-binary")
    _run_git(repo, "add", "governed.txt", "governed.png")
    _run_git(repo, "commit", "-q", "-m", "record governed blobs")
    commit = _run_git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    _run_git(repo, "update-ref", "refs/remotes/origin/master", commit)
    return repo, source, binary, commit


def _synthetic_entry(repo, path, commit, label="origin/master"):
    subject = _run_git(repo, "show", "-s", "--format=%s", commit).stdout.decode(
        "utf-8"
    ).rstrip("\r\n")
    source_date = _run_git(repo, "show", "-s", "--format=%cs", commit).stdout.decode(
        "ascii"
    ).strip()
    return {
        "path": path,
        "source_commit": commit,
        "source_branch_or_local_ref": label,
        "source_commit_subject": subject,
        "source_date": source_date,
    }


def _make_unreachable_present_commit(repo):
    _run_git(repo, "checkout", "-q", "-b", "local-only")
    (repo / "local-only.txt").write_text("local-only\n", encoding="utf-8")
    _run_git(repo, "add", "local-only.txt")
    _run_git(repo, "commit", "-q", "-m", "local-only provenance object")
    return _run_git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()


def test_missing_provenance_commit_fails_closed(tmp_path):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    entry = _synthetic_entry(repo, "governed.txt", commit)
    entry["source_commit"] = "0" * 40
    with pytest.raises(subprocess.CalledProcessError):
        _assert_provenance_entry(entry, repo_root=repo)


@pytest.mark.parametrize("label", ("origin/master", "historical/local-only"))
def test_present_but_unreachable_commit_fails_regardless_of_label(tmp_path, label):
    repo, _source, _binary, _commit = _synthetic_provenance_repository(tmp_path)
    unreachable = _make_unreachable_present_commit(repo)
    entry = _synthetic_entry(repo, "governed.txt", unreachable, label=label)
    _run_git(repo, "cat-file", "-e", f"{unreachable}^{{commit}}")
    with pytest.raises(subprocess.CalledProcessError):
        _assert_provenance_entry(entry, repo_root=repo)


def test_reachable_commit_with_missing_recorded_path_fails_closed(tmp_path):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    (repo / "not-at-commit.txt").write_text("current-only\n", encoding="utf-8")
    entry = _synthetic_entry(repo, "not-at-commit.txt", commit)
    with pytest.raises(subprocess.CalledProcessError):
        _assert_provenance_entry(entry, repo_root=repo)


def test_path_exists_but_recorded_blob_differs(tmp_path):
    repo, source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    source.write_bytes(b"new reachable version\n")
    _run_git(repo, "add", "governed.txt")
    _run_git(repo, "commit", "-q", "-m", "change governed blob")
    new_master = _run_git(repo, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    _run_git(repo, "update-ref", "refs/remotes/origin/master", new_master)
    entry = _synthetic_entry(repo, "governed.txt", commit)
    with pytest.raises(AssertionError, match="raw-byte-match"):
        _assert_provenance_entry(entry, repo_root=repo)


def test_current_governed_file_change_fails_closed(tmp_path):
    repo, source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    source.write_bytes(b"different\n")
    entry = _synthetic_entry(repo, "governed.txt", commit)
    with pytest.raises(AssertionError, match="raw-byte-match"):
        _assert_provenance_entry(entry, repo_root=repo)


def test_blank_source_label_fails_metadata_validation(tmp_path):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    entry = _synthetic_entry(repo, "governed.txt", commit, label="   ")
    with pytest.raises(AssertionError, match="must be nonblank"):
        _assert_provenance_entry(entry, repo_root=repo)


def test_binary_blob_mismatch_fails_closed(tmp_path):
    repo, _source, binary, commit = _synthetic_provenance_repository(tmp_path)
    binary.write_bytes(b"\x89PNG\r\n\x1a\nchanged-binary")
    entry = _synthetic_entry(repo, "governed.png", commit)
    with pytest.raises(AssertionError, match="raw-byte-match"):
        _assert_provenance_entry(entry, repo_root=repo)


def test_new_manifest_record_automatically_enters_validation(tmp_path):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    valid = _synthetic_entry(repo, "governed.txt", commit)
    newly_added = _synthetic_entry(repo, "governed.png", commit)
    newly_added["source_commit"] = "0" * 40
    with pytest.raises(subprocess.CalledProcessError):
        _assert_all_provenance_entries([valid, newly_added], repo_root=repo)


def test_all_manifest_records_are_examined_exactly_once(tmp_path):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    entries = [
        _synthetic_entry(repo, "governed.txt", commit),
        _synthetic_entry(repo, "governed.png", commit),
    ]
    examined = _assert_all_provenance_entries(entries, repo_root=repo)
    assert examined == ["governed.txt", "governed.png"]
    assert Counter(examined) == {"governed.txt": 1, "governed.png": 1}


def test_git_command_failure_is_not_ignored(tmp_path):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    entry = _synthetic_entry(repo, "governed.txt", commit)
    with pytest.raises(subprocess.CalledProcessError):
        _assert_provenance_entry(entry, repo_root=repo, master_ref="origin/missing")


@pytest.mark.parametrize("malformed", ("not-a-sha", "A" * 40, "1" * 39, "1" * 41))
def test_malformed_commit_hash_fails_before_git(tmp_path, malformed):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    entry = _synthetic_entry(repo, "governed.txt", commit)
    entry["source_commit"] = malformed
    with pytest.raises(AssertionError, match="lowercase full SHA"):
        _assert_provenance_entry(entry, repo_root=repo)


@pytest.mark.parametrize(
    "malformed",
    ("../escape.txt", "/absolute.txt", "nested/../escape.txt", "nested\\escape.txt", "double//slash.txt", "C:/drive.txt", ""),
)
def test_malformed_or_escaping_path_fails_before_git(tmp_path, malformed):
    repo, _source, _binary, commit = _synthetic_provenance_repository(tmp_path)
    entry = _synthetic_entry(repo, "governed.txt", commit)
    entry["path"] = malformed
    with pytest.raises(AssertionError):
        _assert_provenance_entry(entry, repo_root=repo)


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
