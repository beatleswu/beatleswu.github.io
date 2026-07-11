"""Verify deploy/build-manifest.json is well-formed and matches repository
state, without containing secret values."""
import json
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"

SECRET_TOKEN_PATTERN = re.compile(
    r"PASSWORD|SECRET|TOKEN|PRIVATE KEY|BEGIN OPENSSH|DATABASE_URL", re.IGNORECASE
)


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_exists_and_is_valid_json():
    data = load_manifest()
    assert isinstance(data, dict)


def test_manifest_references_dockerfile_and_compose():
    data = load_manifest()
    assert data["build"]["dockerfile"] == "Dockerfile"
    assert (REPO_ROOT / data["build"]["dockerfile"]).is_file()
    assert (REPO_ROOT / data["build"]["deploy_compose_template"]).is_file()
    assert (REPO_ROOT / data["build"]["build_compose_template"]).is_file()


def test_manifest_immutable_tag_format_is_not_bare_latest():
    data = load_manifest()
    assert data["build"]["immutable_tag_format"] != "latest"
    assert "<short-git-sha>" in data["build"]["immutable_tag_format"] or "sha" in data["build"]["immutable_tag_format"].lower()


def test_manifest_required_secret_variables_have_no_values():
    data = load_manifest()
    for name in data["required_secret_variables"]:
        assert isinstance(name, str)
        # Variable names only -- must look like an env var identifier, not contain '='
        assert "=" not in name


def test_manifest_contains_no_secret_values():
    raw = MANIFEST.read_text(encoding="utf-8")
    data = json.loads(raw)
    # required_secret_variables intentionally contains the substring "SECRET"
    # in variable names -- that's expected. Check there are no assigned
    # literal-looking values (key=value pairs with a plausible secret body).
    suspicious = re.findall(r'"[A-Za-z0-9_]*(?:PASSWORD|SECRET|TOKEN)[A-Za-z0-9_]*"\s*:\s*"([^"]{8,})"', raw)
    for value in suspicious:
        assert value.startswith("PENDING") or value.startswith("BLOCKED") or "resolved by" in value or "not yet" in value, (
            f"build-manifest.json contains a suspicious literal value: {value}"
        )


def test_manifest_pending_inputs_documented_with_reason():
    data = load_manifest()
    for item in data["build_inputs"]["required_but_not_yet_vendored"]:
        assert "path" in item and "reason" in item and "required_by" in item
