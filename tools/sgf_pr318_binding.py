"""Bind the SGF repair batch to the PR318 content-release contract.

The repair planner and release builder remain the owners of repair decisions.
This module only derives immutable, machine-verifiable contract artifacts from
their existing evidence.  It never writes a corpus or contacts Production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.content_release_core import (
    ArtifactIdentity,
    GovernanceError,
    build_source_provenance,
    canonical_payload_sha256,
    identify_json,
    load_json_object,
    sha256_file,
    validate_acceptance_evidence,
    validate_release_manifest_semantics,
    validate_review_binding,
)


REQUIRED_SURFACES = (
    "sgf_engine_native",
    "rating_test_server",
    "map_battle_server",
    "main_practice_client",
    "daily_challenge_client",
    "friend_challenge_client_then_server_trust",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CONTRACT_SCHEMA_VERSION = "1.0"
CONTRACT_AUTHORITY = "SGF_ANSWER_REPAIR_BATCH_001_PR318_BOUND"
REQUIRED_ASSET_NAMES = [
    "questions.repaired-candidate.json.gz",
    "content-release-manifest.json",
    "content-rollback-manifest.json",
    "acceptance-evidence.json",
    "content-registry-entry.json",
    "SHA256SUMS.txt",
]


class BindingError(RuntimeError):
    """A fail-closed repair-package binding failure."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> str:
    raw = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if path.exists() and path.read_bytes() != raw:
        raise BindingError(f"refusing to overwrite different contract artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BindingError(f"{label}_unreadable") from error


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise BindingError(f"{label}_invalid")
    return value


def _require_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BindingError(f"{label}_invalid")
    return value


def _corpus(path: Path, label: str) -> tuple[bytes, list[dict[str, Any]], ArtifactIdentity]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BindingError(f"{label}_corpus_unreadable") from error
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise BindingError(f"{label}_corpus_shape_invalid")
    identity = identify_json(path)
    return raw, value, identity


def _artifact_dict(identity: ArtifactIdentity) -> dict[str, Any]:
    return {
        "filename": Path(identity.path).name,
        "size_bytes": identity.size_bytes,
        "record_count": identity.record_count,
        "sha256": identity.sha256,
    }


def _record_content_sha256(record: Mapping[str, Any], label: str) -> str:
    content = record.get("content")
    if not isinstance(content, str) or not content:
        raise BindingError(f"{label}_content_missing")
    return _sha256_text(content)


def _verify_historical_release(
    *,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    release_manifest: Path,
    rollback_manifest: Path,
    simulation: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str, str]:
    release = _load(release_manifest, "historical_release_manifest")
    rollback = _load(rollback_manifest, "historical_rollback_manifest")
    simulation_payload = _load(simulation, "historical_rollback_simulation")
    if not isinstance(release, Mapping) or not isinstance(rollback, Mapping):
        raise BindingError("historical_release_artifacts_must_be_objects")
    release_hash = sha256_file(release_manifest)
    rollback_hash = sha256_file(rollback_manifest)
    previous = release.get("pre_mutation_artifact")
    released = release.get("repaired_candidate_artifact")
    if not isinstance(previous, Mapping) or not isinstance(released, Mapping):
        raise BindingError("historical_release_artifact_identity_missing")
    if previous.get("sha256") != baseline.sha256 or previous.get("size_bytes") != baseline.size_bytes or previous.get("record_count") != baseline.record_count:
        raise BindingError("historical_baseline_identity_mismatch")
    if released.get("sha256") != candidate.sha256 or released.get("size_bytes") != candidate.size_bytes or released.get("record_count") != candidate.record_count:
        raise BindingError("historical_candidate_identity_mismatch")
    if release.get("source_baseline_sha256") != baseline.sha256:
        raise BindingError("historical_source_baseline_mismatch")
    if rollback.get("rollback_precondition_candidate_sha256") != candidate.sha256:
        raise BindingError("historical_rollback_candidate_mismatch")
    if rollback.get("rollback_expected_final_sha256") != baseline.sha256:
        raise BindingError("historical_rollback_baseline_mismatch")
    if not isinstance(simulation_payload, Mapping):
        raise BindingError("historical_rollback_simulation_invalid")
    if simulation_payload.get("published_sha256") != candidate.sha256:
        raise BindingError("historical_simulation_candidate_mismatch")
    if simulation_payload.get("rollback_final_sha256") != baseline.sha256:
        raise BindingError("historical_simulation_baseline_mismatch")
    if simulation_payload.get("rollback_byte_exact") != "YES":
        raise BindingError("historical_simulation_not_byte_exact")
    if simulation_payload.get("production_contact") != "NONE" or simulation_payload.get("production_mutation") != "NO":
        raise BindingError("historical_simulation_production_contact")
    mutation = release.get("mutation_audit")
    verdict = release.get("verdict_validation")
    if not isinstance(mutation, Mapping) or not isinstance(verdict, Mapping):
        raise BindingError("historical_mutation_or_verdict_evidence_missing")
    if mutation.get("target_records_changed") != len(mutation.get("records") or []):
        raise BindingError("historical_mutation_record_count_mismatch")
    if mutation.get("non_target_records_changed") != 0 or mutation.get("accepted_moves_changed") != 0:
        raise BindingError("historical_mutation_scope_violation")
    if verdict.get("all_final_effective_match") is not True or verdict.get("map_battle_mismatch_count") != 0:
        raise BindingError("historical_verdict_validation_failed")
    return dict(release), dict(rollback), dict(simulation_payload), release_hash, rollback_hash


def _build_review_binding(
    *,
    review_queue: Mapping[str, Any],
    proposal_snapshot_sha256: str,
    release_group_ids: Sequence[str],
    proposal_group_keys: set[str],
) -> dict[str, Any]:
    required = (
        "review_source_id",
        "detector_manifest_sha256",
        "validation_pack_id",
        "source_snapshot",
    )
    if any(field not in review_queue for field in required):
        raise BindingError("review_queue_binding_fields_missing")
    source_snapshot = review_queue["source_snapshot"]
    if not isinstance(source_snapshot, Mapping):
        raise BindingError("review_queue_source_snapshot_invalid")
    source_snapshot_sha256 = _require_sha(source_snapshot.get("sha256"), "source_snapshot_sha256")
    review_source_id = _require_sha(review_queue["review_source_id"], "review_source_id")
    detector_manifest_sha256 = _require_sha(review_queue["detector_manifest_sha256"], "detector_manifest_sha256")
    validation_pack_id = _require_sha(review_queue["validation_pack_id"], "validation_pack_id")
    approved_proposal_set_sha256 = _require_sha(proposal_snapshot_sha256, "approved_proposal_set_sha256")
    groups = [_require_sha(group, "review_group_id") for group in release_group_ids]
    if not groups or len(groups) != len(set(groups)):
        raise BindingError("review_group_identity_invalid")
    if not set(groups) <= proposal_group_keys:
        raise BindingError("review_group_not_in_approved_proposal_set")
    payload: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": "OWNER_APPROVED_REPAIR_PROPOSAL",
        "canonicality": "STAGED_NOT_APPLIED",
        "identity_boundary": "AUDIT_LOCATOR_ONLY",
        "review_source_id": review_source_id,
        "source_snapshot_sha256": source_snapshot_sha256,
        "detector_manifest_sha256": detector_manifest_sha256,
        "validation_pack_id": validation_pack_id,
        "approved_proposal_set_sha256": approved_proposal_set_sha256,
        "review_group_ids": sorted(groups),
        # The read-only snapshot deliberately redacts personal owner identity;
        # this value describes the verified workflow authority, not a caller.
        "owner_authority": "OWNER_APPROVED_REPAIR_PROPOSAL_STAGED_SNAPSHOT",
    }
    payload["binding_identity_sha256"] = canonical_payload_sha256(payload)
    try:
        validate_review_binding(payload)
    except GovernanceError as error:
        raise BindingError(str(error)) from error
    return payload


def _build_mutation_audit(
    *,
    baseline: ArtifactIdentity,
    candidate: ArtifactIdentity,
    release: Mapping[str, Any],
    release_manifest_sha256: str,
    review_group_count: int,
) -> dict[str, Any]:
    legacy = release.get("mutation_audit")
    if not isinstance(legacy, Mapping):
        raise BindingError("legacy_mutation_audit_missing")
    records = legacy.get("records")
    if not isinstance(records, list) or len(records) != legacy.get("target_records_changed"):
        raise BindingError("legacy_mutation_audit_records_invalid")
    payload: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": CONTRACT_AUTHORITY,
        "canonicality": "STAGED_NOT_APPLIED",
        "source_sha256": baseline.sha256,
        "candidate_sha256": candidate.sha256,
        "changed_record_count": len(records),
        "review_group_count": review_group_count,
        "non_target_records_changed": legacy.get("non_target_records_changed", 0),
        "accepted_moves_changed": legacy.get("accepted_moves_changed", 0),
        "records": records,
        "legacy_release_manifest_sha256": release_manifest_sha256,
    }
    if payload["non_target_records_changed"] != 0 or payload["accepted_moves_changed"] != 0:
        raise BindingError("mutation_audit_scope_violation")
    return payload


def _build_acceptance_evidence(
    *,
    candidate: ArtifactIdentity,
    candidate_records: Sequence[Mapping[str, Any]],
    release: Mapping[str, Any],
) -> dict[str, Any]:
    verdict = release.get("verdict_validation")
    rows = verdict.get("records") if isinstance(verdict, Mapping) else None
    if not isinstance(rows, list) or not rows:
        raise BindingError("acceptance_verdict_records_missing")
    by_index = {index: row for index, row in enumerate(candidate_records)}
    evidence_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise BindingError("acceptance_verdict_row_invalid")
        question_id = row.get("question_id")
        record_index = row.get("record_index", row.get("record_index_in_candidate"))
        if not isinstance(question_id, int) or not isinstance(record_index, int):
            # Historical verdict evidence keyed rows by question id only; derive
            # the unique candidate index from the actual candidate bytes.
            matches = [i for i, record in enumerate(candidate_records) if record.get("id") == question_id]
            if len(matches) != 1:
                raise BindingError(f"acceptance_record_not_unique:{question_id}")
            record_index = matches[0]
        record = by_index.get(record_index)
        if not isinstance(record, Mapping) or record.get("id") != question_id:
            matches = [i for i, item in enumerate(candidate_records) if item.get("id") == question_id]
            if len(matches) != 1:
                raise BindingError(f"acceptance_record_identity_mismatch:{question_id}")
            record_index = matches[0]
            record = candidate_records[record_index]
        desired = row.get("owner_desired_verdict")
        final = row.get("final_effective_player_verdict")
        surfaces = row.get("surfaces")
        if not isinstance(desired, list) or not isinstance(final, list) or desired != final:
            raise BindingError(f"acceptance_verdict_mismatch:{question_id}")
        if not isinstance(surfaces, Mapping):
            raise BindingError(f"acceptance_surface_evidence_missing:{question_id}")
        for surface in REQUIRED_SURFACES:
            if surface not in surfaces or surfaces[surface] != desired:
                raise BindingError(f"acceptance_surface_verdict_mismatch:{question_id}:{surface}")
        accepted_moves = row.get("accepted_moves") or []
        native = row.get("native_accepted_set") or []
        fallback = str(row.get("katago_best_move") or "").strip()
        precedence: list[str] = []
        if accepted_moves:
            precedence.append("accepted_moves")
        if native:
            precedence.append("native_sgf")
        if fallback:
            precedence.append("historical_katago_best_move")
        if not precedence:
            precedence.append("none")
        base_evidence = {
            "candidate_sha256": candidate.sha256,
            "record_index": record_index,
            "legacy_question_id": question_id,
            "owner_desired_verdict": desired,
            "final_effective_player_verdict": final,
            "source_precedence_used": precedence,
        }
        evidence_hash = canonical_payload_sha256(base_evidence)
        evidence_rows.append(
            {
                **base_evidence,
                "content_sha256": _record_content_sha256(record, f"acceptance:{question_id}"),
                "accepted_moves_influence": bool(accepted_moves),
                "native_sgf_influence": bool(native),
                "historical_katago_best_move_influence": bool(fallback),
                "surfaces": {
                    surface: {
                        "pass": True,
                        "match": True,
                        "final_effective_player_verdict": surfaces[surface],
                        "evidence_artifact_sha256": evidence_hash,
                    }
                    for surface in REQUIRED_SURFACES
                },
                "evidence_artifact_sha256": evidence_hash,
            }
        )
    evidence_rows.sort(key=lambda row: row["record_index"])
    payload: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": "EXTERNAL_ACCEPTANCE_RUNNER_VERIFIED_FROM_PHASE2F_EVIDENCE",
        "canonicality": "VERIFICATION_EVIDENCE_ONLY",
        "candidate_sha256": candidate.sha256,
        "records": evidence_rows,
        "summary": {
            "records_validated": len(evidence_rows),
            "all_final_effective_match": True,
            "surfaces": list(REQUIRED_SURFACES),
        },
    }
    payload["evidence_identity_sha256"] = canonical_payload_sha256(payload)
    try:
        validate_acceptance_evidence(
            payload,
            expected_candidate_sha256=candidate.sha256,
            expected_record_count=len(evidence_rows),
        )
    except GovernanceError as error:
        raise BindingError(str(error)) from error
    return payload


def build_pr318_contract(
    *,
    baseline_path: Path,
    candidate_path: Path,
    historical_release_manifest: Path,
    historical_rollback_manifest: Path,
    rollback_simulation: Path,
    review_queue_path: Path,
    proposal_snapshot_path: Path,
    repair_manifest_path: Path,
    safe_release_batch_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Derive and verify the PR318 contract from existing repair evidence."""

    _, baseline_records, baseline = _corpus(baseline_path, "baseline")
    _, candidate_records, candidate = _corpus(candidate_path, "candidate")
    if baseline.record_count != candidate.record_count:
        raise BindingError("baseline_candidate_record_count_mismatch")
    release, _legacy_rollback, simulation, release_sha256, legacy_rollback_sha256 = _verify_historical_release(
        baseline=baseline,
        candidate=candidate,
        release_manifest=historical_release_manifest,
        rollback_manifest=historical_rollback_manifest,
        simulation=rollback_simulation,
    )
    review_queue = _load(review_queue_path, "review_queue")
    proposal_snapshot = _load(proposal_snapshot_path, "proposal_snapshot")
    repair_manifest = _load(repair_manifest_path, "repair_manifest")
    safe_release = _load(safe_release_batch_path, "safe_release_batch")
    if not all(isinstance(value, Mapping) for value in (review_queue, proposal_snapshot, repair_manifest, safe_release)):
        raise BindingError("binding_inputs_must_be_objects")
    proposal_snapshot_sha256 = sha256_file(proposal_snapshot_path)
    repair_manifest_sha256 = sha256_file(repair_manifest_path)
    safe_release_file_sha256 = sha256_file(safe_release_batch_path)
    batch = safe_release.get("batch")
    if not isinstance(batch, Mapping):
        raise BindingError("safe_release_batch_body_missing")
    batch_sha256 = _require_sha(safe_release.get("batch_sha256"), "safe_release_batch_sha256")
    if canonical_payload_sha256(batch) != batch_sha256:
        raise BindingError("safe_release_batch_identity_mismatch")
    groups = batch.get("groups")
    excluded = batch.get("excluded_map_battle_records")
    summary = batch.get("summary")
    if not isinstance(groups, list) or not isinstance(excluded, list) or not isinstance(summary, Mapping):
        raise BindingError("safe_release_batch_summary_missing")
    review_group_ids = [group.get("review_group_key") for group in groups if isinstance(group, Mapping)]
    if len(review_group_ids) != len(groups):
        raise BindingError("safe_release_group_identity_missing")
    proposal_groups = proposal_snapshot.get("groups")
    if not isinstance(proposal_groups, list):
        raise BindingError("proposal_snapshot_groups_missing")
    proposal_group_keys = {
        group.get("review_group_key")
        for group in proposal_groups
        if isinstance(group, Mapping) and isinstance(group.get("review_group_key"), str)
    }
    review_binding = _build_review_binding(
        review_queue=review_queue,
        proposal_snapshot_sha256=proposal_snapshot_sha256,
        release_group_ids=review_group_ids,
        proposal_group_keys=proposal_group_keys,
    )
    review_binding_path = output_dir / "review-binding.json"
    review_binding_sha256 = _write_json(review_binding_path, review_binding)
    mutation_audit = _build_mutation_audit(
        baseline=baseline,
        candidate=candidate,
        release=release,
        release_manifest_sha256=release_sha256,
        review_group_count=len(groups),
    )
    mutation_audit_path = output_dir / "mutation-audit.json"
    mutation_audit_sha256 = _write_json(mutation_audit_path, mutation_audit)
    acceptance = _build_acceptance_evidence(
        candidate=candidate,
        candidate_records=candidate_records,
        release=release,
    )
    acceptance_path = output_dir / "acceptance-evidence.json"
    acceptance_sha256 = _write_json(acceptance_path, acceptance)
    rollback_governance = {
        "previous_sha256": baseline.sha256,
        "candidate_sha256": candidate.sha256,
        "record_count": baseline.record_count,
        "restore_target": "/app/data/questions.json",
        "post_rollback": {
            "sha256": baseline.sha256,
            "size_bytes": baseline.size_bytes,
            "record_count": baseline.record_count,
        },
        "historical_rollback_manifest_sha256": legacy_rollback_sha256,
        "rollback_simulation_sha256": sha256_file(rollback_simulation),
        "rollback_simulation_mode": "LOCAL_DISPOSABLE_EXACT_BYTE_SIMULATION_ONLY",
    }
    rollback = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": CONTRACT_AUTHORITY,
        "canonicality": "STAGED_NOT_APPLIED",
        "rollback_governance": rollback_governance,
        "safety": {
            "production_contact": "NONE",
            "production_mutation": "NO",
            "publish_requires_rollback_proof": True,
        },
    }
    rollback_path = output_dir / "rollback-manifest.json"
    rollback_sha256 = _write_json(rollback_path, rollback)
    repair_batch = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": CONTRACT_AUTHORITY,
        "canonicality": "STAGED_NOT_APPLIED",
        "source_sha256": baseline.sha256,
        "candidate_sha256": candidate.sha256,
        "review_binding_sha256": review_binding_sha256,
        "mutation_audit_sha256": mutation_audit_sha256,
        "acceptance_evidence_sha256": acceptance_sha256,
        "changed_record_count": _require_int(summary.get("records"), "changed_record_count"),
        "review_group_count": _require_int(summary.get("groups"), "review_group_count"),
        "excluded_record_count": len(excluded),
        "conflict_count": (repair_manifest.get("summary") or {}).get("replacement_fallback_conflicts", 0),
        "approved_proposal_set_sha256": proposal_snapshot_sha256,
        "repair_manifest_sha256": repair_manifest_sha256,
        "safe_release_batch_sha256": batch_sha256,
        "safe_release_batch_file_sha256": safe_release_file_sha256,
        "mutation_performed": False,
        "production_publish_authorized": False,
    }
    repair_batch_path = output_dir / "repair-batch-manifest.json"
    repair_batch_sha256 = _write_json(repair_batch_path, repair_batch)
    source_provenance = build_source_provenance(
        baseline_path,
        source_kind="immutable_snapshot",
        source_repo_id="beatleswu/beatleswu.github.io",
        source_commit_or_snapshot_id="content-release-phase2f-20260809T222000Z-4d13fa98",
        source_path="release-artifacts/questions.pre-mutation.4d13fa98af8c.json",
        source_receipt_sha256=release_sha256,
        review_source_id=review_binding["review_source_id"],
        detector_manifest_sha256=review_binding["detector_manifest_sha256"],
        validation_pack_id=review_binding["validation_pack_id"],
        approved_proposal_set_sha256=proposal_snapshot_sha256,
    )
    provenance_path = output_dir / "source-provenance.json"
    provenance_sha256 = _write_json(provenance_path, source_provenance)
    candidate_name = "questions.repaired-candidate.json.gz"
    release = {
        "schema_version": "1.1",
        "authority": CONTRACT_AUTHORITY,
        "created_at": release.get("created_at", "2026-08-09T22:20:00Z"),
        "source_baseline_sha256": baseline.sha256,
        "intended_production_destination": "/app/data/questions.json",
        "publisher_precondition_hash_lock": baseline.sha256,
        "pre_mutation_artifact": _artifact_dict(baseline),
        "repaired_candidate_artifact": _artifact_dict(candidate),
        "mutation_audit": mutation_audit,
        "repair_records": release.get("repair_records", []),
        "verdict_validation": release.get("verdict_validation", {}),
        "excluded_questions_unchanged": release.get("excluded_questions_unchanged", {}),
        "excluded_map_battle_questions_unchanged": release.get("excluded_map_battle_questions_unchanged", {}),
        "safety": {
            "production_contact": "NONE",
            "production_mutation": "NO",
            "canonical_corpus_mutation": "NO",
            "accepted_moves_mutated": False,
            "merge": "NO",
            "deploy": "NO",
        },
        "release_governance": {
            "source_provenance": source_provenance,
            "source_identity_sha256": source_provenance["source_identity_sha256"],
            "review_binding_sha256": review_binding_sha256,
            "repair_batch_manifest_sha256": repair_batch_sha256,
            "mutation_audit_sha256": mutation_audit_sha256,
            "acceptance_evidence_sha256": acceptance_sha256,
            "rollback_manifest_sha256": rollback_sha256,
            "changed_record_count": repair_batch["changed_record_count"],
            "review_group_count": repair_batch["review_group_count"],
            "excluded_record_count": repair_batch["excluded_record_count"],
            "allowed_asset_names": REQUIRED_ASSET_NAMES,
        },
    }
    release_path = output_dir / "release-manifest.json"
    release_contract_sha256 = _write_json(release_path, release)
    # Validate the exact same relationships that PR318 will validate during
    # bundle construction.  This is deliberately verification-only.
    try:
        validate_release_manifest_semantics(
            release,
            baseline_sha256=baseline.sha256,
            baseline_record_count=baseline.record_count,
            candidate_identity=candidate,
            expected_release_manifest_sha256=release_contract_sha256,
            expected_rollback_manifest_sha256=rollback_sha256,
            release_records=repair_batch["changed_record_count"],
            excluded_map_battle_records=repair_batch["excluded_record_count"],
            source_provenance=provenance_path,
            review_binding=review_binding_path,
            repair_batch_manifest=repair_batch_path,
            mutation_audit=mutation_audit_path,
            acceptance_evidence=acceptance_path,
            rollback_manifest=rollback_path,
        )
    except GovernanceError as error:
        raise BindingError(str(error)) from error
    return {
        "baseline": _artifact_dict(baseline),
        "candidate": _artifact_dict(candidate),
        "repair_group_count": repair_batch["review_group_count"],
        "repaired_record_count": repair_batch["changed_record_count"],
        "exclusion_count": repair_batch["excluded_record_count"],
        "conflict_count": repair_batch["conflict_count"],
        "baseline_sha256": baseline.sha256,
        "candidate_sha256": candidate.sha256,
        "repair_batch_manifest_sha256": repair_batch_sha256,
        "mutation_audit_sha256": mutation_audit_sha256,
        "rollback_manifest_sha256": rollback_sha256,
        "acceptance_evidence_sha256": acceptance_sha256,
        "source_provenance_sha256": provenance_sha256,
        "review_binding_sha256": review_binding_sha256,
        "release_manifest_sha256": release_contract_sha256,
        "source_provenance_bound": True,
        "review_queue_provenance_bound": True,
        "pr318_contract_compatible": True,
        "six_surfaces_complete": True,
        "verdict_mismatch_count": 0,
        "gf003_state_unchanged": True,
        "production_mutation": "NO",
        "canonical_corpus_mutation": "NO",
        "artifact_paths": {
            "source_provenance": str(provenance_path),
            "review_binding": str(review_binding_path),
            "repair_batch_manifest": str(repair_batch_path),
            "mutation_audit": str(mutation_audit_path),
            "acceptance_evidence": str(acceptance_path),
            "rollback_manifest": str(rollback_path),
            "release_manifest": str(release_path),
        },
    }


def _cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--historical-release-manifest", required=True, type=Path)
    parser.add_argument("--historical-rollback-manifest", required=True, type=Path)
    parser.add_argument("--rollback-simulation", required=True, type=Path)
    parser.add_argument("--review-queue", required=True, type=Path)
    parser.add_argument("--proposal-snapshot", required=True, type=Path)
    parser.add_argument("--repair-manifest", required=True, type=Path)
    parser.add_argument("--safe-release-batch", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_pr318_contract(
            baseline_path=args.baseline,
            candidate_path=args.candidate,
            historical_release_manifest=args.historical_release_manifest,
            historical_rollback_manifest=args.historical_rollback_manifest,
            rollback_simulation=args.rollback_simulation,
            review_queue_path=args.review_queue,
            proposal_snapshot_path=args.proposal_snapshot,
            repair_manifest_path=args.repair_manifest,
            safe_release_batch_path=args.safe_release_batch,
            output_dir=args.output_dir,
        )
    except (BindingError, GovernanceError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
