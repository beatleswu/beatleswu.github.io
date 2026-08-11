"""Verify content bundles and the triple-hash off-site backup gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

try:
    from tools.content_release_core import (
        GovernanceError,
        LocalReleaseRegistry,
        verify_backup_bundle,
        verify_release_round_trip,
    )
except ModuleNotFoundError:  # Direct script execution.
    from content_release_core import (  # type: ignore[no-redef]
        GovernanceError,
        LocalReleaseRegistry,
        verify_backup_bundle,
        verify_release_round_trip,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    bundle = subparsers.add_parser("bundle")
    bundle.add_argument("--directory", required=True, type=Path)
    triple = subparsers.add_parser("triple-hash-local")
    triple.add_argument("--source", required=True, type=Path)
    triple.add_argument("--compressed", required=True, type=Path)
    triple.add_argument("--remote-dir", required=True, type=Path)
    triple.add_argument("--release-tag", required=True)
    triple.add_argument("--expected-sha256", required=True)
    triple.add_argument("--expected-record-count", required=True, type=int)
    triple.add_argument("--download-dir", required=True, type=Path)
    return result


def run(args: argparse.Namespace) -> dict:
    if args.command == "bundle":
        return {"bundle": asdict(verify_backup_bundle(args.directory))}
    registry = LocalReleaseRegistry(args.remote_dir, visibility="PRIVATE", tag=args.release_tag)
    receipt = verify_release_round_trip(
        registry=registry,
        source=args.source,
        local_compressed=args.compressed,
        expected_source_sha256=args.expected_sha256,
        expected_record_count=args.expected_record_count,
        expected_tag=args.release_tag,
        download_dir=args.download_dir,
    )
    return {"triple_hash": asdict(receipt)}


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(run(args), indent=2, sort_keys=True))
    except GovernanceError as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
