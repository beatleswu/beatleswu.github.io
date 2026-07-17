"""Deployment contracts for the governed Shadow Judging storage module."""
import json
import pathlib


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
BUILD_MANIFEST = REPO_ROOT / "deploy" / "build-manifest.json"
PROVENANCE = REPO_ROOT / "deploy" / "runtime-source-provenance.json"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build-production-image.ps1"
RELEASE_BUILD_SCRIPT = REPO_ROOT / "scripts" / "release" / "build-release-image.ps1"


def _text(path):
    return path.read_text(encoding="utf-8")


def test_shadow_storage_is_explicitly_copied_and_manifest_governed():
    assert "COPY shadow_event_storage.py ./" in _text(DOCKERFILE)
    manifest = json.loads(_text(BUILD_MANIFEST))
    assert "shadow_event_storage.py" in manifest["build_inputs"][
        "tracked_in_canonical_branch_this_sprint"
    ]
    assert "/app/shadow_event_storage.py" in manifest[
        "post_build_verification_files"
    ]


def test_manifest_provenance_count_matches_exact_governed_set():
    manifest = json.loads(_text(BUILD_MANIFEST))
    provenance = json.loads(_text(PROVENANCE))
    assert len(provenance["files"]) == 82
    assert manifest["runtime_dependency_provenance"]["files_covered"] == len(
        provenance["files"]
    )


def test_shadow_storage_provenance_is_exact_and_reachable_contract_is_tested():
    provenance = json.loads(_text(PROVENANCE))
    entry = next(
        item for item in provenance["files"]
        if item["path"] == "shadow_event_storage.py"
    )
    assert entry["source_commit"] == "eee0a73e172264c01816cae016301c4fd2d174e6"
    assert entry["source_commit_subject"] == "feat(sgf): complete shadow judging v1 governance"
    assert entry["source_date"] == "2026-07-17"
    assert entry["content_sha256"] == (
        "6007a0ed06b5f456f1624f67cac56593c035c70a276ee603babc367c16bacc05"
    )
    assert entry["line_ending_policy"] == "LF"


def test_canonical_builder_requires_and_checks_manifest_files_in_one_bounded_run():
    content = _text(BUILD_SCRIPT)
    assert "'shadow_event_storage.py'," in content
    assert "$verificationFiles = @($manifest.post_build_verification_files)" in content
    assert "'^/app/[A-Za-z0-9._/-]+$'" in content
    assert "'(^|/)\\.\\.(/|$)'" in content
    assert "'run', '--rm'," in content
    assert "'--network', 'none'," in content
    assert "'--read-only'," in content
    assert "'--entrypoint', 'python'," in content
    assert "Invoke-BoundedNativeCommand" in content
    assert "-TimeoutSeconds 120" in content
    assert "-OperationLabel 'required built-image filesystem verification'" in content


def test_release_precompile_includes_shadow_storage():
    content = _text(RELEASE_BUILD_SCRIPT)
    compile_line = next(line for line in content.splitlines() if "python -m py_compile" in line)
    assert "shadow_dashboard.py" in compile_line
    assert "shadow_event_storage.py" in compile_line
