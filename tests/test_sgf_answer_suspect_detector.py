import copy
import hashlib
import json

import pytest

from tools.sgf_answer_suspect_detector import (
    IDENTITY_TYPE,
    PLAYER_SIGNAL_AVAILABLE,
    PLAYER_SIGNAL_UNAVAILABLE,
    _render_html,
    analyze_record,
    generate_outputs,
    rank_suspects,
    select_validation_set,
)


LOCAL_INSIDE = (
    "(;GM[1]FF[4]SZ[19]PL[B]"
    "AB[aa][ab][ba][bb][cc]AW[ac][bc];B[cd])"
)
LOCAL_OPPOSITE = (
    "(;GM[1]FF[4]SZ[19]PL[B]"
    "AB[aa][ab][ba][bb][cc]AW[ac][bc];B[ss])"
)
BROAD_POSITION = (
    "(;GM[1]FF[4]SZ[19]PL[B]"
    "AB[aa][as][sa][ss]AW[aj][ja][js][sj];B[jj])"
)
MULTIPLE_ROOTS = (
    "(;GM[1]FF[4]SZ[19]PL[B]"
    "AB[aa][ab][ba][bb][cc]AW[ac][bc](;B[cd])(;B[dc]))"
)


def _record(content, **extra):
    return {
        "id": extra.pop("id", 1001),
        "content": content,
        "source": "synthetic.sgf",
        "discipline": "synthetic",
        **extra,
    }


def _analyze(record, *, index=0, player_metrics=None):
    return analyze_record(
        record,
        record_index=index,
        snapshot_sha256="a" * 64,
        player_metrics=player_metrics,
    )


def _render_one(record):
    rendered = dict(record)
    rendered["deterministic_rank"] = 1
    return _render_html(
        {
            "detector_version": "test",
            "validation_pack_id": "b" * 64,
            "source_snapshot": {"sha256": "a" * 64},
            "records": [rendered],
        }
    ).decode("utf-8")


def test_black_to_play_is_sgf_derived_and_rendered_in_card_header():
    result = _analyze(_record(LOCAL_INSIDE.replace("PL[B]", "")))

    assert result["side_to_move"] == "B"
    assert result["side_to_move_source"] == "SGF_FIRST_SOLUTION_COLOR"
    assert result["side_to_move_display"] == "黑先 / Black to play"
    assert result["side_to_move_reason_codes"] == []
    assert "黑先 / Black to play" in _render_one(result)


def test_white_to_play_is_sgf_derived_and_rendered_in_card_header():
    white = LOCAL_INSIDE.replace("PL[B]", "PL[W]").replace(";B[cd]", ";W[cd]")
    result = _analyze(_record(white))

    assert result["side_to_move"] == "W"
    assert result["side_to_move_source"] == "SGF_ROOT_PL"
    assert result["side_to_move_display"] == "白先 / White to play"
    assert result["side_to_move_reason_codes"] == []
    assert "白先 / White to play" in _render_one(result)


def test_unknown_side_to_move_is_explicit_and_machine_readable():
    result = _analyze(_record("(;GM[1]FF[4]SZ[19]AB[aa][ab]AW[ba])"))

    assert result["side_to_move"] is None
    assert result["side_to_move_source"] is None
    assert result["side_to_move_display"] == "先手不明 / Side to move unknown"
    assert result["side_to_move_reason_codes"] == ["SIDE_TO_MOVE_UNKNOWN"]
    assert "先手不明 / Side to move unknown" in _render_one(result)


def test_side_to_move_metadata_does_not_change_suspect_ranking_order():
    records = [
        _analyze(_record(LOCAL_INSIDE, id=7101, katago_best_move="T1"), index=1),
        _analyze(_record(LOCAL_OPPOSITE, id=7102, katago_best_move="T1"), index=2),
        _analyze(_record("(;GM[1]FF[4]SZ[19]AB[aa])", id=7103), index=3),
    ]
    changed_display_only = copy.deepcopy(records)
    for record, side in zip(changed_display_only, ("W", None, "B"), strict=True):
        record["side_to_move"] = side
        record["side_to_move_display"] = "display-only mutation"
        record["side_to_move_source"] = "TEST_ONLY"
        record["side_to_move_reason_codes"] = [] if side else ["SIDE_TO_MOVE_UNKNOWN"]

    before = rank_suspects(records)
    after = rank_suspects(changed_display_only)

    assert [row["audit_locator"] for row in before] == [row["audit_locator"] for row in after]
    assert [row["deterministic_rank"] for row in before] == [
        row["deterministic_rank"] for row in after
    ]


def test_owner_review_html_offers_exactly_four_primary_statuses():
    html = _render_one(_analyze(_record(LOCAL_INSIDE, katago_best_move="T1")))

    for status in (
        "NO_ISSUE",
        "CONFIRMED_ISSUE",
        "POSSIBLE_MULTIPLE_SOLUTION",
        "UNCERTAIN",
    ):
        assert status in html
    assert "review-status" in html
    assert "aria-pressed" in html


def test_confirmed_issue_requires_one_reason_and_other_note_is_optional_only():
    html = _render_one(_analyze(_record(LOCAL_INSIDE, katago_best_move="T1")))

    for reason in (
        "GLOBAL_TENUKI",
        "WRONG_PRIMARY_ANSWER",
        "WRONG_CONTINUATION",
        "MISSING_EQUIVALENT_SOLUTION",
        "SIDE_TO_MOVE_OR_METADATA_ERROR",
        "SGF_OR_BOARD_STRUCTURE_ERROR",
        "OTHER",
    ):
        assert reason in html
    assert "Reason required before this review is complete." in html
    assert "entry.issue_reason==='OTHER'" in html
    assert "Optional note for OTHER only" in html


def test_owner_review_persistence_is_scoped_to_snapshot_and_exact_pack():
    html = _render_one(_analyze(_record(LOCAL_INSIDE, katago_best_move="T1")))

    assert "pack.source_snapshot.sha256" in html
    assert "pack.validation_pack_id" in html
    assert "localStorage.getItem(storageKey)" in html
    assert "localStorage.setItem(storageKey" in html
    assert "OWNER_VALIDATION_ANNOTATION" in html
    assert "NON_AUTHORITATIVE" in html


def test_owner_review_supports_status_changes_filters_and_progress_counts():
    html = _render_one(_analyze(_record(LOCAL_INSIDE, katago_best_move="T1")))

    assert "setReviewStatus(rec,status)" in html
    assert "setIssueReason(rec,reason)" in html
    assert 'id="review-filter"' in html
    assert 'value="UNREVIEWED"' in html
    assert 'id="reviewed-count"' in html
    assert 'id="unreviewed-count"' in html
    assert "progressSnapshot" in html


def test_owner_review_export_contains_required_identity_status_and_reason_fields():
    html = _render_one(_analyze(_record(LOCAL_INSIDE, katago_best_move="T1")))

    for field in (
        "audit_locator",
        "legacy_question_id",
        "side_to_move",
        "priority_tier",
        "detector_reason_codes",
        "review_status",
        "issue_reason",
        "owner_note",
        "reviewed_at",
        "reviewed_total",
        "issue_reason_counts",
    ):
        assert field in html
    assert "stored_precomputed_move_if_any" not in html.split("function buildExportPayload", 1)[1].split("function downloadExport", 1)[0]
    assert "lastExportSummary" in html
    assert "lastExportFirstRecord" in html


def test_auto_advance_waits_for_complete_review_and_shortcuts_ignore_inputs():
    html = _render_one(_analyze(_record(LOCAL_INSIDE, katago_best_move="T1")))

    assert "if(reviewComplete(entry))finishAndMaybeAdvance(key);else render();" in html
    assert "if(autoAdvance.checked&&stillVisible)navigateRelative(1);" in html
    assert "['INPUT','TEXTAREA','SELECT','BUTTON'].includes(event.target.tagName)" in html
    assert "event.key==='ArrowLeft'" in html
    assert "event.key==='ArrowRight'" in html
    assert "card.tabIndex=0" in html


def test_local_problem_with_answer_inside_region_has_no_tenuki_flag():
    result = _analyze(_record(LOCAL_INSIDE))

    assert result["spatial_metrics"]["appears_strongly_local"] is True
    assert result["spatial_metrics"]["native_first_solution"]["possible_far_signal"] is False
    assert "POSSIBLE_GLOBAL_TENUKI_SUSPECT" not in result["reason_codes"]
    assert "HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT" not in result["reason_codes"]


def test_local_problem_with_answer_opposite_side_is_tenuki_suspect():
    result = _analyze(
        _record(
            LOCAL_OPPOSITE,
            answer_source="katago_full_report",
            katago_full_applied_at="synthetic",
        )
    )

    assert result["spatial_metrics"]["native_first_solution"]["high_far_signal"] is True
    assert "HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT" in result["reason_codes"]
    assert result["classification"] == "OWNER_REVIEW_RECOMMENDED"


def test_broad_whole_board_position_disables_geometry_confidence():
    result = _analyze(
        _record(
            BROAD_POSITION,
            answer_source="katago_full_report",
            katago_full_applied_at="synthetic",
        )
    )

    assert result["spatial_metrics"]["broad_position_guard"] is True
    assert result["spatial_metrics"]["appears_strongly_local"] is False
    assert "POSSIBLE_GLOBAL_TENUKI_SUSPECT" not in result["reason_codes"]
    assert "HIGH_CONFIDENCE_GLOBAL_TENUKI_SUSPECT" not in result["reason_codes"]


def test_multiple_native_root_answers_are_not_automatically_suspicious():
    result = _analyze(_record(MULTIPLE_ROOTS))

    assert result["native_root_solution_count"] == 2
    assert result["reason_codes"] == []
    assert result["classification"] == "NO_OBVIOUS_ISSUE"


def test_duplicate_same_root_move_is_reviewable_but_not_p0_integrity_failure():
    duplicate = (
        "(;GM[1]FF[4]SZ[19]PL[B]AB[aa][ab][ba][bb][cc]AW[ac][bc]"
        "(;B[cd];W[ce])(;B[cd];W[de]))"
    )
    result = _analyze(_record(duplicate))

    assert result["native_root_solution_count"] == 1
    assert "DUPLICATE_ROOT_MOVE_BRANCH" in result["reason_codes"]
    assert "STRUCTURAL_SGF_ISSUE" in result["reason_codes"]
    assert result["priority_tier"] == "P2"


def test_no_solution_branch_is_p0_structural_suspect():
    result = _analyze(
        _record("(;GM[1]FF[4]SZ[19]PL[B]AB[aa][ab][ba][bb]AW[ac])")
    )

    assert result["priority_tier"] == "P0"
    assert "EMPTY_SOLUTION_TREE" in result["reason_codes"]
    assert "NO_VALID_ROOT_ANSWER" in result["reason_codes"]


def test_parser_failure_is_p0_without_leaking_raw_parser_text():
    result = _analyze(_record("(;GM[1]FF[4]SZ[19];B[zz])"))

    assert result["priority_tier"] == "P0"
    assert result["structural_metrics"]["parse_status"] == "failure"
    assert result["structural_metrics"]["parse_error_class"] == "ValueError"
    assert "PARSER_FAILURE" in result["reason_codes"]
    assert "parse_error" not in result


def test_precomputed_move_outside_native_tree_has_separate_reason_codes():
    result = _analyze(_record(LOCAL_INSIDE, katago_best_move="T1"))

    assert result["stored_precomputed_move_if_any"]["x"] == 18
    assert result["stored_precomputed_move_if_any"]["y"] == 18
    assert "PRECOMPUTED_KATAGO_ONLY_FALLBACK" in result["reason_codes"]
    assert "KATAGO_NATIVE_TREE_DISAGREEMENT" in result["reason_codes"]
    assert "ANSWER_PROVENANCE_UNKNOWN" in result["reason_codes"]


def test_combined_signals_rank_above_an_isolated_weak_signal():
    weak = _analyze(
        _record(LOCAL_INSIDE, id=2001, katago_best_move="C16"),
        index=1,
    )
    combined = _analyze(
        _record(LOCAL_INSIDE, id=2002, katago_best_move="T1"),
        index=2,
        player_metrics={
            "status": PLAYER_SIGNAL_AVAILABLE,
            "player_report_count": 4,
            "distinct_reporter_count": 3,
            "report_reason_counts": {"ANSWER_REJECTED": 4},
            "rejected_moves": [{"x": 5, "y": 5, "count": 4}],
            "attempt_count": 0,
            "wrong_count": 0,
            "wrong_rate": None,
            "shadow_disagreement_count": 0,
            "high_skill_rejected_move_count": 0,
            "calibration_dependent": False,
        },
    )

    ranked = rank_suspects([weak, combined])

    assert combined["priority_tier"] == "P1"
    assert ranked[0]["legacy_question_id"] == 2002
    assert "MULTIPLE_SOLUTION_REVIEW" in combined["reason_codes"]


def test_validation_selection_preserves_prefix_and_adds_tier_coverage():
    ranked = []
    for index in range(100):
        tier = "P0" if index < 70 else ("P1" if index < 80 else ("P2" if index < 90 else "P3"))
        ranked.append(
            {
                "deterministic_rank": index + 1,
                "priority_tier": tier,
                "audit_locator": {"record_index": index, "content_sha256": f"{index:064x}"},
            }
        )

    selected = select_validation_set(ranked, limit=100)

    assert len(selected) == 100
    assert [row["deterministic_rank"] for row in selected[:60]] == list(range(1, 61))
    assert {row["priority_tier"] for row in selected} == {"P0", "P1", "P2", "P3"}


def test_absent_player_report_data_is_explicit_and_deterministic():
    first = _analyze(_record(LOCAL_INSIDE))
    second = _analyze(_record(LOCAL_INSIDE))

    assert first == second
    assert first["player_report_metrics_if_available"] == {
        "status": PLAYER_SIGNAL_UNAVAILABLE
    }
    assert "PLAYER_REPORTED" not in first["reason_codes"]


def test_calibration_dependent_strength_does_not_become_primary_truth():
    result = _analyze(
        _record(LOCAL_INSIDE),
        player_metrics={
            "status": PLAYER_SIGNAL_AVAILABLE,
            "player_report_count": 0,
            "distinct_reporter_count": 0,
            "report_reason_counts": {},
            "rejected_moves": [],
            "attempt_count": 0,
            "wrong_count": 0,
            "wrong_rate": None,
            "shadow_disagreement_count": 0,
            "high_skill_rejected_move_count": 9,
            "calibration_dependent": True,
        },
    )

    assert result["reason_codes"] == ["CALIBRATION_DEPENDENT"]
    assert result["priority_tier"] == "P3"
    assert "CALIBRATION_DEPENDENT_EVIDENCE_DOES_NOT_INCREASE_PRIORITY" in result["notes"]


def test_repeated_generation_is_byte_identical_and_source_is_unchanged(tmp_path):
    questions = tmp_path / "questions.json"
    records = [
        _record(LOCAL_INSIDE, id=3001),
        _record(LOCAL_OPPOSITE, id=3002, katago_best_move="T1"),
        _record("(;GM[1]FF[4]SZ[19];B[zz])", id=3003),
    ]
    source_raw = (json.dumps(records, ensure_ascii=False, sort_keys=True) + "\n").encode()
    questions.write_bytes(source_raw)
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = generate_outputs(questions_path=questions, output_dir=first_dir, top_limit=100)
    second = generate_outputs(questions_path=questions, output_dir=second_dir, top_limit=100)

    assert questions.read_bytes() == source_raw
    assert first["summary"] == second["summary"]
    assert first["artifact_manifest"] == second["artifact_manifest"]
    for name in (
        "corpus_summary.json",
        "top_suspects.json",
        "owner_validation_pack.html",
        "owner_review_annotations.template.json",
        "artifact_manifest.json",
    ):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
    manifest = json.loads((first_dir / "top_suspects.json").read_text(encoding="utf-8"))
    assert all("content" not in record and "sgf" not in record for record in manifest["records"])
    annotations = json.loads(
        (first_dir / "owner_review_annotations.template.json").read_text(encoding="utf-8")
    )
    assert annotations["authority"] == "OWNER_VALIDATION_ANNOTATION"
    assert annotations["canonicality"] == "NON_AUTHORITATIVE"
    assert annotations["validation_pack_id"] == manifest["validation_pack_id"]
    assert annotations["allowed_review_statuses"] == [
        "NO_ISSUE",
        "CONFIRMED_ISSUE",
        "POSSIBLE_MULTIPLE_SOLUTION",
        "UNCERTAIN",
    ]


def test_audit_locator_is_snapshot_bound_and_not_canonical_identity():
    result = _analyze(_record(LOCAL_INSIDE, id=4001), index=77)

    locator = result["audit_locator"]
    assert locator["type"] == IDENTITY_TYPE
    assert locator["snapshot_sha256"] == "a" * 64
    assert locator["record_index"] == 77
    assert locator["legacy_question_id"] == 4001
    assert locator["content_sha256"] == hashlib.sha256(LOCAL_INSIDE.encode()).hexdigest()


def test_player_evidence_rejects_pii_shaped_unknown_fields(tmp_path):
    questions = tmp_path / "questions.json"
    records = [_record(LOCAL_INSIDE, id=5001)]
    questions.write_text(json.dumps(records), encoding="utf-8")
    snapshot_sha = hashlib.sha256(questions.read_bytes()).hexdigest()
    evidence = tmp_path / "player.json"
    evidence.write_text(
        json.dumps(
            {
                "snapshot_sha256": snapshot_sha,
                "records": [
                    {
                        "record_index": 0,
                        "legacy_question_id": 5001,
                        "content_sha256": hashlib.sha256(LOCAL_INSIDE.encode()).hexdigest(),
                        "reporter_user_id": 123,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported record fields"):
        generate_outputs(
            questions_path=questions,
            output_dir=tmp_path / "out",
            top_limit=100,
            player_evidence_path=evidence,
        )


def test_valid_aggregate_player_evidence_links_by_exact_audit_locator(tmp_path):
    questions = tmp_path / "questions.json"
    records = [_record(LOCAL_INSIDE, id=6001)]
    questions.write_text(json.dumps(records), encoding="utf-8")
    snapshot_sha = hashlib.sha256(questions.read_bytes()).hexdigest()
    evidence = tmp_path / "player.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": "test-v1",
                "snapshot_sha256": snapshot_sha,
                "records": [
                    {
                        "record_index": 0,
                        "legacy_question_id": 6001,
                        "content_sha256": hashlib.sha256(LOCAL_INSIDE.encode()).hexdigest(),
                        "player_report_count": 5,
                        "distinct_reporter_count": 4,
                        "report_reason_counts": {"ANSWER_REJECTED": 5},
                        "rejected_moves": [{"x": 5, "y": 5, "count": 5}],
                        "attempt_count": 30,
                        "wrong_count": 24,
                        "wrong_rate": 0.8,
                        "shadow_disagreement_count": 2,
                        "high_skill_rejected_move_count": 3,
                        "calibration_dependent": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "out"

    generate_outputs(
        questions_path=questions,
        output_dir=output,
        top_limit=100,
        player_evidence_path=evidence,
    )

    manifest = json.loads((output / "top_suspects.json").read_text(encoding="utf-8"))
    record = manifest["records"][0]
    assert record["player_report_metrics_if_available"]["status"] == PLAYER_SIGNAL_AVAILABLE
    assert "PLAYER_REPORTED" in record["reason_codes"]
    assert "REPEATED_REJECTED_MOVE" in record["reason_codes"]
    assert "MULTIPLE_SOLUTION_REVIEW" in record["reason_codes"]
    assert "ABNORMAL_WRONG_RATE" in record["reason_codes"]
    assert "SHADOW_DISAGREEMENT" in record["reason_codes"]
    assert "CALIBRATION_DEPENDENT" in record["reason_codes"]
