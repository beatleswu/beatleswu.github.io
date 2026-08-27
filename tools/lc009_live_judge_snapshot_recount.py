"""LC009 — full-snapshot recount against the LIVE canonical judge (READ-ONLY).

Walks every record of the byte-verified canonical snapshot through the
*shipped* ``canonical_learning_judge._explicit_terminal_is_correct`` (the
Owner-approved LC009 marker contract) and buckets each record's terminal
semantics, then diffs the result against the pre-LC009 baseline (Policy A of
``docs/planning/lc007_marker_policy_impact.json``).

Owner-approved expectation:
    MALFORMED 163 | AMBIGUOUS 731 | EXPLICIT_SUCCESS 0 | EXPLICIT_FAILURE 0 |
    UNVERIFIABLE 41910
    CHANGED_RECORD_COUNT = 1   CHANGED_RECORD_INDEXES = [17147]   NEWLY_ACCEPTED = 0

Mutates nothing: no corpus write, no Production read, no marker apply. Only the
tree-walk (`bucket_for`) is reused from the LC007 simulator; the verdict
function passed in is the real judge primitive, not the simulator's copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from canonical_learning_judge import (  # noqa: E402
    CANONICAL_JUDGE_VERSION,
    _explicit_terminal_is_correct,
)
from tools.lc007_marker_policy_simulation import BUCKETS, POLICIES, bucket_for  # noqa: E402

EXPECTED_SNAPSHOT_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
EXPECTED_RECORD_COUNT = 42804
LC009_TOOL_VERSION = "lc009-live-judge-snapshot-recount-v1"

# pre-LC009 baseline == LC007 impact JSON, per_policy_bucket.A
_LC007_IMPACT = _REPO / "docs" / "planning" / "lc007_marker_policy_impact.json"

APPROVED_BUCKETS = {
    "MALFORMED": 163,
    "AMBIGUOUS": 731,
    "EXPLICIT_SUCCESS": 0,
    "EXPLICIT_FAILURE": 0,
    "UNVERIFIABLE": 41910,
}
APPROVED_CHANGED_INDEXES = [17147]


def _content_sha(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def verify_snapshot(path: Path) -> tuple[str, bool, list[dict[str, Any]]]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_SNAPSHOT_SHA256:
        return sha, False, []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("snapshot must be a JSON list")
    return sha, True, data


def _baseline_buckets() -> dict[str, int]:
    doc = json.loads(_LC007_IMPACT.read_bytes())
    return dict(doc["per_policy_bucket"]["A"])


def run(path: Path, out_impact: Path | None) -> dict[str, Any]:
    sha, match, records = verify_snapshot(path)
    if not match:
        raise SystemExit(
            f"SNAPSHOT_HASH_MISMATCH: got {sha}, expected {EXPECTED_SNAPSHOT_SHA256}. STOP."
        )
    baseline = _baseline_buckets()

    counts = {b: 0 for b in BUCKETS}
    changed: list[dict[str, Any]] = []
    newly_accepted: list[int] = []
    newly_rejected: list[int] = []
    for idx, rec in enumerate(records):
        content = rec.get("content") or ""
        live = bucket_for(content, _explicit_terminal_is_correct)
        counts[live] += 1
        # per-record pre-LC009 bucket: the frozen Policy A (substring) model
        before = bucket_for(content, POLICIES["A"])
        if before != live:
            changed.append({
                "record_index": idx,
                "legacy_question_id": rec.get("id"),
                "content_sha256": _content_sha(content),
                "from_bucket": before,
                "to_bucket": live,
            })
            if live == "EXPLICIT_SUCCESS" and before != "EXPLICIT_SUCCESS":
                newly_accepted.append(idx)
            if before == "EXPLICIT_SUCCESS" and live != "EXPLICIT_SUCCESS":
                newly_rejected.append(idx)

    changed_indexes = [c["record_index"] for c in changed]
    impact = {
        "lc009_tool_version": LC009_TOOL_VERSION,
        "judge_version": CANONICAL_JUDGE_VERSION,
        "snapshot_sha256": sha,
        "snapshot_hash_match": match,
        "record_count": len(records),
        "record_count_match": len(records) == EXPECTED_RECORD_COUNT,
        "live_buckets": counts,
        "pre_lc009_buckets": baseline,
        "approved_buckets": APPROVED_BUCKETS,
        "buckets_match_approved": counts == APPROVED_BUCKETS,
        "changed_record_count": len(changed),
        "changed_record_indexes": changed_indexes,
        "changed_record_indexes_match_approved": changed_indexes == APPROVED_CHANGED_INDEXES,
        "changed_records": changed,
        "newly_accepted": newly_accepted,
        "newly_accepted_count": len(newly_accepted),
        "newly_rejected": newly_rejected,
        "newly_rejected_count": len(newly_rejected),
        "corpus_mutation": False,
    }
    impact_sha = None
    if out_impact is not None:
        out_impact.write_bytes(
            (json.dumps(impact, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        )
        impact_sha = hashlib.sha256(out_impact.read_bytes()).hexdigest()
    return {"impact": impact, "impact_path": out_impact.as_posix() if out_impact else None,
            "impact_sha256": impact_sha}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LC009 live-judge full-snapshot recount (read-only).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--out-impact", type=Path)
    args = p.parse_args(argv)
    if not args.snapshot.exists():
        raise SystemExit(f"snapshot not found: {args.snapshot}")
    result = run(args.snapshot, args.out_impact)
    imp = dict(result["impact"])
    imp.pop("changed_records", None)
    imp["impact_path"] = result["impact_path"]
    imp["impact_sha256"] = result["impact_sha256"]
    print(json.dumps(imp, indent=2, ensure_ascii=False))
    ok = imp["buckets_match_approved"] and imp["changed_record_indexes_match_approved"] \
        and imp["newly_accepted_count"] == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
