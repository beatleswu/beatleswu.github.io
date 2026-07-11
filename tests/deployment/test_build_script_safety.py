"""Verify scripts/build-production-image.ps1 never deploys, SSHes, or
restarts anything, and derives a Git-SHA-based tag rather than only `latest`."""
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build-production-image.ps1"

FORBIDDEN_TOKENS = [
    "docker compose up",
    "docker-compose up",
    "docker push",
    "ssh ",
    "scp ",
    "docker restart",
    "docker exec",
    "Invoke-Command",
]


def read_script():
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT.is_file()


def test_script_never_deploys_or_touches_remote_hosts():
    content = read_script()
    for token in FORBIDDEN_TOKENS:
        assert token not in content, f"build script must not contain: {token!r}"


def test_script_derives_tag_from_git_sha():
    content = read_script()
    assert "shortSha" in content or "GitSha" in content
    assert 'go-odyssey-app:$shortSha' in content or "go-odyssey-app:" in content


def test_script_does_not_print_secrets():
    content = read_script()
    for name in ("SECRET_KEY", "POSTGRES_PASSWORD", "PAYPAL_SECRET", "NEWEBPAY_HASH_KEY"):
        assert name not in content, f"build script must not reference secret variable {name}"


def test_script_declares_build_only_intent():
    content = read_script()
    assert "never deploy" in content.lower() or "build-only" in content.lower() or "build only" in content.lower()
