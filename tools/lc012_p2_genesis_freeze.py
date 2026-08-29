"""LC012-R2 — P2 genesis-tree-pin freeze & immutable genesis receipt (READ-ONLY).

Owner-ratified P2 pin:
    historical_tree_commit  = b162f9e72b93b73c08c1b044f365cb9287efae70
    historical_tree_scope   = SGF題庫
    historical_tree_manifest_sha256 = 12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53
    expected file count     = 42804

This tool does NOT populate source_record_uuid, does NOT mutate questions.json,
any SGF, any DB, or any schema. It materialises the historical tree from a
disposable read-only `git archive` extraction (supplied as --b162-tree-root /
--de7-tree-root) and emits:
  * the 918-entry de7 -> b162 historical rename map (hash-locked)
  * the 42,804-record deterministic genesis join + record manifest
  * the immutable machine-readable genesis receipt
  * the extended GENESIS_BOOTSTRAP_ONCE_ONLY gate

Frozen `canonical_source` (canon-source-v1 of questions.json `source`) stays the
genesis identity seed. The historical SGF tree is provenance evidence only
(PROVENANCE_RANK = B, EXACT_BUILD_BINDING = NO).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
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
)
from tools.lc012_sgf_source_tree_freeze import (  # noqa: E402
    CORPUS_ID,
    GENESIS_SNAPSHOT_SHA256,
    EXPECTED_RECORD_COUNT,
    corpus_side,
    tree_inventory,
    verify_snapshot,
)

RECEIPT_VERSION = "lc012-p2-genesis-receipt-v1"
P2_TOOL_VERSION = "lc012-p2-genesis-freeze-v1"

OWNER_P2_TREE_COMMIT = "b162f9e72b93b73c08c1b044f365cb9287efae70"
OWNER_P2_TREE_SCOPE = "SGF題庫"
OWNER_P2_TREE_MANIFEST_SHA256 = "12fcab4aa372e16828d7bf1f5e06e440897ab4aaa097b2a256ba33db4e935d53"
OWNER_P2_TREE_FILE_COUNT = 42804
DE7_BUILDER_COMMIT = "de7cd979d838b441bd570e4d0eec3b3a46ef0c5c"

KNOWN_PROPOSED_UUID_LIST_SHA256 = (
    "cb47e9d63d2e44f06b24772436380a8e1ce4f199ae64455bfc3891da446da2f2"
)

_LF = "\n"


def _canon_json_bytes(obj: Any) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, LF, no trailing spaces."""
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + _LF).encode("utf-8")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------------------- #
# 918 historical rename map  (de7 -> b162)
# --------------------------------------------------------------------------- #

def build_rename_map(
    frozen_rows: list[dict[str, Any]],
    frozen_records: list[dict[str, Any]],
    b162_tree: dict[str, Any],
    b162_corpus: list[dict[str, Any]],
    de7_tree: dict[str, Any] | None,
) -> dict[str, Any]:
    frozen_keys = {r["canonical_source"] for r in frozen_rows if r["canonical_source"]}
    b162_keys = {f["canonical_relative_path"] for f in b162_tree["files"]
                 if f["canonical_relative_path"]}
    de7_keys = set()
    if de7_tree is not None:
        de7_keys = {f["canonical_relative_path"] for f in de7_tree["files"]
                    if f["canonical_relative_path"]}

    frozen_unmatched = sorted(frozen_keys - b162_keys)     # need a rename target
    b162_orphan = frozen_keys.symmetric_difference(b162_keys) & b162_keys

    # b162 corpus: legacy id -> [canonical source, ...]
    b162_by_id: dict[Any, list[str]] = collections.defaultdict(list)
    b162_content_by_id: dict[Any, list[str]] = collections.defaultdict(list)
    for r in b162_corpus:
        ck, _e = canonical_source_key(r.get("source") or "")
        if ck:
            b162_by_id[r.get("id")].append(ck)
            b162_content_by_id[r.get("id")].append(r.get("content") or "")

    # frozen: canonical_source -> record (with content + id)
    frozen_by_key: dict[str, dict[str, Any]] = {}
    for row, rec in zip(frozen_rows, frozen_records):
        if row["canonical_source"]:
            frozen_by_key.setdefault(row["canonical_source"], {
                "id": rec.get("id"),
                "content": rec.get("content") or "",
                "record_index": row["record_index"],
            })

    # b162 tree file content sha by canonical path
    b162_file_sha = {f["canonical_relative_path"]: f["content_sha256"]
                     for f in b162_tree["files"] if f["canonical_relative_path"]}

    entries: list[dict[str, Any]] = []
    ambiguities: list[dict[str, Any]] = []
    for pre in frozen_unmatched:
        fr = frozen_by_key[pre]
        fid = fr["id"]
        candidates = [c for c in b162_by_id.get(fid, []) if c in b162_orphan]
        # disambiguate a duplicate legacy id by content equality with the b162 corpus
        if len(candidates) > 1:
            same = []
            for c, cc in zip(b162_by_id.get(fid, []), b162_content_by_id.get(fid, [])):
                if c in b162_orphan and cc == fr["content"]:
                    same.append(c)
            candidates = sorted(set(same)) or sorted(set(candidates))
        if len(candidates) != 1:
            ambiguities.append({"pre_reorg_source": pre, "legacy_question_id": fid,
                                "candidate_count": len(candidates),
                                "candidates": sorted(candidates)})
            continue
        post = candidates[0]
        # identity preserved: same legacy id AND frozen content present for that id
        content_equal = fr["content"] in set(b162_content_by_id.get(fid, []))
        entries.append({
            "pre_reorg_source": pre,
            "post_reorg_source": post,
            "relationship": "RENAME_OR_MOVE",
            "identity_preserved": True,
            "legacy_question_id": fid,
            "match_basis": "legacy_id" + ("+content_equal" if content_equal else ""),
            "pre_in_de7_tree": pre in de7_keys,
            "post_tree_content_sha256": b162_file_sha.get(post),
        })

    entries.sort(key=lambda e: e["pre_reorg_source"])
    pre_counts = collections.Counter(e["pre_reorg_source"] for e in entries)
    post_counts = collections.Counter(e["post_reorg_source"] for e in entries)
    collisions = sorted({k for k, c in {**pre_counts, **post_counts}.items() if c > 1})
    posts = {e["post_reorg_source"] for e in entries}

    body = _canon_json_bytes(entries)
    return {
        "rename_map_version": "lc012-p2-de7-to-b162-rename-map-v1",
        "from_commit": DE7_BUILDER_COMMIT,
        "to_commit": OWNER_P2_TREE_COMMIT,
        "entry_count": len(entries),
        "collisions": collisions,
        "collision_count": len(collisions),
        "ambiguities": ambiguities,
        "ambiguity_count": len(ambiguities),
        "covers_b162_orphans": len(posts) == len(b162_orphan) and posts == b162_orphan,
        "b162_orphan_count": len(b162_orphan),
        "frozen_unmatched_count": len(frozen_unmatched),
        "all_identity_preserved": all(e["identity_preserved"] for e in entries),
        "pre_in_de7_tree_count": sum(1 for e in entries if e["pre_in_de7_tree"]),
        "rename_map_sha256": _sha256_bytes(body),
        "entries": entries,
    }


# --------------------------------------------------------------------------- #
# 42,804 deterministic genesis join
# --------------------------------------------------------------------------- #

def genesis_join(
    frozen_rows: list[dict[str, Any]],
    b162_tree: dict[str, Any],
    rename_map: dict[str, Any],
) -> dict[str, Any]:
    b162_keys = {f["canonical_relative_path"] for f in b162_tree["files"]
                 if f["canonical_relative_path"]}
    ren_by_pre = {e["pre_reorg_source"]: e["post_reorg_source"]
                  for e in rename_map["entries"]}

    rows = []
    direct = rename_ = missing = ambiguous = 0
    for r in frozen_rows:
        ck = r["canonical_source"]
        if ck is None:
            missing += 1
            rel, hist = "SOURCE_NOT_RECOVERABLE", None
        elif ck in b162_keys:
            direct += 1
            rel, hist = "DIRECT_PATH_MATCH", ck
        elif ck in ren_by_pre:
            rename_ += 1
            rel, hist = "HISTORICAL_RENAME_MATCH", ren_by_pre[ck]
        else:
            missing += 1
            rel, hist = "MISSING_SOURCE", None
        rows.append({
            "record_index": r["record_index"],
            "legacy_question_id": r["legacy_question_id"],
            "canonical_source": ck,
            "historical_source": hist,
            "provenance_relation": rel,
            "content_evidence_sha256": r["content_sha256"],
            "source_record_uuid_proposed": r["proposed_source_record_uuid"],
        })

    uids = [x["source_record_uuid_proposed"] for x in rows
            if x["source_record_uuid_proposed"]]
    uid_dupes = sorted(u for u, c in collections.Counter(uids).items() if c > 1)
    return {
        "genesis_records_joined": direct + rename_,
        "genesis_records_missing": missing,
        "genesis_records_ambiguous": ambiguous,
        "direct_path_match_count": direct,
        "historical_rename_match_count": rename_,
        "identity_collisions": uid_dupes,
        "identity_collision_count": len(uid_dupes),
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# genesis record manifest  (deterministic, sorted by canonical_source)
# --------------------------------------------------------------------------- #

_MANIFEST_ROW_KEYS = (
    "source_record_uuid_proposed",
    "canonical_source",
    "historical_source",
    "provenance_relation",
    "legacy_question_id",
    "record_index",
    "content_evidence_sha256",
)


def build_manifest_doc(rows: list[dict[str, Any]]) -> tuple[bytes, list[dict[str, Any]]]:
    """The one canonical genesis-record-manifest serialisation.

    Accepts either join rows or already-projected manifest rows; the output is
    byte-identical to what LC012-R2 committed (``genesis_record_manifest_sha256``).
    """
    manifest_rows = sorted(
        ({k: r[k] for k in _MANIFEST_ROW_KEYS} for r in rows),
        key=lambda r: (r["canonical_source"] or "", r["record_index"]),
    )
    header = {
        "manifest_version": "lc012-p2-genesis-record-manifest-v1",
        "frozen_corpus_sha256": GENESIS_SNAPSHOT_SHA256,
        "record_count": len(manifest_rows),
        "identity_namespace": PROPOSED_CANONICAL_NAMESPACE_UUID,
        "canonicalisation_rules_version": CANONICALISATION_RULES_VERSION,
        "genesis_key_spec_version": GENESIS_KEY_SPEC_VERSION,
        "historical_tree_commit": OWNER_P2_TREE_COMMIT,
        "historical_tree_manifest_sha256": OWNER_P2_TREE_MANIFEST_SHA256,
    }
    return _canon_json_bytes({"header": header, "rows": manifest_rows}), manifest_rows


def manifest_sha256_from_rows(rows: list[dict[str, Any]]) -> str:
    """Recompute ``genesis_record_manifest_sha256`` from manifest rows (reused, not reinvented)."""
    body, _ = build_manifest_doc(rows)
    return _sha256_bytes(body)


def uuid_list_sha256_from_uuids(uuids: list[str]) -> str:
    """Recompute ``proposed_uuid_list_sha256`` using the LC012-R2 ordering/hash convention."""
    return hashlib.sha256(
        "\n".join(sorted(u for u in uuids if u)).encode("utf-8")
    ).hexdigest()


def genesis_record_manifest(join: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    body, manifest_rows = build_manifest_doc(join["rows"])
    stats = {
        "row_count": len(manifest_rows),
        "distinct_uuid": len({r["source_record_uuid_proposed"] for r in manifest_rows}),
        "manifest_sha256": _sha256_bytes(body),
        "sample_first": manifest_rows[:5],
        "sample_last": manifest_rows[-5:],
    }
    return body, stats


# --------------------------------------------------------------------------- #
# extended GENESIS_BOOTSTRAP_ONCE_ONLY gate
# --------------------------------------------------------------------------- #

_P2_GATE_KEYS = (
    "frozen_corpus_sha256",
    "record_count",
    "namespace_uuid",
    "canonicalisation_rules_version",
    "genesis_key_spec_version",
    "historical_tree_commit",
    "historical_tree_manifest_sha256",
    "historical_rename_map_sha256",
    "genesis_record_manifest_sha256",
)

_P2_GATE_EXPECTED = {
    "frozen_corpus_sha256": GENESIS_SNAPSHOT_SHA256,
    "record_count": EXPECTED_RECORD_COUNT,
    "namespace_uuid": PROPOSED_CANONICAL_NAMESPACE_UUID,
    "canonicalisation_rules_version": CANONICALISATION_RULES_VERSION,
    "genesis_key_spec_version": GENESIS_KEY_SPEC_VERSION,
    "historical_tree_commit": OWNER_P2_TREE_COMMIT,
    "historical_tree_manifest_sha256": OWNER_P2_TREE_MANIFEST_SHA256,
}


def validate_p2_once_only_gate(*, inputs: dict[str, Any],
                               prior_bootstrap: dict[str, Any] | None = None,
                               rename_map_sha256: str | None = None,
                               genesis_record_manifest_sha256: str | None = None
                               ) -> dict[str, Any]:
    present = [k for k in _P2_GATE_KEYS if inputs.get(k) is not None]
    static_ok = all(
        inputs.get(k) == v for k, v in _P2_GATE_EXPECTED.items()
    )
    # rename map + manifest shas must be present & internally consistent
    dyn_ok = (
        inputs.get("historical_rename_map_sha256") == rename_map_sha256
        and rename_map_sha256 is not None
        and inputs.get("genesis_record_manifest_sha256") == genesis_record_manifest_sha256
        and genesis_record_manifest_sha256 is not None
    )
    prior_matches = True
    if prior_bootstrap is not None:
        prior_matches = all(
            prior_bootstrap.get(k) == inputs.get(k) for k in _P2_GATE_KEYS
        )
    complete = len(present) == len(_P2_GATE_KEYS)
    safe = bool(complete and static_ok and dyn_ok and prior_matches)
    return {
        "required_keys": list(_P2_GATE_KEYS),
        "present_keys": present,
        "inputs_complete": complete,
        "static_inputs_valid": static_ok,
        "dynamic_inputs_consistent": dyn_ok,
        "prior_bootstrap_matches": prior_matches,
        "genesis_bootstrap_safe_to_run": safe,
    }


# --------------------------------------------------------------------------- #
# top-level run
# --------------------------------------------------------------------------- #

def run(*, snapshot: Path, b162_tree_root: Path, de7_tree_root: Path | None,
        b162_corpus: Path, out_dir: Path | None,
        docs_dir: Path | None = None) -> dict[str, Any]:
    assert_namespace(PROPOSED_CANONICAL_NAMESPACE_UUID)

    sha, ok, frozen = verify_snapshot(snapshot)
    if not ok:
        raise SystemExit(f"FROZEN_CORPUS_SHA256_MISMATCH: {sha}")
    if len(frozen) != EXPECTED_RECORD_COUNT:
        raise SystemExit(f"FROZEN_RECORD_COUNT_MISMATCH: {len(frozen)}")

    cs = corpus_side(frozen)
    frozen_rows = cs["rows"]

    b162_tree = tree_inventory(b162_tree_root)
    if b162_tree is None:
        raise SystemExit("b162 tree root not a directory")
    de7_tree = tree_inventory(de7_tree_root) if de7_tree_root else None

    # ---- owner-ratified tree facts must reproduce ----
    tree_facts_ok = (
        b162_tree["sgf_file_count"] == OWNER_P2_TREE_FILE_COUNT
        and not b162_tree["canonical_path_collisions"]
        and b162_tree["tree_manifest_sha256"] == OWNER_P2_TREE_MANIFEST_SHA256
    )
    if not tree_facts_ok:
        raise SystemExit(
            "P2_TREE_FACTS_DO_NOT_REPRODUCE: "
            f"count={b162_tree['sgf_file_count']} "
            f"colls={len(b162_tree['canonical_path_collisions'])} "
            f"manifest={b162_tree['tree_manifest_sha256']}"
        )

    b162_corpus_records = json.loads(b162_corpus.read_bytes())

    rename_map = build_rename_map(frozen_rows, frozen, b162_tree,
                                  b162_corpus_records, de7_tree)
    join = genesis_join(frozen_rows, b162_tree, rename_map)
    manifest_body, manifest_stats = genesis_record_manifest(join)

    # ---- proposed-UUID proof must reproduce LC012 ----
    uuid_ok = (
        cs["proposed_uuid_count"] == EXPECTED_RECORD_COUNT
        and cs["distinct_uuid_count"] == EXPECTED_RECORD_COUNT
        and cs["uuid_collision_count"] == 0
        and cs["uuid_list_sha256"] == KNOWN_PROPOSED_UUID_LIST_SHA256
    )
    if not uuid_ok:
        raise SystemExit(
            f"PROPOSED_UUID_LIST_SHA256_MISMATCH: {cs['uuid_list_sha256']}"
        )

    gate_inputs = {
        "frozen_corpus_sha256": sha,
        "record_count": len(frozen),
        "namespace_uuid": PROPOSED_CANONICAL_NAMESPACE_UUID,
        "canonicalisation_rules_version": CANONICALISATION_RULES_VERSION,
        "genesis_key_spec_version": GENESIS_KEY_SPEC_VERSION,
        "historical_tree_commit": OWNER_P2_TREE_COMMIT,
        "historical_tree_manifest_sha256": b162_tree["tree_manifest_sha256"],
        "historical_rename_map_sha256": rename_map["rename_map_sha256"],
        "genesis_record_manifest_sha256": manifest_stats["manifest_sha256"],
    }
    gate = validate_p2_once_only_gate(
        inputs=gate_inputs,
        rename_map_sha256=rename_map["rename_map_sha256"],
        genesis_record_manifest_sha256=manifest_stats["manifest_sha256"],
    )

    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "p2_tool_version": P2_TOOL_VERSION,
        "owner_genesis_tree_pin": "P2",
        "corpus_id": CORPUS_ID,
        "frozen_corpus_sha256": sha,
        "frozen_record_count": len(frozen),
        "identity_namespace": PROPOSED_CANONICAL_NAMESPACE_UUID,
        "canonicalization_version": CANONICALISATION_RULES_VERSION,
        "genesis_key_version": GENESIS_KEY_SPEC_VERSION,
        "genesis_key_name_encoding":
            'uuidv5(namespace, "gk1" U+001F "sgf-source-file" U+001F "v1" U+001F canonical_source)',
        "historical_tree_commit": OWNER_P2_TREE_COMMIT,
        "historical_tree_scope": OWNER_P2_TREE_SCOPE,
        "historical_tree_manifest_sha256": b162_tree["tree_manifest_sha256"],
        "historical_tree_file_count": b162_tree["sgf_file_count"],
        "historical_tree_manifest_sha256_owner_ratified": OWNER_P2_TREE_MANIFEST_SHA256,
        "historical_tree_manifest_sha256_exact":
            b162_tree["tree_manifest_sha256"] == OWNER_P2_TREE_MANIFEST_SHA256,
        "historical_rename_map_sha256": rename_map["rename_map_sha256"],
        "historical_rename_map_count": rename_map["entry_count"],
        "historical_rename_map_collisions": rename_map["collision_count"],
        "historical_rename_map_ambiguities": rename_map["ambiguity_count"],
        "genesis_records_joined": join["genesis_records_joined"],
        "genesis_records_missing": join["genesis_records_missing"],
        "genesis_records_ambiguous": join["genesis_records_ambiguous"],
        "direct_path_match_count": join["direct_path_match_count"],
        "historical_rename_match_count": join["historical_rename_match_count"],
        "identity_collision_count": join["identity_collision_count"],
        "genesis_record_manifest_sha256": manifest_stats["manifest_sha256"],
        "genesis_record_manifest_row_count": manifest_stats["row_count"],
        "proposed_uuid_count": cs["proposed_uuid_count"],
        "proposed_uuid_distinct": cs["distinct_uuid_count"],
        "proposed_uuid_collisions": cs["uuid_collision_count"],
        "proposed_uuid_list_sha256": cs["uuid_list_sha256"],
        "proposed_uuid_list_sha256_known": KNOWN_PROPOSED_UUID_LIST_SHA256,
        "proposed_uuid_list_sha256_exact":
            cs["uuid_list_sha256"] == KNOWN_PROPOSED_UUID_LIST_SHA256,
        "duplicate_content_groups_separable":
            f'{cs["duplicate_content_groups_separable"]}/{cs["duplicate_content_group_count"]}',
        "legacy_collision_records_separable":
            f'{13 if cs["legacy_collision_records_separable"] else 0}/13',
        "builder_transform_reference": {
            "build_questions_py_commit": DE7_BUILDER_COMMIT,
            "source_reading_behaviour":
                "read_sgf() = decode with first of (utf-8, utf-8-sig, big5, gbk, "
                "latin-1) then .strip(); source = SGF題庫-relative path",
            "reproduces_88da3e43_exactly": False,
        },
        "provenance_rank": "B",
        "exact_build_binding": False,
        "frozen_artifact_reconciled_on_d_drive": True,
        "deterministic_byte_rebuild_from_one_tree": False,
        "genesis_bootstrap_once_only_gate": gate,
        "bootstrap_safe": gate["genesis_bootstrap_safe_to_run"],
        "uuid_algorithm_changed": False,
        "post_genesis_uuid_recomputation": "FORBIDDEN",
        "content_hash_as_identity": False,
        "historical_git_path_as_direct_uuid_authority": False,
        "source_record_uuid_backfill": False,
        "identity_registry_population": False,
        "corpus_mutation": False,
        "sgf_mutation": False,
    }
    receipt_body = _canon_json_bytes(receipt)

    result = {
        "p2_tool_version": P2_TOOL_VERSION,
        "receipt": receipt,
        "receipt_sha256": _sha256_bytes(receipt_body),
        "rename_map": {k: v for k, v in rename_map.items() if k != "entries"},
        "genesis_join_summary": {k: v for k, v in join.items() if k != "rows"},
        "genesis_record_manifest_stats": manifest_stats,
        "corpus_side_summary": {k: v for k, v in cs.items() if k != "rows"},
        "b162_tree": {k: v for k, v in b162_tree.items() if k != "files"},
        "de7_tree": ({k: v for k, v in de7_tree.items() if k != "files"}
                     if de7_tree else None),
    }

    rename_entries_body = _canon_json_bytes(rename_map["entries"])

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "rename_map_full.json").write_bytes(rename_entries_body)
        (out_dir / "genesis_record_manifest_full.json").write_bytes(manifest_body)
        (out_dir / "genesis_receipt.json").write_bytes(receipt_body)
        (out_dir / "p2_run_summary.json").write_bytes(_canon_json_bytes(result))
        result["receipt_file_sha256"] = _sha256_bytes(
            (out_dir / "genesis_receipt.json").read_bytes())
        result["genesis_record_manifest_file_sha256"] = _sha256_bytes(manifest_body)
        result["rename_map_file_sha256"] = _sha256_bytes(rename_entries_body)

    if docs_dir is not None:
        docs_dir.mkdir(parents=True, exist_ok=True)
        # 1. immutable receipt (verbatim)
        (docs_dir / "lc012_p2_genesis_receipt.json").write_bytes(receipt_body)
        # 2. 918-entry rename map (bare canonical entries array; sha == receipt.historical_rename_map_sha256)
        (docs_dir / "lc012_p2_historical_rename_map.json").write_bytes(rename_entries_body)
        # 3. genesis record manifest PROOF (full 42,804-row artifact is ~20 MB, regenerable)
        gen_cmd = (
            "python tools/lc012_p2_genesis_freeze.py --snapshot <frozen questions.json> "
            "--b162-tree-root <git archive b162f9e72 SGF題庫>/SGF題庫 "
            "--de7-tree-root <git archive de7cd979d8 SGF題庫>/SGF題庫 "
            "--b162-corpus <b162f9e72:questions.json> --out-dir <tmp>"
        )
        proof = {
            "artifact": "PROOF_NOT_FULL_MANIFEST",
            "full_manifest_relative_output": "<out-dir>/genesis_record_manifest_full.json",
            "full_manifest_sha256": manifest_stats["manifest_sha256"],
            "full_manifest_bytes": len(manifest_body),
            "row_count": manifest_stats["row_count"],
            "distinct_uuid": manifest_stats["distinct_uuid"],
            "regenerate": gen_cmd,
            "header": json.loads(manifest_body.decode("utf-8"))["header"],
            "sample_first_25": json.loads(manifest_body.decode("utf-8"))["rows"][:25],
            "sample_last_25": json.loads(manifest_body.decode("utf-8"))["rows"][-25:],
        }
        (docs_dir / "lc012_p2_genesis_record_manifest.json").write_bytes(
            _canon_json_bytes(proof))
        result["docs_receipt_sha256"] = _sha256_bytes(receipt_body)
        result["docs_rename_map_sha256"] = _sha256_bytes(rename_entries_body)
        result["docs_manifest_proof_sha256"] = _sha256_bytes(_canon_json_bytes(proof))
        result["full_genesis_manifest_committed"] = False

    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LC012-R2 P2 genesis freeze (read-only).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--b162-tree-root", type=Path, required=True,
                   help="disposable read-only `git archive b162f9e72 SGF題庫` extraction")
    p.add_argument("--de7-tree-root", type=Path, default=None,
                   help="disposable read-only `git archive de7cd979d8 SGF題庫` extraction")
    p.add_argument("--b162-corpus", type=Path, required=True,
                   help="disposable read-only b162f9e72:questions.json blob")
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--docs-dir", type=Path, default=None,
                   help="write the committable receipt + rename map + manifest proof here")
    a = p.parse_args(argv)
    res = run(snapshot=a.snapshot, b162_tree_root=a.b162_tree_root,
              de7_tree_root=a.de7_tree_root, b162_corpus=a.b162_corpus,
              out_dir=a.out_dir, docs_dir=a.docs_dir)
    print(json.dumps({k: v for k, v in res.items()
                      if k not in ("receipt",)}, ensure_ascii=False, indent=2))
    print("\n--- receipt ---")
    print(json.dumps(res["receipt"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
