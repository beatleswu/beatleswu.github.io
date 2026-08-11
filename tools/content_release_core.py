"""Governed backup, verification, publish, and rollback primitives.

The module is intentionally independent from application startup.  Every
operation defaults to verification-only behavior, and all mutation boundaries
are explicit.  It contains no Production address, credential, or corpus bytes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol


CHUNK_SIZE = 1024 * 1024
PRIVATE_VISIBILITY = "PRIVATE"
REMOTE_EXECUTION_GATE = "GO_GITHUB_CONTENT_BACKUP_RELEASE"
PUBLISH_EXECUTION_GATE = "GO_PRODUCTION_CONTENT_RELEASE"
ROLLBACK_EXECUTION_GATE = "GO_PRODUCTION_CONTENT_ROLLBACK"
CONTENT_MANIFEST_SCHEMA_VERSION = "1.1"
ACCEPTANCE_EVIDENCE_SCHEMA_VERSION = "1.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_ACCEPTANCE_SURFACES = (
    "sgf_engine_native",
    "rating_test_server",
    "map_battle_server",
    "main_practice_client",
    "daily_challenge_client",
    "friend_challenge_client_then_server_trust",
)
PROVENANCE_STATUSES = {
    "LOCAL_BYTE_VERIFIED",
    "GIT_COMMIT_BYTE_VERIFIED",
    "IMMUTABLE_SNAPSHOT_BYTE_VERIFIED",
    "RELEASE_ASSET_BYTE_VERIFIED",
}
PROVENANCE_FIELDS = (
    "source_kind",
    "source_repo_id",
    "source_commit_or_snapshot_id",
    "source_path",
    "source_sha256",
    "source_size_bytes",
    "source_record_count",
    "source_status",
)


class GovernanceError(RuntimeError):
    """A fail-closed governance or verification failure."""


@dataclass(frozen=True)
class ArtifactIdentity:
    path: str
    size_bytes: int
    sha256: str
    record_count: int


@dataclass(frozen=True)
class BackupBundle:
    source: ArtifactIdentity
    compressed_path: str
    compressed_sha256: str
    manifest_path: str
    manifest_sha256: str
    checksums_path: str


@dataclass(frozen=True)
class ReleaseBundle:
    candidate: ArtifactIdentity
    compressed_path: str
    compressed_sha256: str
    release_manifest_path: str
    rollback_manifest_path: str
    acceptance_evidence_path: str
    acceptance_evidence_sha256: str
    registry_entry_path: str
    registry_entry_sha256: str
    checksums_path: str


@dataclass(frozen=True)
class RoundTripReceipt:
    source_uncompressed_sha256: str
    local_uncompressed_sha256: str
    remote_uncompressed_sha256: str
    record_count: int
    repository_visibility: str
    release_tag: str
    remote_asset_name: str
    remote_asset_sha256: str
    remote_asset_inventory_sha256: str
    remote_asset_count: int
    offsite_backup_verified: bool


class ReleaseRegistry(Protocol):
    @property
    def visibility(self) -> str: ...

    @property
    def tag(self) -> str: ...

    def upload(self, paths: Iterable[Path]) -> None: ...

    def asset_exists(self, name: str) -> bool: ...

    def download(self, name: str, destination: Path) -> Path: ...

    def inventory(self) -> dict[str, dict[str, Any]]: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def json_record_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"malformed_or_unreadable_json:{path}") from exc
    if not isinstance(payload, list):
        raise GovernanceError(f"questions_root_must_be_array:{path}")
    return len(payload)


def identify_json(path: Path) -> ArtifactIdentity:
    if not path.is_file():
        raise GovernanceError(f"missing_json_artifact:{path}")
    return ArtifactIdentity(
        path=str(path.resolve()),
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        record_count=json_record_count(path),
    )


def canonical_json_bytes(payload: Any) -> bytes:
    """Return the byte representation used for governance identities."""

    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GovernanceError("governance_payload_not_canonicalizable") from exc


def canonical_payload_sha256(payload: Mapping[str, Any], *, without: str | None = None) -> str:
    value = dict(payload)
    if without is not None:
        value.pop(without, None)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise GovernanceError(f"{label}_must_be_lowercase_sha256")
    return value


def _require_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise GovernanceError(f"{label}_must_be_integer")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceError(f"{label}_must_be_non_empty_string")
    return value


def _reject_unknown_fields(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise GovernanceError(f"{label}_unknown_fields:{','.join(unknown)}")


def _safe_filename(value: Any, label: str) -> str:
    name = _require_string(value, label)
    if name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise GovernanceError(f"{label}_must_be_safe_filename")
    return name


def _normalized_repo_path(path: Path, repo_root: Path, label: str = "source_path") -> str:
    root = repo_root.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise GovernanceError(f"{label}_outside_source_repository") from exc
    return relative.as_posix()


def _git_run(repo_root: Path, *arguments: str, label: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise GovernanceError(f"{label}_git_command_failed")
    return completed.stdout.strip()


def _git_remote_repo_id(repo_root: Path) -> str:
    remote = _git_run(repo_root, "config", "--get", "remote.origin.url", label="source_repo")
    value = remote.strip()
    if value.startswith("git@") and ":" in value:
        value = value.split(":", 1)[1]
    elif "://" in value:
        value = value.split("://", 1)[1]
        if "/" in value:
            value = value.split("/", 1)[1]
    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def build_source_provenance(
    source: Path,
    *,
    source_kind: str = "local_file",
    source_repo_id: str | None = None,
    source_commit_or_snapshot_id: str | None = None,
    source_path: str | None = None,
    source_status: str | None = None,
    source_receipt_sha256: str | None = None,
    review_source_id: str | None = None,
    source_snapshot_sha256: str | None = None,
    detector_manifest_sha256: str | None = None,
    validation_pack_id: str | None = None,
    approved_proposal_set_sha256: str | None = None,
    repair_batch_manifest_sha256: str | None = None,
    repo_root: Path | None = None,
    current_ref: str = "origin/master",
) -> dict[str, Any]:
    """Derive provenance from bytes; optional declarations are assertions."""

    identity = identify_json(source)
    if source_kind not in {"local_file", "git_blob", "immutable_snapshot"}:
        raise GovernanceError("unsupported_source_kind")
    if source_kind == "git_blob":
        if repo_root is None:
            raise GovernanceError("git_source_repo_root_required")
        relative_path = _normalized_repo_path(source, repo_root)
        source_path = relative_path
        source_repo_id = source_repo_id or _git_remote_repo_id(repo_root)
        source_commit_or_snapshot_id = _require_string(
            source_commit_or_snapshot_id, "source_commit_or_snapshot_id"
        )
        source_status = source_status or "GIT_COMMIT_BYTE_VERIFIED"
    elif source_kind == "immutable_snapshot":
        source_commit_or_snapshot_id = _require_string(
            source_commit_or_snapshot_id, "source_commit_or_snapshot_id"
        )
        source_status = source_status or "IMMUTABLE_SNAPSHOT_BYTE_VERIFIED"
        if source_receipt_sha256 is None:
            raise GovernanceError("immutable_snapshot_receipt_required")
        source_snapshot_sha256 = source_snapshot_sha256 or identity.sha256
    else:
        source_repo_id = None
        source_commit_or_snapshot_id = None
        source_path = str(source.resolve())
        source_status = source_status or "LOCAL_BYTE_VERIFIED"

    declared = {
        "source_sha256": identity.sha256,
        "source_size_bytes": identity.size_bytes,
        "source_record_count": identity.record_count,
    }
    if source_path is not None and source_kind != "local_file":
        declared_path = _require_string(source_path, "source_path")
    else:
        declared_path = source_path or str(source.resolve())
    payload: dict[str, Any] = {
        "source_kind": source_kind,
        "source_repo_id": source_repo_id,
        "source_commit_or_snapshot_id": source_commit_or_snapshot_id,
        "source_path": declared_path,
        **declared,
        "source_status": source_status,
    }
    if source_receipt_sha256 is not None:
        payload["source_receipt_sha256"] = _require_sha256(source_receipt_sha256, "source_receipt_sha256")
    optional_links = {
        "review_source_id": review_source_id,
        "source_snapshot_sha256": source_snapshot_sha256,
        "detector_manifest_sha256": detector_manifest_sha256,
        "validation_pack_id": validation_pack_id,
        "approved_proposal_set_sha256": approved_proposal_set_sha256,
        "repair_batch_manifest_sha256": repair_batch_manifest_sha256,
    }
    for name, value in optional_links.items():
        if value is not None:
            payload[name] = _require_sha256(value, name)
    payload["source_identity_sha256"] = canonical_payload_sha256(payload)
    verify_source_provenance(
        payload,
        source=source,
        repo_root=repo_root,
        current_ref=current_ref,
    )
    return payload


def verify_source_provenance(
    provenance: Mapping[str, Any],
    *,
    source: Path | None = None,
    actual_identity: ArtifactIdentity | None = None,
    expected_sha256: str | None = None,
    expected_size_bytes: int | None = None,
    expected_record_count: int | None = None,
    repo_root: Path | None = None,
    current_ref: str = "origin/master",
    verify_source_path: bool = True,
) -> dict[str, Any]:
    """Verify provenance against bytes and, for Git, the actual commit/blob."""

    payload = dict(provenance)
    missing = [field for field in PROVENANCE_FIELDS if field not in payload]
    if missing:
        raise GovernanceError(f"source_provenance_missing_fields:{','.join(missing)}")
    allowed = set(PROVENANCE_FIELDS) | {
        "source_identity_sha256",
        "source_receipt_sha256",
        "review_source_id",
        "source_snapshot_sha256",
        "detector_manifest_sha256",
        "validation_pack_id",
        "approved_proposal_set_sha256",
        "repair_batch_manifest_sha256",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise GovernanceError(f"source_provenance_unknown_fields:{','.join(unknown)}")
    for field in ("source_sha256", "source_receipt_sha256", "review_source_id", "source_snapshot_sha256",
                  "detector_manifest_sha256", "validation_pack_id", "approved_proposal_set_sha256",
                  "repair_batch_manifest_sha256"):
        if field in payload and payload[field] is not None:
            _require_sha256(payload[field], field)
    _require_string(payload["source_kind"], "source_kind")
    _require_string(payload["source_path"], "source_path")
    _require_string(payload["source_status"], "source_status")
    _require_sha256(payload["source_sha256"], "source_sha256")
    _require_int(payload["source_size_bytes"], "source_size_bytes", minimum=1)
    _require_int(payload["source_record_count"], "source_record_count")
    if payload["source_status"] not in PROVENANCE_STATUSES:
        raise GovernanceError("source_status_not_verifiable")
    if payload["source_kind"] == "local_file":
        if payload["source_repo_id"] is not None or payload["source_commit_or_snapshot_id"] is not None:
            raise GovernanceError("local_source_must_not_claim_git_identity")
        if payload["source_status"] != "LOCAL_BYTE_VERIFIED":
            raise GovernanceError("local_source_status_mismatch")
    elif payload["source_kind"] == "git_blob":
        if repo_root is None:
            raise GovernanceError("git_source_repo_root_required")
        _require_string(payload["source_repo_id"], "source_repo_id")
        commit = _require_string(payload["source_commit_or_snapshot_id"], "source_commit_or_snapshot_id")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise GovernanceError("source_commit_or_snapshot_id_must_be_full_sha")
        relative = _normalized_repo_path(Path(repo_root) / payload["source_path"], Path(repo_root))
        if relative != payload["source_path"]:
            raise GovernanceError("source_path_not_normalized")
        if _git_remote_repo_id(Path(repo_root)) != payload["source_repo_id"]:
            raise GovernanceError("source_repo_id_mismatch")
        _git_run(Path(repo_root), "cat-file", "-e", f"{commit}^{{commit}}", label="source_commit")
        ancestry = subprocess.run(
            ["git", "-C", str(Path(repo_root)), "merge-base", "--is-ancestor", commit, current_ref],
            check=False,
            capture_output=True,
        )
        if ancestry.returncode != 0:
            raise GovernanceError("source_commit_not_ancestral")
        blob_sha = _git_run(Path(repo_root), "rev-parse", f"{commit}:{payload['source_path']}", label="source_blob")
        raw = subprocess.run(
            ["git", "-C", str(Path(repo_root)), "cat-file", "blob", blob_sha],
            check=False,
            capture_output=True,
        )
        if raw.returncode != 0:
            raise GovernanceError("source_blob_unreadable")
        if hashlib.sha256(raw.stdout).hexdigest() != payload["source_sha256"]:
            raise GovernanceError("source_blob_sha256_mismatch")
        if len(raw.stdout) != payload["source_size_bytes"]:
            raise GovernanceError("source_blob_size_mismatch")
    elif payload["source_kind"] == "immutable_snapshot":
        _require_string(payload["source_commit_or_snapshot_id"], "source_commit_or_snapshot_id")
        if payload["source_status"] not in {"IMMUTABLE_SNAPSHOT_BYTE_VERIFIED", "RELEASE_ASSET_BYTE_VERIFIED"}:
            raise GovernanceError("external_snapshot_not_immutable")
        _require_sha256(payload.get("source_receipt_sha256"), "source_receipt_sha256")
        if payload.get("source_snapshot_sha256") != payload["source_sha256"]:
            raise GovernanceError("source_snapshot_identity_mismatch")
    else:
        raise GovernanceError("unsupported_source_kind")

    identity_hash = payload.get("source_identity_sha256")
    if identity_hash is None:
        raise GovernanceError("source_identity_hash_missing")
    if _require_sha256(identity_hash, "source_identity_sha256") != canonical_payload_sha256(
        payload, without="source_identity_sha256"
    ):
        raise GovernanceError("source_identity_hash_mismatch")

    if source is not None:
        identity = identify_json(source)
        actual_identity = identity
        if verify_source_path and payload["source_kind"] == "local_file":
            if payload["source_path"] != str(source.resolve()):
                raise GovernanceError("source_path_mismatch")
        if verify_source_path and payload["source_kind"] == "git_blob":
            if _normalized_repo_path(source, Path(repo_root)) != payload["source_path"]:
                raise GovernanceError("source_path_mismatch")
    if actual_identity is not None:
        if actual_identity.sha256 != payload["source_sha256"]:
            raise GovernanceError("source_bytes_sha256_mismatch")
        if actual_identity.size_bytes != payload["source_size_bytes"]:
            raise GovernanceError("source_size_mismatch")
        if actual_identity.record_count != payload["source_record_count"]:
            raise GovernanceError("source_record_count_mismatch")
    expected = {
        "source_sha256": expected_sha256,
        "source_size_bytes": expected_size_bytes,
        "source_record_count": expected_record_count,
    }
    for field, value in expected.items():
        if value is not None and payload[field] != value:
            raise GovernanceError(f"{field}_mismatch")
    return payload


def _load_governance_reference(value: Path | Mapping[str, Any], label: str) -> tuple[dict[str, Any], str, Path | None]:
    if isinstance(value, (str, Path)):
        path = Path(value)
        return load_json_object(path, label=label), sha256_file(path), path
    if isinstance(value, Mapping):
        payload = dict(value)
        return payload, canonical_payload_sha256(payload), None
    raise GovernanceError(f"{label}_reference_invalid")


def _validate_artifact_reference_hash(
    value: Path | Mapping[str, Any] | None,
    *,
    expected_sha256: str,
    label: str,
) -> tuple[dict[str, Any], str, Path | None]:
    if value is None:
        raise GovernanceError(f"{label}_artifact_missing")
    payload, actual_hash, path = _load_governance_reference(value, label)
    if actual_hash != expected_sha256:
        raise GovernanceError(f"{label}_identity_mismatch")
    return payload, actual_hash, path


def validate_review_binding(payload: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "authority",
        "canonicality",
        "identity_boundary",
        "review_source_id",
        "source_snapshot_sha256",
        "detector_manifest_sha256",
        "validation_pack_id",
        "approved_proposal_set_sha256",
        "review_group_ids",
        "owner_authority",
        "binding_identity_sha256",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise GovernanceError(f"review_binding_missing_fields:{','.join(missing)}")
    _reject_unknown_fields(payload, required | {"proposals"}, "review_binding")
    if payload["schema_version"] != "1.0":
        raise GovernanceError("review_binding_schema_version_mismatch")
    if payload["authority"] != "OWNER_APPROVED_REPAIR_PROPOSAL":
        raise GovernanceError("review_binding_authority_mismatch")
    if payload["canonicality"] != "STAGED_NOT_APPLIED":
        raise GovernanceError("review_binding_canonicality_mismatch")
    if payload["identity_boundary"] != "AUDIT_LOCATOR_ONLY":
        raise GovernanceError("review_binding_identity_boundary_mismatch")
    for field in (
        "review_source_id",
        "source_snapshot_sha256",
        "detector_manifest_sha256",
        "validation_pack_id",
        "approved_proposal_set_sha256",
        "binding_identity_sha256",
    ):
        _require_sha256(payload[field], f"review_binding_{field}")
    _require_string(payload["owner_authority"], "review_binding_owner_authority")
    groups = payload["review_group_ids"]
    if not isinstance(groups, list) or not groups or len(set(groups)) != len(groups):
        raise GovernanceError("review_binding_group_ids_invalid")
    for group in groups:
        _require_sha256(group, "review_group_id")
    proposals = payload.get("proposals", [])
    if not isinstance(proposals, list):
        raise GovernanceError("review_binding_proposals_invalid")
    for proposal in proposals:
        if not isinstance(proposal, Mapping):
            raise GovernanceError("review_binding_proposal_invalid")
        if proposal.get("authority") != "OWNER_APPROVED_REPAIR_PROPOSAL":
            raise GovernanceError("review_binding_proposal_authority_mismatch")
        if proposal.get("canonicality") != "STAGED_NOT_APPLIED":
            raise GovernanceError("review_binding_proposal_canonicality_mismatch")
        if proposal.get("identity_boundary") != "AUDIT_LOCATOR_ONLY":
            raise GovernanceError("review_binding_proposal_identity_boundary_mismatch")
    if payload["binding_identity_sha256"] != canonical_payload_sha256(payload, without="binding_identity_sha256"):
        raise GovernanceError("review_binding_identity_hash_mismatch")
    return dict(payload)


def validate_acceptance_evidence(
    payload: Mapping[str, Any],
    *,
    expected_candidate_sha256: str,
    expected_record_count: int | None = None,
    expected_repair_batch_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    required = {
        "schema_version",
        "authority",
        "canonicality",
        "candidate_sha256",
        "records",
        "summary",
        "evidence_identity_sha256",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise GovernanceError(f"acceptance_evidence_missing_fields:{','.join(missing)}")
    _reject_unknown_fields(
        payload,
        required | {"repair_batch_manifest_sha256", "source_snapshot_sha256"},
        "acceptance_evidence",
    )
    if payload["schema_version"] != ACCEPTANCE_EVIDENCE_SCHEMA_VERSION:
        raise GovernanceError("acceptance_evidence_schema_version_mismatch")
    if payload["canonicality"] != "VERIFICATION_EVIDENCE_ONLY":
        raise GovernanceError("acceptance_evidence_canonicality_mismatch")
    _require_string(payload["authority"], "acceptance_evidence_authority")
    if payload["candidate_sha256"] != _require_sha256(expected_candidate_sha256, "candidate_sha256"):
        raise GovernanceError("acceptance_evidence_candidate_sha256_mismatch")
    if expected_repair_batch_manifest_sha256 is not None and "repair_batch_manifest_sha256" in payload:
        if payload.get("repair_batch_manifest_sha256") != _require_sha256(
            expected_repair_batch_manifest_sha256, "repair_batch_manifest_sha256"
        ):
            raise GovernanceError("acceptance_evidence_repair_batch_mismatch")
    records = payload["records"]
    if not isinstance(records, list):
        raise GovernanceError("acceptance_evidence_records_invalid")
    seen = set()
    allowed_precedence = {"accepted_moves", "native_sgf", "historical_katago_best_move", "none"}
    for record in records:
        if not isinstance(record, Mapping):
            raise GovernanceError("acceptance_evidence_record_invalid")
        for field in (
            "record_index",
            "legacy_question_id",
            "content_sha256",
            "owner_desired_verdict",
            "final_effective_player_verdict",
            "source_precedence_used",
            "surfaces",
            "evidence_artifact_sha256",
        ):
            if field not in record:
                raise GovernanceError(f"acceptance_evidence_record_missing:{field}")
        index = _require_int(record["record_index"], "acceptance_record_index")
        if index in seen:
            raise GovernanceError("acceptance_evidence_duplicate_record")
        seen.add(index)
        _require_int(record["legacy_question_id"], "acceptance_legacy_question_id")
        _require_sha256(record["content_sha256"], "acceptance_content_sha256")
        _require_sha256(record["evidence_artifact_sha256"], "acceptance_evidence_artifact_sha256")
        precedence = record["source_precedence_used"]
        if not isinstance(precedence, list) or not precedence or len(set(precedence)) != len(precedence):
            raise GovernanceError("acceptance_precedence_invalid")
        if any(item not in allowed_precedence for item in precedence):
            raise GovernanceError("acceptance_precedence_unknown")
        for field in ("accepted_moves_influence", "native_sgf_influence", "historical_katago_best_move_influence"):
            if field in record and not isinstance(record[field], bool):
                raise GovernanceError(f"{field}_must_be_boolean")
        if record["owner_desired_verdict"] != record["final_effective_player_verdict"]:
            raise GovernanceError("acceptance_verdict_mismatch")
        surfaces = record["surfaces"]
        if not isinstance(surfaces, Mapping) or set(surfaces) != set(REQUIRED_ACCEPTANCE_SURFACES):
            raise GovernanceError("acceptance_surface_set_mismatch")
        for surface in REQUIRED_ACCEPTANCE_SURFACES:
            result = surfaces[surface]
            if not isinstance(result, Mapping):
                raise GovernanceError(f"acceptance_surface_result_invalid:{surface}")
            if result.get("pass") is not True or result.get("match") is not True:
                raise GovernanceError(f"acceptance_surface_failed:{surface}")
            _require_sha256(result.get("evidence_artifact_sha256"), f"acceptance_surface_evidence:{surface}")
    summary = payload["summary"]
    if not isinstance(summary, Mapping):
        raise GovernanceError("acceptance_summary_invalid")
    if summary.get("records_validated") != len(records):
        raise GovernanceError("acceptance_summary_record_count_mismatch")
    if summary.get("all_final_effective_match") is not True:
        raise GovernanceError("acceptance_summary_verdict_mismatch")
    if set(summary.get("surfaces", [])) != set(REQUIRED_ACCEPTANCE_SURFACES):
        raise GovernanceError("acceptance_summary_surface_set_mismatch")
    if expected_record_count is not None and len(records) != expected_record_count:
        raise GovernanceError("acceptance_records_validated_mismatch")
    if payload["evidence_identity_sha256"] != canonical_payload_sha256(payload, without="evidence_identity_sha256"):
        raise GovernanceError("acceptance_evidence_identity_hash_mismatch")
    return dict(payload)


def _validate_mutation_audit(payload: Mapping[str, Any], *, source_sha256: str, candidate_sha256: str,
                             changed_record_count: int, review_group_count: int) -> dict[str, Any]:
    for field in ("schema_version", "source_sha256", "candidate_sha256", "changed_record_count", "review_group_count"):
        if field not in payload:
            raise GovernanceError(f"mutation_audit_missing:{field}")
    _require_sha256(payload["source_sha256"], "mutation_audit_source_sha256")
    _require_sha256(payload["candidate_sha256"], "mutation_audit_candidate_sha256")
    if payload["source_sha256"] != source_sha256 or payload["candidate_sha256"] != candidate_sha256:
        raise GovernanceError("mutation_audit_artifact_identity_mismatch")
    if payload["changed_record_count"] != changed_record_count:
        raise GovernanceError("mutation_audit_changed_record_count_mismatch")
    if payload["review_group_count"] != review_group_count:
        raise GovernanceError("mutation_audit_review_group_count_mismatch")
    if payload.get("non_target_records_changed", 0) != 0:
        raise GovernanceError("mutation_audit_non_target_mutation")
    if payload.get("accepted_moves_changed", 0) != 0:
        raise GovernanceError("mutation_audit_accepted_moves_mutated")
    return dict(payload)


def _validate_repair_batch_manifest(payload: Mapping[str, Any], *, source_sha256: str, candidate_sha256: str,
                                    review_binding_sha256: str, mutation_audit_sha256: str,
                                    acceptance_evidence_sha256: str, changed_record_count: int,
                                    review_group_count: int) -> dict[str, Any]:
    required = {
        "schema_version", "source_sha256", "candidate_sha256", "review_binding_sha256",
        "mutation_audit_sha256", "acceptance_evidence_sha256", "changed_record_count", "review_group_count",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise GovernanceError(f"repair_batch_manifest_missing:{','.join(missing)}")
    for field, expected in (
        ("source_sha256", source_sha256),
        ("candidate_sha256", candidate_sha256),
        ("review_binding_sha256", review_binding_sha256),
        ("mutation_audit_sha256", mutation_audit_sha256),
        ("acceptance_evidence_sha256", acceptance_evidence_sha256),
    ):
        if _require_sha256(payload[field], f"repair_batch_{field}") != expected:
            raise GovernanceError(f"repair_batch_{field}_mismatch")
    if payload["changed_record_count"] != changed_record_count:
        raise GovernanceError("repair_batch_changed_record_count_mismatch")
    if payload["review_group_count"] != review_group_count:
        raise GovernanceError("repair_batch_review_group_count_mismatch")
    return dict(payload)


def _validate_rollback_manifest(payload: Mapping[str, Any], *, baseline_sha256: str,
                                candidate_sha256: str, expected_record_count: int) -> dict[str, Any]:
    governance = payload.get("rollback_governance")
    if not isinstance(governance, Mapping):
        raise GovernanceError("rollback_manifest_governance_missing")
    required = {"previous_sha256", "candidate_sha256", "record_count", "restore_target", "post_rollback"}
    missing = sorted(required - set(governance))
    if missing:
        raise GovernanceError(f"rollback_manifest_missing:{','.join(missing)}")
    if _require_sha256(governance["previous_sha256"], "rollback_previous_sha256") != baseline_sha256:
        raise GovernanceError("rollback_previous_sha256_mismatch")
    if _require_sha256(governance["candidate_sha256"], "rollback_candidate_sha256") != candidate_sha256:
        raise GovernanceError("rollback_candidate_sha256_mismatch")
    if governance["record_count"] != expected_record_count:
        raise GovernanceError("rollback_record_count_mismatch")
    _require_string(governance["restore_target"], "rollback_restore_target")
    post = governance["post_rollback"]
    if not isinstance(post, Mapping):
        raise GovernanceError("rollback_postcheck_invalid")
    for field in ("sha256", "size_bytes", "record_count"):
        if field not in post:
            raise GovernanceError(f"rollback_postcheck_missing:{field}")
    if _require_sha256(post["sha256"], "rollback_postcheck_sha256") != baseline_sha256:
        raise GovernanceError("rollback_postcheck_sha256_mismatch")
    _require_int(post["size_bytes"], "rollback_postcheck_size_bytes", minimum=1)
    if post["record_count"] != expected_record_count:
        raise GovernanceError("rollback_postcheck_record_count_mismatch")
    return dict(payload)


def build_rollback_proof(
    *,
    previous: Path,
    candidate: Path,
    rollback_manifest: Path,
    restore_target: Path,
    local_simulation_id: str,
    remote_predecessor: Mapping[str, Any],
    normalized_rollback_inputs: Mapping[str, Any],
) -> dict[str, Any]:
    previous_identity = identify_json(previous)
    candidate_identity = identify_json(candidate)
    _validate_rollback_manifest(
        load_json_object(rollback_manifest, label="rollback_manifest"),
        baseline_sha256=previous_identity.sha256,
        candidate_sha256=candidate_identity.sha256,
        expected_record_count=previous_identity.record_count,
    )
    predecessor = dict(remote_predecessor)
    if predecessor.get("source_sha256") != previous_identity.sha256:
        raise GovernanceError("rollback_remote_predecessor_mismatch")
    for field in ("asset_sha256", "receipt_sha256"):
        _require_sha256(predecessor.get(field), f"rollback_predecessor_{field}")
    proof: dict[str, Any] = {
        "schema_version": "1.0",
        "previous_corpus": asdict(previous_identity),
        "candidate_corpus": asdict(candidate_identity),
        "rollback_manifest_sha256": sha256_file(rollback_manifest),
        "remote_predecessor": predecessor,
        "restore_target": str(restore_target.resolve()),
        "normalized_rollback_inputs_sha256": canonical_payload_sha256(normalized_rollback_inputs),
        "local_rollback_simulation_id": _require_string(local_simulation_id, "local_simulation_id"),
        "expected_post_rollback": {
            "sha256": previous_identity.sha256,
            "size_bytes": previous_identity.size_bytes,
            "record_count": previous_identity.record_count,
        },
    }
    proof["proof_sha256"] = canonical_payload_sha256(proof)
    return proof


def validate_rollback_proof(
    proof: Path | Mapping[str, Any],
    *,
    live: Path,
    baseline: Path,
    candidate: Path,
    rollback_manifest: Path | Mapping[str, Any],
    expected_remote_predecessor: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload, _raw_hash, _path = _load_governance_reference(proof, "rollback_proof")
    required = {
        "schema_version", "previous_corpus", "candidate_corpus", "rollback_manifest_sha256",
        "remote_predecessor", "restore_target", "normalized_rollback_inputs_sha256",
        "local_rollback_simulation_id", "expected_post_rollback", "proof_sha256",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise GovernanceError(f"rollback_proof_missing:{','.join(missing)}")
    if payload["schema_version"] != "1.0":
        raise GovernanceError("rollback_proof_schema_version_mismatch")
    if payload["proof_sha256"] != canonical_payload_sha256(payload, without="proof_sha256"):
        raise GovernanceError("rollback_proof_hash_mismatch")
    previous_identity = identify_json(baseline)
    candidate_identity = identify_json(candidate)
    proof_previous = payload["previous_corpus"]
    proof_candidate = payload["candidate_corpus"]
    for proof_value, actual, label in (
        (proof_previous, previous_identity, "rollback_proof_previous"),
        (proof_candidate, candidate_identity, "rollback_proof_candidate"),
    ):
        if not isinstance(proof_value, Mapping):
            raise GovernanceError(f"{label}_invalid")
        if proof_value.get("sha256") != actual.sha256 or proof_value.get("size_bytes") != actual.size_bytes or proof_value.get("record_count") != actual.record_count:
            raise GovernanceError(f"{label}_identity_mismatch")
    _rollback_payload, rollback_hash, _rollback_path = _load_governance_reference(
        rollback_manifest, "rollback_manifest"
    )
    if payload["rollback_manifest_sha256"] != rollback_hash:
        raise GovernanceError("rollback_proof_manifest_hash_mismatch")
    if payload["restore_target"] != str(live.resolve()):
        raise GovernanceError("rollback_proof_restore_target_mismatch")
    _require_sha256(payload["normalized_rollback_inputs_sha256"], "normalized_rollback_inputs_sha256")
    _require_string(payload["local_rollback_simulation_id"], "local_rollback_simulation_id")
    predecessor = payload["remote_predecessor"]
    if not isinstance(predecessor, Mapping) or predecessor.get("source_sha256") != previous_identity.sha256:
        raise GovernanceError("rollback_proof_predecessor_mismatch")
    for field in ("asset_sha256", "receipt_sha256"):
        _require_sha256(predecessor.get(field), f"rollback_proof_predecessor_{field}")
    if expected_remote_predecessor is not None:
        for field in ("source_sha256", "asset_sha256", "receipt_sha256"):
            expected = _require_sha256(
                expected_remote_predecessor.get(field),
                f"expected_remote_predecessor_{field}",
            )
            if predecessor.get(field) != expected:
                raise GovernanceError("rollback_proof_remote_predecessor_mismatch")
    expected = payload["expected_post_rollback"]
    if not isinstance(expected, Mapping) or expected.get("sha256") != previous_identity.sha256 or expected.get("size_bytes") != previous_identity.size_bytes or expected.get("record_count") != previous_identity.record_count:
        raise GovernanceError("rollback_proof_postcheck_mismatch")
    return payload


def validate_release_manifest_semantics(
    manifest: Mapping[str, Any],
    *,
    baseline_sha256: str,
    baseline_record_count: int,
    candidate_identity: ArtifactIdentity,
    expected_release_manifest_sha256: str,
    expected_rollback_manifest_sha256: str,
    release_records: int,
    excluded_map_battle_records: int,
    source_provenance: Path | Mapping[str, Any] | None,
    review_binding: Path | Mapping[str, Any] | None,
    repair_batch_manifest: Path | Mapping[str, Any] | None,
    mutation_audit: Path | Mapping[str, Any] | None,
    acceptance_evidence: Path | Mapping[str, Any] | None,
    rollback_manifest: Path | Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate relationships between the candidate and every release proof."""

    if not isinstance(manifest, Mapping):
        raise GovernanceError("release_manifest_must_be_object")
    if not isinstance(manifest.get("schema_version"), str) or not manifest["schema_version"].strip():
        raise GovernanceError("release_manifest_schema_version_missing")
    _require_sha256(baseline_sha256, "baseline_sha256")
    _require_sha256(expected_release_manifest_sha256, "release_manifest_sha256")
    _require_sha256(expected_rollback_manifest_sha256, "rollback_manifest_sha256")
    _require_int(baseline_record_count, "baseline_record_count")
    _require_int(release_records, "release_records")
    _require_int(excluded_map_battle_records, "excluded_map_battle_records")
    if candidate_identity.record_count != baseline_record_count:
        raise GovernanceError("source_candidate_record_count_mismatch")
    if manifest.get("source_baseline_sha256") != baseline_sha256:
        raise GovernanceError("release_manifest_source_baseline_mismatch")

    previous = manifest.get("pre_mutation_artifact")
    candidate = manifest.get("repaired_candidate_artifact")
    if not isinstance(previous, Mapping) or not isinstance(candidate, Mapping):
        raise GovernanceError("release_manifest_artifact_identity_missing")
    if previous.get("sha256") != baseline_sha256 or previous.get("record_count") != baseline_record_count:
        raise GovernanceError("release_manifest_previous_artifact_mismatch")
    if candidate.get("sha256") != candidate_identity.sha256 or candidate.get("record_count") != candidate_identity.record_count or candidate.get("size_bytes") != candidate_identity.size_bytes:
        raise GovernanceError("release_manifest_candidate_artifact_mismatch")

    governance = manifest.get("release_governance")
    if not isinstance(governance, Mapping):
        raise GovernanceError("release_manifest_governance_missing")
    required_governance = {
        "source_provenance",
        "review_binding_sha256",
        "repair_batch_manifest_sha256",
        "mutation_audit_sha256",
        "acceptance_evidence_sha256",
        "rollback_manifest_sha256",
        "changed_record_count",
        "review_group_count",
        "excluded_record_count",
        "allowed_asset_names",
    }
    missing = sorted(required_governance - set(governance))
    if missing:
        raise GovernanceError(f"release_governance_missing:{','.join(missing)}")
    if governance["rollback_manifest_sha256"] != expected_rollback_manifest_sha256:
        raise GovernanceError("release_governance_rollback_manifest_mismatch")
    for field in ("changed_record_count", "review_group_count", "excluded_record_count"):
        _require_int(governance[field], f"release_governance_{field}")
    if governance["changed_record_count"] != release_records:
        raise GovernanceError("release_governance_changed_record_count_mismatch")
    if governance["excluded_record_count"] != excluded_map_battle_records:
        raise GovernanceError("release_governance_count_mismatch")
    allowed_assets = governance["allowed_asset_names"]
    if not isinstance(allowed_assets, list) or not allowed_assets or len(set(allowed_assets)) != len(allowed_assets):
        raise GovernanceError("release_governance_asset_inventory_invalid")
    for asset in allowed_assets:
        _safe_filename(asset, "allowed_asset_name")

    provenance_value = source_provenance
    if provenance_value is None:
        provenance_value = governance.get("source_provenance")
    if provenance_value is None:
        raise GovernanceError("release_source_provenance_missing")
    provenance, _provenance_hash, _provenance_path = _load_governance_reference(
        provenance_value, "source_provenance"
    )
    source_path = Path(provenance["source_path"])
    if provenance.get("source_kind") == "local_file":
        if not source_path.is_file():
            raise GovernanceError("release_source_material_missing")
        verify_source_provenance(
            provenance,
            source=source_path,
            expected_sha256=baseline_sha256,
            expected_record_count=baseline_record_count,
        )
    else:
        verify_source_provenance(
            provenance,
            expected_sha256=baseline_sha256,
            expected_record_count=baseline_record_count,
        )
    if governance.get("source_identity_sha256") is not None and governance["source_identity_sha256"] != provenance["source_identity_sha256"]:
        raise GovernanceError("release_source_identity_mismatch")

    review_payload, review_hash, _ = _validate_artifact_reference_hash(
        review_binding,
        expected_sha256=_require_sha256(governance["review_binding_sha256"], "review_binding_sha256"),
        label="review_binding",
    )
    review_payload = validate_review_binding(review_payload)
    repair_payload, repair_hash, _ = _validate_artifact_reference_hash(
        repair_batch_manifest,
        expected_sha256=_require_sha256(governance["repair_batch_manifest_sha256"], "repair_batch_manifest_sha256"),
        label="repair_batch_manifest",
    )
    mutation_payload, mutation_hash, _ = _validate_artifact_reference_hash(
        mutation_audit,
        expected_sha256=_require_sha256(governance["mutation_audit_sha256"], "mutation_audit_sha256"),
        label="mutation_audit",
    )
    acceptance_payload, acceptance_hash, _ = _validate_artifact_reference_hash(
        acceptance_evidence,
        expected_sha256=_require_sha256(governance["acceptance_evidence_sha256"], "acceptance_evidence_sha256"),
        label="acceptance_evidence",
    )
    rollback_payload, rollback_hash, _ = _validate_artifact_reference_hash(
        rollback_manifest,
        expected_sha256=expected_rollback_manifest_sha256,
        label="rollback_manifest",
    )
    _validate_rollback_manifest(
        rollback_payload,
        baseline_sha256=baseline_sha256,
        candidate_sha256=candidate_identity.sha256,
        expected_record_count=baseline_record_count,
    )
    if review_hash != governance["review_binding_sha256"] or repair_hash != governance["repair_batch_manifest_sha256"] or mutation_hash != governance["mutation_audit_sha256"] or acceptance_hash != governance["acceptance_evidence_sha256"] or rollback_hash != expected_rollback_manifest_sha256:
        raise GovernanceError("release_governance_artifact_hash_mismatch")
    _validate_mutation_audit(
        mutation_payload,
        source_sha256=baseline_sha256,
        candidate_sha256=candidate_identity.sha256,
        changed_record_count=release_records,
        review_group_count=governance["review_group_count"],
    )
    _validate_repair_batch_manifest(
        repair_payload,
        source_sha256=baseline_sha256,
        candidate_sha256=candidate_identity.sha256,
        review_binding_sha256=review_hash,
        mutation_audit_sha256=mutation_hash,
        acceptance_evidence_sha256=acceptance_hash,
        changed_record_count=release_records,
        review_group_count=governance["review_group_count"],
    )
    validate_acceptance_evidence(
        acceptance_payload,
        expected_candidate_sha256=candidate_identity.sha256,
        expected_record_count=release_records,
        expected_repair_batch_manifest_sha256=repair_hash,
    )
    if manifest.get("release_manifest_identity_sha256") is not None:
        if manifest["release_manifest_identity_sha256"] != canonical_payload_sha256(
            manifest, without="release_manifest_identity_sha256"
        ):
            raise GovernanceError("release_manifest_identity_hash_mismatch")
    return {
        "source_provenance": provenance,
        "review_binding": review_payload,
        "repair_batch_manifest": repair_payload,
        "mutation_audit": mutation_payload,
        "acceptance_evidence": acceptance_payload,
        "rollback_manifest": rollback_payload,
        "review_binding_sha256": review_hash,
        "repair_batch_manifest_sha256": repair_hash,
        "mutation_audit_sha256": mutation_hash,
        "acceptance_evidence_sha256": acceptance_hash,
        "rollback_manifest_sha256": rollback_hash,
        "governance": dict(governance),
    }


def validate_registry_entry(
    payload: Mapping[str, Any],
    *,
    expected_asset_names: set[str] | None = None,
    candidate_identity: ArtifactIdentity | None = None,
    baseline_sha256: str | None = None,
) -> dict[str, Any]:
    required = {
        "schema_version", "artifact_role", "created_at_utc", "record_count", "uncompressed_byte_count",
        "uncompressed_sha256", "compressed_filename", "compressed_sha256", "baseline_sha256",
        "release_candidate_sha256", "release_manifest_filename", "release_manifest_sha256",
        "rollback_manifest_filename", "rollback_manifest_sha256", "acceptance_evidence_filename",
        "acceptance_evidence_sha256", "source_provenance", "review_binding_sha256",
        "repair_batch_manifest_sha256", "mutation_audit_sha256", "allowed_asset_names",
        "changed_record_count", "review_group_count", "excluded_record_count", "release_records",
        "excluded_map_battle_records",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise GovernanceError(f"registry_entry_missing:{','.join(missing)}")
    _reject_unknown_fields(payload, required, "registry_entry")
    if payload["schema_version"] != CONTENT_MANIFEST_SCHEMA_VERSION or payload["artifact_role"] != "content_release_candidate":
        raise GovernanceError("registry_entry_schema_mismatch")
    for field in (
        "uncompressed_sha256", "compressed_sha256", "baseline_sha256", "release_candidate_sha256",
        "release_manifest_sha256", "rollback_manifest_sha256", "acceptance_evidence_sha256",
        "review_binding_sha256", "repair_batch_manifest_sha256", "mutation_audit_sha256",
    ):
        _require_sha256(payload[field], f"registry_{field}")
    for field in ("record_count", "uncompressed_byte_count", "release_records", "excluded_map_battle_records",
                  "changed_record_count", "review_group_count", "excluded_record_count"):
        _require_int(payload[field], f"registry_{field}", minimum=0 if field != "uncompressed_byte_count" else 1)
    for field in ("compressed_filename", "release_manifest_filename", "rollback_manifest_filename", "acceptance_evidence_filename"):
        _safe_filename(payload[field], f"registry_{field}")
    if candidate_identity is not None:
        if payload["uncompressed_sha256"] != candidate_identity.sha256 or payload["release_candidate_sha256"] != candidate_identity.sha256 or payload["record_count"] != candidate_identity.record_count or payload["uncompressed_byte_count"] != candidate_identity.size_bytes:
            raise GovernanceError("registry_candidate_identity_mismatch")
    if baseline_sha256 is not None and payload["baseline_sha256"] != baseline_sha256:
        raise GovernanceError("registry_baseline_identity_mismatch")
    verify_source_provenance(payload["source_provenance"], expected_sha256=payload["baseline_sha256"])
    assets = payload["allowed_asset_names"]
    if not isinstance(assets, list) or len(set(assets)) != len(assets):
        raise GovernanceError("registry_asset_inventory_invalid")
    for asset in assets:
        _safe_filename(asset, "registry_allowed_asset")
    if expected_asset_names is not None and set(assets) != expected_asset_names:
        raise GovernanceError("registry_asset_inventory_mismatch")
    if payload["changed_record_count"] != payload["release_records"] or payload["excluded_record_count"] != payload["excluded_map_battle_records"]:
        raise GovernanceError("registry_count_relationship_mismatch")
    return dict(payload)


def verify_json_identity(
    path: Path,
    *,
    expected_sha256: str,
    expected_record_count: int,
    label: str,
) -> ArtifactIdentity:
    identity = identify_json(path)
    if identity.sha256 != expected_sha256:
        raise GovernanceError(f"{label}_sha256_mismatch")
    if identity.record_count != expected_record_count:
        raise GovernanceError(f"{label}_record_count_mismatch")
    return identity


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, payload: dict) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write_bytes(path, encoded)


def deterministic_gzip(source: Path, destination: Path) -> str:
    """Create a gzip with a stable header (`mtime=0`, empty original name)."""

    if not source.is_file():
        raise GovernanceError(f"missing_compression_source:{source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=str(destination.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as raw_out:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, compresslevel=9, mtime=0) as compressed:
                with source.open("rb") as raw_in:
                    shutil.copyfileobj(raw_in, compressed, length=CHUNK_SIZE)
            raw_out.flush()
            os.fsync(raw_out.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_file(destination)


def decompress_gzip_to_file(source: Path, destination: Path) -> ArtifactIdentity:
    if not source.is_file():
        raise GovernanceError(f"missing_compressed_artifact:{source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with gzip.open(source, "rb") as compressed, destination.open("wb") as raw:
            shutil.copyfileobj(compressed, raw, length=CHUNK_SIZE)
            raw.flush()
            os.fsync(raw.fileno())
    except (OSError, EOFError) as exc:
        destination.unlink(missing_ok=True)
        raise GovernanceError(f"invalid_gzip_artifact:{source}") from exc
    return identify_json(destination)


def inspect_gzip(source: Path) -> tuple[str, ArtifactIdentity]:
    with tempfile.TemporaryDirectory(prefix="content-artifact-verify-") as temporary_dir:
        output = Path(temporary_dir) / "questions.json"
        identity = decompress_gzip_to_file(source, output)
    return sha256_file(source), identity


def write_sha256sums(path: Path, assets: Iterable[Path]) -> None:
    resolved = sorted((asset for asset in assets), key=lambda item: item.name)
    lines = [f"{sha256_file(asset)}  {asset.name}" for asset in resolved]
    _atomic_write_bytes(path, ("\n".join(lines) + "\n").encode("ascii"))


def verify_sha256sums(path: Path, directory: Path, expected_assets: set[str] | None = None) -> None:
    if not path.is_file():
        raise GovernanceError("missing_sha256sums")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise GovernanceError("unreadable_sha256sums") from exc
    if not lines:
        raise GovernanceError("empty_sha256sums")
    seen: set[str] = set()
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or SHA256_RE.fullmatch(parts[0]) is None:
            raise GovernanceError("malformed_sha256sums")
        expected, name = parts
        _safe_filename(name, "sha256sums_asset_name")
        if name in seen:
            raise GovernanceError("duplicate_sha256sums_asset")
        seen.add(name)
        asset = directory / name
        if not asset.is_file():
            raise GovernanceError(f"missing_release_asset:{name}")
        if sha256_file(asset) != expected:
            raise GovernanceError(f"release_asset_hash_mismatch:{name}")
    if expected_assets is not None and seen != set(expected_assets):
        raise GovernanceError("sha256sums_asset_inventory_mismatch")


def _validate_backup_manifest(payload: dict) -> None:
    required = {
        "schema_version",
        "artifact_role",
        "created_at_utc",
        "source_environment",
        "source_path",
        "record_count",
        "uncompressed_byte_count",
        "uncompressed_sha256",
        "compressed_filename",
        "compressed_sha256",
        "baseline_sha256",
        "source_provenance",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise GovernanceError(f"backup_manifest_missing_fields:{','.join(missing)}")
    _reject_unknown_fields(
        payload,
        required | {"release_candidate_sha256", "release_manifest_sha256", "rollback_manifest_sha256"},
        "backup_manifest",
    )
    if payload.get("schema_version") != CONTENT_MANIFEST_SCHEMA_VERSION:
        raise GovernanceError("backup_manifest_schema_version_mismatch")
    _require_string(payload.get("artifact_role"), "backup_artifact_role")
    _require_string(payload.get("created_at_utc"), "backup_created_at_utc")
    _require_string(payload.get("source_environment"), "backup_source_environment")
    _safe_filename(payload.get("compressed_filename"), "backup_compressed_filename")
    for field in ("uncompressed_sha256", "compressed_sha256", "baseline_sha256"):
        _require_sha256(payload.get(field), f"backup_{field}")
    for field in ("record_count", "uncompressed_byte_count"):
        _require_int(payload.get(field), f"backup_{field}", minimum=0 if field == "record_count" else 1)
    if not isinstance(payload.get("source_provenance"), Mapping):
        raise GovernanceError("backup_source_provenance_invalid")
    verify_source_provenance(
        payload["source_provenance"],
        expected_sha256=payload["uncompressed_sha256"],
        expected_size_bytes=payload["uncompressed_byte_count"],
        expected_record_count=payload["record_count"],
    )
    for field in ("release_candidate_sha256", "release_manifest_sha256", "rollback_manifest_sha256"):
        if payload.get(field) is not None:
            _require_sha256(payload[field], f"backup_{field}")


def load_json_object(path: Path, *, label: str) -> dict:
    if not path.is_file():
        raise GovernanceError(f"missing_{label}:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"malformed_{label}") from exc
    if not isinstance(payload, dict):
        raise GovernanceError(f"{label}_must_be_object")
    return payload


def build_backup_bundle(
    *,
    source: Path,
    output_dir: Path,
    expected_sha256: str,
    expected_record_count: int,
    artifact_role: str,
    source_environment: str,
    source_path_label: str,
    compressed_filename: str = "questions.pre-mutation.json.gz",
    created_at_utc: str | None = None,
    release_candidate_sha256: str | None = None,
    release_manifest_sha256: str | None = None,
    rollback_manifest_sha256: str | None = None,
    source_provenance: Mapping[str, Any] | None = None,
) -> BackupBundle:
    identity = verify_json_identity(
        source,
        expected_sha256=expected_sha256,
        expected_record_count=expected_record_count,
        label="backup_source",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance = (
        build_source_provenance(source)
        if source_provenance is None
        else verify_source_provenance(
            source_provenance,
            source=source,
            expected_sha256=identity.sha256,
            expected_size_bytes=identity.size_bytes,
            expected_record_count=identity.record_count,
        )
    )
    compressed = output_dir / compressed_filename
    compressed_sha256 = deterministic_gzip(source, compressed)
    manifest = {
        "schema_version": CONTENT_MANIFEST_SCHEMA_VERSION,
        "artifact_role": artifact_role,
        "created_at_utc": created_at_utc or utc_now(),
        "source_environment": source_environment,
        "source_path": provenance["source_path"],
        "record_count": identity.record_count,
        "uncompressed_byte_count": identity.size_bytes,
        "uncompressed_sha256": identity.sha256,
        "compressed_filename": compressed.name,
        "compressed_sha256": compressed_sha256,
        "baseline_sha256": expected_sha256,
        "source_provenance": provenance,
        "release_candidate_sha256": release_candidate_sha256,
        "release_manifest_sha256": release_manifest_sha256,
        "rollback_manifest_sha256": rollback_manifest_sha256,
    }
    _validate_backup_manifest(manifest)
    manifest_path = output_dir / "backup-manifest.json"
    write_json(manifest_path, manifest)
    checksums = output_dir / "SHA256SUMS.txt"
    write_sha256sums(checksums, (compressed, manifest_path))
    return BackupBundle(
        source=identity,
        compressed_path=str(compressed),
        compressed_sha256=compressed_sha256,
        manifest_path=str(manifest_path),
        manifest_sha256=sha256_file(manifest_path),
        checksums_path=str(checksums),
    )


def verify_backup_bundle(directory: Path) -> BackupBundle:
    manifest_path = directory / "backup-manifest.json"
    manifest = load_json_object(manifest_path, label="backup_manifest")
    _validate_backup_manifest(manifest)
    compressed = directory / str(manifest["compressed_filename"])
    compressed_sha256, identity = inspect_gzip(compressed)
    if compressed_sha256 != manifest["compressed_sha256"]:
        raise GovernanceError("compressed_backup_sha256_mismatch")
    if identity.sha256 != manifest["uncompressed_sha256"]:
        raise GovernanceError("uncompressed_backup_sha256_mismatch")
    if identity.size_bytes != manifest["uncompressed_byte_count"]:
        raise GovernanceError("uncompressed_backup_size_mismatch")
    if identity.record_count != manifest["record_count"]:
        raise GovernanceError("uncompressed_backup_record_count_mismatch")
    verify_source_provenance(
        manifest["source_provenance"],
        actual_identity=identity,
        expected_sha256=manifest["uncompressed_sha256"],
        expected_size_bytes=manifest["uncompressed_byte_count"],
        expected_record_count=manifest["record_count"],
        verify_source_path=False,
    )
    if manifest["baseline_sha256"] != identity.sha256:
        raise GovernanceError("backup_baseline_sha256_mismatch")
    checksums = directory / "SHA256SUMS.txt"
    verify_sha256sums(checksums, directory, expected_assets={compressed.name, manifest_path.name})
    return BackupBundle(
        source=identity,
        compressed_path=str(compressed),
        compressed_sha256=compressed_sha256,
        manifest_path=str(manifest_path),
        manifest_sha256=sha256_file(manifest_path),
        checksums_path=str(checksums),
    )


def build_release_bundle(
    *,
    candidate: Path,
    release_manifest: Path,
    rollback_manifest: Path,
    output_dir: Path,
    expected_candidate_sha256: str,
    expected_record_count: int,
    expected_release_manifest_sha256: str,
    expected_rollback_manifest_sha256: str,
    baseline_sha256: str,
    release_records: int,
    excluded_map_battle_records: int,
    created_at_utc: str | None = None,
    source_provenance: Path | Mapping[str, Any] | None = None,
    review_binding: Path | Mapping[str, Any] | None = None,
    repair_batch_manifest: Path | Mapping[str, Any] | None = None,
    mutation_audit: Path | Mapping[str, Any] | None = None,
    acceptance_evidence: Path | Mapping[str, Any] | None = None,
) -> ReleaseBundle:
    identity = verify_json_identity(
        candidate,
        expected_sha256=expected_candidate_sha256,
        expected_record_count=expected_record_count,
        label="release_candidate",
    )
    if sha256_file(release_manifest) != expected_release_manifest_sha256:
        raise GovernanceError("release_manifest_sha256_mismatch")
    if sha256_file(rollback_manifest) != expected_rollback_manifest_sha256:
        raise GovernanceError("rollback_manifest_sha256_mismatch")
    release_payload = load_json_object(release_manifest, label="release_manifest")
    load_json_object(rollback_manifest, label="rollback_manifest")
    semantic = validate_release_manifest_semantics(
        release_payload,
        baseline_sha256=baseline_sha256,
        baseline_record_count=expected_record_count,
        candidate_identity=identity,
        expected_release_manifest_sha256=expected_release_manifest_sha256,
        expected_rollback_manifest_sha256=expected_rollback_manifest_sha256,
        release_records=release_records,
        excluded_map_battle_records=excluded_map_battle_records,
        source_provenance=source_provenance,
        review_binding=review_binding,
        repair_batch_manifest=repair_batch_manifest,
        mutation_audit=mutation_audit,
        acceptance_evidence=acceptance_evidence,
        rollback_manifest=rollback_manifest,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    compressed = output_dir / "questions.repaired-candidate.json.gz"
    compressed_sha256 = deterministic_gzip(candidate, compressed)
    copied_release_manifest = output_dir / "content-release-manifest.json"
    copied_rollback_manifest = output_dir / "content-rollback-manifest.json"
    shutil.copyfile(release_manifest, copied_release_manifest)
    shutil.copyfile(rollback_manifest, copied_rollback_manifest)
    if sha256_file(copied_release_manifest) != expected_release_manifest_sha256:
        raise GovernanceError("copied_release_manifest_sha256_mismatch")
    if sha256_file(copied_rollback_manifest) != expected_rollback_manifest_sha256:
        raise GovernanceError("copied_rollback_manifest_sha256_mismatch")
    acceptance_reference = acceptance_evidence
    if acceptance_reference is None:
        raise GovernanceError("acceptance_evidence_artifact_missing")
    if isinstance(acceptance_reference, (str, Path)):
        acceptance_source = Path(acceptance_reference)
        if not acceptance_source.is_file():
            raise GovernanceError("missing_acceptance_evidence")
        copied_acceptance = output_dir / _safe_filename(acceptance_source.name, "acceptance_evidence_filename")
        shutil.copyfile(acceptance_source, copied_acceptance)
    else:
        copied_acceptance = output_dir / "acceptance-evidence.json"
        write_json(copied_acceptance, dict(acceptance_reference))
    acceptance_sha256 = sha256_file(copied_acceptance)
    if acceptance_sha256 != semantic["acceptance_evidence_sha256"]:
        raise GovernanceError("copied_acceptance_evidence_sha256_mismatch")
    expected_asset_names = {
        compressed.name,
        copied_release_manifest.name,
        copied_rollback_manifest.name,
        copied_acceptance.name,
        "content-registry-entry.json",
        "SHA256SUMS.txt",
    }
    if set(semantic["governance"]["allowed_asset_names"]) != expected_asset_names:
        raise GovernanceError("release_governance_asset_inventory_mismatch")

    registry_entry = {
        "schema_version": CONTENT_MANIFEST_SCHEMA_VERSION,
        "artifact_role": "content_release_candidate",
        "created_at_utc": created_at_utc or utc_now(),
        "record_count": identity.record_count,
        "uncompressed_byte_count": identity.size_bytes,
        "uncompressed_sha256": identity.sha256,
        "compressed_filename": compressed.name,
        "compressed_sha256": compressed_sha256,
        "baseline_sha256": baseline_sha256,
        "release_candidate_sha256": expected_candidate_sha256,
        "release_manifest_filename": copied_release_manifest.name,
        "release_manifest_sha256": expected_release_manifest_sha256,
        "rollback_manifest_filename": copied_rollback_manifest.name,
        "rollback_manifest_sha256": expected_rollback_manifest_sha256,
        "acceptance_evidence_filename": copied_acceptance.name,
        "acceptance_evidence_sha256": acceptance_sha256,
        "source_provenance": semantic["source_provenance"],
        "review_binding_sha256": semantic["review_binding_sha256"],
        "repair_batch_manifest_sha256": semantic["repair_batch_manifest_sha256"],
        "mutation_audit_sha256": semantic["mutation_audit_sha256"],
        "allowed_asset_names": [
            compressed.name,
            copied_release_manifest.name,
            copied_rollback_manifest.name,
            copied_acceptance.name,
            "content-registry-entry.json",
            "SHA256SUMS.txt",
        ],
        "changed_record_count": release_records,
        "review_group_count": semantic["governance"]["review_group_count"],
        "excluded_record_count": excluded_map_battle_records,
        "release_records": release_records,
        "excluded_map_battle_records": excluded_map_battle_records,
    }
    registry_entry_path = output_dir / "content-registry-entry.json"
    validate_registry_entry(
        registry_entry,
        expected_asset_names=expected_asset_names,
        candidate_identity=identity,
        baseline_sha256=baseline_sha256,
    )
    write_json(registry_entry_path, registry_entry)
    checksums = output_dir / "SHA256SUMS.txt"
    write_sha256sums(
        checksums,
        (compressed, copied_release_manifest, copied_rollback_manifest, copied_acceptance, registry_entry_path),
    )
    return ReleaseBundle(
        candidate=identity,
        compressed_path=str(compressed),
        compressed_sha256=compressed_sha256,
        release_manifest_path=str(copied_release_manifest),
        rollback_manifest_path=str(copied_rollback_manifest),
        acceptance_evidence_path=str(copied_acceptance),
        acceptance_evidence_sha256=acceptance_sha256,
        registry_entry_path=str(registry_entry_path),
        registry_entry_sha256=sha256_file(registry_entry_path),
        checksums_path=str(checksums),
    )


class LocalReleaseRegistry:
    """Filesystem-backed test double for an immutable private Release."""

    def __init__(self, root: Path, *, visibility: str, tag: str):
        self.root = root
        self._visibility = visibility
        self._tag = tag

    @property
    def visibility(self) -> str:
        return self._visibility

    @property
    def tag(self) -> str:
        return self._tag

    @property
    def release_dir(self) -> Path:
        return self.root / self._tag

    def upload(self, paths: Iterable[Path]) -> None:
        self.release_dir.mkdir(parents=True, exist_ok=True)
        for path in paths:
            destination = self.release_dir / path.name
            if destination.exists():
                raise GovernanceError(f"immutable_release_asset_exists:{path.name}")
            shutil.copyfile(path, destination)

    def asset_exists(self, name: str) -> bool:
        return (self.release_dir / name).is_file()

    def release_exists(self) -> bool:
        return self.release_dir.is_dir()

    def inventory(self) -> dict[str, dict[str, Any]]:
        if not self.release_dir.is_dir():
            return {}
        return {
            path.name: {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
            for path in sorted(self.release_dir.iterdir())
            if path.is_file()
        }

    def download(self, name: str, destination: Path) -> Path:
        source = self.release_dir / name
        if not source.is_file():
            raise GovernanceError(f"missing_release_asset:{name}")
        destination.mkdir(parents=True, exist_ok=True)
        output = destination / name
        shutil.copyfile(source, output)
        return output


class GitHubReleaseRegistry:
    """`gh`-backed adapter. It never creates repositories.

    Remote Release creation/upload requires the explicit Phase-specific gate.
    Authentication is delegated to the secure `gh` credential store; token
    values are never accepted as arguments or printed by this module.
    """

    def __init__(
        self,
        repository: str,
        *,
        tag: str,
        execute_remote: bool = False,
        owner_gate: str = "",
    ):
        self.repository = repository
        self._tag = tag
        self.execute_remote = execute_remote
        self.owner_gate = owner_gate
        self._visibility: str | None = None

    def _run(self, arguments: list[str], *, capture: bool = True) -> str:
        completed = subprocess.run(
            ["gh", *arguments],
            check=False,
            capture_output=capture,
            text=True,
        )
        if completed.returncode != 0:
            raise GovernanceError(f"github_command_failed:{arguments[0]}")
        return completed.stdout.strip() if capture else ""

    def inspect(self) -> None:
        raw = self._run(["repo", "view", self.repository, "--json", "visibility,nameWithOwner"])
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GovernanceError("github_repo_metadata_malformed") from exc
        self._visibility = str(payload.get("visibility", "")).upper()
        if self._visibility != PRIVATE_VISIBILITY:
            raise GovernanceError("content_repo_visibility_not_private")

    @property
    def visibility(self) -> str:
        if self._visibility is None:
            self.inspect()
        return self._visibility or ""

    @property
    def tag(self) -> str:
        return self._tag

    def prepare_release(self, *, title: str, notes: str) -> None:
        self.inspect()
        if not self.execute_remote or self.owner_gate != REMOTE_EXECUTION_GATE:
            raise GovernanceError("github_remote_execution_not_authorized")
        completed = subprocess.run(
            ["gh", "release", "view", self._tag, "--repo", self.repository, "--json", "tagName,name,isDraft,isPrerelease"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            self._run(
                [
                    "release",
                    "create",
                    self._tag,
                    "--repo",
                    self.repository,
                    "--title",
                    title,
                    "--notes",
                    notes,
                ]
            )
        else:
            try:
                metadata = json.loads(completed.stdout)
                if metadata.get("tagName") != self._tag:
                    raise GovernanceError("wrong_release_tag")
                if metadata.get("isDraft") is True or metadata.get("isPrerelease") is True:
                    raise GovernanceError("github_release_metadata_not_final")
                if metadata.get("name") not in {self._tag, title}:
                    raise GovernanceError("github_release_metadata_mismatch")
            except json.JSONDecodeError as exc:
                raise GovernanceError("github_release_metadata_malformed") from exc

    def upload(self, paths: Iterable[Path]) -> None:
        if not self.execute_remote or self.owner_gate != REMOTE_EXECUTION_GATE:
            raise GovernanceError("github_remote_execution_not_authorized")
        if self.visibility != PRIVATE_VISIBILITY:
            raise GovernanceError("content_repo_visibility_not_private")
        self._run(
            [
                "release",
                "upload",
                self._tag,
                *(str(path) for path in paths),
                "--repo",
                self.repository,
            ]
        )

    def asset_exists(self, name: str) -> bool:
        return name in self.inventory()

    def release_exists(self) -> bool:
        completed = subprocess.run(
            ["gh", "release", "view", self._tag, "--repo", self.repository, "--json", "tagName"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return False
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise GovernanceError("github_release_metadata_malformed") from exc
        if payload.get("tagName") != self._tag:
            raise GovernanceError("wrong_release_tag")
        return True

    def inventory(self) -> dict[str, dict[str, Any]]:
        raw = self._run(
            [
                "release",
                "view",
                self._tag,
                "--repo",
                self.repository,
                "--json",
                "assets,tagName,name,isDraft,isPrerelease",
            ]
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GovernanceError("github_release_metadata_malformed") from exc
        if payload.get("tagName") != self._tag:
            raise GovernanceError("wrong_release_tag")
        if payload.get("isDraft") is True or payload.get("isPrerelease") is True:
            raise GovernanceError("github_release_metadata_not_final")
        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise GovernanceError("github_release_assets_malformed")
        inventory: dict[str, dict[str, Any]] = {}
        with tempfile.TemporaryDirectory(prefix="content-remote-inventory-") as temporary_dir:
            for asset in assets:
                if not isinstance(asset, Mapping) or not isinstance(asset.get("name"), str):
                    raise GovernanceError("github_release_asset_metadata_malformed")
                name = _safe_filename(asset["name"], "remote_asset_name")
                downloaded = self.download(name, Path(temporary_dir))
                inventory[name] = {"sha256": sha256_file(downloaded), "size_bytes": downloaded.stat().st_size}
        return inventory

    def download(self, name: str, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        self._run(
            [
                "release",
                "download",
                self._tag,
                "--repo",
                self.repository,
                "--pattern",
                name,
                "--dir",
                str(destination),
            ]
        )
        output = destination / name
        if not output.is_file():
            raise GovernanceError(f"missing_release_asset:{name}")
        return output


def remote_asset_inventory_sha256(inventory: Mapping[str, Mapping[str, Any]]) -> str:
    normalized = {
        name: {"sha256": value.get("sha256"), "size_bytes": value.get("size_bytes")}
        for name, value in sorted(inventory.items())
    }
    return canonical_payload_sha256(normalized)


def preflight_remote_assets(registry: ReleaseRegistry, paths: Iterable[Path]) -> str:
    """Allow only an absent or byte-identical immutable remote target."""

    if registry.visibility.upper() != PRIVATE_VISIBILITY:
        raise GovernanceError("content_repo_visibility_not_private")
    expected: dict[str, dict[str, Any]] = {}
    for path in paths:
        name = _safe_filename(path.name, "expected_remote_asset")
        if not path.is_file():
            raise GovernanceError(f"missing_expected_remote_asset:{name}")
        expected[name] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    if not expected:
        raise GovernanceError("empty_remote_asset_inventory")
    release_exists = getattr(registry, "release_exists", None)
    if callable(release_exists) and not release_exists():
        return "ABSENT"
    current = registry.inventory()
    if not current:
        if callable(release_exists) and release_exists():
            raise GovernanceError("remote_release_asset_inventory_missing")
        return "ABSENT"
    if set(current) != set(expected):
        raise GovernanceError("remote_asset_inventory_drift")
    for name, identity in expected.items():
        if current[name] != identity:
            raise GovernanceError(f"remote_asset_predecessor_drift:{name}")
    return "EXACT_BYTE_IDENTICAL_WITH_EXPECTED_METADATA"


def upload_immutable_release(registry: ReleaseRegistry, paths: Iterable[Path]) -> str:
    paths = list(paths)
    state = preflight_remote_assets(registry, paths)
    if state == "ABSENT":
        registry.upload(paths)
        after = preflight_remote_assets(registry, paths)
        if after != "EXACT_BYTE_IDENTICAL_WITH_EXPECTED_METADATA":
            raise GovernanceError("remote_post_upload_inventory_mismatch")
    return state


def verify_release_round_trip(
    *,
    registry: ReleaseRegistry,
    source: Path,
    local_compressed: Path,
    expected_source_sha256: str,
    expected_record_count: int,
    expected_tag: str,
    download_dir: Path,
    expected_assets: Iterable[Path] | None = None,
) -> RoundTripReceipt:
    if registry.visibility.upper() != PRIVATE_VISIBILITY:
        raise GovernanceError("content_repo_visibility_not_private")
    if registry.tag != expected_tag:
        raise GovernanceError("wrong_release_tag")
    inventory = registry.inventory()
    if local_compressed.name not in inventory:
        raise GovernanceError(f"missing_release_asset:{local_compressed.name}")
    expected_asset_names = (
        {_safe_filename(path.name, "expected_round_trip_asset") for path in expected_assets}
        if expected_assets is not None
        else set(inventory)
    )
    if set(inventory) != expected_asset_names:
        raise GovernanceError("remote_round_trip_asset_inventory_mismatch")

    source_identity = verify_json_identity(
        source,
        expected_sha256=expected_source_sha256,
        expected_record_count=expected_record_count,
        label="round_trip_source",
    )
    local_compressed_sha, local_identity = inspect_gzip(local_compressed)
    if local_identity.sha256 != source_identity.sha256 or local_identity.record_count != source_identity.record_count:
        raise GovernanceError("local_backup_uncompressed_identity_mismatch")

    remote = registry.download(local_compressed.name, download_dir)
    remote_compressed_sha, remote_identity = inspect_gzip(remote)
    if remote_compressed_sha != local_compressed_sha:
        raise GovernanceError("remote_redownload_compressed_sha256_mismatch")
    if remote_identity.sha256 != source_identity.sha256:
        raise GovernanceError("remote_redownload_uncompressed_sha256_mismatch")
    if remote_identity.record_count != source_identity.record_count:
        raise GovernanceError("remote_redownload_record_count_mismatch")

    for name in sorted(expected_asset_names - {local_compressed.name}):
        downloaded = registry.download(name, download_dir)
        if sha256_file(downloaded) != inventory[name]["sha256"] or downloaded.stat().st_size != inventory[name]["size_bytes"]:
            raise GovernanceError(f"remote_asset_round_trip_mismatch:{name}")

    return RoundTripReceipt(
        source_uncompressed_sha256=source_identity.sha256,
        local_uncompressed_sha256=local_identity.sha256,
        remote_uncompressed_sha256=remote_identity.sha256,
        record_count=source_identity.record_count,
        repository_visibility=registry.visibility.upper(),
        release_tag=registry.tag,
        remote_asset_name=remote.name,
        remote_asset_sha256=remote_compressed_sha,
        remote_asset_inventory_sha256=remote_asset_inventory_sha256(inventory),
        remote_asset_count=len(inventory),
        offsite_backup_verified=True,
    )


def write_round_trip_receipt(path: Path, receipt: RoundTripReceipt) -> None:
    write_json(path, asdict(receipt))


def verify_round_trip_receipt(
    path: Path,
    *,
    expected_sha256: str,
    expected_record_count: int,
    expected_tag: str,
    expected_asset_inventory_sha256: str | None = None,
    expected_asset_count: int | None = None,
) -> dict:
    payload = load_json_object(path, label="offsite_backup_receipt")
    required_matches = (
        payload.get("source_uncompressed_sha256") == expected_sha256,
        payload.get("local_uncompressed_sha256") == expected_sha256,
        payload.get("remote_uncompressed_sha256") == expected_sha256,
        payload.get("record_count") == expected_record_count,
        str(payload.get("repository_visibility", "")).upper() == PRIVATE_VISIBILITY,
        payload.get("release_tag") == expected_tag,
        payload.get("offsite_backup_verified") is True,
        SHA256_RE.fullmatch(str(payload.get("remote_asset_sha256", ""))) is not None,
        isinstance(payload.get("remote_asset_name"), str) and bool(payload.get("remote_asset_name")),
        SHA256_RE.fullmatch(str(payload.get("remote_asset_inventory_sha256", ""))) is not None,
        isinstance(payload.get("remote_asset_count"), int) and payload.get("remote_asset_count", 0) > 0,
    )
    if expected_asset_inventory_sha256 is not None:
        required_matches += (payload.get("remote_asset_inventory_sha256") == expected_asset_inventory_sha256,)
    if expected_asset_count is not None:
        required_matches += (payload.get("remote_asset_count") == expected_asset_count,)
    if not all(required_matches):
        raise GovernanceError("offsite_backup_receipt_not_verified")
    return payload


def _verify_manifest(path: Path, expected_sha256: str, label: str) -> dict:
    if not path.is_file():
        raise GovernanceError(f"missing_{label}")
    if sha256_file(path) != expected_sha256:
        raise GovernanceError(f"{label}_sha256_mismatch")
    return load_json_object(path, label=label)


def verify_local_baseline_backup(
    backup: Path,
    *,
    expected_sha256: str,
    expected_record_count: int,
) -> ArtifactIdentity:
    if not backup.is_file():
        raise GovernanceError("missing_baseline_backup")
    if backup.suffix.lower() == ".gz":
        _compressed_sha, identity = inspect_gzip(backup)
        if identity.sha256 != expected_sha256:
            raise GovernanceError("baseline_backup_sha256_mismatch")
        if identity.record_count != expected_record_count:
            raise GovernanceError("baseline_backup_record_count_mismatch")
        return identity
    return verify_json_identity(
        backup,
        expected_sha256=expected_sha256,
        expected_record_count=expected_record_count,
        label="baseline_backup",
    )


def verify_publish_gates(
    *,
    live: Path,
    candidate: Path,
    local_baseline_backup: Path,
    offsite_receipt: Path,
    release_manifest: Path,
    expected_live_sha256: str,
    expected_candidate_sha256: str,
    expected_release_manifest_sha256: str,
    expected_record_count: int,
    expected_backup_tag: str,
    rollback_manifest: Path | Mapping[str, Any] | None = None,
    rollback_proof: Path | Mapping[str, Any] | None = None,
    source_provenance: Path | Mapping[str, Any] | None = None,
    review_binding: Path | Mapping[str, Any] | None = None,
    repair_batch_manifest: Path | Mapping[str, Any] | None = None,
    mutation_audit: Path | Mapping[str, Any] | None = None,
    acceptance_evidence: Path | Mapping[str, Any] | None = None,
) -> dict:
    live_identity = verify_json_identity(
        live,
        expected_sha256=expected_live_sha256,
        expected_record_count=expected_record_count,
        label="live_baseline",
    )
    candidate_identity = verify_json_identity(
        candidate,
        expected_sha256=expected_candidate_sha256,
        expected_record_count=expected_record_count,
        label="candidate",
    )
    backup_identity = verify_local_baseline_backup(
        local_baseline_backup,
        expected_sha256=expected_live_sha256,
        expected_record_count=expected_record_count,
    )
    receipt = verify_round_trip_receipt(
        offsite_receipt,
        expected_sha256=expected_live_sha256,
        expected_record_count=expected_record_count,
        expected_tag=expected_backup_tag,
    )
    release_payload = _verify_manifest(release_manifest, expected_release_manifest_sha256, "release_manifest")
    if rollback_manifest is None:
        raise GovernanceError("rollback_manifest_required_for_publish")
    _rollback_payload, rollback_manifest_sha256, _rollback_path = _load_governance_reference(
        rollback_manifest, "rollback_manifest"
    )
    semantic = validate_release_manifest_semantics(
        release_payload,
        baseline_sha256=live_identity.sha256,
        baseline_record_count=live_identity.record_count,
        candidate_identity=candidate_identity,
        expected_release_manifest_sha256=expected_release_manifest_sha256,
        expected_rollback_manifest_sha256=rollback_manifest_sha256,
        release_records=release_payload.get("release_governance", {}).get("changed_record_count", 0),
        excluded_map_battle_records=release_payload.get("release_governance", {}).get("excluded_record_count", 0),
        source_provenance=source_provenance,
        review_binding=review_binding,
        repair_batch_manifest=repair_batch_manifest,
        mutation_audit=mutation_audit,
        acceptance_evidence=acceptance_evidence,
        rollback_manifest=rollback_manifest,
    )
    proof = validate_rollback_proof(
        rollback_proof if rollback_proof is not None else {},
        live=live,
        baseline=live,
        candidate=candidate,
        rollback_manifest=rollback_manifest,
        expected_remote_predecessor={
            "source_sha256": expected_live_sha256,
            "asset_sha256": receipt["remote_asset_sha256"],
            "receipt_sha256": sha256_file(offsite_receipt),
        },
    )
    return {
        "live": asdict(live_identity),
        "candidate": asdict(candidate_identity),
        "local_baseline_backup": asdict(backup_identity),
        "offsite_backup_verified": True,
        "release_manifest_verified": True,
        "semantic_manifest_verified": True,
        "rollback_proof_verified": True,
        "release_governance": semantic["governance"],
        "rollback_proof_sha256": proof["proof_sha256"],
    }


def _copy_and_fsync(source: Path, destination: Path) -> None:
    with source.open("rb") as raw_in, destination.open("xb") as raw_out:
        shutil.copyfileobj(raw_in, raw_out, length=CHUNK_SIZE)
        raw_out.flush()
        os.fsync(raw_out.fileno())


def fsync_directory(path: Path) -> None:
    """Fsync a directory, or fail closed when the host cannot provide it.

    The governed Production runner targets Linux. Windows local tests inject a
    simulation hook because CPython/Win32 does not expose durable directory
    fsync with the same semantics.
    """

    if not hasattr(os, "O_DIRECTORY"):
        raise GovernanceError("directory_fsync_unsupported_on_host")
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def simulated_directory_fsync(path: Path) -> None:
    """Local-only durability barrier used inside disposable test directories."""

    marker = path / ".directory-fsync-simulation"
    try:
        with marker.open("wb") as handle:
            handle.write(b"directory-fsync-simulation\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        marker.unlink(missing_ok=True)


def atomic_replace_verified(
    *,
    source: Path,
    live: Path,
    expected_current_sha256: str,
    expected_current_record_count: int,
    expected_source_sha256: str,
    expected_source_record_count: int,
    directory_fsync: Callable[[Path], None] = fsync_directory,
    copy_and_fsync: Callable[[Path, Path], None] = _copy_and_fsync,
    replace: Callable[[Path, Path], None] = os.replace,
) -> ArtifactIdentity:
    verify_json_identity(
        live,
        expected_sha256=expected_current_sha256,
        expected_record_count=expected_current_record_count,
        label="atomic_current",
    )
    verify_json_identity(
        source,
        expected_sha256=expected_source_sha256,
        expected_record_count=expected_source_record_count,
        label="atomic_source",
    )
    source_stat = live.stat()
    fd, temporary_name = tempfile.mkstemp(prefix=f".{live.name}.stage-", dir=str(live.parent))
    os.close(fd)
    stage = Path(temporary_name)
    stage.unlink()
    try:
        try:
            copy_and_fsync(source, stage)
            os.chmod(stage, stat.S_IMODE(source_stat.st_mode))
            if hasattr(os, "chown"):
                os.chown(stage, source_stat.st_uid, source_stat.st_gid)
        except Exception as exc:
            raise GovernanceError("stage_copy_or_file_fsync_failed") from exc
        staged = verify_json_identity(
            stage,
            expected_sha256=expected_source_sha256,
            expected_record_count=expected_source_record_count,
            label="staged_candidate",
        )
        try:
            replace(stage, live)
        except Exception as exc:
            raise GovernanceError("atomic_replace_failed") from exc
        try:
            directory_fsync(live.parent)
        except Exception as exc:
            raise GovernanceError("directory_fsync_failed") from exc
        final = verify_json_identity(
            live,
            expected_sha256=expected_source_sha256,
            expected_record_count=expected_source_record_count,
            label="post_replace",
        )
        if final.sha256 != staged.sha256:
            raise GovernanceError("post_replace_identity_changed")
        return final
    finally:
        stage.unlink(missing_ok=True)


def publish_content(
    *,
    live: Path,
    candidate: Path,
    local_baseline_backup: Path,
    offsite_receipt: Path,
    release_manifest: Path,
    expected_live_sha256: str,
    expected_candidate_sha256: str,
    expected_release_manifest_sha256: str,
    expected_record_count: int,
    expected_backup_tag: str,
    execute: bool,
    owner_gate: str,
    directory_fsync: Callable[[Path], None] = fsync_directory,
    rollback_manifest: Path | Mapping[str, Any] | None = None,
    rollback_proof: Path | Mapping[str, Any] | None = None,
    source_provenance: Path | Mapping[str, Any] | None = None,
    review_binding: Path | Mapping[str, Any] | None = None,
    repair_batch_manifest: Path | Mapping[str, Any] | None = None,
    mutation_audit: Path | Mapping[str, Any] | None = None,
    acceptance_evidence: Path | Mapping[str, Any] | None = None,
) -> dict:
    evidence = verify_publish_gates(
        live=live,
        candidate=candidate,
        local_baseline_backup=local_baseline_backup,
        offsite_receipt=offsite_receipt,
        release_manifest=release_manifest,
        expected_live_sha256=expected_live_sha256,
        expected_candidate_sha256=expected_candidate_sha256,
        expected_release_manifest_sha256=expected_release_manifest_sha256,
        expected_record_count=expected_record_count,
        expected_backup_tag=expected_backup_tag,
        rollback_manifest=rollback_manifest,
        rollback_proof=rollback_proof,
        source_provenance=source_provenance,
        review_binding=review_binding,
        repair_batch_manifest=repair_batch_manifest,
        mutation_audit=mutation_audit,
        acceptance_evidence=acceptance_evidence,
    )
    evidence["mode"] = "dry-run"
    if not execute:
        return evidence
    if owner_gate != PUBLISH_EXECUTION_GATE:
        raise GovernanceError("production_content_publish_not_authorized")
    final = atomic_replace_verified(
        source=candidate,
        live=live,
        expected_current_sha256=expected_live_sha256,
        expected_current_record_count=expected_record_count,
        expected_source_sha256=expected_candidate_sha256,
        expected_source_record_count=expected_record_count,
        directory_fsync=directory_fsync,
    )
    evidence["mode"] = "execute"
    evidence["final"] = asdict(final)
    return evidence


def rollback_content(
    *,
    live: Path,
    baseline: Path,
    rollback_manifest: Path,
    expected_current_sha256: str,
    expected_baseline_sha256: str,
    expected_rollback_manifest_sha256: str,
    expected_record_count: int,
    execute: bool,
    owner_gate: str,
    directory_fsync: Callable[[Path], None] = fsync_directory,
    rollback_proof: Path | Mapping[str, Any] | None = None,
) -> dict:
    current = verify_json_identity(
        live,
        expected_sha256=expected_current_sha256,
        expected_record_count=expected_record_count,
        label="rollback_current",
    )
    baseline_identity = verify_json_identity(
        baseline,
        expected_sha256=expected_baseline_sha256,
        expected_record_count=expected_record_count,
        label="rollback_artifact",
    )
    _verify_manifest(rollback_manifest, expected_rollback_manifest_sha256, "rollback_manifest")
    if rollback_proof is None:
        raise GovernanceError("rollback_proof_required")
    proof = validate_rollback_proof(
        rollback_proof,
        live=live,
        baseline=baseline,
        candidate=live,
        rollback_manifest=rollback_manifest,
    )
    evidence = {
        "current": asdict(current),
        "baseline": asdict(baseline_identity),
        "rollback_manifest_verified": True,
        "mode": "dry-run",
        "rollback_proof_verified": True,
        "rollback_proof_sha256": proof["proof_sha256"],
    }
    if not execute:
        return evidence
    if owner_gate != ROLLBACK_EXECUTION_GATE:
        raise GovernanceError("production_content_rollback_not_authorized")
    final = atomic_replace_verified(
        source=baseline,
        live=live,
        expected_current_sha256=expected_current_sha256,
        expected_current_record_count=expected_record_count,
        expected_source_sha256=expected_baseline_sha256,
        expected_source_record_count=expected_record_count,
        directory_fsync=directory_fsync,
    )
    evidence["mode"] = "execute"
    evidence["final"] = asdict(final)
    return evidence
