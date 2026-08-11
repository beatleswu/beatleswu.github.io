"""Fail-closed content publisher; verification-only unless explicitly gated."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from tools.content_release_core import GovernanceError, publish_content
except ModuleNotFoundError:  # Direct script execution.
    from content_release_core import GovernanceError, publish_content  # type: ignore[no-redef]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live", required=True, type=Path)
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
    result.add_argument("--expected-live-sha256", required=True)
    result.add_argument("--expected-candidate-sha256", required=True)
    result.add_argument("--expected-release-manifest-sha256", required=True)
    result.add_argument("--expected-record-count", required=True, type=int)
    result.add_argument("--expected-backup-tag", required=True)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--owner-gate", default="")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        evidence = publish_content(
            live=args.live,
            candidate=args.candidate,
            local_baseline_backup=args.local_baseline_backup,
            offsite_receipt=args.offsite_receipt,
            release_manifest=args.release_manifest,
            rollback_manifest=args.rollback_manifest,
            rollback_proof=args.rollback_proof,
            source_provenance=args.source_provenance,
            review_binding=args.review_binding,
            repair_batch_manifest=args.repair_batch_manifest,
            mutation_audit=args.mutation_audit,
            acceptance_evidence=args.acceptance_evidence,
            expected_live_sha256=args.expected_live_sha256,
            expected_candidate_sha256=args.expected_candidate_sha256,
            expected_release_manifest_sha256=args.expected_release_manifest_sha256,
            expected_record_count=args.expected_record_count,
            expected_backup_tag=args.expected_backup_tag,
            execute=args.execute,
            owner_gate=args.owner_gate,
        )
        print(json.dumps(evidence, indent=2, sort_keys=True))
    except GovernanceError as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
