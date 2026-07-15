from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
ROLLBACK = (ROOT / "scripts/release/rollback-release.ps1").read_text(encoding="utf-8")
DEPLOY = (ROOT / "scripts/release/deploy-release-image.ps1").read_text(encoding="utf-8")


def _join_helper(text):
    match = re.search(
        r"function Join-RemotePath\s*\{(?P<body>.*?)\n\}",
        text,
        flags=re.DOTALL,
    )
    assert match, "rollback tooling must define Join-RemotePath"
    return match.group(0)


def _join(left, right):
    return left.rstrip("/") + "/" + right.lstrip("/")


def test_rollback_defines_the_same_remote_path_helper_as_deploy():
    assert _join_helper(ROLLBACK) == _join_helper(DEPLOY)


def test_remote_path_join_is_posix_normalized_and_preserves_absolute_base():
    helper = _join_helper(ROLLBACK)
    assert ".TrimEnd('/')" in helper
    assert ".TrimStart('/')" in helper
    assert "\\\\" not in helper
    assert _join("/opt/go-odyssey", "/docker-compose.release.yml") == \
        "/opt/go-odyssey/docker-compose.release.yml"
    assert _join("/opt/go-odyssey/", "nginx/default.conf") == \
        "/opt/go-odyssey/nginx/default.conf"


def test_rollback_gate_and_mutation_controls_remain_present():
    assert "Assert-OwnerGate -Provided $OwnerGate -Expected 'GO_ROLLBACK'" in ROLLBACK
    assert "if (-not $Execute)" in ROLLBACK
    assert "docker compose" in ROLLBACK
