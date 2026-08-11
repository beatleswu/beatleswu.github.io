"""Governed content-only promotion primitives.

This module deliberately has two small responsibilities:

* validate an already-built PR318 content bundle locally; and
* run the reviewed, host-side promotion helper on a Production machine.

The remote mode is intentionally self-contained (standard library only) so
the exact helper can be uploaded through the existing bounded ReleaseTooling
transport.  It resolves the live target from Docker's actual named-volume
mount, never from a guessed host path, and only permits the canonical
``questions.json`` content target.

No repair decisions are generated here.  No application image, container,
static asset, or runtime semantics are changed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


CHUNK_SIZE = 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SAFE_VOLUME_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
REQUIRED_SURFACES = {
    "sgf_engine_native",
    "rating_test_server",
    "map_battle_server",
    "main_practice_client",
    "daily_challenge_client",
    "friend_challenge_client_then_server_trust",
}


class ContentPublishError(RuntimeError):
    """A fail-closed content transport, identity, or promotion error."""


@dataclass(frozen=True)
class FileIdentity:
    path: str
    size_bytes: int
    sha256: str
    record_count: int


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        raise ContentPublishError(f"artifact_unreadable:{path}") from exc
    return digest.hexdigest()


def json_record_count(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentPublishError(f"malformed_or_unreadable_json:{path}") from exc
    if not isinstance(payload, list):
        raise ContentPublishError(f"questions_root_must_be_array:{path}")
    return len(payload)


def identify_file(path: Path, *, record_count: bool = True) -> FileIdentity:
    if not path.is_file() or path.is_symlink():
        raise ContentPublishError(f"regular_file_required:{path}")
    return FileIdentity(
        path=str(path.resolve()),
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        record_count=json_record_count(path) if record_count else -1,
    )


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ContentPublishError(f"{label}_must_be_lowercase_sha256")
    return value


def _require_nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContentPublishError(f"{label}_must_be_non_empty_string")
    return value


def _require_int(value: Any, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContentPublishError(f"{label}_must_be_integer")
    return value


def _canonical_json(payload: Mapping[str, Any], *, without: str | None = None) -> bytes:
    value = dict(payload)
    if without is not None:
        value.pop(without, None)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContentPublishError("governance_payload_not_canonicalizable") from exc


def canonical_payload_sha256(payload: Mapping[str, Any], *, without: str | None = None) -> str:
    return hashlib.sha256(_canonical_json(payload, without=without)).hexdigest()


def load_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ContentPublishError(f"missing_{label}:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentPublishError(f"malformed_{label}") from exc
    if not isinstance(payload, dict):
        raise ContentPublishError(f"{label}_must_be_object")
    return payload


def safe_filename(value: Any, label: str) -> str:
    name = _require_nonempty(value, label)
    if name in {".", ".."} or Path(name).name != name or "/" in name or "\\" in name:
        raise ContentPublishError(f"{label}_must_be_safe_filename")
    return name


def safe_release_id(value: str) -> str:
    if SAFE_RELEASE_ID_RE.fullmatch(value or "") is None:
        raise ContentPublishError("release_id_invalid")
    return value


def _verify_sha256sums(bundle_dir: Path, expected_assets: set[str], expected_package_sha256: str) -> str:
    checksums_path = bundle_dir / "SHA256SUMS.txt"
    if not checksums_path.is_file() or checksums_path.is_symlink():
        raise ContentPublishError("missing_SHA256SUMS")
    package_sha256 = sha256_file(checksums_path)
    if package_sha256 != _require_sha256(expected_package_sha256, "release_package_sha256"):
        raise ContentPublishError("release_package_sha256_mismatch")
    try:
        lines = checksums_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ContentPublishError("malformed_SHA256SUMS") from exc
    observed: dict[str, str] = {}
    for line in lines:
        if not line or "  " not in line:
            raise ContentPublishError("malformed_SHA256SUMS")
        digest, filename = line.split("  ", 1)
        digest = _require_sha256(digest, "checksum")
        filename = safe_filename(filename, "checksum_filename")
        if filename in observed:
            raise ContentPublishError("duplicate_checksum_filename")
        observed[filename] = digest
    if set(observed) != expected_assets:
        raise ContentPublishError("SHA256SUMS_asset_inventory_mismatch")
    for filename, expected in observed.items():
        path = bundle_dir / filename
        if not path.is_file() or path.is_symlink():
            raise ContentPublishError(f"missing_release_asset:{filename}")
        if sha256_file(path) != expected:
            raise ContentPublishError(f"release_asset_sha256_mismatch:{filename}")
    return package_sha256


def _decompress_identity(source: Path) -> FileIdentity:
    with tempfile.TemporaryDirectory(prefix="content-publish-verify-") as temporary:
        destination = Path(temporary) / "questions.json"
        try:
            with gzip.open(source, "rb") as compressed, destination.open("wb") as raw:
                shutil.copyfileobj(compressed, raw, length=CHUNK_SIZE)
                raw.flush()
                os.fsync(raw.fileno())
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            raise ContentPublishError("invalid_candidate_gzip") from exc
        return identify_file(destination)


def _validate_source_provenance(payload: Mapping[str, Any], expected_sha256: str, expected_count: int) -> None:
    required = {
        "source_kind",
        "source_repo_id",
        "source_commit_or_snapshot_id",
        "source_path",
        "source_sha256",
        "source_size_bytes",
        "source_record_count",
        "source_status",
        "source_identity_sha256",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ContentPublishError(f"source_provenance_missing:{','.join(missing)}")
    if payload["source_kind"] != "immutable_snapshot":
        raise ContentPublishError("source_provenance_not_immutable_snapshot")
    if payload["source_status"] not in {"IMMUTABLE_SNAPSHOT_BYTE_VERIFIED", "RELEASE_ASSET_BYTE_VERIFIED"}:
        raise ContentPublishError("source_provenance_status_not_verified")
    if _require_sha256(payload["source_sha256"], "source_sha256") != expected_sha256:
        raise ContentPublishError("source_provenance_sha256_mismatch")
    if payload.get("source_snapshot_sha256") != expected_sha256:
        raise ContentPublishError("source_provenance_snapshot_mismatch")
    if payload.get("source_record_count") != expected_count:
        raise ContentPublishError("source_provenance_record_count_mismatch")
    if not isinstance(payload.get("source_size_bytes"), int) or payload["source_size_bytes"] <= 0:
        raise ContentPublishError("source_provenance_size_invalid")
    _require_nonempty(payload.get("source_commit_or_snapshot_id"), "source_commit_or_snapshot_id")
    _require_nonempty(payload.get("source_path"), "source_path")
    _require_nonempty(payload.get("source_repo_id"), "source_repo_id")
    for field in (
        "source_receipt_sha256",
        "review_source_id",
        "detector_manifest_sha256",
        "validation_pack_id",
        "approved_proposal_set_sha256",
    ):
        _require_sha256(payload.get(field), field)
    identity = _require_sha256(payload.get("source_identity_sha256"), "source_identity_sha256")
    if identity != canonical_payload_sha256(payload, without="source_identity_sha256"):
        raise ContentPublishError("source_identity_hash_mismatch")


def _validate_acceptance(payload: Mapping[str, Any], candidate_sha256: str, expected_count: int) -> None:
    required = {"schema_version", "authority", "canonicality", "candidate_sha256", "records", "summary", "evidence_identity_sha256"}
    missing = sorted(required - set(payload))
    if missing:
        raise ContentPublishError(f"acceptance_evidence_missing:{','.join(missing)}")
    if payload["schema_version"] != "1.0" or payload["canonicality"] != "VERIFICATION_EVIDENCE_ONLY":
        raise ContentPublishError("acceptance_evidence_contract_mismatch")
    if payload["candidate_sha256"] != candidate_sha256:
        raise ContentPublishError("acceptance_candidate_sha256_mismatch")
    records = payload["records"]
    if not isinstance(records, list) or len(records) != expected_count:
        raise ContentPublishError("acceptance_record_count_mismatch")
    for record in records:
        if not isinstance(record, Mapping):
            raise ContentPublishError("acceptance_record_invalid")
        if record.get("owner_desired_verdict") != record.get("final_effective_player_verdict"):
            raise ContentPublishError("acceptance_verdict_mismatch")
        if set(record.get("surfaces", {})) != REQUIRED_SURFACES:
            raise ContentPublishError("acceptance_surface_set_mismatch")
        _require_sha256(record.get("content_sha256"), "acceptance_content_sha256")
        _require_sha256(record.get("evidence_artifact_sha256"), "acceptance_evidence_artifact_sha256")
        precedence = record.get("source_precedence_used")
        if not isinstance(precedence, list) or not precedence:
            raise ContentPublishError("acceptance_precedence_invalid")
        for surface in REQUIRED_SURFACES:
            result = record["surfaces"][surface]
            if not isinstance(result, Mapping) or result.get("pass") is not True or result.get("match") is not True:
                raise ContentPublishError(f"acceptance_surface_failed:{surface}")
            _require_sha256(result.get("evidence_artifact_sha256"), f"acceptance_surface_evidence:{surface}")
    summary = payload["summary"]
    if not isinstance(summary, Mapping) or summary.get("records_validated") != expected_count:
        raise ContentPublishError("acceptance_summary_record_count_mismatch")
    if summary.get("all_final_effective_match") is not True or set(summary.get("surfaces", [])) != REQUIRED_SURFACES:
        raise ContentPublishError("acceptance_summary_mismatch")
    identity = _require_sha256(payload.get("evidence_identity_sha256"), "evidence_identity_sha256")
    if identity != canonical_payload_sha256(payload, without="evidence_identity_sha256"):
        raise ContentPublishError("acceptance_evidence_identity_hash_mismatch")


def validate_bundle(
    bundle_dir: Path,
    *,
    expected_predecessor_sha256: str,
    expected_predecessor_record_count: int,
    expected_candidate_sha256: str,
    expected_candidate_record_count: int,
    expected_release_package_sha256: str,
    expected_rollback_manifest_sha256: str,
    expected_target_path: str = "/app/data/questions.json",
) -> dict[str, Any]:
    """Validate a complete immutable PR318 bundle without mutating it."""

    if not bundle_dir.is_dir() or bundle_dir.is_symlink():
        raise ContentPublishError("bundle_directory_invalid")
    registry = load_object(bundle_dir / "content-registry-entry.json", "content_registry_entry")
    if registry.get("schema_version") != "1.1" or registry.get("artifact_role") != "content_release_candidate":
        raise ContentPublishError("registry_schema_or_role_mismatch")
    allowed = registry.get("allowed_asset_names")
    if not isinstance(allowed, list) or not allowed or len(set(allowed)) != len(allowed):
        raise ContentPublishError("registry_asset_inventory_invalid")
    allowed_set = {safe_filename(name, "registry_asset_name") for name in allowed}
    if "SHA256SUMS.txt" not in allowed_set:
        raise ContentPublishError("registry_checksums_asset_missing")
    for child in bundle_dir.iterdir():
        if child.is_dir() and child.name != ".runner":
            raise ContentPublishError(f"bundle_unexpected_directory:{child.name}")
        if child.name == ".runner" and child.is_symlink():
            raise ContentPublishError("bundle_runner_directory_symlink")
    actual_files = {path.name for path in bundle_dir.iterdir() if path.is_file()}
    if actual_files != allowed_set:
        raise ContentPublishError("bundle_asset_inventory_mismatch")
    package_sha256 = _verify_sha256sums(bundle_dir, allowed_set - {"SHA256SUMS.txt"}, expected_release_package_sha256)

    candidate_sha256 = _require_sha256(expected_candidate_sha256, "expected_candidate_sha256")
    predecessor_sha256 = _require_sha256(expected_predecessor_sha256, "expected_predecessor_sha256")
    rollback_manifest_sha256 = _require_sha256(expected_rollback_manifest_sha256, "expected_rollback_manifest_sha256")
    if registry.get("baseline_sha256") != predecessor_sha256:
        raise ContentPublishError("registry_predecessor_sha256_mismatch")
    if registry.get("release_candidate_sha256") != candidate_sha256 or registry.get("uncompressed_sha256") != candidate_sha256:
        raise ContentPublishError("registry_candidate_sha256_mismatch")
    if registry.get("record_count") != expected_candidate_record_count or registry.get("record_count") != expected_predecessor_record_count:
        raise ContentPublishError("registry_record_count_mismatch")
    for field in ("release_manifest_sha256", "rollback_manifest_sha256", "acceptance_evidence_sha256", "review_binding_sha256", "repair_batch_manifest_sha256", "mutation_audit_sha256"):
        _require_sha256(registry.get(field), f"registry_{field}")
    if registry["rollback_manifest_sha256"] != rollback_manifest_sha256:
        raise ContentPublishError("registry_rollback_manifest_sha256_mismatch")

    compressed_name = safe_filename(registry.get("compressed_filename"), "registry_compressed_filename")
    compressed = bundle_dir / compressed_name
    compressed_sha256 = sha256_file(compressed)
    if compressed_sha256 != registry.get("compressed_sha256"):
        raise ContentPublishError("registry_compressed_sha256_mismatch")
    candidate = _decompress_identity(compressed)
    if candidate.sha256 != candidate_sha256 or candidate.record_count != expected_candidate_record_count:
        raise ContentPublishError("candidate_identity_mismatch")
    if candidate.size_bytes != registry.get("uncompressed_byte_count"):
        raise ContentPublishError("candidate_size_mismatch")

    release_manifest_name = safe_filename(registry.get("release_manifest_filename"), "registry_release_manifest_filename")
    rollback_manifest_name = safe_filename(registry.get("rollback_manifest_filename"), "registry_rollback_manifest_filename")
    acceptance_name = safe_filename(registry.get("acceptance_evidence_filename"), "registry_acceptance_evidence_filename")
    release_manifest_path = bundle_dir / release_manifest_name
    rollback_manifest_path = bundle_dir / rollback_manifest_name
    acceptance_path = bundle_dir / acceptance_name
    if sha256_file(release_manifest_path) != registry["release_manifest_sha256"]:
        raise ContentPublishError("release_manifest_sha256_mismatch")
    if sha256_file(rollback_manifest_path) != rollback_manifest_sha256:
        raise ContentPublishError("rollback_manifest_sha256_mismatch")
    if sha256_file(acceptance_path) != registry["acceptance_evidence_sha256"]:
        raise ContentPublishError("acceptance_evidence_sha256_mismatch")
    if registry.get("changed_record_count") != registry.get("release_records"):
        raise ContentPublishError("registry_changed_record_count_relationship_mismatch")
    if registry.get("excluded_record_count") != registry.get("excluded_map_battle_records"):
        raise ContentPublishError("registry_excluded_record_count_relationship_mismatch")

    release_manifest = load_object(release_manifest_path, "release_manifest")
    if release_manifest.get("intended_production_destination") != expected_target_path:
        raise ContentPublishError("release_target_path_mismatch")
    if release_manifest.get("source_baseline_sha256") != predecessor_sha256:
        raise ContentPublishError("release_manifest_predecessor_sha256_mismatch")
    candidate_artifact = release_manifest.get("repaired_candidate_artifact")
    previous_artifact = release_manifest.get("pre_mutation_artifact")
    if not isinstance(candidate_artifact, Mapping) or candidate_artifact.get("sha256") != candidate_sha256 or candidate_artifact.get("record_count") != expected_candidate_record_count or candidate_artifact.get("size_bytes") != candidate.size_bytes:
        raise ContentPublishError("release_manifest_candidate_identity_mismatch")
    if not isinstance(previous_artifact, Mapping) or previous_artifact.get("sha256") != predecessor_sha256 or previous_artifact.get("record_count") != expected_predecessor_record_count:
        raise ContentPublishError("release_manifest_predecessor_identity_mismatch")
    governance = release_manifest.get("release_governance")
    if not isinstance(governance, Mapping):
        raise ContentPublishError("release_governance_missing")
    for field in ("review_binding_sha256", "repair_batch_manifest_sha256", "mutation_audit_sha256", "acceptance_evidence_sha256", "rollback_manifest_sha256"):
        if governance.get(field) != registry.get(field):
            raise ContentPublishError(f"release_governance_{field}_mismatch")
    for field in ("changed_record_count", "review_group_count", "excluded_record_count"):
        _require_int(governance.get(field), f"release_governance_{field}")
    if governance.get("allowed_asset_names") != registry.get("allowed_asset_names"):
        raise ContentPublishError("release_governance_asset_inventory_mismatch")
    if governance.get("source_provenance") is None:
        raise ContentPublishError("release_source_provenance_missing")
    _validate_source_provenance(governance["source_provenance"], predecessor_sha256, expected_predecessor_record_count)
    if governance.get("source_identity_sha256") != governance["source_provenance"].get("source_identity_sha256"):
        raise ContentPublishError("release_governance_source_identity_sha256_mismatch")
    mutation_audit = release_manifest.get("mutation_audit")
    if not isinstance(mutation_audit, Mapping):
        raise ContentPublishError("mutation_audit_missing")
    if mutation_audit.get("source_sha256") != predecessor_sha256 or mutation_audit.get("candidate_sha256") != candidate_sha256:
        raise ContentPublishError("mutation_audit_identity_mismatch")
    if mutation_audit.get("changed_record_count") != governance.get("changed_record_count") or mutation_audit.get("review_group_count") != governance.get("review_group_count"):
        raise ContentPublishError("mutation_audit_count_mismatch")
    if not isinstance(mutation_audit.get("records"), list) or len(mutation_audit["records"]) != governance.get("changed_record_count"):
        raise ContentPublishError("mutation_audit_record_set_mismatch")
    if mutation_audit.get("non_target_records_changed", 0) != 0 or mutation_audit.get("accepted_moves_changed", 0) != 0:
        raise ContentPublishError("mutation_audit_forbidden_mutation")

    rollback_manifest = load_object(rollback_manifest_path, "rollback_manifest")
    rollback = rollback_manifest.get("rollback_governance")
    if not isinstance(rollback, Mapping):
        raise ContentPublishError("rollback_governance_missing")
    if rollback.get("previous_sha256") != predecessor_sha256 or rollback.get("candidate_sha256") != candidate_sha256:
        raise ContentPublishError("rollback_identity_mismatch")
    if rollback.get("record_count") != expected_predecessor_record_count:
        raise ContentPublishError("rollback_record_count_mismatch")
    if rollback.get("restore_target") != expected_target_path:
        raise ContentPublishError("rollback_target_path_mismatch")
    post = rollback.get("post_rollback")
    if not isinstance(post, Mapping) or post.get("sha256") != predecessor_sha256 or post.get("record_count") != expected_predecessor_record_count:
        raise ContentPublishError("rollback_postcheck_identity_mismatch")
    if rollback_manifest.get("safety", {}).get("publish_requires_rollback_proof") is not True:
        raise ContentPublishError("rollback_publish_gate_missing")

    acceptance = load_object(acceptance_path, "acceptance_evidence")
    _validate_acceptance(acceptance, candidate_sha256, int(governance.get("changed_record_count", 0)))

    return {
        "package_sha256": package_sha256,
        "candidate": asdict(candidate),
        "predecessor_sha256": predecessor_sha256,
        "predecessor_record_count": expected_predecessor_record_count,
        "candidate_sha256": candidate_sha256,
        "candidate_record_count": expected_candidate_record_count,
        "rollback_manifest_sha256": rollback_manifest_sha256,
        "review_binding_sha256": registry["review_binding_sha256"],
        "repair_batch_manifest_sha256": registry["repair_batch_manifest_sha256"],
        "mutation_audit_sha256": registry["mutation_audit_sha256"],
        "acceptance_evidence_sha256": registry["acceptance_evidence_sha256"],
        "changed_record_count": governance["changed_record_count"],
        "review_group_count": governance["review_group_count"],
        "excluded_record_count": governance["excluded_record_count"],
        "target_path": expected_target_path,
        "six_surfaces_complete": True,
        "verdict_mismatch_count": 0,
    }


def _run_json_command(*args: str, label: str) -> Any:
    completed = subprocess.run(args, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise ContentPublishError(f"{label}_command_failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ContentPublishError(f"{label}_response_malformed") from exc


def resolve_volume_target(
    *, container_name: str, mount_destination: str, target_path: str, docker_executable: str = "docker"
) -> dict[str, Any]:
    """Resolve /app/data/questions.json from the actual running volume."""

    _require_nonempty(container_name, "container_name")
    if not mount_destination.startswith("/") or not target_path.startswith("/"):
        raise ContentPublishError("production_target_paths_must_be_absolute")
    destination = mount_destination.rstrip("/")
    target = PurePosixPath(target_path)
    if str(target.parent) != destination or target.name != "questions.json":
        raise ContentPublishError("unsupported_content_target")
    mounts = _run_json_command(docker_executable, "inspect", container_name, "--format", "{{json .Mounts}}", label="docker_inspect")
    if not isinstance(mounts, list):
        raise ContentPublishError("docker_mount_inventory_invalid")
    matches = [mount for mount in mounts if isinstance(mount, Mapping) and mount.get("Destination") == destination]
    if len(matches) != 1:
        raise ContentPublishError("content_mount_identity_ambiguous")
    mount = matches[0]
    if mount.get("Type") != "volume":
        raise ContentPublishError("content_mount_is_not_named_volume")
    volume_name = mount.get("Name")
    if not isinstance(volume_name, str) or SAFE_VOLUME_NAME_RE.fullmatch(volume_name) is None:
        raise ContentPublishError("content_volume_name_invalid")
    volume = _run_json_command(docker_executable, "volume", "inspect", volume_name, label="docker_volume_inspect")
    if not isinstance(volume, list) or len(volume) != 1 or not isinstance(volume[0], Mapping):
        raise ContentPublishError("docker_volume_identity_invalid")
    volume_payload = volume[0]
    mountpoint = volume_payload.get("Mountpoint")
    if not isinstance(mountpoint, str) or not mountpoint.startswith("/") or mountpoint in {"/", "//"}:
        raise ContentPublishError("docker_volume_mountpoint_invalid")
    if volume_payload.get("Driver") not in {None, "local"}:
        raise ContentPublishError("unsupported_docker_volume_driver")
    source = mount.get("Source")
    if isinstance(source, str) and source and os.path.normpath(source) != os.path.normpath(mountpoint):
        raise ContentPublishError("docker_mount_source_mismatch")
    root = Path(mountpoint)
    if not root.is_dir() or root.is_symlink():
        raise ContentPublishError("docker_volume_mountpoint_unavailable")
    live = root / target.name
    if not live.is_file() or live.is_symlink():
        raise ContentPublishError("production_content_target_unavailable")
    return {
        "container_name": container_name,
        "mount_destination": destination,
        "volume_name": volume_name,
        "mountpoint": str(root),
        "target_path": target_path,
        "live_path": str(live),
    }


def validate_remote_staging_paths(staging_root: str, release_dir: str, release_id: str) -> dict[str, str]:
    """Check the governed staging location without creating anything."""

    safe_release_id(release_id)
    root = Path(staging_root)
    directory = Path(release_dir)
    if not root.is_absolute() or not directory.is_absolute():
        raise ContentPublishError("remote_staging_paths_must_be_absolute")
    if root.is_symlink() or not root.is_dir():
        raise ContentPublishError("remote_staging_root_unavailable")
    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise ContentPublishError("remote_release_directory_outside_allowlist") from exc
    if str(relative).replace("\\", "/") != f"content/{release_id}":
        raise ContentPublishError("remote_release_directory_identity_mismatch")
    if directory.exists() or directory.is_symlink():
        raise ContentPublishError("remote_release_directory_already_exists")
    parent = directory.parent
    if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
        raise ContentPublishError("remote_release_parent_invalid")
    if not os.access(root, os.W_OK):
        raise ContentPublishError("remote_staging_root_not_writable")
    return {"staging_root": str(root), "release_dir": str(directory), "release_id": release_id}


def _copy_fsync(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ContentPublishError(f"immutable_destination_exists:{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, length=CHUNK_SIZE)
        dst.flush()
        os.fsync(dst.fileno())


def _fsync_directory(path: Path) -> None:
    # Windows does not expose directory handles for fsync; the production
    # helper runs on the Linux host where this durability gate is enforced.
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ContentPublishError(f"directory_fsync_failed:{path}") from exc


def _write_json_immutable(path: Path, payload: Mapping[str, Any]) -> str:
    if path.exists() or path.is_symlink():
        raise ContentPublishError(f"immutable_receipt_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o644)
    _fsync_directory(path.parent)
    return hashlib.sha256(encoded).hexdigest()


def _target_receipt_identity(target_info: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "container_name": target_info["container_name"],
        "mount_destination": target_info["mount_destination"],
        "volume_name": target_info["volume_name"],
        "mountpoint": target_info["mountpoint"],
        "target_path": target_info["target_path"],
    }


def promote_local(
    *,
    live: Path,
    candidate: Path,
    expected_predecessor_sha256: str,
    expected_predecessor_record_count: int,
    expected_candidate_sha256: str,
    expected_candidate_record_count: int,
    release_id: str,
    receipt_dir: Path,
    package_sha256: str,
    rollback_manifest_sha256: str,
    target_identity: Mapping[str, Any],
    execute: bool,
    fail_after_replace: bool = False,
    candidate_receipt_path: str | None = None,
) -> dict[str, Any]:
    """Testable local equivalent of the remote atomic promotion protocol."""

    safe_release_id(release_id)
    predecessor = identify_file(live)
    candidate_identity = identify_file(candidate)
    if predecessor.sha256 != expected_predecessor_sha256 or predecessor.record_count != expected_predecessor_record_count:
        raise ContentPublishError("predecessor_sha256_or_record_count_mismatch")
    if candidate_identity.sha256 != expected_candidate_sha256 or candidate_identity.record_count != expected_candidate_record_count:
        raise ContentPublishError("candidate_sha256_or_record_count_mismatch")
    if not execute:
        return {
            "status": "DRY_RUN",
            "production_mutation": False,
            "predecessor": asdict(predecessor),
            "candidate": asdict(candidate_identity),
        }
    receipt_dir.mkdir(parents=True, exist_ok=True)
    backup_path = receipt_dir / f"{release_id}.predecessor.json"
    _copy_fsync(live, backup_path)
    backup_identity = identify_file(backup_path)
    if backup_identity.sha256 != predecessor.sha256 or backup_identity.record_count != predecessor.record_count:
        raise ContentPublishError("predecessor_backup_verification_failed")
    candidate_receipt_identity = asdict(candidate_identity)
    if candidate_receipt_path is not None:
        candidate_receipt_identity["path"] = candidate_receipt_path
    rollback_receipt = {
        "schema_version": "1.0",
        "receipt_kind": "remote_content_rollback",
        "state": "PREPARED",
        "release_id": release_id,
        "created_at_utc": utc_now(),
        "target": dict(target_identity),
        "predecessor": {
            **asdict(predecessor),
            "stored_artifact": {"path": str(backup_path), **asdict(backup_identity)},
        },
        "candidate": candidate_receipt_identity,
        "release_package_sha256": _require_sha256(package_sha256, "release_package_sha256"),
        "rollback_manifest_sha256": _require_sha256(rollback_manifest_sha256, "rollback_manifest_sha256"),
    }
    rollback_receipt_path = receipt_dir / f"{release_id}.rollback-receipt.json"
    rollback_receipt_sha256 = _write_json_immutable(rollback_receipt_path, rollback_receipt)
    stage_path = live.parent / f".go-odyssey-content-{release_id}.stage"
    if stage_path.exists() or stage_path.is_symlink():
        raise ContentPublishError("content_stage_already_exists")
    _copy_fsync(candidate, stage_path)
    try:
        staged = identify_file(stage_path)
        if staged.sha256 != candidate_identity.sha256 or staged.record_count != candidate_identity.record_count:
            raise ContentPublishError("staged_candidate_verification_failed")
        os.replace(stage_path, live)
        _fsync_directory(live.parent)
        if fail_after_replace:
            raise ContentPublishError("simulated_post_promotion_failure")
        published = identify_file(live)
        if published.sha256 != candidate_identity.sha256 or published.record_count != candidate_identity.record_count:
            raise ContentPublishError("post_promotion_verification_failed")
        publish_receipt = {
            **rollback_receipt,
            "receipt_kind": "remote_content_publish",
            "state": "NEW_VERIFIED_CONTENT",
            "rollback_receipt_sha256": rollback_receipt_sha256,
            "published_at_utc": utc_now(),
            "post_promotion": asdict(published),
        }
        publish_path = receipt_dir / f"{release_id}.publish-receipt.json"
        publish_sha256 = _write_json_immutable(publish_path, publish_receipt)
        return {
            "status": "NEW_VERIFIED_CONTENT",
            "production_mutation": True,
            "rollback_receipt_sha256": rollback_receipt_sha256,
            "publish_receipt_sha256": publish_sha256,
            "publish_receipt_path": str(publish_path),
            "rollback_receipt_path": str(rollback_receipt_path),
            "predecessor": asdict(predecessor),
            "candidate": asdict(published),
        }
    except Exception as exc:
        if stage_path.exists():
            stage_path.unlink()
        rollback_stage = live.parent / f".go-odyssey-content-{release_id}.rollback-stage"
        try:
            _copy_fsync(backup_path, rollback_stage)
            restored = identify_file(rollback_stage)
            if restored.sha256 != predecessor.sha256 or restored.record_count != predecessor.record_count:
                raise ContentPublishError("rollback_stage_verification_failed")
            os.replace(rollback_stage, live)
            _fsync_directory(live.parent)
            final = identify_file(live)
            if final.sha256 != predecessor.sha256 or final.record_count != predecessor.record_count:
                raise ContentPublishError("rollback_postcheck_failed")
            rollback_result_receipt = {
                **rollback_receipt,
                "receipt_kind": "remote_content_publish",
                "state": "OLD_VERIFIED_CONTENT",
                "rollback_receipt_sha256": rollback_receipt_sha256,
                "published_at_utc": utc_now(),
                "rollback_executed": True,
                "rollback_reason": str(exc),
                "post_promotion": asdict(final),
            }
            rollback_result_path = receipt_dir / f"{release_id}.rollback-result.json"
            rollback_result_sha256 = _write_json_immutable(rollback_result_path, rollback_result_receipt)
            return {
                "status": "OLD_VERIFIED_CONTENT",
                "production_mutation": True,
                "rollback_executed": True,
                "rollback_reason": str(exc),
                "rollback_receipt_sha256": rollback_receipt_sha256,
                "rollback_receipt_path": str(rollback_receipt_path),
                "rollback_result_receipt_sha256": rollback_result_sha256,
                "rollback_result_receipt_path": str(rollback_result_path),
                "predecessor": asdict(final),
            }
        except Exception as rollback_exc:
            raise ContentPublishError(f"unverified_state_after_promotion:{rollback_exc}") from exc


def remote_inspect(args: argparse.Namespace) -> int:
    staging = validate_remote_staging_paths(args.staging_root, args.release_dir, args.release_id)
    target = resolve_volume_target(
        container_name=args.container_name,
        mount_destination=args.mount_destination,
        target_path=args.target_path,
        docker_executable=args.docker_executable,
    )
    identity = identify_file(Path(target["live_path"]))
    if identity.sha256 != args.expected_predecessor_sha256 or identity.record_count != args.expected_predecessor_record_count:
        raise ContentPublishError("predecessor_sha256_or_record_count_mismatch")
    print(json.dumps({"status": "PREDECESSOR_VERIFIED", "target": target, "predecessor": asdict(identity), "rollback_readiness": staging}, sort_keys=True))
    return 0


def remote_promote(args: argparse.Namespace) -> int:
    safe_release_id(args.release_id)
    staging_root = Path(args.staging_root)
    bundle_dir = Path(args.bundle_dir)
    release_dir = Path(args.release_dir)
    if not staging_root.is_absolute() or not release_dir.is_absolute() or not bundle_dir.is_absolute():
        raise ContentPublishError("remote_staging_paths_must_be_absolute")
    try:
        release_dir.relative_to(staging_root)
    except ValueError as exc:
        raise ContentPublishError("remote_release_directory_outside_allowlist") from exc
    if not release_dir.is_dir() or release_dir.is_symlink() or bundle_dir != release_dir:
        raise ContentPublishError("remote_release_directory_invalid")
    bundle_report = validate_bundle(
        bundle_dir,
        expected_predecessor_sha256=args.expected_predecessor_sha256,
        expected_predecessor_record_count=args.expected_predecessor_record_count,
        expected_candidate_sha256=args.expected_candidate_sha256,
        expected_candidate_record_count=args.expected_candidate_record_count,
        expected_release_package_sha256=args.expected_release_package_sha256,
        expected_rollback_manifest_sha256=args.expected_rollback_manifest_sha256,
        expected_target_path=args.target_path,
    )
    target = resolve_volume_target(
        container_name=args.container_name,
        mount_destination=args.mount_destination,
        target_path=args.target_path,
        docker_executable=args.docker_executable,
    )
    live = Path(target["live_path"])
    predecessor = identify_file(live)
    if predecessor.sha256 != args.expected_predecessor_sha256 or predecessor.record_count != args.expected_predecessor_record_count:
        raise ContentPublishError("predecessor_sha256_or_record_count_mismatch_before_mutation")
    candidate_name = safe_filename(load_object(bundle_dir / "content-registry-entry.json", "content_registry_entry")["compressed_filename"], "candidate_filename")
    with tempfile.TemporaryDirectory(prefix="content-publish-remote-") as temporary:
        candidate_path = Path(temporary) / "candidate.json"
        try:
            with gzip.open(bundle_dir / candidate_name, "rb") as compressed, candidate_path.open("wb") as raw:
                shutil.copyfileobj(compressed, raw, length=CHUNK_SIZE)
                raw.flush()
                os.fsync(raw.fileno())
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            raise ContentPublishError("invalid_candidate_gzip") from exc
        result = promote_local(
            live=live,
            candidate=candidate_path,
            expected_predecessor_sha256=args.expected_predecessor_sha256,
            expected_predecessor_record_count=args.expected_predecessor_record_count,
            expected_candidate_sha256=args.expected_candidate_sha256,
            expected_candidate_record_count=args.expected_candidate_record_count,
            release_id=args.release_id,
            receipt_dir=release_dir,
            package_sha256=bundle_report["package_sha256"],
            rollback_manifest_sha256=args.expected_rollback_manifest_sha256,
            target_identity=_target_receipt_identity(target),
            execute=True,
            candidate_receipt_path=str(bundle_dir / candidate_name),
        )
    print(json.dumps({**result, "target": target, "bundle": bundle_report}, sort_keys=True))
    return 0 if result["status"] == "NEW_VERIFIED_CONTENT" else 75


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-bundle")
    validate.add_argument("--bundle-dir", required=True, type=Path)
    validate.add_argument("--expected-predecessor-sha256", required=True)
    validate.add_argument("--expected-predecessor-record-count", required=True, type=int)
    validate.add_argument("--expected-candidate-sha256", required=True)
    validate.add_argument("--expected-candidate-record-count", required=True, type=int)
    validate.add_argument("--expected-release-package-sha256", required=True)
    validate.add_argument("--expected-rollback-manifest-sha256", required=True)
    validate.add_argument("--target-path", default="/app/data/questions.json")
    inspect = sub.add_parser("remote-inspect")
    inspect.add_argument("--container-name", required=True)
    inspect.add_argument("--mount-destination", required=True)
    inspect.add_argument("--target-path", required=True)
    inspect.add_argument("--expected-predecessor-sha256", required=True)
    inspect.add_argument("--expected-predecessor-record-count", required=True, type=int)
    inspect.add_argument("--staging-root", required=True)
    inspect.add_argument("--release-dir", required=True)
    inspect.add_argument("--release-id", required=True)
    inspect.add_argument("--docker-executable", default="docker")
    remote = sub.add_parser("remote-promote")
    remote.add_argument("--bundle-dir", required=True)
    remote.add_argument("--staging-root", required=True)
    remote.add_argument("--release-dir", required=True)
    remote.add_argument("--release-id", required=True)
    remote.add_argument("--container-name", required=True)
    remote.add_argument("--mount-destination", required=True)
    remote.add_argument("--target-path", required=True)
    remote.add_argument("--expected-predecessor-sha256", required=True)
    remote.add_argument("--expected-predecessor-record-count", required=True, type=int)
    remote.add_argument("--expected-candidate-sha256", required=True)
    remote.add_argument("--expected-candidate-record-count", required=True, type=int)
    remote.add_argument("--expected-release-package-sha256", required=True)
    remote.add_argument("--expected-rollback-manifest-sha256", required=True)
    remote.add_argument("--docker-executable", default="docker")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-bundle":
            print(json.dumps(validate_bundle(
                args.bundle_dir,
                expected_predecessor_sha256=args.expected_predecessor_sha256,
                expected_predecessor_record_count=args.expected_predecessor_record_count,
                expected_candidate_sha256=args.expected_candidate_sha256,
                expected_candidate_record_count=args.expected_candidate_record_count,
                expected_release_package_sha256=args.expected_release_package_sha256,
                expected_rollback_manifest_sha256=args.expected_rollback_manifest_sha256,
                expected_target_path=args.target_path,
            ), sort_keys=True))
            return 0
        if args.command == "remote-inspect":
            return remote_inspect(args)
        return remote_promote(args)
    except ContentPublishError as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
