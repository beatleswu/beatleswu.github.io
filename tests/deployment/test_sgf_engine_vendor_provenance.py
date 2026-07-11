"""Verify the SGF Engine provenance state is honestly documented, and that no
engine code was silently vendored despite the recorded mismatch."""
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROVENANCE_DOC = REPO_ROOT / "sgf_engine" / "PROVENANCE_MISMATCH.md"


def test_provenance_doc_exists():
    assert PROVENANCE_DOC.is_file()


def test_provenance_doc_states_blocked():
    content = PROVENANCE_DOC.read_text(encoding="utf-8")
    assert "BLOCKED" in content
    assert "d729645c0ae267be6d89a5b49c007bc64284bbcc" in content, (
        "provenance doc must record the full resolved source commit, not the abbreviated form"
    )


def test_no_sgf_engine_implementation_code_is_tracked():
    import subprocess

    out = subprocess.run(
        ["git", "ls-files", "sgf_engine"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    tracked = out.stdout.splitlines()
    # Only the provenance documentation may be tracked -- no .py implementation files.
    py_files = [f for f in tracked if f.endswith(".py")]
    assert not py_files, f"sgf_engine implementation code must not be vendored while BLOCKED: {py_files}"
    assert "sgf_engine/PROVENANCE_MISMATCH.md" in tracked
