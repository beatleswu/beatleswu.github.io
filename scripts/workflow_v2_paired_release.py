#!/usr/bin/env python3
"""Build and validate a Workflow V2 paired app/static release envelope.

This module is deliberately a pure evidence and decision layer.  It does not
contact Production and it does not invoke deploy or rollback commands.  The
existing release scripts remain responsible for those owner-gated actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


class PairedReleaseError(ValueError):
    """Raised when a paired-release envelope is unsafe or incomplete."""


SCHEMA_VERSION = "workflow-v2-paired-release-v1"
PAIRED_RELEASE_TYPE = "PAIRED_APP_STATIC"
RELEASE_TYPES = frozenset({"APP_ONLY", "STATIC_ONLY", PAIRED_RELEASE_TYPE})
FINAL_STATES = ("NEW_COHERENT_PAIR", "OLD_COHERENT_PAIR")
FAILURE_PHASES = frozenset(
    {"PREPARED", "APP_SWITCHED", "STATIC_SWITCHED", "BOTH_SWITCHED"}
)
OBJECTIVE_FAILURES = frozenset(
    {
        "app_health_failure",
        "container_unhealthy",
        "artifact_identity_mismatch",
        "static_integrity_failure",
        "readiness_failure",
        "critical_affected_path_smoke_failure",
    }
)
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

APP_IDENTITY_FIELDS = (
    "release_manifest_sha256",
    "archive_sha256",
    "image_id",
    "image_tag",
    "oci_revision",
)
STATIC_IDENTITY_FIELDS = (
    "manifest_sha256",
    "archive_sha256",
    "static_generation_id",
    "release_git_sha",
    "service_worker_identity",
)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PairedReleaseError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PairedReleaseError(f"{label} must be a non-empty string")
    return value


def _sha256(value: Any, label: str) -> str:
    value = _text(value, label)
    if not SHA256_PATTERN.fullmatch(value):
        raise PairedReleaseError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _sha40(value: Any, label: str) -> str:
    value = _text(value, label)
    if not SHA40_PATTERN.fullmatch(value):
        raise PairedReleaseError(f"{label} must be a lowercase SHA-40 commit identity")
    return value


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _identity(
    value: Any,
    fields: Sequence[str],
    label: str,
    *,
    source_sha: str | None = None,
) -> dict[str, str]:
    raw = _mapping(value, label)
    result: dict[str, str] = {}
    for field in fields:
        if field.endswith("_sha256"):
            result[field] = _sha256(raw.get(field), f"{label}.{field}")
        elif field in {"oci_revision", "release_git_sha"}:
            result[field] = _sha40(raw.get(field), f"{label}.{field}")
        else:
            result[field] = _text(raw.get(field), f"{label}.{field}")

    if source_sha is not None:
        if "oci_revision" in result and result["oci_revision"] != source_sha:
            raise PairedReleaseError(
                f"{label}.oci_revision must equal merged_source_sha"
            )
        if "release_git_sha" in result and result["release_git_sha"] != source_sha:
            raise PairedReleaseError(
                f"{label}.release_git_sha must equal merged_source_sha"
            )
    return result


def calculate_compatibility_id(
    merged_source_sha: str,
    app_artifact: Mapping[str, Any],
    static_artifact: Mapping[str, Any],
) -> str:
    """Return the deterministic identity of one approved app/static pair."""

    source_sha = _sha40(merged_source_sha, "merged_source_sha")
    app = _identity(
        app_artifact,
        APP_IDENTITY_FIELDS,
        "app_artifact",
        source_sha=source_sha,
    )
    static = _identity(
        static_artifact,
        STATIC_IDENTITY_FIELDS,
        "static_artifact",
        source_sha=source_sha,
    )
    pair_material = {
        "contract": "WORKFLOW_V2_PAIRED_APP_STATIC",
        "merged_source_sha": source_sha,
        "app": app,
        "static": static,
    }
    return f"pair-{_canonical_digest(pair_material)}"


def _validate_compatibility_declaration(
    declaration: Any,
    *,
    merged_source_sha: str,
    app_artifact: Mapping[str, str],
    static_artifact: Mapping[str, str],
    compatibility_id: str,
) -> dict[str, Any]:
    raw = _mapping(declaration, "compatibility_declaration")
    if raw.get("declared") is not True:
        raise PairedReleaseError(
            "compatibility_declaration.declared must be true for a paired release"
        )

    normalized = {
        "declared": True,
        "declared_by": _text(raw.get("declared_by"), "compatibility_declaration.declared_by"),
        "compatibility_id": _text(
            raw.get("compatibility_id"),
            "compatibility_declaration.compatibility_id",
        ),
        "merged_source_sha": _sha40(
            raw.get("merged_source_sha"),
            "compatibility_declaration.merged_source_sha",
        ),
        "app_artifact_identity": _text(
            raw.get("app_artifact_identity"),
            "compatibility_declaration.app_artifact_identity",
        ),
        "app_archive_sha256": _sha256(
            raw.get("app_archive_sha256"),
            "compatibility_declaration.app_archive_sha256",
        ),
        "static_generation_identity": _text(
            raw.get("static_generation_identity"),
            "compatibility_declaration.static_generation_identity",
        ),
        "static_archive_sha256": _sha256(
            raw.get("static_archive_sha256"),
            "compatibility_declaration.static_archive_sha256",
        ),
        "service_worker_identity": _text(
            raw.get("service_worker_identity"),
            "compatibility_declaration.service_worker_identity",
        ),
    }

    expected = {
        "compatibility_id": compatibility_id,
        "merged_source_sha": merged_source_sha,
        "app_artifact_identity": app_artifact["image_id"],
        "app_archive_sha256": app_artifact["archive_sha256"],
        "static_generation_identity": static_artifact["static_generation_id"],
        "static_archive_sha256": static_artifact["archive_sha256"],
        "service_worker_identity": static_artifact["service_worker_identity"],
    }
    for field, expected_value in expected.items():
        if normalized[field] != expected_value:
            raise PairedReleaseError(
                f"compatibility declaration does not bind {field} to the approved artifact"
            )
    return normalized


def _validate_predeploy_capture(
    capture: Any,
    previous_app_identity: Any,
    previous_static_identity: Any,
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    raw = _mapping(capture, "predeploy_capture")
    scope = raw.get("capture_scope")
    if not isinstance(scope, list) or set(scope) != {"app", "static"}:
        raise PairedReleaseError(
            "predeploy_capture.capture_scope must include exactly app and static"
        )
    if raw.get("coherence_verified") is not True:
        raise PairedReleaseError(
            "predeploy_capture.coherence_verified must be true"
        )

    normalized = {
        "observation_id": _text(
            raw.get("observation_id"), "predeploy_capture.observation_id"
        ),
        "captured_at": _text(raw.get("captured_at"), "predeploy_capture.captured_at"),
        "evidence_sha256": _sha256(
            raw.get("evidence_sha256"), "predeploy_capture.evidence_sha256"
        ),
        "source_tool": _text(raw.get("source_tool"), "predeploy_capture.source_tool"),
        "capture_scope": ["app", "static"],
        "coherence_verified": True,
        "previous_compatibility_id": _text(
            raw.get("previous_compatibility_id"),
            "predeploy_capture.previous_compatibility_id",
        ),
    }
    if normalized["source_tool"] != "preflight-production.ps1":
        raise PairedReleaseError(
            "predeploy_capture.source_tool must be preflight-production.ps1"
        )

    previous_app = _identity(
        previous_app_identity,
        APP_IDENTITY_FIELDS,
        "previous_app_identity",
    )
    previous_static = _identity(
        previous_static_identity,
        STATIC_IDENTITY_FIELDS,
        "previous_static_identity",
    )
    if previous_app["oci_revision"] != previous_static["release_git_sha"]:
        raise PairedReleaseError(
            "previous app and static source identities are not a coherent pair"
        )
    expected_previous_compatibility_id = calculate_compatibility_id(
        previous_app["oci_revision"],
        previous_app,
        previous_static,
    )
    if normalized["previous_compatibility_id"] != expected_previous_compatibility_id:
        raise PairedReleaseError(
            "predeploy previous_compatibility_id does not bind the immediate old pair"
        )
    return normalized, previous_app, previous_static


def bind_paired_release(
    *,
    merged_source_sha: str,
    release_id: str,
    app_artifact: Mapping[str, Any],
    static_artifact: Mapping[str, Any],
    compatibility_declaration: Mapping[str, Any],
    previous_app_identity: Mapping[str, Any],
    previous_static_identity: Mapping[str, Any],
    predeploy_capture: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the exact artifact and immediate-predeploy rollback envelope."""

    source_sha = _sha40(merged_source_sha, "merged_source_sha")
    release_id = _text(release_id, "release_id")
    app = _identity(
        app_artifact,
        APP_IDENTITY_FIELDS,
        "app_artifact",
        source_sha=source_sha,
    )
    static = _identity(
        static_artifact,
        STATIC_IDENTITY_FIELDS,
        "static_artifact",
        source_sha=source_sha,
    )
    compatibility_id = calculate_compatibility_id(source_sha, app, static)
    declaration = _validate_compatibility_declaration(
        compatibility_declaration,
        merged_source_sha=source_sha,
        app_artifact=app,
        static_artifact=static,
        compatibility_id=compatibility_id,
    )
    capture, previous_app, previous_static = _validate_predeploy_capture(
        predeploy_capture,
        previous_app_identity,
        previous_static_identity,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "PAIRED_RELEASE_ENVELOPE",
        "release_type": PAIRED_RELEASE_TYPE,
        "release_id": release_id,
        "merged_source_sha": source_sha,
        "new_pair": {
            "compatibility_id": compatibility_id,
            "app": app,
            "static": static,
        },
        "compatibility": declaration,
        "predeploy": capture,
        "old_pair": {
            "compatibility_id": capture["previous_compatibility_id"],
            "app": previous_app,
            "static": previous_static,
        },
        "convergence": {
            "allowed_final_states": list(FINAL_STATES),
            "transition_guard_required": True,
            "subjective_owner_rejection_auto_rollback": False,
            "objective_failures": sorted(OBJECTIVE_FAILURES),
        },
    }


def validate_paired_release(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Validate every binding in an envelope and return it unchanged."""

    raw = _mapping(envelope, "paired_release_envelope")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise PairedReleaseError("unsupported paired-release envelope schema")
    if raw.get("artifact_kind") != "PAIRED_RELEASE_ENVELOPE":
        raise PairedReleaseError("artifact_kind must be PAIRED_RELEASE_ENVELOPE")
    if raw.get("release_type") != PAIRED_RELEASE_TYPE:
        raise PairedReleaseError("paired envelope release_type must be PAIRED_APP_STATIC")

    source_sha = _sha40(raw.get("merged_source_sha"), "merged_source_sha")
    _text(raw.get("release_id"), "release_id")
    new_pair = _mapping(raw.get("new_pair"), "new_pair")
    new_app = _identity(
        new_pair.get("app"),
        APP_IDENTITY_FIELDS,
        "new_pair.app",
        source_sha=source_sha,
    )
    new_static = _identity(
        new_pair.get("static"),
        STATIC_IDENTITY_FIELDS,
        "new_pair.static",
        source_sha=source_sha,
    )
    compatibility_id = calculate_compatibility_id(source_sha, new_app, new_static)
    if new_pair.get("compatibility_id") != compatibility_id:
        raise PairedReleaseError("new_pair.compatibility_id does not match its artifacts")
    _validate_compatibility_declaration(
        raw.get("compatibility"),
        merged_source_sha=source_sha,
        app_artifact=new_app,
        static_artifact=new_static,
        compatibility_id=compatibility_id,
    )

    capture = _mapping(raw.get("predeploy"), "predeploy")
    previous_app = _mapping(_mapping(raw.get("old_pair"), "old_pair").get("app"), "old_pair.app")
    previous_static = _mapping(
        _mapping(raw.get("old_pair"), "old_pair").get("static"),
        "old_pair.static",
    )
    normalized_capture, old_app, old_static = _validate_predeploy_capture(
        capture,
        previous_app,
        previous_static,
    )
    old_pair = _mapping(raw.get("old_pair"), "old_pair")
    if old_pair.get("compatibility_id") != normalized_capture["previous_compatibility_id"]:
        raise PairedReleaseError(
            "old_pair.compatibility_id must match the predeploy compatibility identity"
        )

    convergence = _mapping(raw.get("convergence"), "convergence")
    if convergence.get("allowed_final_states") != list(FINAL_STATES):
        raise PairedReleaseError("paired release must allow only the two coherent final states")
    if convergence.get("transition_guard_required") is not True:
        raise PairedReleaseError("paired release requires a guarded transition")
    if convergence.get("subjective_owner_rejection_auto_rollback") is not False:
        raise PairedReleaseError(
            "subjective Owner rejection must not trigger automatic rollback"
        )
    if sorted(convergence.get("objective_failures", [])) != sorted(OBJECTIVE_FAILURES):
        raise PairedReleaseError("objective failure policy is incomplete or changed")

    # Keep these local assignments explicit: they document that both old
    # identities were parsed from the same predeploy capture.
    _ = (old_app, old_static, normalized_capture)
    return dict(raw)


def validate_independent_release(
    release_type: str,
    *,
    app_artifact: Mapping[str, Any] | None = None,
    static_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate that APP_ONLY and STATIC_ONLY remain independent release modes."""

    if release_type not in RELEASE_TYPES:
        raise PairedReleaseError(f"unsupported release type: {release_type}")
    if release_type == PAIRED_RELEASE_TYPE:
        raise PairedReleaseError("use bind_paired_release for PAIRED_APP_STATIC")
    if release_type == "APP_ONLY":
        if app_artifact is None or static_artifact is not None:
            raise PairedReleaseError("APP_ONLY requires app only")
        artifact = _identity(app_artifact, APP_IDENTITY_FIELDS, "app_artifact")
    else:
        if static_artifact is None or app_artifact is not None:
            raise PairedReleaseError("STATIC_ONLY requires static only")
        artifact = _identity(static_artifact, STATIC_IDENTITY_FIELDS, "static_artifact")
    return {
        "release_type": release_type,
        "paired": False,
        "artifact": artifact,
    }


def _observed_pair(
    state: Mapping[str, Any],
    *,
    expected: Mapping[str, Any],
    label: str,
) -> None:
    observed = _mapping(state, label)
    expected_app = _mapping(expected.get("app"), f"{label}.expected_app")
    expected_static = _mapping(expected.get("static"), f"{label}.expected_static")
    actual_app = _identity(observed.get("app"), APP_IDENTITY_FIELDS, f"{label}.app")
    actual_static = _identity(
        observed.get("static"),
        STATIC_IDENTITY_FIELDS,
        f"{label}.static",
    )
    if dict(actual_app) != dict(expected_app) or dict(actual_static) != dict(expected_static):
        raise PairedReleaseError(f"{label} does not match the approved exact pair")
    if observed.get("compatibility_id") != expected.get("compatibility_id"):
        raise PairedReleaseError(f"{label}.compatibility_id does not match the approved pair")


def verify_pair_state(
    envelope: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    expected_final_state: str,
) -> dict[str, Any]:
    """Verify an observed state against the exact new or old pair."""

    validate_paired_release(envelope)
    if expected_final_state not in FINAL_STATES:
        raise PairedReleaseError(f"unsupported final state: {expected_final_state}")
    key = "new_pair" if expected_final_state == "NEW_COHERENT_PAIR" else "old_pair"
    _observed_pair(state, expected=envelope[key], label=expected_final_state)
    return {
        "final_state": expected_final_state,
        "coherent": True,
        "compatibility_id": envelope[key]["compatibility_id"],
    }


def finalize_new_pair(
    envelope: Mapping[str, Any], state: Mapping[str, Any]
) -> dict[str, Any]:
    """Return release evidence only after the exact new pair is observed."""

    return verify_pair_state(
        envelope,
        state,
        expected_final_state="NEW_COHERENT_PAIR",
    )


def plan_failure_convergence(
    envelope: Mapping[str, Any],
    *,
    phase: str,
    failure_kind: str | None = None,
    subjective_owner_rejection: bool = False,
) -> dict[str, Any]:
    """Plan bounded convergence without executing a deploy or rollback."""

    validate_paired_release(envelope)
    if phase not in FAILURE_PHASES:
        raise PairedReleaseError(f"unsupported switch phase: {phase}")

    if subjective_owner_rejection:
        return {
            "decision": "MANUAL_REVIEW_REQUIRED",
            "phase": phase,
            "failure_kind": "subjective_owner_rejection",
            "auto_rollback": False,
            "final_state": "UNRESOLVED_UNTIL_OWNER_DECISION",
            "transition_guard_required": True,
            "actions": [
                {"operation": "hold_transition_guard"},
                {"operation": "request_owner_decision"},
            ],
        }

    if failure_kind not in OBJECTIVE_FAILURES:
        raise PairedReleaseError(
            "objective failure_kind must be one of the declared automatic failure classes"
        )

    old_pair = envelope["old_pair"]
    actions: list[dict[str, Any]] = []
    if phase == "PREPARED":
        actions.append({"operation": "retain_immediate_predeploy_pair"})
        auto_rollback = False
    else:
        actions.append({"operation": "hold_transition_guard"})
        if phase in {"STATIC_SWITCHED", "BOTH_SWITCHED"}:
            actions.append(
                {
                    "operation": "rollback_static_to_previous",
                    "tool": "scripts/release/rollback-static-release.ps1",
                    "static_generation_id": old_pair["static"]["static_generation_id"],
                    "archive_sha256": old_pair["static"]["archive_sha256"],
                }
            )
        if phase in {"APP_SWITCHED", "BOTH_SWITCHED"}:
            actions.append(
                {
                    "operation": "rollback_app_to_previous",
                    "tool": "scripts/release/rollback-release.ps1",
                    "image_id": old_pair["app"]["image_id"],
                    "archive_sha256": old_pair["app"]["archive_sha256"],
                }
            )
        auto_rollback = True
    actions.extend(
        [
            {
                "operation": "verify_old_app_identity",
                "image_id": old_pair["app"]["image_id"],
            },
            {
                "operation": "verify_old_static_identity",
                "static_generation_id": old_pair["static"]["static_generation_id"],
            },
            {
                "operation": "verify_old_coherent_pair",
                "compatibility_id": old_pair["compatibility_id"],
            },
        ]
    )
    return {
        "decision": "AUTO_ROLLBACK_TO_OLD_PAIR",
        "phase": phase,
        "failure_kind": failure_kind,
        "auto_rollback": auto_rollback,
        "final_state": "OLD_COHERENT_PAIR",
        "transition_guard_required": True,
        "subjective_owner_rejection_auto_rollback": False,
        "actions": actions,
    }


def _read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return dict(_mapping(value, path))


def _write_json(value: Mapping[str, Any], path: str | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path is None:
        print(rendered, end="")
    else:
        Path(path).write_text(rendered, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bind = subparsers.add_parser("bind", help="bind exact new and old pair identities")
    bind.add_argument("--input", required=True, help="JSON input for bind_paired_release")
    bind.add_argument("--output", help="write the envelope to this JSON path")

    validate = subparsers.add_parser("validate", help="validate an envelope")
    validate.add_argument("--envelope", required=True)

    failure = subparsers.add_parser("failure", help="plan objective-failure convergence")
    failure.add_argument("--envelope", required=True)
    failure.add_argument("--phase", choices=sorted(FAILURE_PHASES), required=True)
    failure.add_argument("--failure-kind", choices=sorted(OBJECTIVE_FAILURES))
    failure.add_argument("--subjective-owner-rejection", action="store_true")
    failure.add_argument("--output")

    verify = subparsers.add_parser("verify", help="verify one exact final pair")
    verify.add_argument("--envelope", required=True)
    verify.add_argument("--state", required=True)
    verify.add_argument("--final-state", choices=FINAL_STATES, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "bind":
            payload = _read_json(args.input)
            envelope = bind_paired_release(**payload)
            _write_json(envelope, args.output)
        elif args.command == "validate":
            validate_paired_release(_read_json(args.envelope))
            print("PAIRED_RELEASE_VALID=YES")
        elif args.command == "failure":
            result = plan_failure_convergence(
                _read_json(args.envelope),
                phase=args.phase,
                failure_kind=args.failure_kind,
                subjective_owner_rejection=args.subjective_owner_rejection,
            )
            _write_json(result, args.output)
        else:
            result = verify_pair_state(
                _read_json(args.envelope),
                _read_json(args.state),
                expected_final_state=args.final_state,
            )
            _write_json(result, None)
    except (OSError, json.JSONDecodeError, PairedReleaseError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
