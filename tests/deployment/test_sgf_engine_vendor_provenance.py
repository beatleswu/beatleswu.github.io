"""Verify the SGF Engine is vendored from the exact, verified source commit,
with LF line endings and complete provenance documentation."""
import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROVENANCE_DOC = REPO_ROOT / "sgf_engine" / "PROVENANCE_VERIFICATION.md"
VENDORED_FROM = REPO_ROOT / "sgf_engine" / "VENDORED_FROM.txt"
SOURCE_COMMIT = "d729645c0ae267be6d89a5b49c007bc64284bbcc"

EXPECTED_IMPLEMENTATION_FILES = [
    "sgf_engine/__init__.py",
    "sgf_engine/core/__init__.py",
    "sgf_engine/core/autoreply.py",
    "sgf_engine/core/coord_utils.py",
    "sgf_engine/core/matcher.py",
    "sgf_engine/core/tree.py",
    "sgf_engine/engine/__init__.py",
    "sgf_engine/engine/engine.py",
    "sgf_engine/inventory/__init__.py",
    "sgf_engine/inventory/sgf_inventory.py",
    "sgf_engine/override/__init__.py",
    "sgf_engine/override/override_identity.py",
    "sgf_engine/override/override_loader.py",
    "sgf_engine/override/override_loader_integration.py",
    "sgf_engine/override/override_runtime.py",
    "sgf_engine/override/override_schema.py",
    "sgf_engine/parser/__init__.py",
    "sgf_engine/parser/sgf_parser.py",
]


def tracked_sgf_engine_files():
    out = subprocess.run(
        ["git", "ls-files", "sgf_engine"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


def test_old_mismatch_doc_removed():
    assert not (REPO_ROOT / "sgf_engine" / "PROVENANCE_MISMATCH.md").exists(), (
        "the superseded false-mismatch doc must not remain alongside the corrected one"
    )


def test_provenance_verification_doc_exists():
    assert PROVENANCE_DOC.is_file()


def test_provenance_verification_doc_records_resolution():
    content = PROVENANCE_DOC.read_text(encoding="utf-8")
    assert "RESOLVED" in content
    assert SOURCE_COMMIT in content, (
        "provenance doc must record the full resolved source commit, not the abbreviated form"
    )
    assert "identical" in content.lower()


def test_vendored_from_records_full_commit_and_lf_policy():
    content = VENDORED_FROM.read_text(encoding="utf-8")
    assert f"source_commit: {SOURCE_COMMIT}" in content
    assert "source_branch: testing-baseline-test-isolation" in content
    assert "line_ending_policy: LF" in content
    assert "verification_method:" in content


def test_all_expected_implementation_files_are_tracked():
    tracked = tracked_sgf_engine_files()
    for f in EXPECTED_IMPLEMENTATION_FILES:
        assert f in tracked, f"{f} must be tracked -- vendored from {SOURCE_COMMIT}"
    assert "sgf_engine/VENDORED_FROM.txt" in tracked
    assert "sgf_engine/PROVENANCE_VERIFICATION.md" in tracked


def test_no_extra_untracked_implementation_files():
    tracked = tracked_sgf_engine_files()
    py_files = [f for f in tracked if f.endswith(".py")]
    assert sorted(py_files) == sorted(EXPECTED_IMPLEMENTATION_FILES), (
        f"tracked .py files must exactly match the source commit's set, no more no less: {py_files}"
    )


def test_vendored_files_have_no_cr_bytes():
    for rel in EXPECTED_IMPLEMENTATION_FILES + ["sgf_engine/VENDORED_FROM.txt"]:
        data = (REPO_ROOT / rel).read_bytes()
        assert b"\r" not in data, f"{rel} must contain LF-only line endings, found CR byte(s)"


def test_gitattributes_enforces_lf_for_sgf_engine():
    gitattributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.py text eol=lf" in gitattributes or "* text=auto eol=lf" in gitattributes, (
        "a *.py rule or a general text=auto eol=lf catch-all must enforce LF for vendored engine files"
    )
    assert "sgf_engine/VENDORED_FROM.txt text eol=lf" in gitattributes
