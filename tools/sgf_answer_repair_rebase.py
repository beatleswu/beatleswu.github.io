"""Replay the approved SGF repair batch against a newer canonical corpus.

This adapter deliberately consumes the locked 43-group/54-record safe release
batch.  It does not discover repairs or alter judging/runtime semantics.  The
current corpus is read from an explicitly supplied immutable input and the
candidate is written to an explicitly supplied isolated artifact path.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools import sgf_answer_content_release as release
from tools import sgf_answer_repair_batch as repair
from tools.content_release_core import (
    ArtifactIdentity,
    GovernanceError,
    build_source_provenance,
    canonical_payload_sha256,
    identify_json,
    sha256_file,
    validate_release_manifest_semantics,
)
from tools.sgf_pr318_binding import (
    REQUIRED_SURFACES,
    _build_acceptance_evidence,
    _build_review_binding,
    _write_json,
)


SAFE_RELEASE_BATCH_SHA256 = (
    "b22496144cbbc5af2b1bc1ab46332532fc6849cc24bd66a4b277fd94385427d6"
)
SAFE_RELEASE_BATCH_FILE_SHA256 = (
    "a692796b4f88e985f8ebac0e0f2b520f58b288e6aaf04a1fc135506548a7dc1a"
)
APPROVED_REPAIR_GROUP_COUNT = 43
APPROVED_REPAIRED_RECORD_COUNT = 54
APPROVED_EXCLUSION_COUNT = 11
APPROVED_FALLBACK_CONFLICT_COUNT = 3
HISTORICAL_BASELINE_SHA256 = (
    "4d13fa98af8c1a180e719b7a261c5ca638e042a8edbd3fdfe8d2c2f947cdaa28"
)
HISTORICAL_CANDIDATE_SHA256 = (
    "b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"
)
CONTRACT_AUTHORITY = "SGF_REPAIR_BATCH_REBASE_CURRENT_CANONICAL_001"


class RebaseError(RuntimeError):
    """A fail-closed current-canonical replay failure."""


def _json_load(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RebaseError(f"{label}_unreadable") from error


def _load_corpus(path: Path, label: str) -> tuple[bytes, list[dict[str, Any]], ArtifactIdentity]:
    try:
        raw = path.read_bytes()
        records = release._load_corpus_bytes(raw)
    except (OSError, release.ContentReleaseError) as error:
        raise RebaseError(f"{label}_corpus_invalid") from error
    identity = identify_json(path)
    return raw, records, identity


def _content_sha256(record: Mapping[str, Any], label: str) -> str:
    content = record.get("content")
    if not isinstance(content, str) or not content:
        raise RebaseError(f"{label}_content_missing")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _record_identity(record: Mapping[str, Any], index: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "legacy_question_id": record.get("id"),
        "content_sha256": _content_sha256(record, "record"),
        "fallback_move": str(record.get("katago_best_move") or ""),
    }
    if index is not None:
        result["record_index"] = index
    return result


def _load_approved_batch(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        value, native, fallback = release._load_relocked_release_batch(
            path,
            expected_file_sha256=SAFE_RELEASE_BATCH_FILE_SHA256,
            expected_batch_sha256=SAFE_RELEASE_BATCH_SHA256,
        )
    except release.ContentReleaseError as error:
        raise RebaseError(str(error)) from error
    batch = value["batch"]
    summary = batch.get("summary") or {}
    if (
        len(batch.get("groups") or []) != APPROVED_REPAIR_GROUP_COUNT
        or len(native) + len(fallback) != APPROVED_REPAIRED_RECORD_COUNT
        or len(batch.get("excluded_map_battle_records") or []) != APPROVED_EXCLUSION_COUNT
        or summary.get("records") != APPROVED_REPAIRED_RECORD_COUNT
    ):
        raise RebaseError("approved_repair_scope_identity_mismatch")
    return value, native, fallback


def _proposal_group_keys(proposal_snapshot: Mapping[str, Any]) -> set[str]:
    groups = proposal_snapshot.get("groups")
    if not isinstance(groups, list):
        raise RebaseError("proposal_snapshot_groups_missing")
    keys = {
        group.get("review_group_key")
        for group in groups
        if isinstance(group, Mapping) and isinstance(group.get("review_group_key"), str)
    }
    return {key for key in keys if key}


def classify_approved_targets(
    *,
    current_records: Sequence[Mapping[str, Any]],
    native_records: Sequence[Mapping[str, Any]],
    fallback_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Classify by stable question id and relevant byte-level preconditions."""

    indexes: dict[int, list[int]] = {}
    for index, record in enumerate(current_records):
        question_id = record.get("id")
        if isinstance(question_id, int) and not isinstance(question_id, bool):
            indexes.setdefault(question_id, []).append(index)
    result: list[dict[str, Any]] = []
    for lane, rows in (("NATIVE_SGF_REPAIR", native_records), ("FALLBACK_CLEAR", fallback_records)):
        for locked in rows:
            question_id = int(locked["legacy_question_id"])
            group_key = str(locked["review_group_key"])
            historical = {
                "legacy_question_id": question_id,
                "record_index": locked.get("current_record_index"),
                "content_sha256_before": locked.get("source_content_sha256_before"),
                "content_sha256_after": locked.get("source_content_sha256_after"),
                "fallback_before": str(locked.get("current_fallback_move") or ""),
                "fallback_after": (
                    str(locked.get("current_fallback_move") or "")
                    if lane == "NATIVE_SGF_REPAIR"
                    else ""
                ),
            }
            occurrences = indexes.get(question_id, [])
            base: dict[str, Any] = {
                "review_group_key": group_key,
                "lane": lane,
                "legacy_question_id": question_id,
                "historical_source_identity": historical,
                "approved_intended_change": {
                    "changed_fields": ["content"] if lane == "NATIVE_SGF_REPAIR" else ["katago_best_move"],
                    "owner_desired_verdict": locked.get("owner_desired_verdict"),
                    "desired_native_accepted_set": locked.get("desired_native_accepted_set"),
                    "desired_fallback_move": locked.get("desired_fallback_move"),
                    "source_content_sha256_after": locked.get("source_content_sha256_after"),
                },
            }
            if len(occurrences) != 1:
                base["classification"] = "MISSING_TARGET" if not occurrences else "DRIFTED_TARGET"
                base["current_source_identity"] = {
                    "occurrence_count": len(occurrences),
                    "record_indices": occurrences,
                }
                base["unsafe_reason"] = (
                    "approved target is absent from current corpus"
                    if not occurrences
                    else "stable question id is not unique in current corpus"
                )
                result.append(base)
                continue
            index = occurrences[0]
            current = current_records[index]
            current_identity = _record_identity(current, index)
            base["current_source_identity"] = current_identity
            current_content = current_identity["content_sha256"]
            current_fallback = current_identity["fallback_move"]
            before_match = (
                current_content == historical["content_sha256_before"]
                and current_fallback == historical["fallback_before"]
            )
            after_match = (
                current_content == historical["content_sha256_after"]
                and current_fallback == historical["fallback_after"]
            )
            if before_match:
                classification = "UNCHANGED_TARGET"
            elif after_match:
                classification = "ALREADY_REPAIRED"
            else:
                classification = "DRIFTED_TARGET"
            base["classification"] = classification
            if classification == "DRIFTED_TARGET":
                base["unsafe_reason"] = (
                    "current SGF/content or relevant fallback bytes do not match either "
                    "the approved source precondition or the approved after-state"
                )
            result.append(base)
    result.sort(key=lambda row: (row["lane"], row["legacy_question_id"], row["review_group_key"]))
    return result


def _build_replacements(
    *,
    current_records: Sequence[Mapping[str, Any]],
    classifications: Sequence[Mapping[str, Any]],
    native_records: Sequence[Mapping[str, Any]],
    fallback_records: Sequence[Mapping[str, Any]],
) -> tuple[dict[int, dict[str, str]], dict[int, Sequence[str]]]:
    by_key = {
        (str(row["lane"]), int(row["legacy_question_id"]), str(row["review_group_key"])): row
        for row in classifications
    }
    indexes = {
        int(record["id"]): index
        for index, record in enumerate(current_records)
        if isinstance(record.get("id"), int) and not isinstance(record.get("id"), bool)
    }
    replacements: dict[int, dict[str, str]] = {}
    expected: dict[int, Sequence[str]] = {}
    for lane, rows in (("NATIVE_SGF_REPAIR", native_records), ("FALLBACK_CLEAR", fallback_records)):
        for locked in rows:
            question_id = int(locked["legacy_question_id"])
            key = (lane, question_id, str(locked["review_group_key"]))
            classification = by_key[key]
            if classification["classification"] == "ALREADY_REPAIRED":
                expected[question_id] = locked["owner_desired_verdict"]
                continue
            if classification["classification"] != "UNCHANGED_TARGET":
                raise RebaseError("cannot_build_candidate_with_unsafe_target")
            index = indexes[question_id]
            record = current_records[index]
            content = record.get("content")
            if not isinstance(content, str):
                raise RebaseError(f"target_content_missing:{question_id}")
            expected[question_id] = locked["owner_desired_verdict"]
            if lane == "NATIVE_SGF_REPAIR":
                size = release._board_size(content)
                labels = list(locked["desired_native_accepted_set"])
                operations = [
                    operation
                    for operation in (locked.get("planned_operations") or [])
                    if operation.get("type") == "REWRITE_NATIVE_ROOT_ANSWER_SET"
                ]
                if operations:
                    if len(operations) != 1 or not isinstance(operations[0].get("after"), list):
                        raise RebaseError(f"ambiguous_native_rewrite:{question_id}")
                    labels = list(operations[0]["after"])
                points = [repair._gtp_to_xy(label, size) for label in labels]
                if any(point is None for point in points):
                    raise RebaseError(f"invalid_native_rewrite:{question_id}")
                repaired, _ = repair._rewrite_answer_set(content, points)
                if hashlib.sha256(repaired.encode("utf-8")).hexdigest() != locked["source_content_sha256_after"]:
                    raise RebaseError(f"approved_native_after_hash_mismatch:{question_id}")
                replacements[index] = {"content": repaired}
            else:
                if locked.get("desired_fallback_move") != "":
                    raise RebaseError(f"approved_fallback_after_state_invalid:{question_id}")
                if hashlib.sha256(content.encode("utf-8")).hexdigest() != locked["source_content_sha256_after"]:
                    raise RebaseError(f"fallback_content_drift:{question_id}")
                replacements[index] = {"katago_best_move": ""}
    return replacements, expected


def _rebase_semantic_diff(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    classifications: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    class_by_id = {int(row["legacy_question_id"]): row for row in classifications}
    changed: list[dict[str, Any]] = []
    non_target: list[int] = []
    accepted_moves: list[int] = []
    if len(baseline) != len(candidate):
        raise RebaseError("candidate_record_count_changed")
    for index, (before, after) in enumerate(zip(baseline, candidate)):
        if before.get("id") != after.get("id"):
            raise RebaseError(f"record_identity_or_order_changed:{index}")
        question_id = int(before["id"])
        fields = sorted(
            key for key in (set(before) | set(after)) if before.get(key) != after.get(key)
        )
        if before.get("accepted_moves") != after.get("accepted_moves"):
            accepted_moves.append(question_id)
        if not fields:
            continue
        row = class_by_id.get(question_id)
        if row is None:
            non_target.append(question_id)
            continue
        lane = row["lane"]
        expected_fields = ["content"] if lane == "NATIVE_SGF_REPAIR" else ["katago_best_move"]
        if row["classification"] == "ALREADY_REPAIRED":
            raise RebaseError(f"already_repaired_target_changed:{question_id}")
        if fields != expected_fields:
            raise RebaseError(f"target_changed_unapproved_fields:{question_id}:{fields}")
        changed.append(
            {
                "question_id": question_id,
                "record_index": index,
                "changed_fields": fields,
                "classification": row["classification"],
                "review_group_key": row["review_group_key"],
                "lane": lane,
            }
        )
    expected_changed = {
        int(row["legacy_question_id"])
        for row in classifications
        if row["classification"] == "UNCHANGED_TARGET"
    }
    actual_changed = {int(row["question_id"]) for row in changed}
    if actual_changed != expected_changed:
        raise RebaseError(
            f"target_mutation_mismatch:missing={sorted(expected_changed - actual_changed)},"
            f"extra={sorted(actual_changed - expected_changed)}"
        )
    if non_target or accepted_moves:
        raise RebaseError("non_target_or_accepted_moves_mutation")
    return {
        "target_records_changed": len(changed),
        "non_target_records_changed": 0,
        "accepted_moves_changed": 0,
        "native_repair_records": sum(1 for row in changed if row["lane"] == "NATIVE_SGF_REPAIR"),
        "fallback_fields_cleared": sum(1 for row in changed if row["lane"] == "FALLBACK_CLEAR"),
        "records": sorted(changed, key=lambda row: row["question_id"]),
    }


def build_current_candidate(
    *,
    baseline_path: Path,
    safe_release_batch_path: Path,
    output_path: Path,
    expected_baseline_sha256: str,
    expected_record_count: int,
) -> dict[str, Any]:
    raw, baseline_records, baseline = _load_corpus(baseline_path, "current_baseline")
    if baseline.sha256 != expected_baseline_sha256 or baseline.record_count != expected_record_count:
        raise RebaseError(
            f"current_baseline_precondition_mismatch:sha256={baseline.sha256}:records={baseline.record_count}"
        )
    _, native_records, fallback_records = _load_approved_batch(safe_release_batch_path)
    classifications = classify_approved_targets(
        current_records=baseline_records,
        native_records=native_records,
        fallback_records=fallback_records,
    )
    summary = {
        "UNCHANGED_TARGET": sum(row["classification"] == "UNCHANGED_TARGET" for row in classifications),
        "ALREADY_REPAIRED": sum(row["classification"] == "ALREADY_REPAIRED" for row in classifications),
        "DRIFTED_TARGET": sum(row["classification"] == "DRIFTED_TARGET" for row in classifications),
        "MISSING_TARGET": sum(row["classification"] == "MISSING_TARGET" for row in classifications),
    }
    if summary["DRIFTED_TARGET"] or summary["MISSING_TARGET"]:
        raise RebaseError("unsafe_targets_present")
    replacements, expected_by_id = _build_replacements(
        current_records=baseline_records,
        classifications=classifications,
        native_records=native_records,
        fallback_records=fallback_records,
    )
    candidate_raw, _ = release.patch_corpus_string_fields(raw, baseline_records, replacements)
    candidate_records = release._load_corpus_bytes(candidate_raw)
    diff = _rebase_semantic_diff(baseline_records, candidate_records, classifications)
    candidate_path = output_path
    if candidate_path.exists() and candidate_path.read_bytes() != candidate_raw:
        raise RebaseError(f"refusing_to_overwrite_different_candidate:{candidate_path}")
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    if not candidate_path.exists():
        candidate_path.write_bytes(candidate_raw)
    candidate_identity = identify_json(candidate_path)
    return {
        "baseline_identity": baseline,
        "candidate_identity": candidate_identity,
        "baseline_records": baseline_records,
        "candidate_records": candidate_records,
        "classifications": classifications,
        "classification_summary": summary,
        "expected_by_id": expected_by_id,
        "mutation_audit": diff,
    }


def _artifact_dict(identity: ArtifactIdentity) -> dict[str, Any]:
    return {
        "filename": Path(identity.path).name,
        "size_bytes": identity.size_bytes,
        "record_count": identity.record_count,
        "sha256": identity.sha256,
    }


def build_current_contract(
    *,
    rebase: Mapping[str, Any],
    base_ref: str,
    safe_release_batch_path: Path,
    review_queue_path: Path,
    proposal_snapshot_path: Path,
    repair_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline: ArtifactIdentity = rebase["baseline_identity"]
    candidate: ArtifactIdentity = rebase["candidate_identity"]
    classifications = list(rebase["classifications"])
    mutation_audit = dict(rebase["mutation_audit"])
    review_queue = _json_load(review_queue_path, "review_queue")
    proposal_snapshot = _json_load(proposal_snapshot_path, "proposal_snapshot")
    repair_manifest = _json_load(repair_manifest_path, "repair_manifest")
    safe_release = _json_load(safe_release_batch_path, "safe_release_batch")
    if not all(isinstance(value, Mapping) for value in (review_queue, proposal_snapshot, repair_manifest, safe_release)):
        raise RebaseError("contract_inputs_must_be_objects")
    proposal_sha256 = sha256_file(proposal_snapshot_path)
    repair_manifest_sha256 = sha256_file(repair_manifest_path)
    safe_release_sha256 = sha256_file(safe_release_batch_path)
    batch = safe_release["batch"]
    group_ids = [str(group["review_group_key"]) for group in batch["groups"]]
    if review_queue.get("source_snapshot", {}).get("sha256") != baseline.sha256:
        raise RebaseError("review_queue_source_snapshot_does_not_match_current_baseline")
    review_binding = _build_review_binding(
        review_queue=review_queue,
        proposal_snapshot_sha256=proposal_sha256,
        release_group_ids=group_ids,
        proposal_group_keys=_proposal_group_keys(proposal_snapshot),
    )
    review_binding_path = output_dir / "review-binding.json"
    review_binding_sha256 = _write_json(review_binding_path, review_binding)
    mutation_audit.update(
        {
            "schema_version": "1.0",
            "authority": CONTRACT_AUTHORITY,
            "canonicality": "STAGED_NOT_APPLIED",
            "source_sha256": baseline.sha256,
            "candidate_sha256": candidate.sha256,
            "changed_record_count": mutation_audit["target_records_changed"],
            "review_group_count": APPROVED_REPAIR_GROUP_COUNT,
            "historical_baseline_sha256": HISTORICAL_BASELINE_SHA256,
            "historical_candidate_sha256": HISTORICAL_CANDIDATE_SHA256,
            "classification_summary": rebase["classification_summary"],
        }
    )
    mutation_audit_path = output_dir / "mutation-audit.json"
    mutation_audit_sha256 = _write_json(mutation_audit_path, mutation_audit)
    verdict = release.validate_player_verdicts(
        rebase["candidate_records"],
        rebase["expected_by_id"],
    )
    acceptance = _build_acceptance_evidence(
        candidate=candidate,
        candidate_records=rebase["candidate_records"],
        release={"verdict_validation": verdict},
    )
    acceptance_path = output_dir / "acceptance-evidence.json"
    acceptance_sha256 = _write_json(acceptance_path, acceptance)
    receipt = {
        "schema_version": "1.0",
        "authority": CONTRACT_AUTHORITY,
        "source_kind": "CURRENT_CANONICAL_CORPUS_READ_ONLY_SNAPSHOT",
        "source_repo_id": "beatleswu/beatleswu.github.io",
        "source_commit_or_snapshot_id": f"{base_ref}:{baseline.sha256}",
        "source_path": "canonical/current/questions.json",
        "source_sha256": baseline.sha256,
        "source_size_bytes": baseline.size_bytes,
        "source_record_count": baseline.record_count,
        "production_contact": "NONE",
        "canonical_mutation": "NO",
    }
    receipt_path = output_dir / "current-baseline-receipt.json"
    receipt_sha256 = _write_json(receipt_path, receipt)
    provenance = build_source_provenance(
        Path(baseline.path),
        source_kind="immutable_snapshot",
        source_repo_id="beatleswu/beatleswu.github.io",
        source_commit_or_snapshot_id=f"{base_ref}:{baseline.sha256}",
        source_path="canonical/current/questions.json",
        source_receipt_sha256=receipt_sha256,
        review_source_id=review_binding["review_source_id"],
        detector_manifest_sha256=review_binding["detector_manifest_sha256"],
        validation_pack_id=review_binding["validation_pack_id"],
        approved_proposal_set_sha256=proposal_sha256,
    )
    provenance_path = output_dir / "source-provenance.json"
    provenance_sha256 = _write_json(provenance_path, provenance)
    simulation_path = output_dir / "rollback-simulation.json"
    simulation = release.simulate_publish_and_rollback(
        baseline_artifact=Path(baseline.path),
        candidate_artifact=Path(candidate.path),
        baseline_sha256=baseline.sha256,
        candidate_sha256=candidate.sha256,
        expected_record_count=baseline.record_count,
        output_path=simulation_path,
        created_at="2026-08-11T00:00:00Z",
    )
    rollback = {
        "schema_version": "1.0",
        "authority": CONTRACT_AUTHORITY,
        "canonicality": "STAGED_NOT_APPLIED",
        "rollback_governance": {
            "previous_sha256": baseline.sha256,
            "candidate_sha256": candidate.sha256,
            "record_count": baseline.record_count,
            "restore_target": "/app/data/questions.json",
            "post_rollback": {
                "sha256": baseline.sha256,
                "size_bytes": baseline.size_bytes,
                "record_count": baseline.record_count,
            },
            "simulation_sha256": sha256_file(simulation_path),
            "simulation_mode": "LOCAL_DISPOSABLE_EXACT_BYTE_SIMULATION_ONLY",
        },
        "safety": {
            "production_contact": "NONE",
            "production_mutation": "NO",
            "publish_requires_rollback_proof": True,
        },
    }
    rollback_path = output_dir / "rollback-manifest.json"
    rollback_sha256 = _write_json(rollback_path, rollback)
    repair_batch = {
        "schema_version": "1.0",
        "authority": CONTRACT_AUTHORITY,
        "canonicality": "STAGED_NOT_APPLIED",
        "source_sha256": baseline.sha256,
        "candidate_sha256": candidate.sha256,
        "review_binding_sha256": review_binding_sha256,
        "mutation_audit_sha256": mutation_audit_sha256,
        "acceptance_evidence_sha256": acceptance_sha256,
        "changed_record_count": mutation_audit["target_records_changed"],
        "review_group_count": APPROVED_REPAIR_GROUP_COUNT,
        "excluded_record_count": APPROVED_EXCLUSION_COUNT,
        "conflict_count": APPROVED_FALLBACK_CONFLICT_COUNT,
        "approved_proposal_set_sha256": proposal_sha256,
        "repair_manifest_sha256": repair_manifest_sha256,
        "safe_release_batch_sha256": safe_release["batch_sha256"],
        "safe_release_batch_file_sha256": safe_release_sha256,
        "current_baseline_sha256": baseline.sha256,
        "historical_baseline_sha256": HISTORICAL_BASELINE_SHA256,
        "historical_candidate_sha256": HISTORICAL_CANDIDATE_SHA256,
        "mutation_performed": False,
        "production_publish_authorized": False,
    }
    repair_batch_path = output_dir / "repair-batch-manifest.json"
    repair_batch_sha256 = _write_json(repair_batch_path, repair_batch)
    release_manifest = {
        "schema_version": "1.1",
        "authority": CONTRACT_AUTHORITY,
        "created_at": "2026-08-11T00:00:00Z",
        "source_baseline_sha256": baseline.sha256,
        "intended_production_destination": "/app/data/questions.json",
        "publisher_precondition_hash_lock": baseline.sha256,
        "pre_mutation_artifact": _artifact_dict(baseline),
        "repaired_candidate_artifact": _artifact_dict(candidate),
        "mutation_audit": mutation_audit,
        "repair_records": classifications,
        "verdict_validation": verdict,
        "safety": {
            "production_contact": "NONE",
            "production_mutation": "NO",
            "canonical_corpus_mutation": "NO",
            "accepted_moves_mutated": False,
            "merge": "NO",
            "deploy": "NO",
        },
        "release_governance": {
            "source_provenance": provenance,
            "source_identity_sha256": provenance["source_identity_sha256"],
            "review_binding_sha256": review_binding_sha256,
            "repair_batch_manifest_sha256": repair_batch_sha256,
            "mutation_audit_sha256": mutation_audit_sha256,
            "acceptance_evidence_sha256": acceptance_sha256,
            "rollback_manifest_sha256": rollback_sha256,
            "changed_record_count": mutation_audit["target_records_changed"],
            "review_group_count": APPROVED_REPAIR_GROUP_COUNT,
            "excluded_record_count": APPROVED_EXCLUSION_COUNT,
            "allowed_asset_names": [
                "questions.repaired-candidate.json.gz",
                "content-release-manifest.json",
                "content-rollback-manifest.json",
                "acceptance-evidence.json",
                "content-registry-entry.json",
                "SHA256SUMS.txt",
            ],
        },
    }
    release_manifest_path = output_dir / "release-manifest.json"
    release_manifest_sha256 = _write_json(release_manifest_path, release_manifest)
    try:
        validate_release_manifest_semantics(
            release_manifest,
            baseline_sha256=baseline.sha256,
            baseline_record_count=baseline.record_count,
            candidate_identity=candidate,
            expected_release_manifest_sha256=release_manifest_sha256,
            expected_rollback_manifest_sha256=rollback_sha256,
            release_records=mutation_audit["target_records_changed"],
            excluded_map_battle_records=APPROVED_EXCLUSION_COUNT,
            source_provenance=provenance_path,
            review_binding=review_binding_path,
            repair_batch_manifest=repair_batch_path,
            mutation_audit=mutation_audit_path,
            acceptance_evidence=acceptance_path,
            rollback_manifest=rollback_path,
        )
    except GovernanceError as error:
        raise RebaseError(str(error)) from error
    report = {
        "schema_version": "1.0",
        "authority": CONTRACT_AUTHORITY,
        "base": base_ref,
        "current_baseline": _artifact_dict(baseline),
        "current_candidate": _artifact_dict(candidate),
        "classification_summary": rebase["classification_summary"],
        "approved_repair_group_count": APPROVED_REPAIR_GROUP_COUNT,
        "approved_record_count": APPROVED_REPAIRED_RECORD_COUNT,
        "exclusion_count": APPROVED_EXCLUSION_COUNT,
        "fallback_conflict_count": APPROVED_FALLBACK_CONFLICT_COUNT,
        "verdict_mismatch_count": 0,
        "six_surfaces_complete": set(acceptance["summary"]["surfaces"]) == set(REQUIRED_SURFACES),
        "target_classifications": classifications,
        "production_mutation": "NO",
        "canonical_mutation": "NO",
        "gf003_state": {
            "runtime_status": "disabled",
            "apply_automatically": False,
            "ready_promotion": "NO",
        },
        "artifact_hashes": {
            "source_provenance_sha256": provenance_sha256,
            "review_binding_sha256": review_binding_sha256,
            "repair_batch_manifest_sha256": repair_batch_sha256,
            "mutation_audit_sha256": mutation_audit_sha256,
            "acceptance_evidence_sha256": acceptance_sha256,
            "rollback_manifest_sha256": rollback_sha256,
            "release_manifest_sha256": release_manifest_sha256,
            "rollback_simulation_sha256": sha256_file(simulation_path),
        },
    }
    report_path = output_dir / "current-canonical-rebase-report.json"
    report_sha256 = _write_json(report_path, report)
    return {
        **report,
        "report_sha256": report_sha256,
        "artifact_paths": {
            "candidate": str(candidate.path),
            "report": str(report_path),
            "source_provenance": str(provenance_path),
            "review_binding": str(review_binding_path),
            "repair_batch_manifest": str(repair_batch_path),
            "mutation_audit": str(mutation_audit_path),
            "acceptance_evidence": str(acceptance_path),
            "rollback_manifest": str(rollback_path),
            "release_manifest": str(release_manifest_path),
            "rollback_simulation": str(simulation_path),
        },
    }


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate-output", required=True, type=Path)
    parser.add_argument("--safe-release-batch", required=True, type=Path)
    parser.add_argument("--review-queue", required=True, type=Path)
    parser.add_argument("--proposal-snapshot", required=True, type=Path)
    parser.add_argument("--repair-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        rebase = build_current_candidate(
            baseline_path=args.baseline,
            safe_release_batch_path=args.safe_release_batch,
            output_path=args.candidate_output,
            expected_baseline_sha256="88da3e43b41f46380a2c0534fa2fc892b69eb99df4055dd635333b7153f654ff",
            expected_record_count=42804,
        )
        result = build_current_contract(
            rebase=rebase,
            base_ref=args.base_ref,
            safe_release_batch_path=args.safe_release_batch,
            review_queue_path=args.review_queue,
            proposal_snapshot_path=args.proposal_snapshot,
            repair_manifest_path=args.repair_manifest,
            output_dir=args.output_dir,
        )
    except (RebaseError, GovernanceError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
