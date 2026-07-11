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
    assert len(data["files"]) == 69


def test_manifest_covers_every_recovered_runtime_file():
    data = load_manifest()
    paths = {entry["path"] for entry in data["files"]}
    expected = {
        "backend_i18n.py", "chapter_i18n.py", "explain_overrides.py", "grimoire_api.py",
        "katago_explain.py", "monster_taxonomy.py", "question_taxonomy.py", "scheduler.py",
        "community_leaderboard_rewards.py", "db.py",
        "tools/community_leaderboard_rewards_export_entries.py",
        "tools/community_leaderboard_rewards_manual.py",
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
        out = subprocess.run(
            ["git", "cat-file", "blob", f"{entry['source_commit']}:{entry['path']}"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        )
        actual = (REPO_ROOT / entry["path"]).read_bytes()
        if _is_binary(entry["path"]):
            assert actual == out.stdout, f"{entry['path']} does not match its recorded source commit"
        else:
            src_norm = out.stdout.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            assert actual == src_norm, f"{entry['path']} does not match its recorded source commit"


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
        directory = path.split("/", 1)[0] if "/" in path else None
        assert path in tokens or filename in tokens or directory in tokens, (
            f"Dockerfile must explicitly COPY {path}"
        )
