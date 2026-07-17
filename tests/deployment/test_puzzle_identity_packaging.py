"""Release-artifact contracts for canonical puzzle identity files."""

import json
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
BUILD_MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"
PROVENANCE = REPO_ROOT / "deploy" / "runtime-source-provenance.json"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-production-image.ps1"
RELEASE_BUILD_SCRIPT = REPO_ROOT / "scripts" / "release" / "build-release-image.ps1"

SOURCE_COMMIT = "d507df960fc5303229279068d16a5c49c4c83ecf"
SOURCE_SUBJECT = "feat(sgf): add composite canonical puzzle identity"
IDENTITY_HASHES = {
    "puzzle_identity.py": (
        "0b0ba05bfc806d9197892bdd133cc73d585e2e628800d3e9b211a4b6bdc8efd1"
    ),
    "migrations/__init__.py": (
        "407b7990e34e7b358d7252c776e460d9cacc64c6c5a1355adac41c1edd9ba6bf"
    ),
    "migrations/puzzle_identity_alias_v1.py": (
        "0faef6b73888ad088c5f323ba4e35813001d3c4c42f19319db0248f5636f476c"
    ),
    "tools/puzzle_identity_backfill.py": (
        "b450ab3d896b18bdf4ad39d2c9e07d9618fafce70799c2cc5b290791ecc7a979"
    ),
}
ARTIFACT_PATHS = {
    "puzzle_identity.py": "/app/puzzle_identity.py",
    "migrations/__init__.py": "/app/migrations/__init__.py",
    "migrations/puzzle_identity_alias_v1.py": (
        "/app/migrations/puzzle_identity_alias_v1.py"
    ),
    "tools/puzzle_identity_backfill.py": "/app/tools/puzzle_identity_backfill.py",
}


def _text(path):
    return path.read_text(encoding="utf-8")


def test_identity_files_are_explicitly_copied_without_directory_wildcards():
    content = _text(DOCKERFILE)
    expected = {
        "COPY puzzle_identity.py ./",
        "COPY migrations/__init__.py /app/migrations/__init__.py",
        (
            "COPY migrations/puzzle_identity_alias_v1.py "
            "/app/migrations/puzzle_identity_alias_v1.py"
        ),
        (
            "COPY tools/puzzle_identity_backfill.py "
            "/app/tools/puzzle_identity_backfill.py"
        ),
    }
    for copy_line in expected:
        assert copy_line in content
    assert "COPY migrations ./migrations" not in content
    assert "COPY tools ./tools" not in content


def test_identity_files_are_manifest_tracked_and_verified_in_artifact():
    manifest = json.loads(_text(BUILD_MANIFEST))
    tracked = set(
        manifest["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
    )
    verified = set(manifest["post_build_verification_files"])

    assert set(IDENTITY_HASHES).issubset(tracked)
    assert set(ARTIFACT_PATHS.values()).issubset(verified)


def test_identity_provenance_points_to_exact_reachable_source_blobs():
    provenance = json.loads(_text(PROVENANCE))
    entries = {entry["path"]: entry for entry in provenance["files"]}

    for path, content_hash in IDENTITY_HASHES.items():
        entry = entries[path]
        assert entry["source_commit"] == SOURCE_COMMIT
        assert entry["source_branch_or_local_ref"] == (
            "codex/sgf-canonical-identity-20260717"
        )
        assert entry["source_commit_subject"] == SOURCE_SUBJECT
        assert entry["source_date"] == "2026-07-17"
        assert entry["content_sha256"] == content_hash
        assert entry["line_ending_policy"] == "LF"


def test_build_and_release_whitelists_include_every_identity_file():
    build_content = _text(BUILD_SCRIPT)
    for path in IDENTITY_HASHES:
        assert f"'{path}'," in build_content

    release_content = _text(RELEASE_BUILD_SCRIPT)
    compile_line = next(
        line for line in release_content.splitlines()
        if "python -m py_compile" in line
    )
    for path in IDENTITY_HASHES:
        assert path in compile_line


def test_migration_and_backfill_are_not_automatic_runtime_or_rollback_steps():
    execution_surfaces = [
        REPO_ROOT / "app.py",
        REPO_ROOT / "scheduler.py",
        REPO_ROOT / "entrypoint.sh",
        REPO_ROOT / "scripts" / "release" / "deploy-release-image.ps1",
        REPO_ROOT / "scripts" / "release" / "rollback-release.ps1",
    ]
    forbidden_invocations = (
        "puzzle_identity_alias_v1",
        "puzzle_identity_backfill",
    )

    for surface in execution_surfaces:
        content = _text(surface)
        for invocation in forbidden_invocations:
            assert invocation not in content, (
                f"{surface.relative_to(REPO_ROOT)} must not invoke {invocation}"
            )
