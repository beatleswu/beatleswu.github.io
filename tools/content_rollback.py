"""Separately gated byte-exact content rollback runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from tools.content_release_core import GovernanceError, rollback_content
except ModuleNotFoundError:  # Direct script execution.
    from content_release_core import GovernanceError, rollback_content  # type: ignore[no-redef]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--live", required=True, type=Path)
    result.add_argument("--baseline", required=True, type=Path)
    result.add_argument("--rollback-manifest", required=True, type=Path)
    result.add_argument("--rollback-proof", required=True, type=Path)
    result.add_argument("--expected-current-sha256", required=True)
    result.add_argument("--expected-baseline-sha256", required=True)
    result.add_argument("--expected-rollback-manifest-sha256", required=True)
    result.add_argument("--expected-record-count", required=True, type=int)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--owner-gate", default="")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        evidence = rollback_content(
            live=args.live,
            baseline=args.baseline,
            rollback_manifest=args.rollback_manifest,
            rollback_proof=args.rollback_proof,
            expected_current_sha256=args.expected_current_sha256,
            expected_baseline_sha256=args.expected_baseline_sha256,
            expected_rollback_manifest_sha256=args.expected_rollback_manifest_sha256,
            expected_record_count=args.expected_record_count,
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
