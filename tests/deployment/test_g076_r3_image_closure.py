"""G076-R3 guarded runtime packaging: no accidental omitting new modules."""
import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

PYTHON=(
    "g076_question_privacy.py",
    "g076_server_step_authority.py",
    "g076_step_ledger.py",
    "sgf_point_transform.py",
    "sgf_answer_authority.py",
)
BROWSER=("js/game/g076_authoritative_step_client.js",)


def test_all_g076_runtime_dependencies_are_in_explicit_docker_copy():
    docker=(ROOT/"Dockerfile").read_text(encoding="utf-8")
    for name in (*PYTHON,*BROWSER):
        assert f"COPY {name} " in docker
        assert (ROOT/name).is_file()


def test_build_manifest_has_matching_tracked_and_baked_paths():
    data=json.loads((ROOT/"deploy/build-manifest.json").read_text(encoding="utf-8"))
    tracked=data["build_inputs"]["tracked_in_canonical_branch_this_sprint"]
    verification=data["post_build_verification_files"]
    for name in (*PYTHON,*BROWSER):
        assert tracked.count(name)==1
        assert verification.count("/app/"+name)==1


def test_referenced_browser_adapter_has_a_serving_route():
    app=ast.parse((ROOT/"app.py").read_text(encoding="utf-8"))
    functions={node.name:node for node in app.body if isinstance(node,ast.FunctionDef)}
    assert "serve_g076_authoritative_step_client_js" in functions
    src=(ROOT/"index.html").read_text(encoding="utf-8")
    assert '<script src="/js/game/g076_authoritative_step_client.js' in src


def test_step_endpoints_remain_dark_without_both_gate_flags():
    src=(ROOT/"app.py").read_text(encoding="utf-8")
    assert "G076_STEP_RUNTIME_ENABLED" in src
    assert "privacy_enforced(os.environ)" in src
    assert src.count("if not _g076_step_enabled():")>=2
