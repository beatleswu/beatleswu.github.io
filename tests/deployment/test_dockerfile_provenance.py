"""Verify the Dockerfile stamps build/revision identity and doesn't reference
missing tracked paths for the inputs that ARE currently vendored."""
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"


def read_dockerfile():
    return DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_exists():
    assert DOCKERFILE.is_file()


def test_dockerfile_declares_build_args():
    content = read_dockerfile()
    for arg in ("APP_GIT_SHA", "APP_BUILD_DATE", "SGF_ENGINE_SOURCE_COMMIT"):
        assert f"ARG {arg}" in content, f"Dockerfile must declare ARG {arg}"


def test_dockerfile_stamps_oci_revision_label():
    content = read_dockerfile()
    assert "org.opencontainers.image.revision" in content
    assert "org.opencontainers.image.created" in content
    assert "org.opencontainers.image.source" in content


def test_dockerfile_references_currently_vendored_inputs_correctly():
    content = read_dockerfile()
    # Files that ARE tracked this Sprint must be referenced by a COPY that
    # matches their tracked path.
    vendored_copy_targets = [
        "requirements.txt",
        "entrypoint.sh",
        "sgf_engine",
        "nginx",  # not actually COPYed into the image (compose bind-mounts it) -- skip
    ]
    assert "COPY requirements.txt ." in content
    assert "COPY entrypoint.sh ." in content
    assert "COPY sgf_engine ./sgf_engine" in content


def test_dockerfile_does_not_hardcode_secrets():
    content = read_dockerfile().lower()
    for token in ("password", "secret_key=", "api_key=", "-----begin"):
        assert token not in content, f"Dockerfile must not contain literal secret-like token: {token}"
