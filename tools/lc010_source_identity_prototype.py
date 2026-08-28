"""LC010 — source_record_uuid identity-foundation feasibility PROTOTYPE (READ-ONLY).

PROTOTYPE_ONLY / NOT_CANONICAL. This tool answers one question: *could* a
stable, reconstructible, collision-free, non-request-time `source_record_uuid`
be built for every canonical question record from provenance that already
exists in the corpus?

It computes **hypothetical** UUIDs in memory and in the manifest only. It
NEVER writes a UUID into the corpus, any SGF, a database, a runtime record, or
Production. It does not mutate anything. It does not touch LC009 semantics.

Model under evaluation (Lead recommendation — see
docs/planning/lc010_source_record_uuid_identity_foundation.md):

    Model B + D  —  deterministic UUIDv5 keyed on the canonicalised source-SGF
    path, backed by a persistent lineage registry for rename / move / split /
    merge governance events.

    prototype_uuid = uuidv5(NAMESPACE, "sgf-source-file:v1:" + canonical_key)
    canonical_key  = _canonical_source_key(record["source"])

`_canonical_source_key` (governance rules, §14 of the report):
  * Unicode NFC;
  * back-slash -> forward-slash;
  * strip leading/trailing whitespace and separators;
  * collapse repeated separators;
  * **case preserved** (no evidence of case-insensitive source semantics in a
    CJK workbook corpus; lowering could manufacture collisions on rebuild);
  * `.sgf` extension kept verbatim.

The namespace here is a documented PLACEHOLDER. The real namespace UUID is an
owner governance artifact (ownership + immutability + versioning) and must be
substituted before any backfill.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import unicodedata
import uuid
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

LC010_TOOL_VERSION = "lc010-source-identity-prototype-v1"
EXPECTED_SNAPSHOT_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
EXPECTED_RECORD_COUNT = 42804

# PROTOTYPE_ONLY namespace — deterministic, documented, replaceable. The real
# namespace is an owner governance decision (see report §14).
PROTOTYPE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "source-record.canonical.godokoro.com")
KEY_SCHEME = "sgf-source-file:v1:"

CENSUS_CLASSES = (
    "IDENTITY_PROVABLE",
    "IDENTITY_PROVABLE_WITH_REGISTRY",
    "IDENTITY_AMBIGUOUS",
    "IDENTITY_MISSING_SOURCE_PROVENANCE",
    "IDENTITY_COLLISION",
    "SOURCE_NOT_RECOVERABLE",
)

_LEGACY_COLLISION_INDEXES = (
    16715, 16716, 16751, 16786, 16787, 17094,
    32194, 33715, 41082, 41155, 41283, 41321, 41467,
)


def _canonical_source_key(source: Any) -> str | None:
    if source is None:
        return None
    s = unicodedata.normalize("NFC", str(source))
    s = s.replace("\\", "/")
    s = s.strip().strip("/")
    while "//" in s:
        s = s.replace("//", "/")
    s = s.strip().strip("/")
    return s or None


def _prototype_uuid(canonical_key: str) -> str:
    return str(uuid.uuid5(PROTOTYPE_NAMESPACE, KEY_SCHEME + canonical_key))


def _content_sha256(content: str) -> str:
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


def _classify(records: list[dict[str, Any]]):
    """Per-record identity feasibility class + prototype uuid (or None)."""
    keys: list[str | None] = []
    for r in records:
        keys.append(_canonical_source_key(r.get("source")))

    keyc = collections.Counter(k for k in keys if k is not None)
    rows = []
    for i, (r, k) in enumerate(zip(records, keys)):
        src = r.get("source")
        if src is None or not str(src).strip():
            cls, pid, reason = "IDENTITY_MISSING_SOURCE_PROVENANCE", None, "no source field"
        elif k is None:
            cls, pid, reason = "SOURCE_NOT_RECOVERABLE", None, "source did not canonicalise to a key"
        elif not k.lower().endswith(".sgf"):
            cls, pid, reason = "SOURCE_NOT_RECOVERABLE", None, "canonical key is not an .sgf file path"
        elif keyc[k] > 1:
            cls, pid, reason = "IDENTITY_AMBIGUOUS", None, f"canonical key shared by {keyc[k]} records"
            # a genuine collision only if the two records are actually distinct entities
            # (byte-identical source strings would be IDENTITY_COLLISION)
        else:
            cls, pid, reason = "IDENTITY_PROVABLE", _prototype_uuid(k), "unique canonical source-SGF path"
        rows.append({
            "record_index": i,
            "legacy_question_id": r.get("id"),
            "source": src,
            "canonical_source_key": k,
            "identity_feasibility_class": cls,
            "prototype_source_record_uuid": pid,
            "reason": reason,
        })

    # split IDENTITY_AMBIGUOUS into true byte-identical-source COLLISION vs AMBIGUOUS
    raw_src = collections.Counter(json.dumps(r.get("source"), ensure_ascii=False) for r in records)
    for row in rows:
        if row["identity_feasibility_class"] == "IDENTITY_AMBIGUOUS":
            if raw_src[json.dumps(row["source"], ensure_ascii=False)] > 1:
                row["identity_feasibility_class"] = "IDENTITY_COLLISION"
                row["reason"] = "two records carry a byte-identical source path"
    return rows


def run(path: Path, out_manifest: Path | None, full_records: bool = False) -> dict[str, Any]:
    sha, match, records = verify_snapshot(path)
    if not match:
        raise SystemExit(
            f"SNAPSHOT_HASH_MISMATCH: got {sha}, expected {EXPECTED_SNAPSHOT_SHA256}. STOP."
        )
    n = len(records)
    rows = _classify(records)

    counts = collections.Counter(r["identity_feasibility_class"] for r in rows)
    census = {c: counts.get(c, 0) for c in CENSUS_CLASSES}
    census_total = sum(census.values())

    # uniqueness of the prototype UUIDs actually assigned
    assigned = [r["prototype_source_record_uuid"] for r in rows if r["prototype_source_record_uuid"]]
    uuid_dupe = sum(c for c in collections.Counter(assigned).values() if c > 1)

    # --- 404 exact-content duplicate group identity audit (§10) ---
    by_hash: dict[str, list[int]] = collections.defaultdict(list)
    for i, r in enumerate(records):
        by_hash[_content_sha256(r.get("content") or "")].append(i)
    dup = {h: idxs for h, idxs in by_hash.items() if len(idxs) > 1}
    g_prov = g_partial = g_unres = 0
    g_prov_rec = g_partial_rec = g_unres_rec = 0
    for idxs in dup.values():
        ids = [rows[i]["prototype_source_record_uuid"] for i in idxs]
        distinct = len({x for x in ids if x is not None})
        assigned_n = sum(1 for x in ids if x is not None)
        if assigned_n == len(idxs) and distinct == len(idxs):
            g_prov += 1; g_prov_rec += len(idxs)
        elif distinct >= 2:
            g_partial += 1; g_partial_rec += len(idxs)
        else:
            g_unres += 1; g_unres_rec += len(idxs)

    # --- 13 legacy-collision separability (§11) ---
    lc_ids = [rows[i]["prototype_source_record_uuid"] for i in _LEGACY_COLLISION_INDEXES]
    lc_assigned = [x for x in lc_ids if x is not None]
    lc_separable = len(set(lc_assigned)) == len(_LEGACY_COLLISION_INDEXES)
    lc_blocked = [_LEGACY_COLLISION_INDEXES[j] for j, x in enumerate(lc_ids) if x is None]

    summary = {
        "lc010_tool_version": LC010_TOOL_VERSION,
        "prototype_only": True,
        "not_canonical": True,
        "corpus_mutated": False,
        "source_record_uuid_backfill": False,
        "request_time_uuid_generation": False,
        "snapshot_sha256": sha,
        "snapshot_hash_match": match,
        "record_count": n,
        "record_count_match": n == EXPECTED_RECORD_COUNT,
        "identity_model_candidates": ["A_random_uuidv4_persisted", "B_deterministic_uuidv5_live_source_key",
                                     "C_native_source_id_mapping", "D_persistent_registry_frozen_genesis"],
        "recommended_identity_model": "D_persistent_registry_frozen_genesis "
        "(genesis UUID = UUIDv5(owner_namespace, genesis_sha256 + ':sgf-source-file:v1:' + canonical(source)); "
        "registry + resolver + lineage ledger are the post-genesis authority)",
        "recommended_uuid_version": "UUIDv5 (SHA-1, name-based) for the genesis mint",
        "model_b_live_source_rejected_reason": "the live `source` field is regenerated by build_questions.py "
        "on every rebuild and record_index has already shifted +201; a pure live-field key is not "
        "re-ingestion-stable (LC10-A)",
        "identity_namespace_required": True,
        "identity_registry_required": True,
        "prototype_namespace_uuid": str(PROTOTYPE_NAMESPACE),
        "prototype_namespace_status": "PLACEHOLDER — real namespace is an owner governance artifact",
        "key_scheme": KEY_SCHEME,
        "identity_provable_count": census["IDENTITY_PROVABLE"],
        "identity_provable_with_registry_count": census["IDENTITY_PROVABLE_WITH_REGISTRY"],
        "identity_ambiguous_count": census["IDENTITY_AMBIGUOUS"],
        "identity_missing_source_provenance_count": census["IDENTITY_MISSING_SOURCE_PROVENANCE"],
        "identity_collision_count": census["IDENTITY_COLLISION"],
        "source_not_recoverable_count": census["SOURCE_NOT_RECOVERABLE"],
        "identity_census_total": census_total,
        "identity_census_accounting_pass": census_total == n,
        "prototype_uuid_assigned_count": len(assigned),
        "prototype_uuid_collision_count": uuid_dupe,
        "distinct_canonical_source_keys": len({r["canonical_source_key"] for r in rows
                                               if r["canonical_source_key"]}),
        "duplicate_groups_total": len(dup),
        "duplicate_groups_identity_provable": g_prov,
        "duplicate_groups_partial": g_partial,
        "duplicate_groups_unresolved": g_unres,
        "duplicate_group_records_identity_provable": g_prov_rec,
        "duplicate_group_records_partial": g_partial_rec,
        "duplicate_group_records_unresolved": g_unres_rec,
        "legacy_collision_records": len(_LEGACY_COLLISION_INDEXES),
        "legacy_collision_records_separable_count": len(set(lc_assigned)),
        "legacy_collision_records_separable": lc_separable,
        "legacy_collision_blocked_indexes": lc_blocked,
        "invariants": {
            "I1_uniqueness_uuid_collision_count": uuid_dupe,
            "I2_reingestion_stability": "BLOCKED for a live-field key (build_questions.py regenerates "
                                        "`source`; record_index already shifted +201). MET only by the "
                                        "Model-D registry + resolver + lineage ledger, which do not exist yet. "
                                        "The genesis key is stable for THIS frozen snapshot only.",
            "I3_ordering_independence": "PASS — genesis key derives from source path only, never record_index",
            "I4_request_independence": "PASS — offline genesis mint + offline resolver, never at request time",
            "I5_exact_content_duplicates_separable": g_unres == 0,
            "I6_non_identity_metadata_edit_stability": "PASS — key + registry ignore every metadata field",
            "I7_legacy_id_not_authority": "PASS — UUID derives from source path / registry, not id",
            "I8_fail_closed": "PASS — missing/ambiguous/non-recoverable source -> no UUID assigned",
        },
        "backfill_feasibility": "PARTIAL",
        "backfill_blockers": [
            "OWNER_DECISION — canonical alias-key decision still OWNER_DECISION_REQUIRED",
            "NAMESPACE — no owner-ratified namespace + canonicalisation ADR (prototype namespace is a placeholder)",
            "REGISTRY — Model-D registry + resolver + lineage ledger unbuilt (the V1.1 scope)",
            "SOURCE_TREE — external SGF題庫 tree not version-controlled; build_questions.py regenerates `source`",
            "ADD_QUESTION — app.py add_question() writes source='' for admin-created records",
        ],
        "lc009_semantics_changed": False,
    }

    # bounded manifest: summary + the two required audits + a small deterministic
    # record sample. The full 42,804-row classification is reproducible with
    # --full but is NOT committed (it would be a ~21 MB planning artifact).
    def _slim(row):
        return {k: row[k] for k in ("record_index", "legacy_question_id", "source",
                                    "canonical_source_key", "identity_feasibility_class",
                                    "prototype_source_record_uuid", "reason")}

    dup_audit = []
    for h, idxs in sorted(dup.items()):
        member_uuids = [rows[i]["prototype_source_record_uuid"] for i in idxs]
        dup_audit.append({
            "content_sha256": h,
            "member_count": len(idxs),
            "record_indexes": idxs,
            "member_prototype_uuids": member_uuids,
            "distinct_prototype_uuids": len({x for x in member_uuids if x is not None}),
            "identity_result": ("IDENTITY_PROVABLE" if len({x for x in member_uuids if x}) == len(idxs)
                                else "PARTIAL" if len({x for x in member_uuids if x}) >= 2
                                else "UNRESOLVED"),
        })
    legacy_audit = [_slim(rows[i]) for i in _LEGACY_COLLISION_INDEXES]
    sample = [_slim(rows[i]) for i in list(range(25)) + list(range(n - 25, n))]

    manifest = {
        "schema_version": "1.0",
        "authority": "LC010_SOURCE_RECORD_UUID_IDENTITY_FOUNDATION_AND_BACKFILL_FEASIBILITY_001",
        "canonicality": "PROTOTYPE_ONLY__NOT_CANONICAL__NO_MUTATION__NO_BACKFILL",
        "summary": summary,
        "duplicate_group_identity_audit": dup_audit,
        "legacy_collision_identity_audit": legacy_audit,
        "record_sample_first25_last25": sample,
        "full_record_manifest_committed": False,
        "full_record_manifest_reproduce_with": "tools/lc010_source_identity_prototype.py --full --out-manifest <path>",
    }
    if full_records:
        manifest["records"] = rows
    manifest_sha = None
    if out_manifest is not None:
        out_manifest.write_bytes(
            (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        )
        manifest_sha = hashlib.sha256(out_manifest.read_bytes()).hexdigest()
    return {"summary": summary, "manifest": manifest,
            "manifest_path": out_manifest.as_posix() if out_manifest else None,
            "manifest_sha256": manifest_sha}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LC010 source-identity feasibility prototype (read-only, PROTOTYPE_ONLY).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--out-manifest", type=Path)
    p.add_argument("--full", action="store_true",
                   help="embed all 42,804 per-record rows (large; not for commit)")
    args = p.parse_args(argv)
    if not args.snapshot.exists():
        raise SystemExit(f"snapshot not found: {args.snapshot}")
    result = run(args.snapshot, args.out_manifest, full_records=args.full)
    rep = dict(result["summary"])
    rep["manifest_path"] = result["manifest_path"]
    rep["manifest_sha256"] = result["manifest_sha256"]
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0 if result["summary"]["identity_census_accounting_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
