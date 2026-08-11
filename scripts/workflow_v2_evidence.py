#!/usr/bin/env python3
"""Create and validate Workflow V2 candidate/release evidence.

This is a read-only Git metadata helper. It never merges, deploys, rolls
back, or contacts Production.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "workflow-v2-evidence-v1"
RISK_CLASSES = ("NORMAL", "HOTFIX", "HEAVY")
RELEASE_TYPES = ("APP_ONLY", "STATIC_ONLY", "PAIRED_APP_STATIC")
NORMAL_BASIS = {
    "ordinary_application_behavior",
    "ui",
    "bounded_server_logic",
    "documentation",
    "contracted_static",
    "test_only",
}
HEAVY_BASIS = {
    "deployment_tooling",
    "database_schema_authority",
    "sgf_judging_parser_core",
    "authentication_security",
    "rollout_architecture",
    "infrastructure",
    "broad_cross_system",
    "release_governance",
}
ALL_BASIS = NORMAL_BASIS | HEAVY_BASIS | {"urgent_known_regression"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


class EvidenceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


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
        raise EvidenceError("git failed: " + (result.stderr or result.stdout).strip())
    return result.stdout.strip()


def _sha(value: Any, label: str, length: int = 40) -> None:
    pattern = SHA40 if length == 40 else SHA64
    _require(isinstance(value, str) and pattern.fullmatch(value), f"{label} must be a lowercase SHA-{length}")


def _commit(repo: Path, ref: str) -> str:
    value = _git(repo, "rev-parse", "--verify", ref + "^{commit}")
    _sha(value, "commit")
    return value


def _tree(repo: Path, commit: str) -> str:
    value = _git(repo, "rev-parse", "--verify", commit + "^{tree}")
    _sha(value, "tree")
    return value


def _parents(repo: Path, commit: str) -> list[str]:
    parts = _git(repo, "rev-list", "--parents", "-n", "1", commit).split()
    _require(parts and parts[0] == commit, "could not read commit parents")
    for parent in parts[1:]:
        _sha(parent, "parent")
    return parts[1:]


def _ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        check=False,
    ).returncode == 0


def _blob(repo: Path, commit: str, path: str) -> str:
    value = _git(repo, "rev-parse", "--verify", commit + ":" + path)
    _sha(value, "blob")
    return value


def _changed_files(repo: Path, base: str, head: str) -> list[dict[str, Any]]:
    raw = _git(
        repo,
        "diff",
        "--name-status",
        "--find-renames",
        "-z",
        base + "..." + head,
    )
    tokens = [token for token in raw.split("\0") if token]
    files: list[dict[str, Any]] = []
    index = 0
    while index < len(tokens):
        status_token = tokens[index]
        index += 1
        status = status_token[0]
        previous = None
        if status in {"R", "C"}:
            _require(index + 1 < len(tokens), "malformed rename diff")
            previous, path = tokens[index:index + 2]
            index += 2
        else:
            _require(index < len(tokens), "malformed Git diff")
            path = tokens[index]
            index += 1
        item = {
            "path": path,
            "status": status,
            "blob_sha": None if status == "D" else _blob(repo, head, path),
        }
        if previous is not None:
            item["previous_path"] = previous
        files.append(item)
    return files


def required_check_categories(
    risk_class: str,
    *,
    python_relevant: bool,
    javascript_relevant: bool,
    browser_relevant: bool,
) -> set[str]:
    required = {"focused_tests", "affected_regression", "diff_check", "scope_check"}
    if python_relevant:
        required.update({"python_syntax", "compileall"})
    if javascript_relevant:
        required.add("javascript_syntax")
    if browser_relevant:
        required.add("browser_contract")
    if risk_class == "HEAVY":
        required.add("broader_validation")
    return required


def _classification(risk_class: str, basis: list[str]) -> None:
    _require(risk_class in RISK_CLASSES, "invalid risk_class")
    _require(basis and all(item in ALL_BASIS for item in basis), "invalid classification_basis")
    values = set(basis)
    if risk_class == "NORMAL":
        _require(not values & HEAVY_BASIS and values <= NORMAL_BASIS, "NORMAL cannot claim a Heavy authority")
    elif risk_class == "HOTFIX":
        _require("urgent_known_regression" in values, "HOTFIX requires urgent_known_regression")
        _require(not values & HEAVY_BASIS, "HOTFIX cannot claim a Heavy authority")
    else:
        _require(bool(values & HEAVY_BASIS), "HEAVY requires a Heavy authority basis")


def _checks(validation: Any, required: set[str]) -> None:
    checks = validation.get("checks") if isinstance(validation, dict) else None
    _require(isinstance(checks, list) and checks, "validation.checks must be non-empty")
    by_category = {}
    for check in checks:
        _require(isinstance(check, dict) and check.get("category"), "invalid validation check")
        category = check["category"]
        _require(category not in by_category, "duplicate validation category: " + category)
        _require(check.get("status") in {"PASS", "FAIL", "NOT_APPLICABLE"}, "invalid validation status")
        by_category[category] = check
    missing = required - set(by_category)
    _require(not missing, "missing required validation: " + ", ".join(sorted(missing)))
    failed = [name for name in required if by_category[name]["status"] != "PASS"]
    _require(not failed, "required validation is not PASS: " + ", ".join(sorted(failed)))
    _require(validation.get("result") == "PASS", "validation.result must be PASS")


def validate_candidate_evidence(payload: dict[str, Any], repo: Path | None = None) -> None:
    _require(isinstance(payload, dict), "candidate evidence must be an object")
    required = {
        "schema_version", "artifact_kind", "repository", "generated_at",
        "base_ref", "base_sha", "pr_head", "risk_class",
        "classification_basis", "scope", "relevance", "validation",
    }
    _require(required <= payload.keys(), "candidate evidence is missing required fields")
    _require(payload["schema_version"] == SCHEMA_VERSION, "unsupported evidence schema")
    _require(payload["artifact_kind"] == "PR_EVIDENCE", "artifact_kind must be PR_EVIDENCE")
    _sha(payload["base_sha"], "base_sha")
    head = payload["pr_head"]
    _require(isinstance(head, dict), "pr_head must be an object")
    _require(all(isinstance(head.get(key), str) for key in ("ref", "sha", "tree_sha")), "invalid pr_head")
    _sha(head["sha"], "pr_head.sha")
    _sha(head["tree_sha"], "pr_head.tree_sha")
    basis = payload["classification_basis"]
    _require(isinstance(basis, list) and all(isinstance(item, str) for item in basis), "invalid classification_basis")
    _classification(payload["risk_class"], basis)
    relevance = payload["relevance"]
    _require(isinstance(relevance, dict), "relevance must be an object")
    _require(all(isinstance(relevance.get(key), bool) for key in (
        "python_relevant", "javascript_relevant", "browser_relevant"
    )), "invalid relevance flags")
    scope = payload["scope"]
    _require(isinstance(scope, dict) and scope.get("statement"), "scope.statement is required")
    files = scope.get("changed_files")
    _require(isinstance(files, list) and files, "scope.changed_files must be non-empty")
    for item in files:
        _require(isinstance(item, dict) and item.get("path"), "invalid changed file")
        _require(item.get("status") in {"A", "C", "D", "M", "R", "T", "U"}, "invalid changed-file status")
        if item.get("blob_sha") is not None:
            _sha(item["blob_sha"], "changed-file blob")
    _checks(payload["validation"], required_check_categories(
        payload["risk_class"],
        python_relevant=relevance["python_relevant"],
        javascript_relevant=relevance["javascript_relevant"],
        browser_relevant=relevance["browser_relevant"],
    ))
    _require(payload.get("planned_release_type") in RELEASE_TYPES or payload.get("planned_release_type") is None, "invalid planned_release_type")
    if payload.get("pr_number") is not None:
        _require(isinstance(payload["pr_number"], int) and payload["pr_number"] > 0, "invalid pr_number")
    if repo is not None:
        _require(_commit(repo, payload["base_sha"]) == payload["base_sha"], "base SHA is not present in Git")
        _require(_commit(repo, head["sha"]) == head["sha"], "PR head SHA is not present in Git")
        _require(_tree(repo, head["sha"]) == head["tree_sha"], "PR tree SHA does not match Git")
        _require(_changed_files(repo, payload["base_sha"], head["sha"]) == files, "changed files do not match Git")


def _app(artifact: Any, source: str) -> None:
    _require(isinstance(artifact, dict), "app artifact is required")
    _require(all(isinstance(artifact.get(key), str) and artifact[key] for key in (
        "image_tag", "image_id", "archive_sha256", "oci_revision"
    )), "incomplete app artifact")
    _sha(artifact["archive_sha256"], "app archive", 64)
    _sha(artifact["oci_revision"], "app OCI revision")
    _require(artifact["oci_revision"] == source, "app OCI revision must equal merged source")


def _static(artifact: Any, source: str) -> None:
    _require(isinstance(artifact, dict), "static artifact is required")
    _require(all(isinstance(artifact.get(key), str) and artifact[key] for key in (
        "static_generation_id", "archive_sha256", "release_git_sha", "service_worker_identity"
    )), "incomplete static artifact")
    _sha(artifact["archive_sha256"], "static archive", 64)
    _sha(artifact["release_git_sha"], "static release SHA")
    _require(artifact["release_git_sha"] == source, "static release SHA must equal merged source")


def validate_release_provenance(payload: dict[str, Any], repo: Path | None = None) -> None:
    _require(isinstance(payload, dict), "release provenance must be an object")
    required = {
        "schema_version", "artifact_kind", "repository", "generated_at",
        "release_id", "release_type", "risk_class", "classification_basis",
        "merged_source_sha", "merged_tree_sha", "merge_parents",
        "canonical_ref", "canonical_ancestor", "artifacts",
    }
    _require(required <= payload.keys(), "release provenance is missing required fields")
    _require(payload["schema_version"] == SCHEMA_VERSION, "unsupported release schema")
    _require(payload["artifact_kind"] == "RELEASE_PROVENANCE", "artifact_kind must be RELEASE_PROVENANCE")
    _require(isinstance(payload["release_id"], str) and RELEASE_ID.fullmatch(payload["release_id"]), "invalid release_id")
    _require(payload["release_type"] in RELEASE_TYPES, "invalid release_type")
    basis = payload["classification_basis"]
    _require(isinstance(basis, list) and all(isinstance(item, str) for item in basis), "invalid classification_basis")
    _classification(payload["risk_class"], basis)
    _sha(payload["merged_source_sha"], "merged_source_sha")
    _sha(payload["merged_tree_sha"], "merged_tree_sha")
    _require(isinstance(payload["merge_parents"], list) and payload["merge_parents"], "merge_parents must be non-empty")
    for parent in payload["merge_parents"]:
        _sha(parent, "merge parent")
    _require(payload["canonical_ancestor"] is True, "canonical_ancestor must be true")
    artifacts = payload["artifacts"]
    _require(isinstance(artifacts, dict), "artifacts must be an object")
    app = artifacts.get("app")
    static = artifacts.get("static")
    if payload["release_type"] in {"APP_ONLY", "PAIRED_APP_STATIC"}:
        _app(app, payload["merged_source_sha"])
    else:
        _require(app is None, "STATIC_ONLY cannot include an app artifact")
    if payload["release_type"] in {"STATIC_ONLY", "PAIRED_APP_STATIC"}:
        _static(static, payload["merged_source_sha"])
    else:
        _require(static is None, "APP_ONLY cannot include a static artifact")
    external = artifacts.get("external_content")
    _require(isinstance(external, list), "external_content must be a list")
    for item in external:
        _require(isinstance(item, dict) and item.get("name") and item.get("identity"), "invalid external identity")
    if payload.get("pr_evidence") is not None:
        link = payload["pr_evidence"]
        _require(isinstance(link, dict), "pr_evidence must be an object")
        _sha(link.get("pr_head_sha"), "PR head SHA")
        if link.get("artifact_sha256") is not None:
            _sha(link["artifact_sha256"], "PR artifact SHA", 64)
    if repo is not None:
        source = payload["merged_source_sha"]
        _require(_tree(repo, source) == payload["merged_tree_sha"], "merged tree does not match Git")
        _require(_parents(repo, source) == payload["merge_parents"], "merge parents do not match Git")
        _require(_ancestor(repo, source, _commit(repo, payload["canonical_ref"])), "merged source is not reachable from canonical ref")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _checks_input(value: Any) -> dict[str, Any]:
    checks = value.get("checks") if isinstance(value, dict) else value
    _require(isinstance(checks, list), "checks input must be a list or object with checks")
    return {"result": "PASS", "checks": checks}


def collect_candidate_evidence(
    repo: Path,
    *,
    base_ref: str,
    head_ref: str,
    repository: str,
    risk_class: str,
    classification_basis: list[str],
    scope_statement: str,
    checks: Any,
    python_relevant: bool = False,
    javascript_relevant: bool = False,
    browser_relevant: bool = False,
    planned_release_type: str | None = None,
    pr_number: int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    base = _commit(repo, base_ref)
    head = _commit(repo, head_ref)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "PR_EVIDENCE",
        "repository": repository,
        "generated_at": generated_at or _now(),
        "base_ref": base_ref,
        "base_sha": base,
        "pr_head": {
            "ref": head_ref,
            "sha": head,
            "tree_sha": _tree(repo, head),
            "parents": _parents(repo, head),
        },
        "risk_class": risk_class,
        "classification_basis": classification_basis,
        "scope": {
            "statement": scope_statement,
            "changed_files": _changed_files(repo, base, head),
        },
        "relevance": {
            "python_relevant": python_relevant,
            "javascript_relevant": javascript_relevant,
            "browser_relevant": browser_relevant,
        },
        "validation": _checks_input(checks),
    }
    if planned_release_type is not None:
        payload["planned_release_type"] = planned_release_type
    if pr_number is not None:
        payload["pr_number"] = pr_number
    validate_candidate_evidence(payload, repo)
    return payload


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError("could not read JSON " + str(path)) from exc


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_release_provenance(
    repo: Path,
    *,
    merged_ref: str,
    canonical_ref: str,
    repository: str,
    release_id: str,
    release_type: str,
    risk_class: str,
    classification_basis: list[str],
    app_artifact: dict[str, Any] | None,
    static_artifact: dict[str, Any] | None,
    external_content: list[dict[str, Any]] | None = None,
    candidate_evidence_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    source = _commit(repo, merged_ref)
    canonical = _commit(repo, canonical_ref)
    _require(_ancestor(repo, source, canonical), "merged source is not reachable from canonical_ref")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "RELEASE_PROVENANCE",
        "repository": repository,
        "generated_at": generated_at or _now(),
        "release_id": release_id,
        "release_type": release_type,
        "risk_class": risk_class,
        "classification_basis": classification_basis,
        "merged_source_sha": source,
        "merged_tree_sha": _tree(repo, source),
        "merge_parents": _parents(repo, source),
        "canonical_ref": canonical_ref,
        "canonical_ancestor": True,
        "artifacts": {
            "app": app_artifact,
            "static": static_artifact,
            "external_content": external_content or [],
        },
    }
    if candidate_evidence_path is not None:
        candidate = _load(candidate_evidence_path)
        validate_candidate_evidence(candidate, repo)
        _require(candidate["risk_class"] == risk_class, "release risk_class must match PR evidence")
        _require(candidate["classification_basis"] == classification_basis, "release classification_basis must match PR evidence")
        planned = candidate.get("planned_release_type")
        _require(planned is None or planned == release_type, "release type does not match PR evidence")
        payload["pr_evidence"] = {
            "pr_head_sha": candidate["pr_head"]["sha"],
            "artifact_sha256": _file_sha(candidate_evidence_path),
        }
        if candidate.get("pr_number") is not None:
            payload["pr_evidence"]["pr_number"] = candidate["pr_number"]
    validate_release_provenance(payload, repo)
    return payload


def _write(path: Path, payload: dict[str, Any], force: bool) -> None:
    _require(force or not path.exists(), "output exists; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    candidate = subs.add_parser("candidate")
    candidate.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    candidate.add_argument("--base-ref", default="origin/master")
    candidate.add_argument("--head-ref", default="HEAD")
    candidate.add_argument("--repository", default="go-odyssey")
    candidate.add_argument("--pr-number", type=int)
    candidate.add_argument("--risk-class", choices=RISK_CLASSES, required=True)
    candidate.add_argument("--basis", dest="classification_basis", action="append", required=True)
    candidate.add_argument("--scope-statement", required=True)
    candidate.add_argument("--python-relevant", action="store_true")
    candidate.add_argument("--javascript-relevant", action="store_true")
    candidate.add_argument("--browser-relevant", action="store_true")
    candidate.add_argument("--planned-release-type", choices=RELEASE_TYPES)
    candidate.add_argument("--checks-json", type=Path, required=True)
    candidate.add_argument("--output", type=Path, required=True)
    candidate.add_argument("--force", action="store_true")

    release = subs.add_parser("release")
    release.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    release.add_argument("--merged-ref", required=True)
    release.add_argument("--canonical-ref", default="origin/master")
    release.add_argument("--repository", default="go-odyssey")
    release.add_argument("--release-id", required=True)
    release.add_argument("--release-type", choices=RELEASE_TYPES, required=True)
    release.add_argument("--risk-class", choices=RISK_CLASSES, required=True)
    release.add_argument("--basis", dest="classification_basis", action="append", required=True)
    release.add_argument("--app-artifact-json", type=Path)
    release.add_argument("--static-artifact-json", type=Path)
    release.add_argument("--external-content-json", type=Path)
    release.add_argument("--candidate-evidence-json", type=Path)
    release.add_argument("--output", type=Path, required=True)
    release.add_argument("--force", action="store_true")

    validate = subs.add_parser("validate")
    validate.add_argument("--kind", choices=("candidate", "release"), required=True)
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--repo", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "candidate":
            payload = collect_candidate_evidence(
                args.repo,
                base_ref=args.base_ref,
                head_ref=args.head_ref,
                repository=args.repository,
                risk_class=args.risk_class,
                classification_basis=args.classification_basis,
                scope_statement=args.scope_statement,
                checks=_load(args.checks_json),
                python_relevant=args.python_relevant,
                javascript_relevant=args.javascript_relevant,
                browser_relevant=args.browser_relevant,
                planned_release_type=args.planned_release_type,
                pr_number=args.pr_number,
            )
        elif args.command == "release":
            external = _load(args.external_content_json) if args.external_content_json else []
            _require(isinstance(external, list), "external content JSON must be a list")
            payload = collect_release_provenance(
                args.repo,
                merged_ref=args.merged_ref,
                canonical_ref=args.canonical_ref,
                repository=args.repository,
                release_id=args.release_id,
                release_type=args.release_type,
                risk_class=args.risk_class,
                classification_basis=args.classification_basis,
                app_artifact=_load(args.app_artifact_json) if args.app_artifact_json else None,
                static_artifact=_load(args.static_artifact_json) if args.static_artifact_json else None,
                external_content=external,
                candidate_evidence_path=args.candidate_evidence_json,
            )
        else:
            payload = _load(args.input)
            if args.kind == "candidate":
                validate_candidate_evidence(payload, args.repo)
            else:
                validate_release_provenance(payload, args.repo)
            print(json.dumps({"status": "PASS", "artifact_kind": payload["artifact_kind"]}))
            return 0
        _write(args.output, payload, args.force)
        print(json.dumps({"status": "PASS", "output": str(args.output)}))
        return 0
    except EvidenceError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
