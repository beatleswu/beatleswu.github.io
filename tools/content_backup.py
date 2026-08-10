"""Build and optionally round-trip a governed content backup bundle."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

try:
    from tools.content_release_core import (
        GitHubReleaseRegistry,
        GovernanceError,
        LocalReleaseRegistry,
        REMOTE_EXECUTION_GATE,
        build_backup_bundle,
        build_release_bundle,
        verify_release_round_trip,
        write_round_trip_receipt,
    )
except ModuleNotFoundError:  # Direct `python tools/content_backup.py` execution.
    from content_release_core import (  # type: ignore[no-redef]
        GitHubReleaseRegistry,
        GovernanceError,
        LocalReleaseRegistry,
        REMOTE_EXECUTION_GATE,
        build_backup_bundle,
        build_release_bundle,
        verify_release_round_trip,
        write_round_trip_receipt,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source", required=True, type=Path)
    result.add_argument("--output-dir", required=True, type=Path)
    result.add_argument("--bundle-role", choices=("baseline", "release"), default="baseline")
    result.add_argument("--expected-sha256", required=True)
    result.add_argument("--expected-record-count", required=True, type=int)
    result.add_argument("--artifact-role", default="pre_mutation_baseline")
    result.add_argument("--source-environment", default="production_read_only_stream")
    result.add_argument("--source-path-label", default="/app/data/questions.json")
    result.add_argument("--release-tag", required=True)
    result.add_argument("--baseline-sha256")
    result.add_argument("--release-manifest", type=Path)
    result.add_argument("--rollback-manifest", type=Path)
    result.add_argument("--expected-release-manifest-sha256")
    result.add_argument("--expected-rollback-manifest-sha256")
    result.add_argument("--release-records", type=int)
    result.add_argument("--excluded-map-battle-records", type=int)
    result.add_argument("--simulate-remote-dir", type=Path)
    result.add_argument("--github-repo")
    result.add_argument("--execute-remote", action="store_true")
    result.add_argument("--owner-gate", default="")
    return result


def run(args: argparse.Namespace) -> dict:
    if args.bundle_role == "release":
        required = {
            "baseline_sha256": args.baseline_sha256,
            "release_manifest": args.release_manifest,
            "rollback_manifest": args.rollback_manifest,
            "expected_release_manifest_sha256": args.expected_release_manifest_sha256,
            "expected_rollback_manifest_sha256": args.expected_rollback_manifest_sha256,
            "release_records": args.release_records,
            "excluded_map_battle_records": args.excluded_map_battle_records,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise GovernanceError(f"missing_release_bundle_arguments:{','.join(missing)}")
        bundle = build_release_bundle(
            candidate=args.source,
            release_manifest=args.release_manifest,
            rollback_manifest=args.rollback_manifest,
            output_dir=args.output_dir,
            expected_candidate_sha256=args.expected_sha256,
            expected_record_count=args.expected_record_count,
            expected_release_manifest_sha256=args.expected_release_manifest_sha256,
            expected_rollback_manifest_sha256=args.expected_rollback_manifest_sha256,
            baseline_sha256=args.baseline_sha256,
            release_records=args.release_records,
            excluded_map_battle_records=args.excluded_map_battle_records,
        )
        upload_paths = [
            Path(bundle.compressed_path),
            Path(bundle.release_manifest_path),
            Path(bundle.rollback_manifest_path),
            Path(bundle.registry_entry_path),
            Path(bundle.checksums_path),
        ]
    else:
        bundle = build_backup_bundle(
            source=args.source,
            output_dir=args.output_dir,
            expected_sha256=args.expected_sha256,
            expected_record_count=args.expected_record_count,
            artifact_role=args.artifact_role,
            source_environment=args.source_environment,
            source_path_label=args.source_path_label,
        )
        upload_paths = [Path(bundle.compressed_path), Path(bundle.manifest_path), Path(bundle.checksums_path)]
    evidence: dict = {"bundle": asdict(bundle), "remote_execution": "not_requested"}
    registry = None
    if args.simulate_remote_dir:
        registry = LocalReleaseRegistry(args.simulate_remote_dir, visibility="PRIVATE", tag=args.release_tag)
        registry.upload(upload_paths)
        evidence["remote_execution"] = "local_simulation"
    elif args.github_repo:
        registry = GitHubReleaseRegistry(
            args.github_repo,
            tag=args.release_tag,
            execute_remote=args.execute_remote,
            owner_gate=args.owner_gate,
        )
        if not args.execute_remote:
            raise GovernanceError("github_repo_supplied_without_execute_remote")
        if args.owner_gate != REMOTE_EXECUTION_GATE:
            raise GovernanceError("github_remote_execution_not_authorized")
        registry.prepare_release(title=args.release_tag, notes="Governed Go Odyssey content backup")
        registry.upload(upload_paths)
        evidence["remote_execution"] = "github_release"

    if registry is not None:
        receipt = verify_release_round_trip(
            registry=registry,
            source=args.source,
            local_compressed=Path(bundle.compressed_path),
            expected_source_sha256=args.expected_sha256,
            expected_record_count=args.expected_record_count,
            expected_tag=args.release_tag,
            download_dir=args.output_dir / "remote-redownload",
        )
        receipt_path = args.output_dir / "offsite-verification-receipt.json"
        write_round_trip_receipt(receipt_path, receipt)
        evidence["round_trip_receipt"] = asdict(receipt)
        evidence["round_trip_receipt_path"] = str(receipt_path)
    return evidence


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
