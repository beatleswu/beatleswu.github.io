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
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Protocol


CHUNK_SIZE = 1024 * 1024
PRIVATE_VISIBILITY = "PRIVATE"
REMOTE_EXECUTION_GATE = "GO_GITHUB_CONTENT_BACKUP_RELEASE"
PUBLISH_EXECUTION_GATE = "GO_PRODUCTION_CONTENT_RELEASE_54"
ROLLBACK_EXECUTION_GATE = "GO_PRODUCTION_CONTENT_ROLLBACK_54"


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
    offsite_backup_verified: bool


class ReleaseRegistry(Protocol):
    @property
    def visibility(self) -> str: ...

    @property
    def tag(self) -> str: ...

    def upload(self, paths: Iterable[Path]) -> None: ...

    def asset_exists(self, name: str) -> bool: ...

    def download(self, name: str, destination: Path) -> Path: ...


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


def verify_sha256sums(path: Path, directory: Path) -> None:
    if not path.is_file():
        raise GovernanceError("missing_sha256sums")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise GovernanceError("unreadable_sha256sums") from exc
    if not lines:
        raise GovernanceError("empty_sha256sums")
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise GovernanceError("malformed_sha256sums")
        expected, name = parts
        asset = directory / name
        if not asset.is_file():
            raise GovernanceError(f"missing_release_asset:{name}")
        if sha256_file(asset) != expected:
            raise GovernanceError(f"release_asset_hash_mismatch:{name}")


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
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise GovernanceError(f"backup_manifest_missing_fields:{','.join(missing)}")


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
) -> BackupBundle:
    identity = verify_json_identity(
        source,
        expected_sha256=expected_sha256,
        expected_record_count=expected_record_count,
        label="backup_source",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    compressed = output_dir / compressed_filename
    compressed_sha256 = deterministic_gzip(source, compressed)
    manifest = {
        "schema_version": "1.0",
        "artifact_role": artifact_role,
        "created_at_utc": created_at_utc or utc_now(),
        "source_environment": source_environment,
        "source_path": source_path_label,
        "record_count": identity.record_count,
        "uncompressed_byte_count": identity.size_bytes,
        "uncompressed_sha256": identity.sha256,
        "compressed_filename": compressed.name,
        "compressed_sha256": compressed_sha256,
        "baseline_sha256": expected_sha256,
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
    checksums = directory / "SHA256SUMS.txt"
    verify_sha256sums(checksums, directory)
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
    load_json_object(release_manifest, label="release_manifest")
    load_json_object(rollback_manifest, label="rollback_manifest")

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

    registry_entry = {
        "schema_version": "1.0",
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
        "release_records": release_records,
        "excluded_map_battle_records": excluded_map_battle_records,
    }
    registry_entry_path = output_dir / "content-registry-entry.json"
    write_json(registry_entry_path, registry_entry)
    checksums = output_dir / "SHA256SUMS.txt"
    write_sha256sums(
        checksums,
        (compressed, copied_release_manifest, copied_rollback_manifest, registry_entry_path),
    )
    return ReleaseBundle(
        candidate=identity,
        compressed_path=str(compressed),
        compressed_sha256=compressed_sha256,
        release_manifest_path=str(copied_release_manifest),
        rollback_manifest_path=str(copied_rollback_manifest),
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
            ["gh", "release", "view", self._tag, "--repo", self.repository, "--json", "tagName"],
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
                if json.loads(completed.stdout).get("tagName") != self._tag:
                    raise GovernanceError("wrong_release_tag")
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
        raw = self._run(["release", "view", self._tag, "--repo", self.repository, "--json", "assets,tagName"])
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GovernanceError("github_release_metadata_malformed") from exc
        if payload.get("tagName") != self._tag:
            raise GovernanceError("wrong_release_tag")
        return name in {asset.get("name") for asset in payload.get("assets", [])}

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


def verify_release_round_trip(
    *,
    registry: ReleaseRegistry,
    source: Path,
    local_compressed: Path,
    expected_source_sha256: str,
    expected_record_count: int,
    expected_tag: str,
    download_dir: Path,
) -> RoundTripReceipt:
    if registry.visibility.upper() != PRIVATE_VISIBILITY:
        raise GovernanceError("content_repo_visibility_not_private")
    if registry.tag != expected_tag:
        raise GovernanceError("wrong_release_tag")
    if not registry.asset_exists(local_compressed.name):
        raise GovernanceError(f"missing_release_asset:{local_compressed.name}")

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

    return RoundTripReceipt(
        source_uncompressed_sha256=source_identity.sha256,
        local_uncompressed_sha256=local_identity.sha256,
        remote_uncompressed_sha256=remote_identity.sha256,
        record_count=source_identity.record_count,
        repository_visibility=registry.visibility.upper(),
        release_tag=registry.tag,
        remote_asset_name=remote.name,
        remote_asset_sha256=remote_compressed_sha,
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
    )
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
    verify_round_trip_receipt(
        offsite_receipt,
        expected_sha256=expected_live_sha256,
        expected_record_count=expected_record_count,
        expected_tag=expected_backup_tag,
    )
    _verify_manifest(release_manifest, expected_release_manifest_sha256, "release_manifest")
    return {
        "live": asdict(live_identity),
        "candidate": asdict(candidate_identity),
        "local_baseline_backup": asdict(backup_identity),
        "offsite_backup_verified": True,
        "release_manifest_verified": True,
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
    evidence = {
        "current": asdict(current),
        "baseline": asdict(baseline_identity),
        "rollback_manifest_verified": True,
        "mode": "dry-run",
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
