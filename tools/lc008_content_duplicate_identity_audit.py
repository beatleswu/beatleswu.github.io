"""LC008 — content-duplicate identity & review-fanout audit (READ-ONLY).

Groups the canonical snapshot by exact ``content`` byte-hash, classifies each
duplicate-content group's *identity* and whether a future human
terminal-verdict review of one member could safely fan out to the others,
and emits a deterministic manifest + owner report inputs.

It mutates NOTHING: no corpus write, no record edit, no ``source_record_uuid``
generation, no marker apply, no Production read. It does not modify or
re-litigate LC009 semantics; it only *reads* the LC005/LC009 classifier as
evidence for which duplicate members sit in the MANUAL population.

Owner-locked identity model (LC008 spec §2):
  * ``source_record_uuid`` == canonical identity (request-time generation
    FORBIDDEN);
  * ``id`` == legacy compatibility alias only;
  * ``record_index`` == ingestion/positional locator only;
  * identical ``content`` does NOT imply identical canonical identity.

content_sha256 semantics (LC008 spec §14): ``sha256(record["content"]
.encode("utf-8"))`` — the SGF string ONLY. It excludes ``comment`` (a
sibling top-level field), every metadata / provenance / answer-authority
field, and applies NO normalisation. Equal hash == byte-identical SGF, and
nothing more.

SAFE_REVIEW_FANOUT is assigned only when the audit can *prove* the members
share the semantic context relevant to terminal answer correctness. It fails
closed: distinct source identity, absent canonical identity, answer-authority
drift, metadata drift or authoring drift each block it. SAFE_REVIEW_FANOUT is
never a record merge (spec §8).
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

from tools.lc005_terminal_verdict_census import classify_record  # noqa: E402

LC008_TOOL_VERSION = "lc008-content-duplicate-identity-audit-v1"
EXPECTED_SNAPSHOT_SHA256 = "88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff"
EXPECTED_RECORD_COUNT = 42804

# ---------------------------------------------------------------------------
# field groups actually present in the snapshot (spec §5 — no invented fields)
# ---------------------------------------------------------------------------

IDENTITY_FIELDS = ("id",)                      # legacy alias; source_record_uuid ABSENT
PROVENANCE_FIELDS = ("source",)               # per-file SGF path
ANSWER_AUTHORITY_FIELDS = (
    "katago_best_move", "answer_source", "katago_full_report_status",
    "katago_full_previous_answer", "katago_full_score_gap", "katago_full_visits",
    "katago_full_applied_at", "katago_full_report", "katago_auto_source",
    "katago_auto_previous_answer", "katago_auto_applied_at",
    "answer", "answer_tactic", "answer_prev_move", "answer_conflict",
    "katago_match", "score_gap",
)
METADATA_FIELDS = (
    "topic", "topic_en", "level", "level_en", "difficulty", "rank", "stage",
    "stage_label", "stage_label_en", "discipline", "discipline_label",
    "discipline_label_en", "discipline_order", "grimoire_id",
    "grimoire_difficulty", "difficulty_score", "tags", "map_id", "map_name",
    "map_chapter", "weakness_topic", "monster_family", "monster_family_label",
    "monster_attribute", "encounter_type", "encounter_label", "boss_level",
    "boss_title", "monster_name", "battle_monster_type", "sort_order",
    "display_name", "enabled",
)
AUTHORING_FIELDS = ("comment", "manual_restore_note")

# canonical-identity field the owner model requires — audited for readiness
CANONICAL_UUID_KEYS = ("source_record_uuid", "uuid", "source_uuid", "record_uuid", "canonical_id")


def content_sha256(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _jkey(v: Any) -> str:
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _drifting_fields(records: list[dict[str, Any]], fields) -> list[str]:
    out = []
    for f in fields:
        if len({_jkey(r.get(f)) for r in records}) > 1:
            out.append(f)
    return out


def verify_snapshot(path: Path) -> tuple[str, bool, list[dict[str, Any]]]:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_SNAPSHOT_SHA256:
        return sha, False, []
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("snapshot must be a JSON list")
    return sha, True, data


# ---------------------------------------------------------------------------
# per-group classification
# ---------------------------------------------------------------------------

def classify_group(idxs: list[int], records: list[dict[str, Any]],
                   dup_legacy_ids: frozenset) -> dict[str, Any]:
    members = [records[i] for i in idxs]
    ids = [m.get("id") for m in members]
    sources = [m.get("source") for m in members]
    uuids = [next((m[k] for k in CANONICAL_UUID_KEYS if k in m), None) for m in members]

    legacy_ids_distinct = len(set(ids)) == len(ids)
    legacy_ids_all_same = len(set(ids)) == 1
    sources_distinct = len(set(sources)) == len(sources)
    uuid_present = all(u is not None for u in uuids)

    answer_drift = _drifting_fields(members, ANSWER_AUTHORITY_FIELDS)
    metadata_drift = _drifting_fields(members, METADATA_FIELDS)
    authoring_drift = _drifting_fields(members, AUTHORING_FIELDS)

    flags = []
    if legacy_ids_all_same:
        flags.append("SAME_CONTENT_SAME_LEGACY_ID")
    if not legacy_ids_all_same:
        flags.append("SAME_CONTENT_DIFFERENT_LEGACY_ID")
    if uuid_present and len(set(uuids)) == 1:
        flags.append("SAME_CONTENT_SAME_SOURCE_IDENTITY")
    if uuid_present and len(set(uuids)) > 1:
        flags.append("SAME_CONTENT_DIFFERENT_SOURCE_IDENTITY")
    if not uuid_present:
        flags.append("SAME_CONTENT_IDENTITY_INCOMPLETE")
    if sources_distinct and not uuid_present:
        # distinct per-file provenance and no canonical id to reconcile it
        flags.append("SAME_CONTENT_DIFFERENT_SOURCE_IDENTITY")
    if metadata_drift:
        flags.append("SAME_CONTENT_WITH_METADATA_DRIFT")
    if answer_drift:
        flags.append("SAME_CONTENT_WITH_PROVENANCE_DRIFT")
    if authoring_drift:
        flags.append("SAME_CONTENT_WITH_AUTHORING_DRIFT")
    flags = sorted(set(flags))

    # primary classification — most specific identity obstacle first
    if not uuid_present:
        primary = "SAME_CONTENT_IDENTITY_INCOMPLETE"
    elif len(set(uuids)) > 1:
        primary = "SAME_CONTENT_DIFFERENT_SOURCE_IDENTITY"
    elif answer_drift:
        primary = "SAME_CONTENT_WITH_PROVENANCE_DRIFT"
    elif metadata_drift:
        primary = "SAME_CONTENT_WITH_METADATA_DRIFT"
    elif authoring_drift:
        primary = "SAME_CONTENT_WITH_AUTHORING_DRIFT"
    elif not legacy_ids_all_same:
        primary = "SAME_CONTENT_DIFFERENT_LEGACY_ID"
    else:
        primary = "SAME_CONTENT_SAME_SOURCE_IDENTITY"

    # fanout — fail closed (spec §6/§7)
    if not uuid_present:
        fanout, reason = "BLOCKED_BY_INCOMPLETE_IDENTITY", (
            "source_record_uuid absent from every member; identical content does "
            "not prove identical canonical identity (spec §2)")
    elif len(set(uuids)) > 1:
        fanout, reason = "BLOCKED_BY_SOURCE_IDENTITY", "members carry different source_record_uuid"
    elif answer_drift:
        fanout, reason = "BLOCKED_BY_PROVENANCE", f"answer-authority drift: {answer_drift}"
    elif metadata_drift:
        fanout, reason = "BLOCKED_BY_METADATA", f"metadata drift: {metadata_drift}"
    elif authoring_drift:
        fanout, reason = "BLOCKED_BY_AUTHORING_CONTEXT", f"authoring drift: {authoring_drift}"
    elif not sources_distinct:
        fanout, reason = "SAFE_REVIEW_FANOUT", "same source_record_uuid, no drift, shared source"
    else:
        fanout, reason = "REQUIRES_INDEPENDENT_REVIEW", (
            "same source_record_uuid and no field drift, but distinct source paths "
            "leave independent-intent unproven")

    member_classes = [
        classify_record(records[i], duplicate_legacy_ids=dup_legacy_ids, snapshot_sha256="lc008").classification
        for i in idxs
    ]
    manual_members = [i for i, c in zip(idxs, member_classes) if c == "MANUAL_SEMANTIC_REVIEW"]

    without_fanout = len(manual_members)
    if fanout == "SAFE_REVIEW_FANOUT" and manual_members:
        with_fanout = 1
        savings = without_fanout - 1
        safe_primary = min(idxs)
    else:
        with_fanout = without_fanout
        savings = 0
        safe_primary = None

    return {
        "content_sha256": content_sha256(records[idxs[0]].get("content") or ""),
        "member_count": len(idxs),
        "record_indexes": list(idxs),
        "legacy_question_ids": ids,
        "source_record_uuids": uuids,
        "source_paths": sources,
        "primary_identity_classification": primary,
        "identity_flags": flags,
        "fanout_classification": fanout,
        "fanout_reason_code": reason,
        "metadata_drift": metadata_drift,
        "provenance_drift": answer_drift,
        "authoring_context_drift": authoring_drift,
        "member_post_lc009_classes": member_classes,
        "safe_primary_review_record": safe_primary,
        "manual_reviews_without_fanout": without_fanout,
        "manual_reviews_with_safe_fanout": with_fanout,
        "potential_review_savings": savings,
    }


def run(path: Path, out_manifest: Path | None) -> dict[str, Any]:
    sha, match, records = verify_snapshot(path)
    if not match:
        raise SystemExit(
            f"SNAPSHOT_HASH_MISMATCH: got {sha}, expected {EXPECTED_SNAPSHOT_SHA256}. STOP."
        )
    n = len(records)

    by_hash: dict[str, list[int]] = collections.defaultdict(list)
    for i, r in enumerate(records):
        by_hash[content_sha256(r.get("content") or "")].append(i)
    dup = {h: idxs for h, idxs in sorted(by_hash.items()) if len(idxs) > 1}

    idc = collections.Counter(r.get("id") for r in records)
    dup_legacy_ids = frozenset(k for k, c in idc.items() if c is not None and c > 1)

    group_rows = [classify_group(idxs, records, dup_legacy_ids) for idxs in dup.values()]

    # aggregates
    size_dist = collections.Counter(g["member_count"] for g in group_rows)
    prim = collections.Counter(g["primary_identity_classification"] for g in group_rows)
    fan = collections.Counter(g["fanout_classification"] for g in group_rows)
    dup_records = sum(g["member_count"] for g in group_rows)
    manual_in_dup = sum(g["manual_reviews_without_fanout"] for g in group_rows)
    safe_groups = [g for g in group_rows if g["fanout_classification"] == "SAFE_REVIEW_FANOUT"]
    savings = sum(g["potential_review_savings"] for g in group_rows)
    primary_reviews = sum(g["manual_reviews_with_safe_fanout"] for g in group_rows
                          if g["fanout_classification"] == "SAFE_REVIEW_FANOUT")

    # source_record_uuid readiness (spec §13)
    uuid_present = sum(1 for r in records if any(k in r for k in CANONICAL_UUID_KEYS))
    uuid_values = [next((r[k] for k in CANONICAL_UUID_KEYS if k in r), None) for r in records]
    uuid_nonnull = [v for v in uuid_values if v is not None]
    uuid_vc = collections.Counter(uuid_nonnull)
    uuid_dupe = sum(c for c in uuid_vc.values() if c > 1)
    uuid_anom = sum(1 for v in uuid_nonnull
                    if not (isinstance(v, str) and 8 <= len(v) <= 64))

    # 13 DUPLICATE_IDENTITY_BLOCKED reconciliation (spec §12)
    dib_idx = [i for i, r in enumerate(records)
               if classify_record(r, duplicate_legacy_ids=dup_legacy_ids,
                                  snapshot_sha256="lc008").classification == "DUPLICATE_IDENTITY_BLOCKED"]
    dib_hashes = {content_sha256(records[i].get("content") or "") for i in dib_idx}
    dib_in_content_dup = sorted(i for i in dib_idx
                                if content_sha256(records[i].get("content") or "") in dup)
    dib_legacy_ids = sorted({records[i].get("id") for i in dib_idx})

    summary = {
        "lc008_tool_version": LC008_TOOL_VERSION,
        "snapshot_sha256": sha,
        "snapshot_hash_match": match,
        "corpus_record_count": n,
        "record_count_match": n == EXPECTED_RECORD_COUNT,
        "distinct_content_hashes": len(by_hash),
        "content_duplicate_groups": len(dup),
        "content_duplicate_records": dup_records,
        "records_not_in_any_duplicate_group": n - dup_records,
        "duplicate_group_size_min": min(size_dist),
        "duplicate_group_size_max": max(size_dist),
        "duplicate_group_size_distribution": {str(k): v for k, v in sorted(size_dist.items())},
        "primary_identity_classification_counts": dict(prim),
        "fanout_classification_counts": dict(fan),
        "manual_records_in_duplicate_groups": manual_in_dup,
        "safe_review_fanout_groups": len(safe_groups),
        "safe_review_fanout_records": sum(g["member_count"] for g in safe_groups),
        "safe_fanout_primary_reviews_required": primary_reviews,
        "potential_manual_review_dedup_savings": savings,
        "fields_available": {
            "identity": list(IDENTITY_FIELDS),
            "canonical_uuid_present": uuid_present > 0,
            "provenance": list(PROVENANCE_FIELDS),
            "answer_authority": list(ANSWER_AUTHORITY_FIELDS),
            "metadata": list(METADATA_FIELDS),
            "authoring": list(AUTHORING_FIELDS),
        },
        "source_record_uuid_present_count": uuid_present,
        "source_record_uuid_missing_count": n - uuid_present,
        "source_record_uuid_duplicate_count": uuid_dupe,
        "source_record_uuid_collision_count": uuid_dupe,
        "source_record_uuid_format_anomaly_count": uuid_anom,
        "source_record_uuid_generated": False,
        "content_hash_semantics": {
            "algorithm": "sha256",
            "input": "record['content'] encoded utf-8 (the SGF string only)",
            "excludes": ["comment (sibling top-level field)", "all metadata fields",
                         "all provenance / source fields", "all answer-authority / katago fields"],
            "normalisation": "none",
            "equal_hash_implies": "byte-identical SGF content and nothing else",
        },
        "duplicate_identity_blocked_records": len(dib_idx),
        "duplicate_identity_blocked_indexes": dib_idx,
        "duplicate_identity_blocked_legacy_ids": dib_legacy_ids,
        "duplicate_identity_blocked_distinct_content_hashes": len(dib_hashes),
        "duplicate_identity_blocked_in_content_duplicate_groups": dib_in_content_dup,
        "all_13_accounted_for": (
            len(dib_idx) == 13 and not dib_in_content_dup and len(dib_hashes) == len(dib_idx)
        ),
        "duplicate_legacy_id_groups": len(dup_legacy_ids),
        "duplicate_legacy_id_values": sorted(dup_legacy_ids),
        "content_dedup_does_not_rewrite_identity": True,
        "lc009_semantics_changed": False,
        "corpus_mutation": False,
    }

    manifest = {
        "schema_version": "1.0",
        "authority": "LC008_CONTENT_DUPLICATE_IDENTITY_AND_REVIEW_FANOUT_AUDIT_001",
        "canonicality": "AUDIT_ONLY__NO_MUTATION__NO_IDENTITY_REWRITE",
        "summary": summary,
        "groups": group_rows,
    }
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
    p = argparse.ArgumentParser(description="LC008 content-duplicate identity & fanout audit (read-only).")
    p.add_argument("--snapshot", type=Path, required=True)
    p.add_argument("--out-manifest", type=Path)
    args = p.parse_args(argv)
    if not args.snapshot.exists():
        raise SystemExit(f"snapshot not found: {args.snapshot}")
    result = run(args.snapshot, args.out_manifest)
    rep = dict(result["summary"])
    rep["manifest_path"] = result["manifest_path"]
    rep["manifest_sha256"] = result["manifest_sha256"]
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
