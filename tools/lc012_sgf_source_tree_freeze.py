"""LC012 — SGF source-tree genesis freeze + manifest closure (READ-ONLY).

Two independent halves:

  CORPUS SIDE (always available):  over the frozen questions.json snapshot,
    canonicalise every ``source`` with canon-source-v1 and compute the
    ratified LC011 genesis UUIDv5. Prove: 42,804 canonical sources, 0
    canonical-path collisions, 0 SOURCE_NOT_RECOVERABLE, 42,804 distinct
    proposed UUIDs, 404/404 content-duplicate groups + 13/13 legacy-collision
    records separable, cross-process deterministic.

  TREE SIDE (needs an authoritative external SGF tree):  inventory every .sgf
    file, build a deterministic SGF_SOURCE_TREE_GENESIS_MANIFEST, join it to
    the frozen corpus by canonical source alias, classify every byte
    difference, and run the drift fail-closed gate (A..J).

LC012 could NOT locate an authoritative SGF source tree for the 42,804 frozen
snapshot (see docs/planning/lc012_sgf_source_tree_genesis_freeze_report.md),
so the TREE SIDE returns TREE_AUTHORITY_UNRESOLVED and NO genesis record
manifest is produced (§21). Nothing is mutated: no corpus write, no SGF write,
no ``source_record_uuid`` backfill, no schema, no ``app.py``, no LC009 change.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.lc011_identity_registry_prototype import (  # noqa: E402
    CANONICALISATION_RULES_VERSION,
    GENESIS_KEY_SPEC_VERSION,
    PROPOSED_CANONICAL_NAMESPACE_UUID,
    assert_namespace,
    canonical_source_key,
    mint_genesis_uuid,
)

LC012_TOOL_VERSION = "lc012-sgf-source-tree-freeze-v1"
GENESIS_SNAPSHOT_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
EXPECTED_RECORD_COUNT = 42804
CORPUS_ID = "godokoro-canonical"

# LC008 / LC010 / LC011 established
DUPLICATE_CONTENT_GROUP_COUNT = 404
DUPLICATE_CONTENT_RECORD_COUNT = 940
LEGACY_COLLISION_INDEXES = (
    16715, 16716, 16751, 16786, 16787, 17094,
    32194, 33715, 41082, 41155, 41283, 41321, 41467,
)

_BS = chr(92)


def _sha256_str(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# corpus side
# --------------------------------------------------------------------------- #

def verify_snapshot(path: Path) -> tuple[str, bool, list[dict[str, Any]]]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != GENESIS_SNAPSHOT_SHA256:
        return sha, False, []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("snapshot must be a JSON list")
    return sha, True, data


def corpus_side(records: list[dict[str, Any]]) -> dict[str, Any]:
    assert_namespace(PROPOSED_CANONICAL_NAMESPACE_UUID)
    rows = []
    canon_errors = collections.Counter()
    canon_keys: list[str | None] = []
    for i, r in enumerate(records):
        raw = r.get("source")
        canon, err = canonical_source_key(raw)
        canon_keys.append(canon)
        uid = None
        if err:
            canon_errors[err] += 1
        else:
            uid = mint_genesis_uuid(canon)
        rows.append({
            "record_index": i,                                   # AUDIT ONLY
            "legacy_question_id": r.get("id"),                   # ALIAS ONLY
            "raw_source": raw,
            "canonical_source": canon,
            "content_sha256": _sha256_str(r.get("content") or ""),
            "proposed_source_record_uuid": uid,
        })

    key_counts = collections.Counter(k for k in canon_keys if k is not None)
    canonical_path_collisions = sorted(k for k, c in key_counts.items() if c > 1)
    uids = [row["proposed_source_record_uuid"] for row in rows if row["proposed_source_record_uuid"]]
    uid_dupes = sorted(u for u, c in collections.Counter(uids).items() if c > 1)

    # 404 content-duplicate groups separability
    by_content: dict[str, list[int]] = collections.defaultdict(list)
    for i, r in enumerate(records):
        by_content[_sha256_str(r.get("content") or "")].append(i)
    dup_groups = {h: idxs for h, idxs in by_content.items() if len(idxs) > 1}
    dup_separable = sum(
        1 for idxs in dup_groups.values()
        if len({rows[i]["proposed_source_record_uuid"] for i in idxs
                if rows[i]["proposed_source_record_uuid"]}) == len(idxs)
    )

    # 13 legacy-collision records separability
    lc_uids = [rows[i]["proposed_source_record_uuid"] for i in LEGACY_COLLISION_INDEXES]
    lc_separable = len({u for u in lc_uids if u}) == len(LEGACY_COLLISION_INDEXES)

    # deterministic digest of the full sorted UUID list (for cross-process check)
    uid_list_sha = hashlib.sha256("\n".join(sorted(uids)).encode("utf-8")).hexdigest()

    return {
        "namespace_uuid": PROPOSED_CANONICAL_NAMESPACE_UUID,
        "genesis_key_spec_version": GENESIS_KEY_SPEC_VERSION,
        "canonicalisation_rules_version": CANONICALISATION_RULES_VERSION,
        "corpus_record_count": len(records),
        "distinct_canonical_sources": len(set(k for k in canon_keys if k is not None)),
        "canonicalisation_fail_closed_counts": dict(canon_errors),
        "source_not_recoverable": sum(canon_errors.values()),
        "canonical_path_collisions": canonical_path_collisions,
        "canonical_path_collision_count": len(canonical_path_collisions),
        "proposed_uuid_count": len(uids),
        "distinct_uuid_count": len(set(uids)),
        "uuid_collisions": uid_dupes,
        "uuid_collision_count": len(uid_dupes),
        "uuid_list_sha256": uid_list_sha,
        "duplicate_content_group_count": len(dup_groups),
        "duplicate_content_groups_separable": dup_separable,
        "legacy_collision_records": len(LEGACY_COLLISION_INDEXES),
        "legacy_collision_records_separable": lc_separable,
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# tree side
# --------------------------------------------------------------------------- #

def tree_inventory(root: Path) -> dict[str, Any] | None:
    if not root.is_dir():
        return None
    files = []
    for dp, dns, fns in os.walk(root):
        dns.sort()
        for fn in sorted(fns):
            if not fn.lower().endswith(".sgf"):
                continue
            full = Path(dp) / fn
            raw_rel = os.path.relpath(full, root)
            try:
                data = full.read_bytes()
            except OSError:
                continue
            canon, err = canonical_source_key(raw_rel)
            files.append({
                "raw_relative_path": raw_rel,
                "canonical_relative_path": canon,
                "canonicalisation_error": err,
                "content_sha256": hashlib.sha256(data).hexdigest(),
                "byte_size": len(data),
                "collection": (canon.split("/", 1)[0] if canon else None),
            })
    files.sort(key=lambda f: (f["canonical_relative_path"] or "", f["raw_relative_path"]))
    # deterministic tree-manifest hash: sorted "canon\tsize\tsha" lines
    body = "\n".join(
        f"{f['canonical_relative_path']}\t{f['byte_size']}\t{f['content_sha256']}"
        for f in files
    ).encode("utf-8")
    key_counts = collections.Counter(f["canonical_relative_path"] for f in files
                                     if f["canonical_relative_path"])
    return {
        "sgf_file_count": len(files),
        "canonical_path_collisions": sorted(k for k, c in key_counts.items() if c > 1),
        "canonicalisation_error_count": sum(1 for f in files if f["canonicalisation_error"]),
        "tree_manifest_sha256": hashlib.sha256(body).hexdigest(),
        "files": files,
    }


def join_corpus_to_tree(corpus_rows: list[dict[str, Any]], tree: dict[str, Any]) -> dict[str, Any]:
    by_canon = {f["canonical_relative_path"]: f for f in tree["files"] if f["canonical_relative_path"]}
    matched = missing = ambiguous = content_equal = builder_transform = drift = 0
    audit = []
    for row in corpus_rows:
        ck = row["canonical_source"]
        f = by_canon.get(ck)
        if ck is None:
            status = "SOURCE_NOT_RECOVERABLE"; missing += 1
        elif f is None:
            status = "MISSING_SOURCE"; missing += 1
        else:
            matched += 1
            if f["content_sha256"] == row["content_sha256"]:
                status = "EXACT_RAW_EQUIVALENT"; content_equal += 1
            else:
                # no canonical build_questions.py in-repo -> cannot certify a transform
                status = "UNEXPLAINED_CONTENT_DRIFT"; drift += 1
        audit.append({
            "record_index": row["record_index"], "legacy_question_id": row["legacy_question_id"],
            "raw_source": row["raw_source"], "canonical_source": ck,
            "corpus_content_sha256": row["content_sha256"],
            "sgf_tree_content_sha256": (f["content_sha256"] if f else None),
            "source_tree_match_status": status,
        })
    return {
        "corpus_records": len(corpus_rows),
        "matched_to_source_tree": matched,
        "missing_source": missing,
        "ambiguous_source": ambiguous,
        "exact_raw_equivalent_count": content_equal,
        "expected_builder_transform_count": builder_transform,
        "unexplained_content_drift_count": drift,
        "audit_sample": audit[:25] + audit[-25:],
    }


# --------------------------------------------------------------------------- #
# once-only genesis bootstrap gate (§27)
# --------------------------------------------------------------------------- #

def validate_once_only_gate(*, corpus_id: str, snapshot_sha256: str, record_count: int,
                            sgf_tree_manifest_sha256: str | None, namespace_uuid: str,
                            genesis_key_spec_version: str, canonicalisation_rules_version: str,
                            prior_bootstrap: dict[str, Any] | None) -> dict[str, Any]:
    required = {
        "corpus_id": corpus_id, "snapshot_sha256": snapshot_sha256.strip().lower(),
        "record_count": record_count, "sgf_tree_manifest_sha256": sgf_tree_manifest_sha256,
        "namespace_uuid": namespace_uuid, "genesis_key_spec_version": genesis_key_spec_version,
        "canonicalisation_rules_version": canonicalisation_rules_version,
    }
    ok_static = (
        snapshot_sha256.strip().lower() == GENESIS_SNAPSHOT_SHA256
        and record_count == EXPECTED_RECORD_COUNT
        and namespace_uuid == PROPOSED_CANONICAL_NAMESPACE_UUID
        and genesis_key_spec_version == GENESIS_KEY_SPEC_VERSION
        and canonicalisation_rules_version == CANONICALISATION_RULES_VERSION
        and sgf_tree_manifest_sha256 is not None
    )
    if prior_bootstrap is None:
        return {"safe_to_bootstrap": bool(ok_static), "reason": "no prior bootstrap",
                "required_keys": sorted(required), "static_inputs_valid": bool(ok_static)}
    same = prior_bootstrap == required
    return {"safe_to_bootstrap": False,
            "reason": "idempotent re-entry (identical)" if same
                      else "REFUSED — a genesis bootstrap already ran for a different input",
            "prior_matches": same, "static_inputs_valid": bool(ok_static)}


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #

def run(snapshot: Path, tree_root: Path | None, out_report: Path | None) -> dict[str, Any]:
    sha, match, records = verify_snapshot(snapshot)
    if not match:
        raise SystemExit(f"SNAPSHOT_HASH_MISMATCH: {sha} != {GENESIS_SNAPSHOT_SHA256}. STOP.")

    cs = corpus_side(records)
    tree = tree_inventory(tree_root) if tree_root is not None else None

    result: dict[str, Any] = {
        "lc012_tool_version": LC012_TOOL_VERSION,
        "prototype_only": True,
        "corpus_mutated": False,
        "sgf_content_mutated": False,
        "sgf_source_files_mutated": 0,
        "source_record_uuid_backfill": False,
        "lc009_semantics_changed": False,
        "snapshot_sha256": sha,
        "snapshot_hash_match": match,
        "corpus_record_count": len(records),
        "namespace_uuid": PROPOSED_CANONICAL_NAMESPACE_UUID,
        "genesis_key_spec_version": GENESIS_KEY_SPEC_VERSION,
        "canonicalisation_rules_version": CANONICALISATION_RULES_VERSION,
        "corpus_side": {k: v for k, v in cs.items() if k != "rows"},
        "genesis_bootstrap_once_only_gate": validate_once_only_gate(
            corpus_id=CORPUS_ID, snapshot_sha256=sha, record_count=len(records),
            sgf_tree_manifest_sha256=(tree["tree_manifest_sha256"] if tree else None),
            namespace_uuid=PROPOSED_CANONICAL_NAMESPACE_UUID,
            genesis_key_spec_version=GENESIS_KEY_SPEC_VERSION,
            canonicalisation_rules_version=CANONICALISATION_RULES_VERSION,
            prior_bootstrap=None),
    }

    if tree is None:
        result["tree_side"] = {
            "status": "TREE_AUTHORITY_UNRESOLVED",
            "actual_source_tree_traced": False,
            "note": "no authoritative SGF source tree for the 42,804 frozen snapshot was located; "
                    "see lc012_sgf_source_tree_genesis_freeze_report.md",
        }
        result["genesis_record_manifest"] = {
            "status": "NOT_GENERATED",
            "reason": "§21 — a genesis record manifest is produced ONLY if all source-tree "
                      "reconciliation gates pass; ACTUAL_SOURCE_TREE_TRACED = NO",
        }
        result["result"] = "STOP_AND_REPORT: SOURCE_TREE_AUTHORITY_UNRESOLVED"
    else:
        join = join_corpus_to_tree(cs["rows"], tree)
        gates_pass = (
            tree["sgf_file_count"] == EXPECTED_RECORD_COUNT
            and join["matched_to_source_tree"] == EXPECTED_RECORD_COUNT
            and join["missing_source"] == 0 and join["ambiguous_source"] == 0
            and not tree["canonical_path_collisions"]
            and join["unexplained_content_drift_count"] == 0
            and cs["source_not_recoverable"] == 0
            and not cs["canonical_path_collisions"]
        )
        result["tree_side"] = {
            "status": "TRACED", "actual_source_tree_traced": True,
            "tree_root": str(tree_root), "sgf_file_count": tree["sgf_file_count"],
            "tree_manifest_sha256": tree["tree_manifest_sha256"],
            "canonical_path_collision_count": len(tree["canonical_path_collisions"]),
            "join": join,
            "all_reconciliation_gates_pass": bool(gates_pass),
        }
        result["result"] = "GATES_PASS" if gates_pass else "STOP_AND_REPORT: JOIN_OR_DRIFT_UNRECONCILED"

    if out_report is not None:
        out_report.write_bytes(
            (json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        result["report_sha256"] = hashlib.sha256(out_report.read_bytes()).hexdigest()
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LC012 SGF source-tree genesis freeze (read-only).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--tree-root", type=Path, default=None,
                   help="authoritative external SGF tree; omit -> TREE_AUTHORITY_UNRESOLVED")
    p.add_argument("--out-report", type=Path)
    a = p.parse_args(argv)
    if not a.snapshot.exists():
        raise SystemExit(f"snapshot not found: {a.snapshot}")
    res = run(a.snapshot, a.tree_root, a.out_report)
    print(json.dumps({k: v for k, v in res.items()
                      if k not in ("corpus_side",)}, indent=2, ensure_ascii=False))
    print("\ncorpus_side:", json.dumps(res["corpus_side"], indent=2, ensure_ascii=False))
    return 0 if res["snapshot_hash_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
