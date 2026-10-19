"""Read-only source admission checker for the owner-approved 13-star maintenance.

THIS IS NOT A SIGNATURE OR EXECUTION PERMIT.  A separately trusted
Owner/Reviewer executor must verify the pinned manifest hash through its own
authority channel, attest the machine/command, and grant one specific run.
This module does not import, run, extract or stage bundle contents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import stat
import zipfile

MAINTENANCE_FILES = frozenset({
    "tools/incident_019b_owner_scoped_production_apply_20261019.py",
    "tools/incident_019b_historical_second_star_catchup.py",
    "migrations/adventure_zone_star_historical_catchup_v1.py",
})
RUNTIME_DEPENDENCIES = frozenset({
    "db.py",
    "adventure_progress_compatibility.py",
    "adventure_zone_progression_authority.py",
})
MAX_FILE_BYTES = 128 * 1024
MAX_MANIFEST_BYTES = 32 * 1024
EXPECTED_COUNT = 3


class BundleRefused(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_archive(
    archive: pathlib.Path,
    manifest_path: pathlib.Path,
    *,
    expected_manifest_sha256: str,
    runtime_root: pathlib.Path | None = None,
) -> dict:
    # Pin obtained from the independent reviewer. Trusting the manifest found
    # beside an archive without this out-of-band pin would be self-assertion.
    if len(expected_manifest_sha256) != 64:
        raise BundleRefused("trusted pinned SHA-256 required")
    raw = manifest_path.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES or sha256(raw) != expected_manifest_sha256:
        raise BundleRefused("manifest is not the independently pinned version")
    manifest = json.loads(raw.decode("utf-8"))
    if manifest.get("status") != "SOURCE_REVIEW_PACKAGE_ONLY_NOT_A_EXECUTION_PERMIT":
        raise BundleRefused("source audit status mismatch")
    if manifest.get("production_observation", {}).get("production_change_committed") is not False:
        raise BundleRefused("expected no committed production write")
    approved = manifest.get("source", {})
    if set(approved) != MAINTENANCE_FILES or len(approved) != EXPECTED_COUNT:
        raise BundleRefused("wrong approved source set")
    if manifest.get("immutable_preflight", {}).get("eligible_unawarded_users") != 13:
        raise BundleRefused("scope is not the approved 13-player batch")

    with zipfile.ZipFile(archive, "r") as z:
        files = z.infolist()
        if len(files) != EXPECTED_COUNT or set(v.filename for v in files) != MAINTENANCE_FILES:
            raise BundleRefused("archive contains missing, duplicate or additional files")
        for info in files:
            if (
                info.is_dir() or info.flag_bits & 0x1
                or info.file_size < 1 or info.file_size > MAX_FILE_BYTES
                or info.filename.startswith("/")
                or "\\" in info.filename
                or ".." in pathlib.PurePosixPath(info.filename).parts
            ):
                raise BundleRefused("unsafe or oversize archive entry")
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise BundleRefused("archive symlink not allowed")
            contents = z.read(info)
            expected = approved[info.filename]
            if len(contents) != expected["size_bytes"] or sha256(contents) != expected["sha256"]:
                raise BundleRefused("source bytes differ from reviewed version")

    checked_runtime = False
    if runtime_root is not None:
        checked = manifest.get("production_runtime_dependencies_sha256", {})
        if set(checked) != RUNTIME_DEPENDENCIES:
            raise BundleRefused("runtime dependency hash contract missing")
        for rel, known_sha in checked.items():
            p = runtime_root / rel
            if not p.is_file() or sha256(p.read_bytes()) != known_sha:
                raise BundleRefused("runtime dependency checksum mismatch")
        checked_runtime = True

    return {
        "verdict": "SOURCE_BYTES_MATCH_REVIEWED_MANIFEST_NOT_EXECUTION_AUTHORITY",
        "file_count": len(approved),
        "manifest_sha256": expected_manifest_sha256,
        "archive_sha256": sha256(archive.read_bytes()),
        "runtime_dependencies_byte_identical": checked_runtime,
        "production_mutated": False,
        "independent_execution_permit_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--pinned-manifest-sha256", required=True)
    parser.add_argument("--runtime-root", type=pathlib.Path)
    args = parser.parse_args()
    result = verify_archive(
        args.bundle, args.manifest,
        expected_manifest_sha256=args.pinned_manifest_sha256,
        runtime_root=args.runtime_root,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
