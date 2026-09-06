from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_default_v2a_surface_contains_shadow_identity_authority_and_staging_controls():
    js = (ROOT / "sgf_workbench_v2a.js").read_text(encoding="utf-8")
    routes = (ROOT / "sgf_answer_review_routes.py").read_text(encoding="utf-8")
    backend = (ROOT / "sgf_admin_workbench.py").read_text(encoding="utf-8")
    assert "/api/admin/sgf-answer-review/shadow/context" in routes
    assert "/api/admin/sgf-answer-review/shadow/review" in routes
    assert "source_record_uuid" in js
    assert "HELPFUL_BUT_NOT_AUTHORITATIVE" in js
    assert "stageShadow" in js
    assert "retestShadow" in js
    assert "SHADOW_REVIEWED_AUTHORITY" in backend
    assert "pointerup" in js
    assert "data-shadow-operation" in js
    assert "data-shadow-retest" in js


def test_default_surface_is_touch_first_without_manual_sgf_or_coordinate_entry():
    js = (ROOT / "sgf_workbench_v2a.js").read_text(encoding="utf-8")
    assert "min-height:44px" in js
    assert "min-height:56px" in js
    assert "touch-action:none" in js
    assert ":hover" not in js
    assert "pointerup" in js
    assert "candidate_move:candidate" in js
    assert "<textarea" not in js
    assert "manual" not in js.lower()
    assert "input id=\"candidate" not in js
    assert "record_index" in js  # server locator only; no record-index input exists
    assert "<input id=\"record_index" not in js


def test_surface_exposes_both_orientation_contracts_and_shadow_is_non_runtime():
    js = (ROOT / "sgf_workbench_v2a.js").read_text(encoding="utf-8")
    backend = (ROOT / "sgf_admin_workbench.py").read_text(encoding="utf-8")
    assert "@media(orientation:portrait)" in js
    assert "runtime_authority:false" in js or '"runtime_authority": False' in backend
    assert "affects_progression:false" in js or '"affects_progression": False' in backend
    assert "direct_apply_enabled:false" in js or '"direct_apply_enabled": False' in backend
