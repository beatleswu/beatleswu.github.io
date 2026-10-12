"""R12 integration successor for the N07/N08 A1 narrow-scope check.

The A1 successor requires app.py to be byte-identical to the baseline. The
integrated candidate legitimately carries two separately authorized app.py
changes (N33 .glb/MIME overrides, EQ-F flag-off effect closure). This test keeps
every other A1 scope assertion and requires app.py to equal the baseline once
exactly those two recorded hunks are reversed. Original frozen tests are not edited.
"""
import hashlib
import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "ec213d06dce2393dba94a18c00738509d4994a1f"
FROZEN_SHA = "153d5edf592e5dc9b275abd1dce11b59517a10e562aab4b98a5ecf8ae17a1165"
HUNKS = ROOT / "tests/fixtures/g009_r12_authorized_app_hunks"


def _git_show(path):
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT)


def _norm(data):
    return data.replace(b"\r\n", b"\n")


def test_a1_index_scope_is_submit_srs_only_and_other_frozen_files_unchanged():
    frozen_path = ROOT / "tests/test_e10_presentation_dispatcher_v1b.py"
    assert hashlib.sha256(frozen_path.read_bytes()).hexdigest() == FROZEN_SHA
    spec = importlib.util.spec_from_file_location("r12_a1_frozen_helpers", frozen_path)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    current = (ROOT / "index.html").read_text(encoding="utf-8")
    base = _git_show("index.html").decode("utf-8")
    before = original._extract_function(base, "submitSRS")
    after = original._extract_function(current, "submitSRS")
    assert before != after
    assert current.replace(after, "A1_SUBMIT_BODY", 1) == base.replace(before, "A1_SUBMIT_BODY", 1)
    for name in original.FROZEN_INDEX_FUNCTIONS:
        if name != "submitSRS":
            assert original._extract_function(current, name) == original._extract_function(base, name)
    for path in ["js/game/lord_trial_controller.js", "srs.js", "js/game/mode_context.js", "js/game/question_loader.js"]:
        assert (ROOT / path).read_bytes() == _git_show(path)


def test_app_py_differs_from_baseline_only_by_the_two_authorized_hunks():
    patches = sorted(HUNKS.glob("*.diff"))
    assert [p.name for p in patches] == [
        "eqf_flag_off_effect_closure.diff",
        "n33_glb_and_mime_overrides.diff",
    ]
    work = Path(tempfile.mkdtemp(prefix="r12-app-scope-"))
    try:
        subprocess.check_call(["git", "init", "-q"], cwd=work)
        (work / "app.py").write_bytes(_norm((ROOT / "app.py").read_bytes()))
        for patch in reversed(patches):
            subprocess.check_call(
                ["git", "apply", "-R", "--ignore-whitespace", str(patch)], cwd=work)
        assert _norm((work / "app.py").read_bytes()) == _norm(_git_show("app.py"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
