"""P048 first-wave runtime projection and browser-contract proofs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from shop_3d_presentation_foundation import ManifestValidationError, validate_manifest
from tools.validate_3d_shop_p048_runtime import (
    EXPECTED_FOUNDATION_SHA256,
    EXPECTED_PROMOTED_IDS,
    FOUNDATION_MANIFEST_PATH,
    RUNTIME_MANIFEST_PATH,
    validate_runtime_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_JS_PATH = ROOT / "js" / "3d_shop_p048_runtime.js"
PREVIEW_PATH = ROOT / "p048_3d_shop_preview.html"


def _foundation() -> dict:
    return json.loads(FOUNDATION_MANIFEST_PATH.read_text(encoding="utf-8"))


def _runtime() -> dict:
    return json.loads(RUNTIME_MANIFEST_PATH.read_text(encoding="utf-8"))


def test_p048_projection_validates_against_p047_and_promotes_exact_first_wave():
    report = validate_runtime_manifest()
    assert report["foundation_manifest_validation"] == "PASS"
    assert report["foundation_external_sha256"] == EXPECTED_FOUNDATION_SHA256
    assert report["promoted_presentation_ids"] == list(EXPECTED_PROMOTED_IDS)
    assert report["head_entry_count"] == 5
    assert report["back_entry_count"] == 1
    assert report["companion_entry_count"] == 2
    assert report["victory_entry_count"] == 1


def test_p048_gate_is_default_off_and_preview_is_explicit():
    manifest = _runtime()
    assert manifest["feature_gate"] == {
        "name": "3D_SHOP_PRESENTATION_ENABLED",
        "default_enabled": False,
        "preview_override_required": True,
        "model_request_when_off": 0,
    }
    assert manifest["renderer_contract"]["shop_grid_realtime_renderers"] == 0
    assert manifest["renderer_contract"]["max_active_realtime_renderers"] == 1
    assert manifest["renderer_contract"]["normal_non_3d_page_model_requests"] == 0


def test_no_universal_item_id_or_commerce_authority_in_projection():
    runtime_text = RUNTIME_MANIFEST_PATH.read_text(encoding="utf-8")
    assert "universal_item_id" not in runtime_text
    assert '"product_sku_created": 0' in runtime_text
    assert '"preview_mutates_ownership": false' in runtime_text
    assert '"preview_mutates_equipment": false' in runtime_text
    assert _runtime()["paid_asset_purchase_count"] == 0
    assert _runtime()["paid_asset_runtime_promotion"] == 0


def test_forbidden_foundation_field_fails_closed():
    candidate = copy.deepcopy(_foundation())
    candidate["entries"][0]["sku"] = "NOT_A_PRESENTATION_FIELD"
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "FORBIDDEN_AUTHORITY_FIELD"


def test_runtime_projection_rejects_forbidden_field_fail_closed():
    candidate = copy.deepcopy(_runtime())
    candidate["entries"][0]["sku"] = "NOT_A_PRESENTATION_FIELD"
    with pytest.raises(AssertionError, match="forbidden business/self-hash"):
        validate_runtime_manifest(candidate, _foundation())


def test_runtime_projection_rejects_missing_derivative_hash():
    candidate = copy.deepcopy(_runtime())
    candidate["entries"][0]["runtime_sha256"] = ""
    with pytest.raises(AssertionError, match="runtime hash mismatch"):
        validate_runtime_manifest(candidate, _foundation())


def test_runtime_projection_rejects_wrong_domain_identity():
    candidate = copy.deepcopy(_runtime())
    candidate["entries"][6]["authority_domain"] = "HEAD_PRESENTATION"
    with pytest.raises(AssertionError, match="wrong presentation authority domain"):
        validate_runtime_manifest(candidate, _foundation())


def test_runtime_projection_rejects_unsupported_companion_profile():
    candidate = copy.deepcopy(_runtime())
    candidate["entries"][7]["animation_profile"] = "UNSUPPORTED_PROFILE"
    with pytest.raises(AssertionError, match="C04 segmented timeline contract changed"):
        validate_runtime_manifest(candidate, _foundation())


def test_c01_is_rigid_and_c04_subclips_are_segmented_from_clip():
    entries = {entry["presentation_id"]: entry for entry in _runtime()["entries"]}
    assert entries["P045_C01_BUNNY"]["animation_profile"] == "RIGID_TRANSFORM"
    assert "subclips" not in entries["P045_C01_BUNNY"]
    c04 = entries["P045_C04_CORGI"]
    assert c04["animation_profile"] == "SKINNED_SEGMENTED_TIMELINE"
    assert c04["animation_source"] == "clip"
    assert [(x["name"], x["start_frame"], x["end_frame_exclusive"]) for x in c04["subclips"]] == [
        ("idle", 0, 30),
        ("attack", 30, 60),
        ("dead", 60, 90),
        ("walk", 90, 120),
    ]
    assert all(x["fps"] == 24 for x in c04["subclips"])


def test_v01_is_victory_effect_with_proposed_runtime_timing():
    v01 = next(entry for entry in _runtime()["entries"] if entry["presentation_id"] == "P045_V01_CONFETTI")
    assert v01["role"] == "VICTORY_EFFECT"
    assert v01["source_timing_authority"] == "NONE"
    assert v01["timing_authority"] == "PROPOSED_ONLY"
    assert v01["runtime_timing_profile"]["initial_runtime_direction"] == 2048


def test_runtime_source_contains_fail_closed_unknown_and_lifecycle_guards():
    source = RUNTIME_JS_PATH.read_text(encoding="utf-8")
    for marker in (
        "Unknown presentation ID rejected",
        "forbidden presentation field rejected",
        "renderer singleton limit exceeded",
        "MAX_ACTIVE_REALTIME_RENDERERS",
        "dispose()",
        "preview_mutates_ownership: false",
        "preview_mutates_equipment: false",
    ):
        assert marker in source


def test_runtime_contains_required_lazy_controls_and_touch_rotation():
    source = RUNTIME_JS_PATH.read_text(encoding="utf-8")
    preview = PREVIEW_PATH.read_text(encoding="utf-8")
    for marker in ("loadGLTF", "loadTexture", "pointerType === \"touch\"", "setHead", "setBack", "setCompanion", "triggerVictory", "reset"):
        assert marker in source
    for marker in ('id="head-select"', 'id="back-select"', 'id="companion-select"', 'id="victory-button"', 'id="reset-button"'):
        assert marker in preview
    assert 'window.addEventListener("pagehide", () => runtime?.dispose()' in preview


def test_p045_runtime_promotion_is_exactly_nine_and_holds_are_not_promoted():
    manifest = _runtime()
    ids = {entry["presentation_id"] for entry in manifest["entries"]}
    assert len(ids) == 9
    assert ids == set(EXPECTED_PROMOTED_IDS)
    assert set(manifest["hold_assets_not_promoted"]) == {"H01", "B01", "B19", "H09", "A10", "T01", "V05"}
