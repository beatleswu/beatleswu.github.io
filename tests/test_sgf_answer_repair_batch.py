import hashlib
import os
from pathlib import Path

import pytest

from sgf_engine.core.matcher import BRANCH, OFF_TREE, match_move
from sgf_engine.parser.sgf_parser import parse_sgf
from tools import sgf_answer_repair_batch as repair


SNAPSHOT_SHA = "a" * 64
QUESTIONS_SHA = "b" * 64
PROPOSAL_SHA = "c" * 64
TARGETS_SHA = "d" * 64

TWO_ANSWER_SGF = (
    "(;GM[1]FF[4]SZ[19]PL[W]AB[cc]AW[cd]C[root]"
    "(;W[ar]C[A2 branch];B[aq])"
    "(;W[bs]C[B1 branch];B[br]))"
)
ONE_ANSWER_SGF = (
    "(;GM[1]FF[4]SZ[19]PL[W]AB[cc]AW[cd]C[root]"
    "(;W[ar]C[A2 branch];B[aq]))"
)


def _sha(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _move(x, y, color="W"):
    return {"x": x, "y": y, "color": color}


def _proposal(proposal_type, original, proposed=None):
    result = {
        "type": proposal_type,
        "original_answers": list(original),
    }
    if proposed is not None:
        result["proposed_move"] = proposed
    return result


def _case(
    *,
    content=TWO_ANSWER_SGF,
    proposal_types=("REPLACE_PRIMARY_ANSWER",),
    proposed_moves=((1, 18),),
    legacy_ids=(15436,),
    current_contents=None,
    fallbacks=None,
    accepted_moves=None,
    historical_moves=None,
    resolution_statuses=None,
    source_paths=None,
    current_source_paths=None,
):
    structure = repair._answer_structure(content)
    side = structure["side_to_move"]
    current_points = list(structure["ordered_points"])
    original = [_move(x, y, side) for x, y in current_points]
    proposals = []
    proposed_iter = iter(proposed_moves)
    for proposal_type in proposal_types:
        proposed = None
        if proposal_type in {
            "REPLACE_PRIMARY_ANSWER",
            "ADD_EQUIVALENT_SOLUTION",
        }:
            x, y = next(proposed_iter)
            proposed = _move(x, y, side)
        proposals.append(_proposal(proposal_type, original, proposed))

    size = len(legacy_ids)
    current_contents = list(current_contents or [content] * size)
    fallbacks = list(fallbacks or [""] * size)
    accepted_moves = list(accepted_moves or [[] for _ in range(size)])
    resolution_statuses = list(
        resolution_statuses or ["CURRENT_CONTENT_MATCH"] * size
    )
    source_paths = list(
        source_paths
        or [f"synthetic/{legacy_id}.sgf" for legacy_id in legacy_ids]
    )
    current_source_paths = list(current_source_paths or source_paths)

    reviewed = []
    linked = []
    targets = []
    for index, legacy_id in enumerate(legacy_ids):
        locator = {
            "type": "AUDIT_LOCATOR_ONLY",
            "snapshot_sha256": SNAPSHOT_SHA,
            "record_index": index,
            "legacy_question_id": legacy_id,
            "content_sha256": _sha(content),
        }
        reviewed.append(
            {
                "id": legacy_id,
                "source": source_paths[index],
                "content": content,
            }
        )
        linked.append(
            {
                "legacy_question_id": legacy_id,
                "audit_locator": locator,
            }
        )
        target = {
            "audit_locator": locator,
            "legacy_question_id": legacy_id,
            "resolution_status": resolution_statuses[index],
            "current_record_index": 100 + index,
            "current_source_path": current_source_paths[index],
            "current_content": current_contents[index],
            "current_content_sha256": _sha(current_contents[index]),
            "current_katago_best_move": fallbacks[index],
            "current_accepted_moves": accepted_moves[index],
        }
        if resolution_statuses[index] != "CURRENT_CONTENT_MATCH":
            target["current_content"] = None
            target["current_content_sha256"] = None
        targets.append(target)

    group = {
        "review_group_key": _sha(content),
        "group_order": 1,
        "group_size": size,
        "board_size": 19,
        "side_to_move": side,
        "current_first_solution_moves": original,
        "historical_precomputed_moves": list(historical_moves or []),
        "linked_records": linked,
        "state": {
            "revision": 1,
            "updated_at": "2026-08-09T00:00:00Z",
            "proposals": proposals,
        },
    }
    return group, reviewed, targets


def _classify(case, simulation_dir=None):
    group, reviewed, targets = case
    by_key = {repair._target_key(target): target for target in targets}
    return repair._classify_group(
        group,
        reviewed_questions=reviewed,
        targets_by_key=by_key,
        simulation_dir=simulation_dir,
    )


def _manifest_inputs(case):
    group, reviewed, targets = case
    proposal_snapshot = {
        "authority": "PRODUCTION_OWNER_REVIEW_QUEUE_READ_ONLY_SNAPSHOT",
        "captured_at": "2026-08-09T00:00:00Z",
        "counts": {
            "active_proposals": len(group["state"]["proposals"]),
            "active_review_groups": 1,
            "affected_question_records": len(group["linked_records"]),
        },
        "queue_source": {
            "source_snapshot": {
                "sha256": QUESTIONS_SHA,
                "question_count": len(reviewed),
            }
        },
        "groups": [group],
    }
    current_targets = {
        "authority": "PRODUCTION_CANONICAL_TARGET_READ_ONLY_SNAPSHOT",
        "captured_at": "2026-08-09T00:01:00Z",
        "proposal_snapshot_sha256": PROPOSAL_SHA,
        "production_questions": {
            "content_sha256": "e" * 64,
            "record_count": len(reviewed),
        },
        "production_app": {"commit": "f" * 40},
        "records": targets,
    }
    return proposal_snapshot, reviewed, current_targets


def _build(case):
    proposal_snapshot, reviewed, current_targets = _manifest_inputs(case)
    return repair.build_repair_plan(
        proposal_snapshot,
        reviewed,
        current_targets,
        proposal_snapshot_sha256=PROPOSAL_SHA,
        reviewed_questions_sha256=QUESTIONS_SHA,
        current_targets_sha256=TARGETS_SHA,
    )


def test_subset_replacement_preserves_surviving_branch_and_removes_a2(tmp_path):
    plan = _classify(_case(), simulation_dir=tmp_path)

    assert plan["classification"] == repair.CLASS_AUTO
    assert plan["current_answer_set"] == ["A2", "B1"]
    assert plan["desired_answer_set"] == ["B1"]
    record = plan["records"][0]
    repaired = (tmp_path / record["simulation_artifact"]).read_text(
        encoding="utf-8"
    )
    assert "C[B1 branch]" in repaired
    assert "C[A2 branch]" not in repaired
    root = parse_sgf(repaired, strict=True)
    assert match_move(root, "bs", None) == BRANCH
    assert match_move(root, "ar", None) == OFF_TREE
    assert record["validation"]["surviving_variations_preserved"] is True


def test_completely_new_replacement_accepts_b2_and_removes_both_old_moves(tmp_path):
    plan = _classify(
        _case(proposed_moves=((1, 17),)), simulation_dir=tmp_path
    )

    assert plan["classification"] == repair.CLASS_AUTO
    assert plan["desired_answer_set"] == ["B2"]
    repaired = (tmp_path / plan["records"][0]["simulation_artifact"]).read_text(
        encoding="utf-8"
    )
    root = parse_sgf(repaired, strict=True)
    assert match_move(root, "br", None) == BRANCH
    assert match_move(root, "ar", None) == OFF_TREE
    assert match_move(root, "bs", None) == OFF_TREE


def test_add_equivalent_preserves_all_existing_duplicate_first_move_variations(tmp_path):
    duplicate_variations = (
        "(;GM[1]FF[4]SZ[19]PL[W]C[root]"
        "(;W[ar]C[first A2];B[aq])"
        "(;W[ar]C[second A2];B[br]))"
    )
    plan = _classify(
        _case(
            content=duplicate_variations,
            proposal_types=("ADD_EQUIVALENT_SOLUTION",),
            proposed_moves=((1, 18),),
        ),
        simulation_dir=tmp_path,
    )

    assert plan["classification"] == repair.CLASS_AUTO
    assert plan["current_answer_set"] == ["A2"]
    assert plan["desired_answer_set"] == ["A2", "B1"]
    record = plan["records"][0]
    assert record["existing_tree"] == {
        "native_root_solution_count": 1,
        "root_variation_count": 2,
    }
    repaired = (tmp_path / record["simulation_artifact"]).read_text(
        encoding="utf-8"
    )
    assert "C[first A2]" in repaired
    assert "C[second A2]" in repaired
    root = parse_sgf(repaired, strict=True)
    assert match_move(root, "ar", None) == BRANCH
    assert match_move(root, "bs", None) == BRANCH


def test_exact_reviewed_precomputed_fallback_can_be_cleared_without_sgf_change(tmp_path):
    case = _case(
        content=ONE_ANSWER_SGF,
        proposal_types=("REJECT_HISTORICAL_PRECOMPUTED_FALLBACK",),
        proposed_moves=(),
        fallbacks=("Q4",),
        historical_moves=({**_move(15, 15), "gtp": "Q4"},),
    )
    plan = _classify(case, simulation_dir=tmp_path)

    assert plan["classification"] == repair.CLASS_AUTO
    record = plan["records"][0]
    assert record["current_katago_best_move"] == "Q4"
    assert record["desired_katago_best_move"] == ""
    assert record["source_content_sha256_before"] == record[
        "source_content_sha256_after"
    ]
    assert record["planned_operations"] == [
        {
            "type": "CLEAR_PRECOMPUTED_KATAGO_FALLBACK",
            "before": "Q4",
            "after": "",
        }
    ]


def test_replacement_fails_closed_when_unrejected_fallback_stays_outside_set():
    plan = _classify(_case(fallbacks=("Q4",)))

    assert plan["classification"] == repair.CLASS_STALE
    assert "UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET" in plan[
        "reason_codes"
    ]
    assert plan["current_answer_set"] == ["A2", "B1"]
    assert plan["desired_answer_set"] == ["B1"]


def test_replacement_fails_closed_when_accepted_move_would_survive_outside_set():
    plan = _classify(
        _case(accepted_moves=([_move(15, 15)],))
    )

    assert plan["classification"] == repair.CLASS_STALE
    assert "SIMULATION_VALIDATION_FAILED" in plan["reason_codes"]


def test_missing_current_source_is_unresolved_and_never_simulated(tmp_path):
    plan = _classify(
        _case(
            resolution_statuses=("MISSING_CURRENT_SOURCE",),
            current_contents=(TWO_ANSWER_SGF,),
        ),
        simulation_dir=tmp_path,
    )

    assert plan["classification"] == repair.CLASS_UNRESOLVED
    assert plan["reason_codes"] == ["MISSING_CURRENT_SOURCE"]
    assert list(tmp_path.iterdir()) == []


def test_changed_current_content_is_stale_and_not_silently_rebased():
    changed = TWO_ANSWER_SGF.replace("C[root]", "C[current changed]")
    plan = _classify(_case(current_contents=(changed,)))

    assert plan["classification"] == repair.CLASS_STALE
    assert "CURRENT_CONTENT_CHANGED" in plan["reason_codes"]


def test_parser_failure_is_isolated_as_stale_instead_of_aborting_batch():
    group, reviewed, targets = _case()
    invalid = "(;GM[1]FF[4]SZ[19]PL[W](;W[ar])"
    digest = _sha(invalid)
    locator = group["linked_records"][0]["audit_locator"]
    locator["content_sha256"] = digest
    group["review_group_key"] = digest
    reviewed[0]["content"] = invalid
    targets[0]["current_content"] = invalid
    targets[0]["current_content_sha256"] = digest

    plan = _classify((group, reviewed, targets))

    assert plan["classification"] == repair.CLASS_STALE
    assert "CURRENT_SGF_STRUCTURE_INVALID" in plan["reason_codes"]


def test_rejecting_only_fallback_without_native_answer_requires_reconstruction():
    empty = "(;GM[1]FF[4]SZ[19]PL[W]AB[cc]AW[cd])"
    plan = _classify(
        _case(
            content=empty,
            proposal_types=("REJECT_HISTORICAL_PRECOMPUTED_FALLBACK",),
            proposed_moves=(),
            fallbacks=("Q4",),
            historical_moves=({**_move(15, 15), "gtp": "Q4"},),
        )
    )

    assert plan["classification"] == repair.CLASS_MANUAL
    assert plan["reason_codes"] == [
        "NO_VALID_NATIVE_ANSWER_AFTER_REPAIR"
    ]


def test_duplicate_group_fans_out_only_when_every_member_matches(tmp_path):
    plan = _classify(
        _case(legacy_ids=(101, 102)), simulation_dir=tmp_path
    )

    assert plan["classification"] == repair.CLASS_AUTO
    assert len(plan["records"]) == 2
    assert {record["legacy_question_id"] for record in plan["records"]} == {
        101,
        102,
    }
    assert len(list(tmp_path.glob("*.sgf"))) == 2


def test_duplicate_group_fails_as_a_whole_when_one_member_changed(tmp_path):
    changed = TWO_ANSWER_SGF.replace("C[root]", "C[drift]")
    plan = _classify(
        _case(
            legacy_ids=(101, 102),
            current_contents=(TWO_ANSWER_SGF, changed),
        ),
        simulation_dir=tmp_path,
    )

    assert plan["classification"] == repair.CLASS_STALE
    assert "CURRENT_CONTENT_CHANGED" in plan["reason_codes"]
    assert list(tmp_path.iterdir()) == []


def test_source_reconstruction_is_manual_and_does_not_rewrite_sgf(tmp_path):
    plan = _classify(
        _case(
            proposal_types=("NEEDS_SOURCE_RECONSTRUCTION",),
            proposed_moves=(),
        ),
        simulation_dir=tmp_path,
    )

    assert plan["classification"] == repair.CLASS_MANUAL
    assert plan["repair_classes"] == [
        "SOURCE_CONVERSION_OR_SIDE_TO_MOVE_ERROR"
    ]
    assert list(tmp_path.iterdir()) == []


def test_exact_semantic_no_op_is_classified_without_writing(tmp_path):
    plan = _classify(
        _case(
            proposed_moves=((0, 17), (1, 18)),
            proposal_types=(
                "REPLACE_PRIMARY_ANSWER",
                "REPLACE_PRIMARY_ANSWER",
            ),
        ),
        simulation_dir=tmp_path,
    )

    assert plan["classification"] == repair.CLASS_NO_OP
    assert plan["reason_codes"] == ["EXACT_SEMANTIC_NO_OP"]
    assert list(tmp_path.iterdir()) == []


def test_repair_plan_hash_and_order_are_deterministic():
    case = _case(content=ONE_ANSWER_SGF, proposed_moves=((1, 17),))

    first = _build(case)
    second = _build(case)

    assert first == second
    assert first["repair_plan_sha256"] == second["repair_plan_sha256"]
    assert first["summary"]["auto_applyable"] == 1


def test_plan_hash_is_bound_to_current_target_snapshot_hash():
    case = _case(content=ONE_ANSWER_SGF, proposed_moves=((1, 17),))
    proposal_snapshot, reviewed, current_targets = _manifest_inputs(case)
    first = repair.build_repair_plan(
        proposal_snapshot,
        reviewed,
        current_targets,
        proposal_snapshot_sha256=PROPOSAL_SHA,
        reviewed_questions_sha256=QUESTIONS_SHA,
        current_targets_sha256=TARGETS_SHA,
    )
    second = repair.build_repair_plan(
        proposal_snapshot,
        reviewed,
        current_targets,
        proposal_snapshot_sha256=PROPOSAL_SHA,
        reviewed_questions_sha256=QUESTIONS_SHA,
        current_targets_sha256="9" * 64,
    )

    assert first["repair_plan_sha256"] != second["repair_plan_sha256"]


def test_run_rejects_simulation_output_inside_repository(tmp_path):
    proposal = tmp_path / "proposal.json"
    questions = tmp_path / "questions.json"
    targets = tmp_path / "targets.json"
    manifest = tmp_path / "manifest.json"
    report = tmp_path / "report.md"

    with pytest.raises(
        ValueError,
        match="isolated SGF simulation directory must be outside",
    ):
        repair.run(
            proposal_snapshot_path=proposal,
            reviewed_questions_path=questions,
            current_targets_path=targets,
            manifest_path=manifest,
            report_path=report,
            simulation_dir=Path(repair.__file__).resolve().parents[1]
            / "unsafe-simulation-output",
        )


def test_legacy_adapter_accepts_survivor_and_rejects_removed_move():
    os.environ.setdefault(
        "SECRET_KEY", "synthetic-sgf-answer-repair-batch-test-secret"
    )
    os.environ.setdefault("SITE_URL", "http://localhost")
    import app as app_module

    repaired, _ = repair._rewrite_answer_set(
        TWO_ANSWER_SGF, [(1, 18)]
    )
    legacy_tree = app_module._rt_parse_answer_tree(repaired)

    assert legacy_tree is not None
    assert app_module._rt_replay(
        legacy_tree, [{"x": 1, "y": 18}]
    ) is True
    assert app_module._rt_replay(
        legacy_tree, [{"x": 0, "y": 17}]
    ) is False


def test_committed_manifest_records_question_15436_intent_and_fail_closed_guard():
    path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "planning"
        / "sgf_answer_repair_batch_001_manifest.json"
    )
    if not path.exists():
        pytest.skip("generated dry-run manifest has not been created yet")
    import json

    manifest = json.loads(path.read_text(encoding="utf-8"))
    question = manifest["question_15436"]

    assert question["present"] is True
    assert question["current"] == ["A2", "B1"]
    assert question["desired"] == ["B1"]
    assert question["plan"][0]["removed"] == ["A2"]
    assert question["plan"][0]["added"] == []
    assert question["current_precomputed_fallbacks"] == ["Q4"]
    assert question["classification"] == repair.CLASS_STALE
    assert (
        "UNREJECTED_PRECOMPUTED_FALLBACK_OUTSIDE_REPLACEMENT_SET"
        in question["reason_codes"]
    )
