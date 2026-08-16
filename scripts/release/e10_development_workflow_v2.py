#!/usr/bin/env python3
"""Run the local-only E10 Development Workflow V2 foundation contracts.

The three commands in this module are evidence and handoff stages only:

* ``pr-ready`` validates an implementation worktree and its supplied tests.
* ``post-merge`` validates an Owner-executed merge without performing one.
* ``release-prep`` emits a local handoff to the existing release tooling.

This module never merges, deploys, rolls back, enables, grants, contacts
Production, or infers an Owner gate.  Product source and workflow/tooling
source are required to be explicit, separate identities in every packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "e10-development-workflow-v2-foundation-v1"
NOT_YET_MERGED = "NOT_YET_MERGED"
CONTROL_PLANE_ONLY = "CONTROL_PLANE_ONLY"
PRODUCT_CHANGE = "PRODUCT_CHANGE"
SCOPE_MODES = frozenset({CONTROL_PLANE_ONLY, PRODUCT_CHANGE})
R2A_HISTORY_PRESENT = "YES_EXPECTED"
R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE = "NO"
OWNER_GATES = frozenset(
    {"GO_MERGE", "GO_DEPLOY", "GO_ROLLBACK", "GO_ENABLE", "GO_GRANT"}
)
ROLLBACK_AUTHORITY = "EXPLICIT_PRE_DEPLOY_CURRENT_PAIR"
REQUIRED_POST_MERGE_GATES = frozenset(
    {"source_separation", "canonical_ancestry", "runtime_provenance", "repository_status"}
)
CANONICAL_RELEASE_TOOLS = {
    "static_builder": "scripts/release/package-static-release.ps1",
    "static_deployer": "scripts/release/deploy-static-release.ps1",
    "oci_builder": "scripts/release/build-release-image.ps1",
    "oci_packager": "scripts/release/package-release-image.ps1",
    "rollback_preflight": "scripts/release/preflight-production.ps1",
}

SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CONFLICT_MARKER_LINE = re.compile(rb"(?m)^(?:<<<<<<<|=======|>>>>>>>)")

# CONTROL_PLANE_ONLY owns only local workflow/release tooling, deployment
# tests, and workflow documentation.  PRODUCT_CHANGE uses an explicit exact
# file set and never broadens this control-plane allowlist implicitly.
ALLOWED_WORKFLOW_PREFIXES = (
    "scripts/release/",
    "tests/deployment/",
    "docs/deployment/",
)
FORBIDDEN_EXACT_PATHS = frozenset(
    {
        "app.py",
        "index.html",
        "srs.js",
        "sw.js",
        "questions.json",
        "secret_key.txt",
    }
)


class WorkflowError(ValueError):
    """Raised when a Workflow V2 packet cannot be proven safe."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = dict(details or {})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkflowError(message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{label} is required")
    return value.strip()


def _sha40(value: Any, label: str) -> str:
    value = _text(value, label)
    _require(bool(SHA40.fullmatch(value)), f"{label} must be a lowercase SHA-1 commit")
    return value


def _sha256(value: Any, label: str) -> str:
    value = _text(value, label)
    _require(bool(SHA256.fullmatch(value)), f"{label} must be a lowercase SHA-256 digest")
    return value


def _repo_path(payload: Mapping[str, Any]) -> Path:
    path = Path(_text(payload.get("repo"), "repo")).resolve()
    _require(path.is_dir(), f"worktree does not exist: {path}")
    try:
        root = _git(path, "rev-parse", "--show-toplevel")
    except WorkflowError as exc:
        raise WorkflowError(f"repo is not a Git worktree: {path}") from exc
    _require(Path(root).resolve() == path, "repo must be the requested worktree root")
    return path


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise WorkflowError(f"git failed: {detail}")
    return result.stdout.strip()


def _git_bytes(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise WorkflowError(f"git failed: {detail}")
    return result.stdout


def _commit(repo: Path, value: Any, label: str) -> str:
    requested = _sha40(value, label)
    try:
        resolved = _git(repo, "rev-parse", "--verify", requested + "^{commit}")
    except WorkflowError as exc:
        raise WorkflowError(f"{label} is not present in this repository") from exc
    _require(resolved == requested, f"{label} is not present in this repository")
    return resolved


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _parents(repo: Path, commit: str) -> list[str]:
    parts = _git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    _require(parts and parts[0] == commit, f"could not read parents for {commit}")
    for parent in parts[1:]:
        _sha40(parent, "merge parent")
    return parts[1:]


def _working_tree_status(repo: Path) -> list[str]:
    raw = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    return [line for line in raw.splitlines() if line]


def _parse_changed_files(raw: str) -> list[dict[str, str]]:
    tokens = [token for token in raw.split("\0") if token]
    result: list[dict[str, str]] = []
    index = 0
    while index < len(tokens):
        status_token = tokens[index]
        index += 1
        status = status_token[0]
        if status in {"R", "C"}:
            _require(index + 1 < len(tokens), "malformed rename diff")
            previous, path = tokens[index], tokens[index + 1]
            index += 2
            result.append({"path": path, "status": status, "previous_path": previous})
        else:
            _require(index < len(tokens), "malformed Git diff")
            result.append({"path": tokens[index], "status": status})
            index += 1
    return sorted(result, key=lambda item: (item["path"], item["status"], item.get("previous_path", "")))


def _changed_files(repo: Path, base: str, head: str) -> list[dict[str, str]]:
    raw = _git(
        repo,
        "diff",
        "--name-status",
        "--find-renames",
        "-z",
        base + "..." + head,
    )
    return _parse_changed_files(raw)


def _path_for_scope(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _scope_mode(value: Any) -> str:
    mode = _text(value, "SCOPE_MODE")
    _require(mode in SCOPE_MODES, "SCOPE_MODE must be CONTROL_PLANE_ONLY or PRODUCT_CHANGE")
    return mode


def _is_protected_local_artifact_path(path: str) -> bool:
    normalized = _path_for_scope(path)
    lower = normalized.lower()
    components = lower.split("/")
    name = components[-1]
    if name == "secret_key.txt" or name.startswith(".env"):
        return True
    if name.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx", ".exe", ".dll")):
        return True
    if any(component in {"node_modules", "backups", "katago", "ngrok", "cygwin"} for component in components):
        return True
    if any(component.startswith("venv") for component in components):
        return True
    return False


def _is_forbidden_product_path(path: str) -> bool:
    normalized = _path_for_scope(path)
    lower = normalized.lower()
    if normalized in FORBIDDEN_EXACT_PATHS:
        return True
    if lower.startswith(("js/game/", "js/e9/")):
        return True
    if lower.startswith(("sgf/", "data/sgf/", "corpus/", "data/corpus/")):
        return True
    if lower.startswith(("db/", "database/", "schema/", "schemas/", "migrations/")):
        return True
    if lower.endswith((".db", ".sqlite", ".sqlite3")):
        return True
    if lower == "dockerfile" or lower.startswith("dockerfile."):
        return True
    if lower.startswith("docker-compose") and lower.endswith((".yml", ".yaml")):
        return True
    return False


def _is_allowed_workflow_path(path: str) -> bool:
    normalized = _path_for_scope(path)
    return normalized.startswith(ALLOWED_WORKFLOW_PREFIXES)


def _product_runtime_changed_files(paths: Sequence[str]) -> list[str]:
    non_runtime_prefixes = ("tests/", "docs/", "scripts/release/")
    return sorted(
        path
        for path in {_path_for_scope(item) for item in paths}
        if not path.startswith(non_runtime_prefixes)
    )


def _read_committed_file(repo: Path, commit: str, path: str) -> bytes:
    # secret_key.txt is intentionally never read, even if a caller supplies a
    # malicious packet that names it.
    if _path_for_scope(path) == "secret_key.txt":
        raise WorkflowError("secret_key.txt is protected and cannot be inspected")
    return _git_bytes(repo, "show", f"{commit}:{path}")


def _conflict_paths(repo: Path, commit: str, files: Sequence[Mapping[str, str]]) -> list[str]:
    conflicts: list[str] = []
    for item in files:
        path = _path_for_scope(item["path"])
        if path == "secret_key.txt":
            continue
        if item.get("status") == "D":
            continue
        content = _read_committed_file(repo, commit, path)
        if CONFLICT_MARKER_LINE.search(content):
            conflicts.append(path)
    return conflicts


def _identity_separation(
    *,
    scope_mode: str,
    product_source_sha: str,
    tooling_sha: str,
    implementation_sha: str,
    merge_sha: str | None = None,
) -> None:
    _require(product_source_sha != tooling_sha, "PRODUCT_SOURCE_SHA must not equal TOOLING_SHA")
    if scope_mode == CONTROL_PLANE_ONLY:
        _require(
            product_source_sha != implementation_sha,
            "PRODUCT_SOURCE_SHA must not equal IMPLEMENTATION_SHA in CONTROL_PLANE_ONLY",
        )
    else:
        _require(
            product_source_sha == implementation_sha,
            "PRODUCT_SOURCE_SHA must equal IMPLEMENTATION_SHA in PRODUCT_CHANGE",
        )
    if merge_sha is not None:
        _require(product_source_sha != merge_sha, "PRODUCT_SOURCE_SHA must not equal MERGE_SHA")


def _runtime_paths(value: Any, label: str) -> list[str]:
    _require(isinstance(value, list), f"{label} must be a list")
    paths: list[str] = []
    for index, item in enumerate(value):
        path = _path_for_scope(_text(item, f"{label}[{index}]"))
        _require(path not in paths, f"duplicate {label} path: {path}")
        paths.append(path)
    return sorted(paths)


def _validate_scope(
    scope_mode: str,
    changed_paths: Sequence[str],
    *,
    expected_paths: set[str] | None = None,
) -> list[str]:
    normalized_paths = sorted({_path_for_scope(path) for path in changed_paths})
    protected = sorted(path for path in normalized_paths if _is_protected_local_artifact_path(path))
    _require(
        not protected,
        "protected/local artifact paths changed: " + ", ".join(protected),
    )
    if scope_mode == CONTROL_PLANE_ONLY:
        forbidden = sorted(path for path in normalized_paths if _is_forbidden_product_path(path))
        runtime = sorted(path for path in normalized_paths if not _is_allowed_workflow_path(path))
        _require(not forbidden, "forbidden Product files changed: " + ", ".join(forbidden))
        _require(not runtime, "Product/runtime scope changed outside Lane W: " + ", ".join(runtime))
        if expected_paths is not None:
            _require(
                set(normalized_paths) == expected_paths,
                "changed files do not match expected_changed_files",
            )
        return []

    _require(expected_paths is not None, "expected_changed_files are required for PRODUCT_CHANGE")
    _require(
        set(normalized_paths) == expected_paths,
        "changed files do not match expected_changed_files",
    )
    mixed = sorted(path for path in normalized_paths if _is_allowed_workflow_path(path))
    _require(
        not mixed,
        "mixed Product and control-plane changes are not supported: " + ", ".join(mixed),
    )
    return _product_runtime_changed_files(normalized_paths)


def _test_spec(value: Any, index: int) -> tuple[str, str, list[str]]:
    item = _mapping(value, f"tests[{index}]")
    name = _text(item.get("name"), f"tests[{index}].name")
    path = _path_for_scope(_text(item.get("path"), f"tests[{index}].path"))
    command = item.get("command")
    _require(
        isinstance(command, list) and command and all(isinstance(part, str) and part for part in command),
        f"tests[{index}].command must be a non-empty argv list",
    )
    return name, path, list(command)


def _run_supplied_tests(repo: Path, supplied: Any) -> list[dict[str, Any]]:
    _require(isinstance(supplied, list) and supplied, "supplied tests are required")
    records: list[dict[str, Any]] = []
    for index, value in enumerate(supplied):
        name, path, command = _test_spec(value, index)
        _require(path != "secret_key.txt", "supplied tests cannot reference secret_key.txt")
        test_path = repo / Path(path)
        _require(test_path.is_file(), f"supplied test does not exist: {path}")
        result = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        record = {
            "name": name,
            "path": path,
            "command": command,
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode,
        }
        records.append(record)
        if result.returncode != 0:
            raise WorkflowError(
                f"supplied test failed: {name}",
                details={"tests": records},
            )
    return records


def _expected_paths(value: Any) -> set[str]:
    _require(isinstance(value, list) and value, "expected_changed_files are required")
    paths: set[str] = set()
    for index, item in enumerate(value):
        if isinstance(item, str):
            path = _path_for_scope(item)
        else:
            mapping = _mapping(item, f"expected_changed_files[{index}]")
            path = _path_for_scope(_text(mapping.get("path"), f"expected_changed_files[{index}].path"))
        _require(path not in paths, f"duplicate expected changed file: {path}")
        paths.add(path)
    return paths


def _validate_required_gates(value: Any) -> list[dict[str, Any]]:
    _require(isinstance(value, list) and value, "required_test_gates are required")
    records: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, item in enumerate(value):
        mapping = _mapping(item, f"required_test_gates[{index}]")
        name = _text(mapping.get("name"), f"required_test_gates[{index}].name")
        _require(name not in names, f"duplicate required test gate: {name}")
        _require(mapping.get("status") == "PASS", f"required test gate is not PASS: {name}")
        evidence = _text(mapping.get("evidence"), f"required_test_gates[{index}].evidence")
        names.add(name)
        records.append({"name": name, "status": "PASS", "evidence": evidence})
    return sorted(records, key=lambda item: item["name"])


def calculate_current_pair_id(app: Mapping[str, Any], static: Mapping[str, Any]) -> str:
    """Calculate the deterministic identity for one live app/static pair."""

    app_identity = {
        "image_id": _text(app.get("image_id"), "rollback app.image_id"),
        "image_tag": _text(app.get("image_tag"), "rollback app.image_tag"),
        "oci_revision": _sha40(app.get("oci_revision"), "rollback app.oci_revision"),
    }
    static_identity = {
        "manifest_sha256": _sha256(
            static.get("manifest_sha256"), "rollback static.manifest_sha256"
        ),
        "static_generation_id": _text(
            static.get("static_generation_id"), "rollback static.static_generation_id"
        ),
        "release_git_sha": _sha40(
            static.get("release_git_sha"), "rollback static.release_git_sha"
        ),
        "service_worker_identity": _text(
            static.get("service_worker_identity"),
            "rollback static.service_worker_identity",
        ),
    }
    material = {
        "contract": ROLLBACK_AUTHORITY,
        "app": app_identity,
        "static": static_identity,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "pair-" + hashlib.sha256(encoded).hexdigest()


def validate_rollback_authority(value: Any) -> dict[str, Any]:
    """Require the explicit pre-deploy live app/static pair as rollback authority."""

    raw = _mapping(value, "rollback_authority")
    authority = _text(raw.get("authority"), "rollback_authority.authority")
    _require(
        authority == ROLLBACK_AUTHORITY,
        "rollback authority must be EXPLICIT_PRE_DEPLOY_CURRENT_PAIR; a previous symlink is insufficient",
    )
    _require(raw.get("captured_before_deploy") is True, "rollback authority must be captured before deploy")
    _require(
        _text(raw.get("source_tool"), "rollback_authority.source_tool")
        == "preflight-production.ps1",
        "rollback authority source_tool must be preflight-production.ps1",
    )
    app = _mapping(raw.get("app"), "rollback_authority.app")
    static = _mapping(raw.get("static"), "rollback_authority.static")
    pair_id = _text(raw.get("pair_id"), "rollback_authority.pair_id")
    expected_pair_id = calculate_current_pair_id(app, static)
    _require(pair_id == expected_pair_id, "rollback authority pair_id does not bind the explicit current pair")
    normalized = {
        "authority": ROLLBACK_AUTHORITY,
        "captured_before_deploy": True,
        "source_tool": "preflight-production.ps1",
        "capture_id": _text(raw.get("capture_id"), "rollback_authority.capture_id"),
        "pair_id": pair_id,
        "app": {
            "image_id": _text(app.get("image_id"), "rollback app.image_id"),
            "image_tag": _text(app.get("image_tag"), "rollback app.image_tag"),
            "oci_revision": _sha40(app.get("oci_revision"), "rollback app.oci_revision"),
        },
        "static": {
            "manifest_sha256": _sha256(
                static.get("manifest_sha256"), "rollback static.manifest_sha256"
            ),
            "static_generation_id": _text(
                static.get("static_generation_id"), "rollback static.static_generation_id"
            ),
            "release_git_sha": _sha40(
                static.get("release_git_sha"), "rollback static.release_git_sha"
            ),
            "service_worker_identity": _text(
                static.get("service_worker_identity"),
                "rollback static.service_worker_identity",
            ),
        },
    }
    _require(
        normalized["app"]["oci_revision"] == normalized["static"]["release_git_sha"],
        "rollback current app/static pair has mismatched source identities",
    )
    return normalized


def _base_packet(stage: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "OWNER_GATE_INFERENCE": "FORBIDDEN",
        "MERGE_EXECUTED": "NO",
        "DEPLOY_EXECUTED": "NO",
        "ROLLBACK_EXECUTED": "NO",
        "PRODUCTION_CONTACTED": "NO",
    }


def build_pr_ready_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    repo = _repo_path(payload)
    scope_mode = _scope_mode(payload.get("scope_mode"))
    base = _commit(repo, payload.get("base_sha"), "BASE_SHA")
    candidate = _commit(repo, payload.get("candidate_sha"), "CANDIDATE_SHA")
    implementation = _commit(repo, payload.get("implementation_sha"), "IMPLEMENTATION_SHA")
    product = _commit(repo, payload.get("product_source_sha"), "PRODUCT_SOURCE_SHA")
    tooling = _commit(repo, payload.get("tooling_sha"), "TOOLING_SHA")
    _require(_git(repo, "rev-parse", "HEAD") == candidate, "candidate SHA must equal worktree HEAD")
    _require(_is_ancestor(repo, base, candidate), "candidate is not a descendant of BASE_SHA")
    _require(_is_ancestor(repo, product, candidate), "PRODUCT_SOURCE_SHA is not in candidate lineage")
    _require(_is_ancestor(repo, tooling, candidate), "TOOLING_SHA is not in candidate lineage")
    _require(implementation == candidate, "IMPLEMENTATION_SHA must equal CANDIDATE_SHA")
    _identity_separation(
        scope_mode=scope_mode,
        product_source_sha=product,
        tooling_sha=tooling,
        implementation_sha=implementation,
    )

    status = _working_tree_status(repo)
    _require(not status, "worktree must be clean")
    changed = _changed_files(repo, base, candidate)
    _require(changed, "changed files could not be proven for the candidate")
    changed_paths = {_path_for_scope(item["path"]) for item in changed}
    expected_paths = None
    if scope_mode == PRODUCT_CHANGE or payload.get("expected_changed_files") is not None:
        expected_paths = _expected_paths(payload.get("expected_changed_files"))
    runtime = _validate_scope(scope_mode, changed_paths, expected_paths=expected_paths)
    conflicts = _conflict_paths(repo, candidate, changed)
    _require(not conflicts, "unresolved conflict markers found: " + ", ".join(conflicts))
    tests = _run_supplied_tests(repo, payload.get("tests"))

    packet = _base_packet("PR_READY")
    packet.update(
        {
            "PR_READY": "YES",
            "SCOPE_MODE": scope_mode,
            "BASE_SHA": base,
            "CANDIDATE_SHA": candidate,
            "IMPLEMENTATION_SHA": implementation,
            "PRODUCT_SOURCE_SHA": product,
            "TOOLING_SHA": tooling,
            "MERGE_SHA": NOT_YET_MERGED,
            "WORKTREE": str(repo),
            "BRANCH": _git(repo, "branch", "--show-current"),
            "WORKTREE_CLEAN": True,
            "CHANGED_FILES": changed,
            "TESTS": tests,
            "PRODUCT_RUNTIME_CHANGED": "YES" if runtime else "NO",
            "PRODUCT_RUNTIME_CHANGED_FILES": runtime,
            "R2A_HISTORY_PRESENT": R2A_HISTORY_PRESENT,
            "R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE": R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE,
            "BLOCKERS": [],
        }
    )
    return packet


def _validate_provenance(
    repo: Path,
    value: Any,
    *,
    base: str,
    implementation: str,
    product: str,
    tooling: str,
    merge: str,
    scope_mode: str,
    runtime_files: Sequence[str],
) -> dict[str, Any]:
    raw = _mapping(value, "provenance")
    _require(
        _scope_mode(raw.get("scope_mode")) == scope_mode,
        "provenance.scope_mode does not match the explicit workflow scope",
    )
    expected = {
        "base_sha": base,
        "implementation_sha": implementation,
        "product_source_sha": product,
        "tooling_sha": tooling,
        "merge_sha": merge,
        "runtime_source_sha": product,
    }
    for field, expected_value in expected.items():
        _require(
            _sha40(raw.get(field), f"provenance.{field}") == expected_value,
            f"provenance.{field} does not match the explicit workflow identity",
        )
    canonical_ref = _text(raw.get("canonical_ref"), "provenance.canonical_ref")
    canonical_ref_sha = _commit(repo, raw.get("canonical_ref_sha"), "provenance.canonical_ref_sha")
    try:
        resolved_canonical_ref = _git(
            repo,
            "rev-parse",
            "--verify",
            canonical_ref + "^{commit}",
        )
    except WorkflowError as exc:
        raise WorkflowError("provenance.canonical_ref is not present in this repository") from exc
    _require(
        resolved_canonical_ref == canonical_ref_sha,
        "provenance.canonical_ref does not resolve to canonical_ref_sha",
    )
    _require(
        _is_ancestor(repo, merge, canonical_ref_sha),
        "MERGE_SHA is not in the canonical provenance lineage",
    )
    gates = _mapping(raw.get("gates"), "provenance.gates")
    _require(
        REQUIRED_POST_MERGE_GATES <= set(gates),
        "canonical provenance gates are incomplete",
    )
    for name in REQUIRED_POST_MERGE_GATES:
        record = _mapping(gates.get(name), f"provenance.gates.{name}")
        _require(record.get("status") == "PASS", f"canonical provenance gate is not PASS: {name}")
    expected_runtime_files = sorted({_path_for_scope(path) for path in runtime_files})
    actual_runtime_files = _runtime_paths(
        raw.get("product_runtime_changed_files"),
        "provenance.product_runtime_changed_files",
    )
    _require(
        actual_runtime_files == expected_runtime_files,
        "provenance.product_runtime_changed_files does not match the validated Product scope",
    )
    if scope_mode == CONTROL_PLANE_ONLY:
        _require(not actual_runtime_files, "CONTROL_PLANE_ONLY cannot carry Product runtime changes")
    _require(canonical_ref, "canonical_ref is required")
    return {
        "scope_mode": scope_mode,
        "base_sha": base,
        "implementation_sha": implementation,
        "product_source_sha": product,
        "tooling_sha": tooling,
        "merge_sha": merge,
        "runtime_source_sha": product,
        "canonical_ref": canonical_ref,
        "canonical_ref_sha": canonical_ref_sha,
        "gates": {name: {"status": "PASS"} for name in sorted(REQUIRED_POST_MERGE_GATES)},
        "product_runtime_changed_files": actual_runtime_files,
    }


def build_post_merge_packet(payload: Mapping[str, Any]) -> dict[str, Any]:
    repo = _repo_path(payload)
    scope_mode = _scope_mode(payload.get("scope_mode"))
    base = _commit(repo, payload.get("base_sha"), "BASE_SHA")
    implementation = _commit(
        repo, payload.get("expected_implementation_sha"), "EXPECTED_IMPLEMENTATION_SHA"
    )
    product = _commit(repo, payload.get("expected_product_source_sha"), "EXPECTED_PRODUCT_SOURCE_SHA")
    tooling = _commit(repo, payload.get("tooling_sha"), "TOOLING_SHA")
    merge = _commit(repo, payload.get("actual_merge_sha"), "ACTUAL_MERGE_SHA")
    _require(_git(repo, "rev-parse", "HEAD") == merge, "ACTUAL_MERGE_SHA must equal canonical worktree HEAD")
    _require(_is_ancestor(repo, base, implementation), "implementation is not a descendant of BASE_SHA")
    _require(_is_ancestor(repo, implementation, merge), "expected implementation is not in merge lineage")
    _require(_is_ancestor(repo, product, merge), "PRODUCT_SOURCE_SHA is not in merge lineage")
    _require(_is_ancestor(repo, tooling, merge), "TOOLING_SHA is not in merge lineage")
    _identity_separation(
        scope_mode=scope_mode,
        product_source_sha=product,
        tooling_sha=tooling,
        implementation_sha=implementation,
        merge_sha=merge,
    )
    parents = _parents(repo, merge)
    _require(parents, "actual merge SHA has no valid parent lineage")
    expected_paths = _expected_paths(payload.get("expected_changed_files"))
    changed = _changed_files(repo, base, merge)
    actual_paths = {_path_for_scope(item["path"]) for item in changed}
    _require(
        actual_paths == expected_paths,
        "post-merge changed files contain unrelated or missing paths",
    )
    runtime = _validate_scope(scope_mode, actual_paths, expected_paths=expected_paths)
    conflicts = _conflict_paths(repo, merge, changed)
    _require(not conflicts, "unresolved conflict markers found after merge: " + ", ".join(conflicts))
    _require(not _working_tree_status(repo), "post-merge repository status must be clean")
    provenance = _validate_provenance(
        repo,
        payload.get("provenance"),
        base=base,
        implementation=implementation,
        product=product,
        tooling=tooling,
        merge=merge,
        scope_mode=scope_mode,
        runtime_files=runtime,
    )

    packet = _base_packet("POST_MERGE")
    packet.update(
        {
            "POST_MERGE": "YES",
            "SCOPE_MODE": scope_mode,
            "BASE_SHA": base,
            "CANDIDATE_SHA": implementation,
            "IMPLEMENTATION_SHA": implementation,
            "PRODUCT_SOURCE_SHA": product,
            "TOOLING_SHA": tooling,
            "MERGE_SHA": merge,
            "WORKTREE": str(repo),
            "BRANCH": _git(repo, "branch", "--show-current"),
            "WORKTREE_CLEAN": True,
            "MERGE_PARENTS": parents,
            "CHANGED_FILES": changed,
            "PRODUCT_RUNTIME_CHANGED": "YES" if runtime else "NO",
            "PRODUCT_RUNTIME_CHANGED_FILES": runtime,
            "R2A_HISTORY_PRESENT": R2A_HISTORY_PRESENT,
            "R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE": R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE,
            "PROVENANCE": provenance,
            "BLOCKERS": [],
            "OWNER_MERGE_OBSERVED": "YES",
        }
    )
    return packet


def _post_merge_reference(value: Any) -> dict[str, Any]:
    packet = dict(_mapping(value, "post_merge"))
    _require(packet.get("stage") == "POST_MERGE", "post_merge must be a POST_MERGE packet")
    _require(packet.get("POST_MERGE") == "YES", "post_merge packet is not valid")
    _require(packet.get("BLOCKERS") == [], "post_merge packet contains blockers")
    scope_mode = _scope_mode(packet.get("SCOPE_MODE"))
    for field in ("BASE_SHA", "IMPLEMENTATION_SHA", "PRODUCT_SOURCE_SHA", "TOOLING_SHA", "MERGE_SHA"):
        _sha40(packet.get(field), f"post_merge.{field}")
    _identity_separation(
        scope_mode=scope_mode,
        product_source_sha=packet["PRODUCT_SOURCE_SHA"],
        tooling_sha=packet["TOOLING_SHA"],
        implementation_sha=packet["IMPLEMENTATION_SHA"],
        merge_sha=packet["MERGE_SHA"],
    )
    runtime = _runtime_paths(packet.get("PRODUCT_RUNTIME_CHANGED_FILES"), "post_merge.PRODUCT_RUNTIME_CHANGED_FILES")
    if scope_mode == CONTROL_PLANE_ONLY:
        _require(not runtime, "CONTROL_PLANE_ONLY post_merge runtime changes are not closed")
    _require(
        packet.get("PRODUCT_RUNTIME_CHANGED") == ("YES" if runtime else "NO"),
        "post_merge Product runtime status does not match its files",
    )
    packet["SCOPE_MODE"] = scope_mode
    packet["PRODUCT_RUNTIME_CHANGED_FILES"] = runtime
    return packet


def build_release_prep_handoff(payload: Mapping[str, Any]) -> dict[str, Any]:
    post = _post_merge_reference(payload.get("post_merge"))
    repo = Path(_text(post.get("WORKTREE"), "post_merge.WORKTREE")).resolve()
    _require(repo.is_dir(), "post_merge worktree does not exist")
    tools = {
        name: path
        for name, path in CANONICAL_RELEASE_TOOLS.items()
        if (repo / Path(path)).is_file()
    }
    _require(set(tools) == set(CANONICAL_RELEASE_TOOLS), "canonical release tooling is incomplete")
    gates = _validate_required_gates(payload.get("required_test_gates"))
    static_required = payload.get("static_build_required")
    oci_required = payload.get("oci_build_required")
    rollback_required = payload.get("rollback_preflight_required")
    _require(isinstance(static_required, bool), "STATIC_BUILD_REQUIRED must be explicit boolean")
    _require(isinstance(oci_required, bool), "OCI_BUILD_REQUIRED must be explicit boolean")
    _require(isinstance(rollback_required, bool), "ROLLBACK_PREFLIGHT_REQUIRED must be explicit boolean")
    owner_gate = _mapping(payload.get("owner_gate"), "owner_gate")
    _require(owner_gate.get("explicit") is True, "Owner gate must be explicitly supplied")
    next_gate = _text(owner_gate.get("name"), "owner_gate.name")
    _require(next_gate in OWNER_GATES, "owner_gate.name is not a recognized Owner gate")
    _text(owner_gate.get("evidence"), "owner_gate.evidence")
    rollback = validate_rollback_authority(payload.get("rollback_authority"))

    packet = _base_packet("RELEASE_PREP_HANDOFF")
    packet.update(
        {
            "RELEASE_PREP_HANDOFF": "YES",
            "SCOPE_MODE": post["SCOPE_MODE"],
            "BASE_SHA": post["BASE_SHA"],
            "CANDIDATE_SHA": post["CANDIDATE_SHA"],
            "IMPLEMENTATION_SHA": post["IMPLEMENTATION_SHA"],
            "PRODUCT_SOURCE_SHA": post["PRODUCT_SOURCE_SHA"],
            "TOOLING_SHA": post["TOOLING_SHA"],
            "MERGE_SHA": post["MERGE_SHA"],
            "WORKTREE": str(repo),
            "PRODUCT_RUNTIME_CHANGED": post["PRODUCT_RUNTIME_CHANGED"],
            "PRODUCT_RUNTIME_CHANGED_FILES": list(post["PRODUCT_RUNTIME_CHANGED_FILES"]),
            "R2A_HISTORY_PRESENT": R2A_HISTORY_PRESENT,
            "R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE": R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE,
            "REQUIRED_TEST_GATES": gates,
            "STATIC_BUILD_REQUIRED": static_required,
            "OCI_BUILD_REQUIRED": oci_required,
            "ROLLBACK_PREFLIGHT_REQUIRED": rollback_required,
            "NEXT_OWNER_GATE": next_gate,
            "OWNER_GATE_EXPLICIT": "YES",
            "ROLLBACK_CURRENT_PAIR_AUTHORITY": ROLLBACK_AUTHORITY,
            "ROLLBACK_AUTHORITY": rollback,
            "CANONICAL_RELEASE_TOOLS": tools,
            "BLOCKERS": [],
        }
    )
    return packet


def _failure_packet(stage: str, payload: Mapping[str, Any], error: WorkflowError) -> dict[str, Any]:
    packet = _base_packet(stage)
    yes_field = {
        "PR_READY": "PR_READY",
        "POST_MERGE": "POST_MERGE",
        "RELEASE_PREP_HANDOFF": "RELEASE_PREP_HANDOFF",
    }[stage]
    packet[yes_field] = "NO"
    input_fields = {
        "BASE_SHA": ("base_sha",),
        "PRODUCT_SOURCE_SHA": ("product_source_sha", "expected_product_source_sha"),
        "TOOLING_SHA": ("tooling_sha",),
        "MERGE_SHA": ("actual_merge_sha",),
    }
    for field, candidates in input_fields.items():
        value = next((payload.get(name) for name in candidates if payload.get(name) is not None), None)
        packet[field] = value if isinstance(value, str) else None
    implementation = payload.get("implementation_sha", payload.get("expected_implementation_sha"))
    candidate = payload.get("candidate_sha", implementation)
    packet["CANDIDATE_SHA"] = candidate if isinstance(candidate, str) else None
    packet["IMPLEMENTATION_SHA"] = implementation if isinstance(implementation, str) else None
    scope_mode = payload.get("scope_mode")
    if isinstance(scope_mode, str) and scope_mode in SCOPE_MODES:
        packet["SCOPE_MODE"] = scope_mode
    packet["PRODUCT_RUNTIME_CHANGED"] = "UNKNOWN"
    packet["PRODUCT_RUNTIME_CHANGED_FILES"] = []
    packet["R2A_HISTORY_PRESENT"] = R2A_HISTORY_PRESENT
    packet["R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE"] = R2A_HISTORY_ANCESTRY_CAUSES_WORKFLOW_FAILURE
    packet["BLOCKERS"] = [str(error)]
    packet.update(error.details)
    return packet


def render_human(packet: Mapping[str, Any]) -> str:
    stage = str(packet.get("stage", "UNKNOWN"))
    lines = [
        "E10 Development Workflow V2 Foundation",
        f"STAGE={stage}",
    ]
    for field in (
        "PR_READY",
        "POST_MERGE",
        "RELEASE_PREP_HANDOFF",
        "SCOPE_MODE",
        "BASE_SHA",
        "CANDIDATE_SHA",
        "IMPLEMENTATION_SHA",
        "PRODUCT_SOURCE_SHA",
        "TOOLING_SHA",
        "MERGE_SHA",
        "PRODUCT_RUNTIME_CHANGED",
        "PRODUCT_RUNTIME_CHANGED_FILES",
        "STATIC_BUILD_REQUIRED",
        "OCI_BUILD_REQUIRED",
        "ROLLBACK_PREFLIGHT_REQUIRED",
        "NEXT_OWNER_GATE",
        "ROLLBACK_CURRENT_PAIR_AUTHORITY",
        "OWNER_GATE_INFERENCE",
    ):
        if field in packet:
            lines.append(f"{field}={packet[field]}")
    blockers = packet.get("BLOCKERS") or []
    lines.append("BLOCKERS=" + ("NONE" if not blockers else " | ".join(str(item) for item in blockers)))
    return "\n".join(lines) + "\n"


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"could not read JSON input {path}: {exc}") from exc
    return _mapping(value, str(path))


def _write_json(path: Path | None, packet: Mapping[str, Any]) -> None:
    rendered = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(rendered, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


def _write_human(path: Path | None, packet: Mapping[str, Any]) -> None:
    rendered = render_human(packet)
    if path is None:
        print(rendered, end="", file=sys.stderr)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="stage", required=True)
    for name in ("pr-ready", "post-merge", "release-prep"):
        command = subparsers.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--output", type=Path)
        command.add_argument("--human-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    stage_map = {
        "pr-ready": ("PR_READY", build_pr_ready_packet),
        "post-merge": ("POST_MERGE", build_post_merge_packet),
        "release-prep": ("RELEASE_PREP_HANDOFF", build_release_prep_handoff),
    }
    stage, builder = stage_map[args.stage]
    try:
        payload = _load_json(args.input)
        packet = builder(payload)
        exit_code = 0
    except WorkflowError as exc:
        payload = locals().get("payload", {})
        packet = _failure_packet(stage, payload, exc)
        exit_code = 2
    _write_json(args.output, packet)
    if args.output is not None:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    _write_human(args.human_output, packet)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
