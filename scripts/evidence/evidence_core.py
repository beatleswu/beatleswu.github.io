#!/usr/bin/env python3
"""Durable, content-addressed evidence artifact authority.

The module is deliberately filesystem-only. It does not contact GitHub,
Production, a database, or a deployment system. Artifact bytes are immutable
content authority; manifests bind metadata to those bytes; the central index
is a discoverability and relationship registry.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None
    import msvcrt  # type: ignore


DEFAULT_ROOT = Path(
    os.environ.get("GO_ODYSSEY_EVIDENCE_ROOT", r"D:\go-odyssey-release-evidence")
)
INDEX_FILENAME = "evidence-index.json"
LOCK_FILENAME = ".evidence-index.lock"
MANIFEST_FILENAME = "artifact.manifest.json"
ARTIFACT_SCHEMA_VERSION = "go-odyssey-evidence-artifact-v1"
BOOTSTRAP_SCHEMA_VERSION = "go-odyssey-evidence-bootstrap-v1"
INDEX_SCHEMA_VERSION = "go-odyssey-evidence-index-v1"
HASH_ALGORITHM = "SHA256"

ARTIFACT_CLASSES = frozenset(
    {
        "CENSUS",
        "MASTERPLAN",
        "TASK_SCOPE_LOCK",
        "INDEPENDENT_REVIEW",
        "ADMISSION_RECONCILIATION",
        "OWNER_GATE_EVIDENCE",
        "RELEASE_ARTIFACT",
        "STATIC_RELEASE_MANIFEST",
        "DATA_PROMOTION_ARTIFACT",
        "DB_MIGRATION_PREFLIGHT",
        "DB_MIGRATION_POSTCHECK",
        "PRODUCTION_ACCEPTANCE",
        "INCIDENT_EVIDENCE",
        "PRESERVATION_MANIFEST",
        "RECOVERY_MANIFEST",
        "FINAL_CLOSEOUT_LEDGER",
    }
)
AUTHORITY_STATES = frozenset(
    {
        "ORIGINAL",
        "RECOVERED_ORIGINAL",
        "RECONSTRUCTED",
        "DERIVED",
        "HISTORICAL",
        "PRODUCTION_ACCEPTANCE",
        "PRESERVATION_ONLY",
    }
)
LIFECYCLE_STATES = frozenset({"CURRENT_ACTIONABLE", "SUPERSEDED"})
RETENTION_CLASSES = frozenset(
    {
        "ACTIVE_AUTHORITY",
        "OWNER_BOUND",
        "PRODUCTION_AUDIT",
        "INCIDENT_HOLD",
        "HISTORICAL_PRESERVATION",
        "RECOVERED_ORIGINAL",
    }
)
DEFAULT_RETENTION = {
    "CENSUS": "HISTORICAL_PRESERVATION",
    "MASTERPLAN": "ACTIVE_AUTHORITY",
    "TASK_SCOPE_LOCK": "OWNER_BOUND",
    "INDEPENDENT_REVIEW": "OWNER_BOUND",
    "ADMISSION_RECONCILIATION": "OWNER_BOUND",
    "OWNER_GATE_EVIDENCE": "OWNER_BOUND",
    "RELEASE_ARTIFACT": "PRODUCTION_AUDIT",
    "STATIC_RELEASE_MANIFEST": "PRODUCTION_AUDIT",
    "DATA_PROMOTION_ARTIFACT": "PRODUCTION_AUDIT",
    "DB_MIGRATION_PREFLIGHT": "PRODUCTION_AUDIT",
    "DB_MIGRATION_POSTCHECK": "PRODUCTION_AUDIT",
    "PRODUCTION_ACCEPTANCE": "PRODUCTION_AUDIT",
    "INCIDENT_EVIDENCE": "INCIDENT_HOLD",
    "PRESERVATION_MANIFEST": "HISTORICAL_PRESERVATION",
    "RECOVERY_MANIFEST": "RECOVERED_ORIGINAL",
    "FINAL_CLOSEOUT_LEDGER": "OWNER_BOUND",
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_ID_RE = re.compile(r"^GOE1-[A-Za-z0-9._-]{3,240}-[0-9a-f]{16}$")
COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
PROTECTED_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        "secret_key.txt",
        "id_rsa",
        "id_ed25519",
        "private_key.pem",
    }
)
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(rb"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(rb"(?i)\b(?:ghp_|github_pat_|glpat-|sk-|AKIA)[A-Za-z0-9_-]{16,}\b"),
    re.compile(rb"(?i)(?:postgres(?:ql)?|mysql)://[^\s:@/]+:[^@\s]+@"),
    re.compile(
        rb"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?key|"
        rb"client[_-]?secret|secret[_-]?key)\s*[:=]\s*[\"']?"
        rb"[A-Za-z0-9/+=._-]{12,}"
    ),
)
IDENTITY_KEYS = (
    "artifact_id",
    "schema_version",
    "task",
    "artifact_class",
    "filename",
    "stable_path",
    "manifest_path",
    "content_type",
    "bytes",
    "hash_algorithm",
    "sha256",
    "program",
    "authority_state",
    "lifecycle_state",
    "retention_class",
    "immutable",
    "canonical_head",
    "canonical_tree",
    "source_authority_ref",
    "source_head",
    "source_tree",
    "production_identity",
    "owner_gate_ref",
    "recovered_from",
    "reconstruction_of",
    "supersedes",
    "superseded_by",
)


class EvidenceError(RuntimeError):
    """Expected fail-closed error with a stable, non-sensitive error code."""

    def __init__(self, code: str, detail: str | None = None):
        self.code = code
        super().__init__(detail or code)


def _require(condition: bool, code: str, detail: str | None = None) -> None:
    if not condition:
        raise EvidenceError(code, detail)


def _now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise EvidenceError("ARTIFACT_READ_FAILED") from exc
    return digest.hexdigest()


def _file_identity(path: Path) -> tuple[int, str]:
    try:
        return path.stat().st_size, sha256_file(path)
    except OSError as exc:
        raise EvidenceError("ARTIFACT_READ_FAILED") from exc


def _validate_sha(value: Any, code: str = "INVALID_SHA256") -> str:
    _require(isinstance(value, str) and SHA256_RE.fullmatch(value) is not None, code)
    return value


def _validate_component(value: Any, code: str = "UNSAFE_PATH_COMPONENT") -> str:
    _require(isinstance(value, str), code)
    _require(
        value not in {".", ".."}
        and "\x00" not in value
        and "/" not in value
        and "\\" not in value
        and COMPONENT_RE.fullmatch(value) is not None,
        code,
    )
    return value


def _validate_filename(value: Any) -> str:
    _require(isinstance(value, str), "INVALID_FILENAME")
    _require(
        value
        and value not in {".", ".."}
        and "\x00" not in value
        and "/" not in value
        and "\\" not in value
        and value != MANIFEST_FILENAME,
        "INVALID_FILENAME",
    )
    return value


def _ensure_root(root: Path | str) -> Path:
    try:
        path = Path(root).expanduser()
        _require(path.is_absolute(), "STABLE_ROOT_MUST_BE_ABSOLUTE")
        if path.exists() and (path.is_symlink() or not path.is_dir()):
            raise EvidenceError("STABLE_ROOT_UNAVAILABLE")
        path.mkdir(parents=True, exist_ok=True)
        _require(path.is_dir() and not path.is_symlink(), "STABLE_ROOT_UNAVAILABLE")
        return path.resolve()
    except EvidenceError:
        raise
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("STABLE_ROOT_UNAVAILABLE") from exc


def _ensure_source(source: Path | str) -> Path:
    try:
        path = Path(source).expanduser()
        if path.name.casefold() in {name.casefold() for name in PROTECTED_BASENAMES}:
            raise EvidenceError("PROTECTED_SOURCE_PATH_REJECTED")
        _require(path.exists() and path.is_file(), "ARTIFACT_MISSING")
        _require(not path.is_symlink(), "SOURCE_MUST_BE_REGULAR_FILE")
        return path.resolve(strict=True)
    except EvidenceError:
        raise
    except (OSError, RuntimeError) as exc:
        raise EvidenceError("ARTIFACT_MISSING") from exc


def _ensure_inside(root: Path, path: Path, code: str = "PATH_OUTSIDE_STABLE_ROOT") -> Path:
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(root)
        return resolved
    except (OSError, RuntimeError, ValueError) as exc:
        raise EvidenceError(code) from exc


def _scan_secret_bytes(data: bytes) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise EvidenceError("PROHIBITED_SECRET_CONTENT")


def _read_source_bytes(source: Path) -> bytes:
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise EvidenceError("ARTIFACT_READ_FAILED") from exc
    _scan_secret_bytes(data)
    return data


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        data = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise EvidenceError("INVALID_METADATA") from exc
    _scan_secret_bytes(data)
    return data


def _load_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
        _scan_secret_bytes(raw)
        return json.loads(raw.decode("utf-8"))
    except EvidenceError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("INVALID_JSON") from exc


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = None
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except (OSError, ValueError) as exc:
        raise EvidenceError("ATOMIC_WRITE_FAILED") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    descriptor = None
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=str(destination.parent),
        )
        temporary = Path(temporary_name)
        with source.open("rb") as source_handle, os.fdopen(descriptor, "wb") as output:
            descriptor = None
            while True:
                chunk = source_handle.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        _require(
            _file_identity(temporary) == _file_identity(source),
            "ARTIFACT_PERSISTED_HASH_MISMATCH",
        )
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    except EvidenceError:
        raise
    except (OSError, ValueError) as exc:
        raise EvidenceError("ARTIFACT_PERSIST_FAILED") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def _index_lock(root: Path):
    lock_path = root / LOCK_FILENAME
    if lock_path.exists() and lock_path.is_symlink():
        raise EvidenceError("LOCK_PATH_INVALID")
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
        handle = os.fdopen(descriptor, "r+b")
    except OSError as exc:
        raise EvidenceError("LOCK_PATH_INVALID") from exc

    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except OSError as exc:
                raise EvidenceError("LOCK_UNAVAILABLE") from exc
            locked = True
        else:  # pragma: no cover - exercised on Windows
            deadline = time.monotonic() + 10.0
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise EvidenceError("LOCK_UNAVAILABLE") from exc
                    time.sleep(0.05)
        yield
    finally:
        if locked:
            try:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                else:  # pragma: no cover - exercised on Windows
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        handle.close()


def _validate_artifact_id(value: Any) -> str:
    _require(
        isinstance(value, str) and ARTIFACT_ID_RE.fullmatch(value) is not None,
        "INVALID_ARTIFACT_ID",
    )
    return value


def artifact_id_for(task: str, artifact_class: str, sha256: str) -> str:
    task = _validate_component(task, "INVALID_TASK")
    _require(artifact_class in ARTIFACT_CLASSES, "INVALID_ARTIFACT_CLASS")
    sha256 = _validate_sha(sha256)
    value = f"GOE1-{task}-{artifact_class}-{sha256[:16]}"
    return _validate_artifact_id(value)


def _validate_string_field(value: Any, code: str) -> str:
    _require(isinstance(value, str) and bool(value), code)
    _require("\x00" not in value, code)
    return value


def _validate_optional_sha(value: Any, code: str) -> None:
    if value is not None:
        _validate_sha(value, code)


def _validate_optional_git_sha(value: Any, code: str) -> None:
    if value is not None:
        _require(isinstance(value, str) and GIT_SHA_RE.fullmatch(value) is not None, code)


def _normalize_id_list(value: Any, code: str) -> list[str]:
    if value is None:
        return []
    _require(isinstance(value, list), code)
    result = []
    for item in value:
        result.append(_validate_artifact_id(item))
    return result


def _prepare_metadata(
    root: Path,
    source: Path,
    metadata: Mapping[str, Any],
    byte_count: int,
    sha256: str,
) -> tuple[dict[str, Any], Path, Path]:
    _require(isinstance(metadata, Mapping), "INVALID_METADATA")
    task = _validate_component(metadata.get("task"), "INVALID_TASK")
    artifact_class = metadata.get("artifact_class")
    _require(artifact_class in ARTIFACT_CLASSES, "INVALID_ARTIFACT_CLASS")
    program = _validate_component(metadata.get("program", "GO-ODYSSEY"), "INVALID_PROGRAM")
    filename = _validate_filename(metadata.get("filename"))
    content_type = _validate_string_field(
        metadata.get("content_type", "application/octet-stream"),
        "INVALID_CONTENT_TYPE",
    )
    producer = _validate_string_field(
        metadata.get("producer", "evidence-cli"),
        "INVALID_PRODUCER",
    )
    provenance = metadata.get("provenance", {"source_type": "local-file"})
    _require(isinstance(provenance, Mapping), "INVALID_PROVENANCE")
    authority_state = metadata.get("authority_state", "ORIGINAL")
    lifecycle_state = metadata.get("lifecycle_state", "CURRENT_ACTIONABLE")
    retention_class = metadata.get(
        "retention_class", DEFAULT_RETENTION[artifact_class]
    )
    _require(authority_state in AUTHORITY_STATES, "INVALID_AUTHORITY_STATE")
    _require(lifecycle_state in LIFECYCLE_STATES, "INVALID_LIFECYCLE_STATE")
    _require(retention_class in RETENTION_CLASSES, "INVALID_RETENTION_CLASS")
    _require(metadata.get("immutable", True) is True, "ARTIFACT_MUST_BE_IMMUTABLE")

    expected_id = artifact_id_for(task, artifact_class, sha256)
    supplied_id = metadata.get("artifact_id")
    if supplied_id is not None:
        _require(supplied_id == expected_id, "ARTIFACT_ID_CONTENT_MISMATCH")

    stable_path = root / program / task / artifact_class / expected_id / filename
    stable_path = _ensure_inside(root, stable_path)
    manifest_path = stable_path.parent / MANIFEST_FILENAME
    _require(
        metadata.get("stable_path", str(stable_path)) == str(stable_path),
        "STABLE_PATH_IDENTITY_MISMATCH",
    )

    created_at = metadata.get("created_at_utc", _now())
    _validate_string_field(created_at, "INVALID_CREATED_AT")

    prepared: dict[str, Any] = {
        "artifact_id": expected_id,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "task": task,
        "artifact_class": artifact_class,
        "filename": filename,
        "stable_path": str(stable_path),
        "manifest_path": str(manifest_path),
        "content_type": content_type,
        "bytes": byte_count,
        "hash_algorithm": HASH_ALGORITHM,
        "sha256": sha256,
        "created_at_utc": created_at,
        "producer": producer,
        "provenance": dict(provenance),
        "authority_state": authority_state,
        "lifecycle_state": lifecycle_state,
        "retention_class": retention_class,
        "immutable": True,
        "program": program,
    }

    for key in (
        "canonical_head",
        "canonical_tree",
        "source_authority_ref",
        "source_head",
        "source_tree",
        "production_identity",
        "owner_gate_ref",
        "verification",
        "notes",
    ):
        if key in metadata:
            prepared[key] = metadata[key]

    _validate_optional_git_sha(prepared.get("canonical_head"), "INVALID_CANONICAL_HEAD")
    _validate_optional_git_sha(prepared.get("canonical_tree"), "INVALID_CANONICAL_TREE")
    _validate_optional_git_sha(prepared.get("source_head"), "INVALID_SOURCE_HEAD")
    _validate_optional_git_sha(prepared.get("source_tree"), "INVALID_SOURCE_TREE")
    prepared["supersedes"] = _normalize_id_list(
        metadata.get("supersedes"), "INVALID_SUPERSEDES"
    )
    prepared["superseded_by"] = _normalize_id_list(
        metadata.get("superseded_by"), "INVALID_SUPERSEDED_BY"
    )

    for key in ("recovered_from", "reconstruction_of"):
        if key in metadata and metadata[key] is not None:
            prepared[key] = _validate_string_field(metadata[key], f"INVALID_{key.upper()}")
    if authority_state == "RECONSTRUCTED":
        _require(
            isinstance(prepared.get("reconstruction_of"), str),
            "RECONSTRUCTION_ORIGINAL_LINK_REQUIRED",
        )

    _json_bytes(prepared)
    return prepared, stable_path, manifest_path


def _same_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(key) == right.get(key) for key in IDENTITY_KEYS)


def _load_index(root: Path, *, allow_missing: bool = True) -> dict[str, Any]:
    index_path = root / INDEX_FILENAME
    if not index_path.exists():
        _require(allow_missing, "INDEX_MISSING")
        return {
            "schema_version": INDEX_SCHEMA_VERSION,
            "updated_at_utc": _now(),
            "entries": [],
        }
    _require(index_path.is_file() and not index_path.is_symlink(), "INDEX_PATH_INVALID")
    payload = _load_json(index_path)
    _require(isinstance(payload, dict), "INDEX_CORRUPT")
    _require(payload.get("schema_version") == INDEX_SCHEMA_VERSION, "INDEX_SCHEMA_MISMATCH")
    entries = payload.get("entries")
    _require(isinstance(entries, list), "INDEX_CORRUPT")
    seen: set[str] = set()
    for entry in entries:
        _validate_index_entry(entry)
        _require(entry["artifact_id"] not in seen, "DUPLICATE_ARTIFACT_ID")
        seen.add(entry["artifact_id"])
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "updated_at_utc": payload.get("updated_at_utc", _now()),
        "entries": entries,
    }


def _validate_index_entry(entry: Any) -> dict[str, Any]:
    _require(isinstance(entry, dict), "INDEX_CORRUPT")
    required = (
        "index_entry_id",
        "artifact_id",
        "task",
        "artifact_class",
        "stable_path",
        "manifest_path",
        "bytes",
        "sha256",
        "manifest_sha256",
        "authority_state",
        "lifecycle_state",
        "retention_class",
    )
    _require(all(key in entry for key in required), "INDEX_CORRUPT")
    _validate_artifact_id(entry["index_entry_id"])
    _require(entry["index_entry_id"] == entry["artifact_id"], "INDEX_IDENTITY_MISMATCH")
    _validate_artifact_id(entry["artifact_id"])
    _validate_component(entry["task"], "INDEX_CORRUPT")
    _require(entry["artifact_class"] in ARTIFACT_CLASSES, "INDEX_CORRUPT")
    _require(isinstance(entry["stable_path"], str), "INDEX_CORRUPT")
    _require(isinstance(entry["manifest_path"], str), "INDEX_CORRUPT")
    _require(isinstance(entry["bytes"], int) and entry["bytes"] >= 0, "INDEX_CORRUPT")
    _validate_sha(entry["sha256"], "INDEX_CORRUPT")
    _validate_sha(entry["manifest_sha256"], "INDEX_CORRUPT")
    _require(entry["authority_state"] in AUTHORITY_STATES, "INDEX_CORRUPT")
    _require(entry["lifecycle_state"] in LIFECYCLE_STATES, "INDEX_CORRUPT")
    _require(entry["retention_class"] in RETENTION_CLASSES, "INDEX_CORRUPT")
    for key in ("supersedes", "superseded_by"):
        _normalize_id_list(entry.get(key), "INDEX_CORRUPT")
    return entry


def _write_index(root: Path, index: Mapping[str, Any]) -> None:
    entries = sorted(index["entries"], key=lambda item: item["artifact_id"])
    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "updated_at_utc": _now(),
        "entries": entries,
    }
    _atomic_write(root / INDEX_FILENAME, _json_bytes(payload))


def _merge_index_entry(index: dict[str, Any], entry: dict[str, Any]) -> bool:
    _validate_index_entry(entry)
    entries = index["entries"]
    for existing in entries:
        if existing["artifact_id"] == entry["artifact_id"]:
            _require(existing == entry, "DUPLICATE_ARTIFACT_ID")
            return False
    entries.append(entry)
    return True


def _manifest_payload(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    _require(isinstance(payload, dict), "INVALID_MANIFEST")
    _require(
        payload.get("schema_version")
        in {ARTIFACT_SCHEMA_VERSION, BOOTSTRAP_SCHEMA_VERSION},
        "INVALID_MANIFEST_SCHEMA",
    )
    required = (
        "artifact_id",
        "task",
        "artifact_class",
        "filename",
        "stable_path",
        "bytes",
        "hash_algorithm",
        "sha256",
        "authority_state",
        "lifecycle_state",
        "retention_class",
        "immutable",
    )
    _require(all(key in payload for key in required), "INVALID_MANIFEST")
    _validate_artifact_id(payload["artifact_id"])
    _validate_component(payload["task"], "INVALID_MANIFEST")
    _require(payload["artifact_class"] in ARTIFACT_CLASSES, "INVALID_MANIFEST")
    _validate_filename(payload["filename"])
    _require(isinstance(payload["stable_path"], str), "INVALID_MANIFEST")
    _require(
        isinstance(payload["bytes"], int) and payload["bytes"] >= 0,
        "INVALID_MANIFEST",
    )
    _validate_sha(payload["sha256"], "INVALID_MANIFEST")
    _require(payload["hash_algorithm"] == HASH_ALGORITHM, "INVALID_MANIFEST")
    _require(payload["authority_state"] in AUTHORITY_STATES, "INVALID_MANIFEST")
    _require(payload["lifecycle_state"] in LIFECYCLE_STATES, "INVALID_MANIFEST")
    _require(payload["retention_class"] in RETENTION_CLASSES, "INVALID_MANIFEST")
    _require(payload["immutable"] is True, "INVALID_MANIFEST")
    _require(isinstance(payload.get("provenance", {}), dict), "INVALID_MANIFEST")
    _validate_optional_git_sha(payload.get("canonical_head"), "INVALID_MANIFEST")
    _validate_optional_git_sha(payload.get("canonical_tree"), "INVALID_MANIFEST")
    _validate_optional_git_sha(payload.get("source_head"), "INVALID_MANIFEST")
    _validate_optional_git_sha(payload.get("source_tree"), "INVALID_MANIFEST")
    _normalize_id_list(payload.get("supersedes"), "INVALID_MANIFEST")
    _normalize_id_list(payload.get("superseded_by"), "INVALID_MANIFEST")
    expected_id = artifact_id_for(payload["task"], payload["artifact_class"], payload["sha256"])
    legacy_bootstrap_id = (
        f"GOE1-W2-INFRA-EVIDENCE-001-MASTERPLAN-{payload['sha256'][:16]}"
    )
    _require(
        payload["artifact_id"] == expected_id
        or (
            payload["schema_version"] == BOOTSTRAP_SCHEMA_VERSION
            and payload["artifact_id"] == legacy_bootstrap_id
        ),
        "MANIFEST_CONTENT_ID_MISMATCH",
    )
    return payload


def _verify_pair(root: Path, artifact_path: Path, manifest_path: Path) -> tuple[dict[str, Any], int, str, str]:
    artifact_path = _ensure_inside(root, artifact_path)
    manifest_path = _ensure_inside(root, manifest_path)
    _require(
        artifact_path.is_file() and not artifact_path.is_symlink(),
        "ARTIFACT_MISSING",
    )
    _require(
        manifest_path.is_file() and not manifest_path.is_symlink(),
        "MANIFEST_MISSING",
    )
    payload = _manifest_payload(manifest_path)
    _require(payload["filename"] == artifact_path.name, "MANIFEST_PATH_MISMATCH")
    _require(payload["stable_path"] == str(artifact_path), "MANIFEST_PATH_MISMATCH")
    if payload.get("manifest_path") is not None:
        _require(
            payload["manifest_path"] == str(manifest_path),
            "MANIFEST_PATH_MISMATCH",
        )
    byte_count, sha256 = _file_identity(artifact_path)
    _require(byte_count == payload["bytes"], "ARTIFACT_BYTE_COUNT_MISMATCH")
    _require(sha256 == payload["sha256"], "ARTIFACT_HASH_MISMATCH")
    manifest_sha = sha256_file(manifest_path)
    return payload, byte_count, sha256, manifest_sha


def _index_entry_from_manifest(
    payload: Mapping[str, Any],
    manifest_path: Path,
    manifest_sha256: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "index_entry_id": payload["artifact_id"],
        "artifact_id": payload["artifact_id"],
        "task": payload["task"],
        "artifact_class": payload["artifact_class"],
        "filename": payload["filename"],
        "stable_path": payload["stable_path"],
        "manifest_path": str(manifest_path),
        "bytes": payload["bytes"],
        "sha256": payload["sha256"],
        "manifest_sha256": manifest_sha256,
        "authority_state": payload["authority_state"],
        "lifecycle_state": payload["lifecycle_state"],
        "retention_class": payload["retention_class"],
        "created_at_utc": payload.get("created_at_utc"),
        "canonical_head": payload.get("canonical_head"),
        "canonical_tree": payload.get("canonical_tree"),
        "supersedes": list(payload.get("supersedes") or []),
        "superseded_by": list(payload.get("superseded_by") or []),
    }
    if payload.get("program") is not None:
        entry["program"] = payload["program"]
    if payload.get("owner_gate_ref") is not None:
        entry["owner_gate_ref"] = payload["owner_gate_ref"]
    _validate_index_entry(entry)
    return entry


def _result(
    payload: Mapping[str, Any],
    manifest_path: Path,
    manifest_sha256: str,
    *,
    idempotent: bool = False,
) -> dict[str, Any]:
    return {
        "status": "PASS",
        "artifact_id": payload["artifact_id"],
        "artifact_class": payload["artifact_class"],
        "durable_path": payload["stable_path"],
        "manifest_path": str(manifest_path),
        "bytes": payload["bytes"],
        "sha256": payload["sha256"],
        "manifest_sha256": manifest_sha256,
        "index_entry_id": payload["artifact_id"],
        "verified": "YES",
        "idempotent": idempotent,
    }


def register(
    source_path: Path | str,
    *,
    root: Path | str = DEFAULT_ROOT,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    stable_root = _ensure_root(root)
    source = _ensure_source(source_path)
    data = _read_source_bytes(source)
    sha256 = _sha256_bytes(data)
    prepared, artifact_path, manifest_path = _prepare_metadata(
        stable_root,
        source,
        metadata,
        len(data),
        sha256,
    )
    return {
        "status": "PROPOSED",
        "artifact_id": prepared["artifact_id"],
        "artifact_class": prepared["artifact_class"],
        "durable_path": str(artifact_path),
        "manifest_path": str(manifest_path),
        "bytes": len(data),
        "sha256": sha256,
        "verified": "NO",
    }


def finalize(
    source_path: Path | str,
    *,
    root: Path | str = DEFAULT_ROOT,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    stable_root = _ensure_root(root)
    source = _ensure_source(source_path)
    data = _read_source_bytes(source)
    sha256 = _sha256_bytes(data)
    byte_count = len(data)
    prepared, artifact_path, manifest_path = _prepare_metadata(
        stable_root,
        source,
        metadata,
        byte_count,
        sha256,
    )

    with _index_lock(stable_root):
        index = _load_index(stable_root)
        artifact_exists = artifact_path.exists()
        manifest_exists = manifest_path.exists()
        if artifact_exists or manifest_exists:
            _require(
                artifact_exists
                and manifest_exists
                and artifact_path.is_file()
                and manifest_path.is_file()
                and not artifact_path.is_symlink()
                and not manifest_path.is_symlink(),
                "PARTIAL_PUBLICATION",
            )
            existing, existing_bytes, existing_sha, existing_manifest_sha = _verify_pair(
                stable_root, artifact_path, manifest_path
            )
            _require(
                existing_bytes == byte_count
                and existing_sha == sha256
                and _same_identity(existing, prepared),
                "DUPLICATE_ARTIFACT_ID",
            )
            entry = _index_entry_from_manifest(
                existing, manifest_path, existing_manifest_sha
            )
            changed = _merge_index_entry(index, entry)
            if changed:
                _write_index(stable_root, index)
            return _result(
                existing,
                manifest_path,
                existing_manifest_sha,
                idempotent=True,
            )

        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_copy(source, artifact_path)
        destination_bytes, destination_sha = _file_identity(artifact_path)
        _require(
            destination_bytes == byte_count and destination_sha == sha256,
            "ARTIFACT_PERSISTED_HASH_MISMATCH",
        )

        manifest_data = _json_bytes(prepared)
        _atomic_write(manifest_path, manifest_data)
        payload, verified_bytes, verified_sha, manifest_sha = _verify_pair(
            stable_root, artifact_path, manifest_path
        )
        _require(
            verified_bytes == byte_count and verified_sha == sha256,
            "ARTIFACT_PERSISTED_HASH_MISMATCH",
        )
        entry = _index_entry_from_manifest(payload, manifest_path, manifest_sha)
        changed = _merge_index_entry(index, entry)
        if changed:
            try:
                _write_index(stable_root, index)
            except EvidenceError as exc:
                raise EvidenceError("INDEX_UPDATE_FAILED") from exc
        _verify_index_entry(stable_root, entry)
        return _result(payload, manifest_path, manifest_sha)


def _verify_index_entry(root: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    _validate_index_entry(dict(entry))
    artifact_path = _ensure_inside(root, Path(entry["stable_path"]))
    manifest_path = _ensure_inside(root, Path(entry["manifest_path"]))
    payload, byte_count, sha256, manifest_sha = _verify_pair(
        root, artifact_path, manifest_path
    )
    _require(payload["artifact_id"] == entry["artifact_id"], "INDEX_IDENTITY_MISMATCH")
    _require(byte_count == entry["bytes"], "INDEX_BYTE_COUNT_MISMATCH")
    _require(sha256 == entry["sha256"], "INDEX_ARTIFACT_HASH_MISMATCH")
    _require(manifest_sha == entry["manifest_sha256"], "INDEX_MANIFEST_HASH_MISMATCH")
    _require(
        entry["stable_path"] == payload["stable_path"]
        and entry["manifest_path"] == str(manifest_path),
        "INDEX_PATH_MISMATCH",
    )
    return _result(payload, manifest_path, manifest_sha)


def verify(
    artifact_id: str,
    *,
    root: Path | str = DEFAULT_ROOT,
) -> dict[str, Any]:
    stable_root = _ensure_root(root)
    artifact_id = _validate_artifact_id(artifact_id)
    index = _load_index(stable_root, allow_missing=False)
    matches = [item for item in index["entries"] if item["artifact_id"] == artifact_id]
    _require(len(matches) == 1, "INDEX_ENTRY_MISSING")
    return _verify_index_entry(stable_root, matches[0])


def backfill_existing_artifact(
    artifact_path: Path | str,
    *,
    root: Path | str = DEFAULT_ROOT,
) -> dict[str, Any]:
    stable_root = _ensure_root(root)
    artifact = _ensure_inside(stable_root, Path(artifact_path))
    manifest = artifact.parent / MANIFEST_FILENAME
    with _index_lock(stable_root):
        index = _load_index(stable_root, allow_missing=True)
        payload, byte_count, sha256, manifest_sha = _verify_pair(
            stable_root, artifact, manifest
        )
        entry = _index_entry_from_manifest(payload, manifest, manifest_sha)
        changed = _merge_index_entry(index, entry)
        if changed:
            try:
                _write_index(stable_root, index)
            except EvidenceError as exc:
                raise EvidenceError("INDEX_UPDATE_FAILED") from exc
        _verify_index_entry(stable_root, entry)
        return _result(payload, manifest, manifest_sha, idempotent=not changed)


def _manifest_paths_for_audit(
    root: Path,
    artifact_paths: Iterable[Path | str] | None,
) -> list[Path]:
    if artifact_paths is None:
        paths = sorted(root.rglob(MANIFEST_FILENAME))
        _require(paths is not None, "ARTIFACT_MISSING")
        return paths
    result = []
    for raw_path in artifact_paths:
        path = _ensure_inside(root, Path(raw_path))
        if path.name != MANIFEST_FILENAME:
            path = path.parent / MANIFEST_FILENAME
        result.append(path)
    return sorted(set(result))


def audit(
    *,
    root: Path | str = DEFAULT_ROOT,
    rebuild_index: bool = False,
    artifact_paths: Iterable[Path | str] | None = None,
) -> dict[str, Any]:
    stable_root = _ensure_root(root)
    if not rebuild_index:
        index = _load_index(stable_root, allow_missing=False)
        verified = [_verify_index_entry(stable_root, entry) for entry in index["entries"]]
        return {
            "status": "PASS",
            "audit": "verified",
            "entries": len(verified),
            "verified": "YES",
        }

    manifests = _manifest_paths_for_audit(stable_root, artifact_paths)
    verified_entries = []
    for manifest in manifests:
        artifact = manifest.parent / _manifest_payload(manifest)["filename"]
        payload, _bytes, _sha, manifest_sha = _verify_pair(
            stable_root, artifact, manifest
        )
        verified_entries.append(
            _index_entry_from_manifest(payload, manifest, manifest_sha)
        )

    with _index_lock(stable_root):
        if artifact_paths is None:
            index = {
                "schema_version": INDEX_SCHEMA_VERSION,
                "updated_at_utc": _now(),
                "entries": [],
            }
        else:
            index = _load_index(stable_root)
        for entry in verified_entries:
            _merge_index_entry(index, entry)
        _write_index(stable_root, index)
        for entry in index["entries"]:
            _verify_index_entry(stable_root, entry)
    return {
        "status": "PASS",
        "audit": "rebuild-index",
        "entries": len(index["entries"]),
        "verified": "YES",
    }


def lookup(
    *,
    root: Path | str = DEFAULT_ROOT,
    task: str | None = None,
    artifact_class: str | None = None,
    sha256: str | None = None,
    canonical_head: str | None = None,
    canonical_tree: str | None = None,
    owner_gate_ref: str | None = None,
) -> dict[str, Any]:
    stable_root = _ensure_root(root)
    index = _load_index(stable_root, allow_missing=False)
    if task is not None:
        _validate_component(task, "INVALID_TASK")
    if artifact_class is not None:
        _require(artifact_class in ARTIFACT_CLASSES, "INVALID_ARTIFACT_CLASS")
    if sha256 is not None:
        _validate_sha(sha256)
    _validate_optional_git_sha(canonical_head, "INVALID_CANONICAL_HEAD")
    _validate_optional_git_sha(canonical_tree, "INVALID_CANONICAL_TREE")
    matches = []
    for entry in index["entries"]:
        if task is not None and entry["task"] != task:
            continue
        if artifact_class is not None and entry["artifact_class"] != artifact_class:
            continue
        if sha256 is not None and entry["sha256"] != sha256:
            continue
        if canonical_head is not None and entry.get("canonical_head") != canonical_head:
            continue
        if canonical_tree is not None and entry.get("canonical_tree") != canonical_tree:
            continue
        if owner_gate_ref is not None and entry.get("owner_gate_ref") != owner_gate_ref:
            continue
        matches.append(entry)
    return {"status": "PASS", "entries": sorted(matches, key=lambda x: x["artifact_id"])}


def supersede(
    old_artifact_id: str,
    new_artifact_id: str,
    *,
    root: Path | str = DEFAULT_ROOT,
) -> dict[str, Any]:
    stable_root = _ensure_root(root)
    old_artifact_id = _validate_artifact_id(old_artifact_id)
    new_artifact_id = _validate_artifact_id(new_artifact_id)
    _require(old_artifact_id != new_artifact_id, "SUPERSESSION_SELF_REFERENCE")
    with _index_lock(stable_root):
        index = _load_index(stable_root, allow_missing=False)
        old = next(
            (item for item in index["entries"] if item["artifact_id"] == old_artifact_id),
            None,
        )
        new = next(
            (item for item in index["entries"] if item["artifact_id"] == new_artifact_id),
            None,
        )
        _require(old is not None and new is not None, "SUPERSESSION_ARTIFACT_MISSING")
        if new_artifact_id not in old["superseded_by"]:
            old["superseded_by"].append(new_artifact_id)
        if old_artifact_id not in new["supersedes"]:
            new["supersedes"].append(old_artifact_id)
        old["lifecycle_state"] = "SUPERSEDED"
        _write_index(stable_root, index)
        return {
            "status": "PASS",
            "supersedes": old_artifact_id,
            "superseded_by": new_artifact_id,
            "verified": "YES",
        }


def recover(
    source_path: Path | str,
    *,
    root: Path | str = DEFAULT_ROOT,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    state = metadata.get("authority_state")
    _require(
        state in {"RECOVERED_ORIGINAL", "RECONSTRUCTED"},
        "INVALID_RECOVERY_AUTHORITY_STATE",
    )
    if state == "RECOVERED_ORIGINAL":
        _require(
            isinstance(metadata.get("recovered_from"), str)
            and bool(metadata.get("recovered_from")),
            "RECOVERY_SOURCE_LINK_REQUIRED",
        )
    else:
        _require(
            isinstance(metadata.get("reconstruction_of"), str)
            and bool(metadata.get("reconstruction_of")),
            "RECONSTRUCTION_ORIGINAL_LINK_REQUIRED",
        )
        # A reconstruction is secondary evidence and must never reuse the
        # original content-bound identity.
        data = _read_source_bytes(_ensure_source(source_path))
        candidate_id = artifact_id_for(
            _validate_component(metadata.get("task"), "INVALID_TASK"),
            metadata.get("artifact_class"),
            _sha256_bytes(data),
        )
        _require(
            candidate_id != metadata.get("reconstruction_of"),
            "RECONSTRUCTION_ID_NOT_NEW",
        )
    return finalize(source_path, root=root, metadata=metadata)


def _load_metadata_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = _load_json(_ensure_source(path))
    _require(isinstance(payload, dict), "INVALID_METADATA")
    return payload


def _metadata_from_args(args: argparse.Namespace) -> dict[str, Any]:
    metadata = _load_metadata_json(args.metadata_json)
    direct = {
        "program": args.program,
        "task": args.task,
        "artifact_class": args.artifact_class,
        "filename": args.filename,
        "content_type": args.content_type,
        "producer": args.producer,
        "authority_state": args.authority_state,
        "lifecycle_state": args.lifecycle_state,
        "retention_class": args.retention_class,
        "canonical_head": args.canonical_head,
        "canonical_tree": args.canonical_tree,
        "owner_gate_ref": args.owner_gate_ref,
        "created_at_utc": args.created_at_utc,
        "recovered_from": args.recovered_from,
        "reconstruction_of": args.reconstruction_of,
        "notes": args.notes,
    }
    for key, value in direct.items():
        if value is not None:
            metadata[key] = value
    if args.provenance_json is not None:
        provenance = _load_json(_ensure_source(args.provenance_json))
        _require(isinstance(provenance, dict), "INVALID_PROVENANCE")
        metadata["provenance"] = provenance
    return metadata


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_artifact_arguments(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--source", type=Path, required=True)
        subparser.add_argument("--metadata-json", type=Path)
        subparser.add_argument("--program")
        subparser.add_argument("--task")
        subparser.add_argument("--artifact-class", choices=sorted(ARTIFACT_CLASSES))
        subparser.add_argument("--filename")
        subparser.add_argument("--content-type")
        subparser.add_argument("--producer")
        subparser.add_argument("--authority-state")
        subparser.add_argument("--lifecycle-state")
        subparser.add_argument("--retention-class")
        subparser.add_argument("--canonical-head")
        subparser.add_argument("--canonical-tree")
        subparser.add_argument("--owner-gate-ref")
        subparser.add_argument("--created-at-utc")
        subparser.add_argument("--recovered-from")
        subparser.add_argument("--reconstruction-of")
        subparser.add_argument("--provenance-json", type=Path)
        subparser.add_argument("--notes")

    register_parser = subparsers.add_parser("register")
    add_artifact_arguments(register_parser)
    finalize_parser = subparsers.add_parser("finalize")
    add_artifact_arguments(finalize_parser)
    recover_parser = subparsers.add_parser("recover")
    add_artifact_arguments(recover_parser)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--artifact-id", required=True)

    lookup_parser = subparsers.add_parser("lookup")
    lookup_parser.add_argument("--task")
    lookup_parser.add_argument("--artifact-class", choices=sorted(ARTIFACT_CLASSES))
    lookup_parser.add_argument("--sha256")
    lookup_parser.add_argument("--canonical-head")
    lookup_parser.add_argument("--canonical-tree")
    lookup_parser.add_argument("--owner-gate-ref")

    supersede_parser = subparsers.add_parser("supersede")
    supersede_parser.add_argument("--old-artifact-id", required=True)
    supersede_parser.add_argument("--new-artifact-id", required=True)

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--rebuild-index", action="store_true")
    audit_parser.add_argument("--path", action="append", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "register":
            result = register(
                args.source,
                root=args.root,
                metadata=_metadata_from_args(args),
            )
        elif args.command == "finalize":
            result = finalize(
                args.source,
                root=args.root,
                metadata=_metadata_from_args(args),
            )
        elif args.command == "recover":
            result = recover(
                args.source,
                root=args.root,
                metadata=_metadata_from_args(args),
            )
        elif args.command == "verify":
            result = verify(args.artifact_id, root=args.root)
        elif args.command == "lookup":
            result = lookup(
                root=args.root,
                task=args.task,
                artifact_class=args.artifact_class,
                sha256=args.sha256,
                canonical_head=args.canonical_head,
                canonical_tree=args.canonical_tree,
                owner_gate_ref=args.owner_gate_ref,
            )
        elif args.command == "supersede":
            result = supersede(
                args.old_artifact_id,
                args.new_artifact_id,
                root=args.root,
            )
        elif args.command == "audit":
            result = audit(
                root=args.root,
                rebuild_index=args.rebuild_index,
                artifact_paths=args.path,
            )
        else:  # pragma: no cover
            raise EvidenceError("UNSUPPORTED_COMMAND")
    except EvidenceError as exc:
        print(json.dumps({"status": "FAIL", "error": exc.code}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
