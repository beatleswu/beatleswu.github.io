"""Run baseline -> candidate -> byte-exact rollback in an isolated directory."""

from __future__ import annotations

import argparse
import filecmp
import json
import shutil
from pathlib import Path

try:
    from tools.content_release_core import (
        PUBLISH_EXECUTION_GATE,
        ROLLBACK_EXECUTION_GATE,
        GovernanceError,
        publish_content,
        rollback_content,
        sha256_file,
        simulated_directory_fsync,
        write_json,
    )
except ModuleNotFoundError:  # Direct script execution.
    from content_release_core import (  # type: ignore[no-redef]
        PUBLISH_EXECUTION_GATE,
        ROLLBACK_EXECUTION_GATE,
        GovernanceError,
        publish_content,
        rollback_content,
        sha256_file,
        simulated_directory_fsync,
        write_json,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--baseline", required=True, type=Path)
    result.add_argument("--candidate", required=True, type=Path)
    result.add_argument("--local-baseline-backup", required=True, type=Path)
    result.add_argument("--offsite-receipt", required=True, type=Path)
    result.add_argument("--release-manifest", required=True, type=Path)
    result.add_argument("--rollback-manifest", required=True, type=Path)
    result.add_argument("--rollback-proof", required=True, type=Path)
    result.add_argument("--source-provenance", required=True, type=Path)
    result.add_argument("--review-binding", required=True, type=Path)
    result.add_argument("--repair-batch-manifest", required=True, type=Path)
    result.add_argument("--mutation-audit", required=True, type=Path)
    result.add_argument("--acceptance-evidence", required=True, type=Path)
    result.add_argument("--expected-baseline-sha256", required=True)
    result.add_argument("--expected-candidate-sha256", required=True)
    result.add_argument("--expected-release-manifest-sha256", required=True)
    result.add_argument("--expected-rollback-manifest-sha256", required=True)
    result.add_argument("--expected-record-count", required=True, type=int)
    result.add_argument("--expected-backup-tag", required=True)
    result.add_argument("--simulation-dir", required=True, type=Path)
    return result


def run(args: argparse.Namespace) -> dict:
    if args.simulation_dir.exists():
        raise GovernanceError("simulation_directory_must_not_exist")
    args.simulation_dir.mkdir(parents=True)
    live = args.simulation_dir / "questions.live-simulation.json"
    shutil.copyfile(args.baseline, live)
    publish = publish_content(
        live=live,
        candidate=args.candidate,
        local_baseline_backup=args.local_baseline_backup,
        offsite_receipt=args.offsite_receipt,
        release_manifest=args.release_manifest,
        expected_live_sha256=args.expected_baseline_sha256,
        expected_candidate_sha256=args.expected_candidate_sha256,
        expected_release_manifest_sha256=args.expected_release_manifest_sha256,
        expected_record_count=args.expected_record_count,
        expected_backup_tag=args.expected_backup_tag,
        rollback_manifest=args.rollback_manifest,
        rollback_proof=args.rollback_proof,
        source_provenance=args.source_provenance,
        review_binding=args.review_binding,
        repair_batch_manifest=args.repair_batch_manifest,
        mutation_audit=args.mutation_audit,
        acceptance_evidence=args.acceptance_evidence,
        execute=True,
        owner_gate=PUBLISH_EXECUTION_GATE,
        directory_fsync=simulated_directory_fsync,
    )
    published_sha256 = sha256_file(live)
    rollback = rollback_content(
        live=live,
        baseline=args.baseline,
        rollback_manifest=args.rollback_manifest,
        expected_current_sha256=args.expected_candidate_sha256,
        expected_baseline_sha256=args.expected_baseline_sha256,
        expected_rollback_manifest_sha256=args.expected_rollback_manifest_sha256,
        expected_record_count=args.expected_record_count,
        rollback_proof=args.rollback_proof,
        execute=True,
        owner_gate=ROLLBACK_EXECUTION_GATE,
        directory_fsync=simulated_directory_fsync,
    )
    final_sha256 = sha256_file(live)
    result = {
        "simulation_scope": str(args.simulation_dir.resolve()),
        "production_contact": "NONE",
        "publish": publish,
        "published_sha256": published_sha256,
        "rollback": rollback,
        "rollback_final_sha256": final_sha256,
        "rollback_byte_exact": filecmp.cmp(live, args.baseline, shallow=False),
    }
    write_json(args.simulation_dir / "simulation-evidence.json", result)
    return result


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
