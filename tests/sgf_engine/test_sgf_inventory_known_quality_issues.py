import hashlib
import json

from sgf_engine.inventory.sgf_inventory import (
    LOCAL_PROBLEM_PATH_HINTS,
    build_sgf_inventory,
    scan_sgf_file,
    sgf_coord_to_go_coord,
    write_inventory_artifacts,
)


def _write_sgf(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_valid_sgf_inventory_records_hash_source_and_root_moves(tmp_path):
    sgf = _write_sgf(tmp_path / "valid.sgf", "(;AB[dd][de];B[sd];W[of])")
    before = sgf.read_bytes()

    item = scan_sgf_file(sgf)

    assert sgf.read_bytes() == before
    assert item.source_path == sgf.as_posix()
    assert item.filename == "valid.sgf"
    assert item.sha256 == hashlib.sha256(before).hexdigest().upper()
    assert item.parse_status == "ok"
    assert item.root_children_count == 1
    assert item.root_child_moves == ("B[sd]",)
    assert item.root_child_moves_go_coords == ("B[sd] / T16",)
    assert item.first_player_color_candidates == ("B",)
    assert item.setup_stone_count == 2
    assert item.setup_bounding_box["stone_count"] == 2


def test_sgf_coord_to_go_coord_uses_normal_19x19_labels():
    assert sgf_coord_to_go_coord("sd") == "T16"
    assert sgf_coord_to_go_coord("sf") == "T14"
    assert sgf_coord_to_go_coord("of") == "P14"


def test_parse_error_is_reported_without_crashing(tmp_path):
    sgf = _write_sgf(tmp_path / "bad.sgf", "(;B[DD])")

    item = scan_sgf_file(sgf)

    assert item.parse_status.startswith("PARSE_ERROR")
    assert "PARSE_ERROR" in item.quality_flags
    assert item.root_child_moves == ()


def test_missing_answer_flags_cover_no_root_children_setup_only_and_empty(tmp_path):
    no_children = scan_sgf_file(_write_sgf(tmp_path / "no_children.sgf", "(;C[root])"))
    setup_only = scan_sgf_file(_write_sgf(tmp_path / "setup_only.sgf", "(;AB[dd][de])"))
    empty = scan_sgf_file(_write_sgf(tmp_path / "empty.sgf", "(;)"))

    assert {"NO_ROOT_CHILDREN", "NO_ANSWER_BRANCH"} <= set(no_children.quality_flags)
    assert {
        "NO_ROOT_CHILDREN",
        "NO_ANSWER_BRANCH",
        "SETUP_ONLY_NO_SOLUTION",
    } <= set(setup_only.quality_flags)
    assert {
        "EMPTY_GAME_TREE",
        "NO_ROOT_CHILDREN",
        "NO_ANSWER_BRANCH",
    } <= set(empty.quality_flags)


def test_board_crop_and_coordinate_mismatch_candidates_are_flagged(tmp_path):
    sgf = _write_sgf(tmp_path / "edge_far.sgf", "(;AB[dd][de][ed];B[sa])")

    item = scan_sgf_file(sgf)

    assert "ANSWER_ON_EDGE_LINE" in item.quality_flags
    assert "ANSWER_FAR_FROM_SETUP_STONES" in item.quality_flags
    assert "ANSWER_OUTSIDE_LOCAL_REGION" in item.quality_flags
    assert "POSSIBLE_BOARD_CROP_COORDINATE_MISMATCH" in item.quality_flags
    assert item.answer_distance_from_setup >= 8
    assert any("B[sa] / T19" in reason for reason in item.quality_reasons)


def test_local_problem_path_with_distant_answer_flags_possible_global_ai_tenuki(tmp_path):
    sgf = _write_sgf(
        tmp_path / "life-and-death" / "candidate.sgf",
        "(;AB[dd][de][ed];W[pd])",
    )

    item = scan_sgf_file(sgf)

    assert "LIFE_AND_DEATH_CATEGORY_WITH_DISTANT_ANSWER" in item.quality_flags
    assert "ANSWER_FAR_FROM_LOCAL_CLUSTER" in item.quality_flags
    assert "ANSWER_OUTSIDE_PROBLEM_REGION" in item.quality_flags
    assert "POSSIBLE_GLOBAL_AI_TENUKI_ANSWER" in item.quality_flags


def test_chinese_local_problem_path_hints_are_recognized(tmp_path):
    for folder_name in ("做活的要點", "死活", "手筋", "對殺"):
        sgf = _write_sgf(
            tmp_path / folder_name / "candidate.sgf",
            "(;AB[dd][de][ed];W[pd])",
        )

        item = scan_sgf_file(sgf)

        assert "LIFE_AND_DEATH_CATEGORY_WITH_DISTANT_ANSWER" in item.quality_flags
        assert "POSSIBLE_GLOBAL_AI_TENUKI_ANSWER" in item.quality_flags


def test_english_local_problem_path_hints_are_still_recognized(tmp_path):
    for folder_name in ("life-and-death", "tesuji"):
        sgf = _write_sgf(
            tmp_path / folder_name / "candidate.sgf",
            "(;AB[dd][de][ed];W[pd])",
        )

        item = scan_sgf_file(sgf)

        assert "LIFE_AND_DEATH_CATEGORY_WITH_DISTANT_ANSWER" in item.quality_flags
        assert "POSSIBLE_GLOBAL_AI_TENUKI_ANSWER" in item.quality_flags


def test_non_local_problem_paths_do_not_trigger_global_tenuki_flags(tmp_path):
    for folder_name in ("全局", "定石", "綜合測驗", "gold_fixtures"):
        sgf = _write_sgf(
            tmp_path / folder_name / "candidate.sgf",
            "(;AB[dd][de][ed];W[pd])",
        )

        item = scan_sgf_file(sgf)

        assert "LIFE_AND_DEATH_CATEGORY_WITH_DISTANT_ANSWER" not in item.quality_flags
        assert "POSSIBLE_GLOBAL_AI_TENUKI_ANSWER" not in item.quality_flags


def test_local_problem_path_hints_use_conservative_keyword_set():
    assert LOCAL_PROBLEM_PATH_HINTS == (
        "死活",
        "做活",
        "殺棋",
        "杀棋",
        "手筋",
        "對殺",
        "对杀",
        "眼形",
        "活棋",
        "life-and-death",
        "life_and_death",
        "tesuji",
    )


def test_other_quality_flags_multiple_variations_auto_reply_and_shallow(tmp_path):
    variation = scan_sgf_file(_write_sgf(tmp_path / "variation.sgf", "(;AB[dd](;B[ee])(;W[ff]))"))
    auto_reply = scan_sgf_file(_write_sgf(tmp_path / "auto_reply.sgf", "(;AB[dd];B[ee];W[ef])"))
    shallow = scan_sgf_file(_write_sgf(tmp_path / "shallow.sgf", "(;AB[dd];B[ee])"))

    assert "MULTIPLE_ROOT_CHILDREN" in variation.quality_flags
    assert "HAS_VARIATIONS" in variation.quality_flags
    assert "POSSIBLE_AUTO_REPLY_PATTERN" in auto_reply.quality_flags
    assert auto_reply.auto_reply_pattern_candidates == ("B[ee] -> W[ef]",)
    assert "TERMINAL_TOO_SHALLOW" in shallow.quality_flags


def test_build_inventory_and_report_are_read_only_artifacts(tmp_path):
    root = tmp_path / "scan"
    sgf = _write_sgf(root / "431.sgf", "(;AB[dd][de][ed];B[sf])")
    original_bytes = sgf.read_bytes()
    markdown = tmp_path / "report.md"
    json_report = tmp_path / "report.json"

    inventory = write_inventory_artifacts(root, markdown, json_report)

    assert sgf.read_bytes() == original_bytes
    assert inventory["summary"]["total_sgf_files"] == 1
    assert markdown.read_text(encoding="utf-8").startswith(
        "# SGF Inventory / Known Quality Issues Report"
    )
    assert "GF-003 production override enabled: no" in markdown.read_text(
        encoding="utf-8"
    )
    loaded = json.loads(json_report.read_text(encoding="utf-8"))
    assert loaded["items"][0]["filename"] == "431.sgf"


def test_build_sgf_inventory_scans_tree_without_touching_override_config(tmp_path):
    root = tmp_path / "scan"
    _write_sgf(root / "a.sgf", "(;AB[dd];B[ee])")
    _write_sgf(root / "nested" / "b.sgf", "(;AB[pp])")

    inventory = build_sgf_inventory(root)

    assert [item["filename"] for item in inventory["items"]] == ["a.sgf", "b.sgf"]
    assert inventory["summary"]["missing_answers"] == 1
