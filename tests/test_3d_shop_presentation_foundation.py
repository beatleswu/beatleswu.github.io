"""P046 deterministic proofs for the presentation-only 3D Shop foundation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from shop_3d_presentation_foundation import (
    DEFAULT_HERO_BASE_3D_REGISTRY,
    MANIFEST_SCHEMA_ID,
    ManifestValidationError,
    ModelRequestProbe,
    P040_EQUIPMENT_PRESENTATION_CONTRACT,
    PRESENTATION_FOUNDATION_CONTRACT,
    PRESENTATION_GATE_NAME,
    PresentationIdentity,
    canonical_manifest_bytes,
    companion_authority_contract,
    manifest_external_sha256,
    model_request_count_when_gate_off,
    presentation_gate_enabled,
    validate_manifest,
    verify_external_admission_hash,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "contracts" / "3d_shop_v1_p045_presentation_reference_manifest.json"
SCHEMA_PATH = ROOT / "schemas" / "3d_shop_presentation_manifest.schema.json"


@pytest.fixture()
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _entry(manifest: dict, presentation_id: str) -> dict:
    return next(item for item in manifest["entries"] if item["presentation_id"] == presentation_id)


def test_reference_manifest_is_valid_and_has_nine_admitted_metadata_entries(manifest):
    validated = validate_manifest(manifest)
    assert validated["foundation_contract"] == PRESENTATION_FOUNDATION_CONTRACT
    assert len(validated["entries"]) == 9
    assert {item["authority_domain"] for item in validated["entries"]} == {
        "HEAD_PRESENTATION",
        "BACK_PRESENTATION",
        "COMPANION_PRESENTATION",
        "VICTORY_EFFECT_PRESENTATION",
    }


def test_schema_is_strict_at_manifest_and_entry_boundaries():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["$id"] == MANIFEST_SCHEMA_ID
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["entry"]["additionalProperties"] is False
    assert "item_id" not in json.dumps(schema)
    assert "universal_item_id" not in json.dumps(schema)


def test_forbidden_business_authority_field_fails_closed(manifest):
    candidate = copy.deepcopy(manifest)
    candidate["entries"][0]["sku"] = "SHOP_HEAD_001"
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "FORBIDDEN_AUTHORITY_FIELD"


def test_nested_forbidden_identity_field_fails_closed(manifest):
    candidate = copy.deepcopy(manifest)
    candidate["entries"][0]["source_provenance"]["product_id"] = "not-a-presentation-field"
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "FORBIDDEN_AUTHORITY_FIELD"


def test_self_hash_field_is_rejected_instead_of_being_ambiguous(manifest):
    candidate = copy.deepcopy(manifest)
    candidate["manifest_sha256"] = "0" * 64
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "SELF_HASH_FORBIDDEN"


def test_universal_item_id_is_not_created_or_accepted(manifest):
    keys = set()

    def collect(value):
        if isinstance(value, dict):
            keys.update(value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(manifest)
    assert "universal_item_id" not in keys
    assert "item_id" not in keys


def test_presentation_identity_has_three_part_domain_bridge(manifest):
    identity = PresentationIdentity.from_entry(_entry(manifest, "P045_H06_BEANIE"))
    assert identity.key == (
        "HEAD_PRESENTATION",
        "PRESENTATION_ONLY:H06_BEANIE",
        "P045_H06_BEANIE",
    )
    assert not hasattr(identity, "sku")
    assert not hasattr(identity, "item_id")


def test_manifest_hash_is_deterministic_and_external(manifest):
    reordered = {key: manifest[key] for key in reversed(list(manifest))}
    digest = manifest_external_sha256(manifest)
    assert canonical_manifest_bytes(manifest) == canonical_manifest_bytes(reordered)
    assert verify_external_admission_hash(manifest, digest)
    assert digest == digest.lower()


def test_hash_function_rejects_nonfinite_values(manifest):
    candidate = copy.deepcopy(manifest)
    candidate["entries"][0]["presentation_scale"] = float("nan")
    with pytest.raises(ManifestValidationError) as error:
        canonical_manifest_bytes(candidate)
    assert error.value.code == "NON_CANONICAL_JSON"


def test_normalized_scale_is_separate_from_presentation_scale(manifest):
    beanie = _entry(manifest, "P045_H06_BEANIE")
    assert beanie["normalized_asset_scale"] == 1.0
    assert beanie["presentation_scale"] == 0.46
    assert beanie["normalized_asset_scale"] != beanie["presentation_scale"]


def test_local_position_and_forward_offsets_are_explicit_and_not_implicitly_added(manifest):
    backpack = _entry(manifest, "P045_B02_BACKPACK")
    assert backpack["local_position_offset"] == [0.0, 0.0, 0.12]
    assert backpack["local_forward_offset"] == [0.0, 0.0, 0.12]
    assert "not additive" in backpack["offset_semantics"]


def test_head_adapter_schema_is_shared_and_bounded(manifest):
    head_entries = [item for item in manifest["entries"] if item["authority_domain"] == "HEAD_PRESENTATION"]
    assert len(head_entries) == 5
    assert {item["adapter_profile"] for item in head_entries} == {"HEAD_SHARED_A1_HEAD_BOUNDS"}
    assert all(item["adapter_per_character_transform"] is False for item in head_entries)


def test_back_adapter_schema_preserves_single_local_vector(manifest):
    backpack = _entry(manifest, "P045_B02_BACKPACK")
    assert backpack["attachment_slot"] == "BACK"
    assert backpack["adapter_profile"] == "B02_SHARED_A3_A1_K1_BODY_REAR_AABB"
    assert backpack["local_position_offset"] == backpack["local_forward_offset"]


def test_p040_equipment_precedent_is_locked():
    assert dict(P040_EQUIPMENT_PRESENTATION_CONTRACT) == {
        "owner_uat": "PASS",
        "sword_presentation_scale": 5.0,
        "shield_presentation_scale": 3.5,
        "shield_original_baseline": 0.3315,
        "shield_world_scale": 1.16025,
        "shield_local_forward_offset": (0.0, 0.0, 0.13),
        "shield_local_forward_direction": "+Z",
    }


def test_c01_uses_rigid_transform_profile_without_skeleton(manifest):
    bunny = _entry(manifest, "P045_C01_BUNNY")
    assert bunny["animation_profile"] == "RIGID_TRANSFORM"
    assert bunny["animation_source"] == "presentation_transform"
    assert "skeleton_profile" not in bunny
    assert "subclips" not in bunny


def test_c04_uses_one_segmented_source_clip(manifest):
    corgi = _entry(manifest, "P045_C04_CORGI")
    assert corgi["animation_profile"] == "SKINNED_SEGMENTED_TIMELINE"
    assert corgi["animation_source"] == "clip"
    assert corgi["skeleton_profile"] == "C04_16_JOINT"
    assert corgi["fps"] == 24
    assert [(item["name"], item["start_frame"], item["end_frame_exclusive"]) for item in corgi["subclips"]] == [
        ("idle", 0, 30),
        ("attack", 30, 60),
        ("dead", 60, 90),
        ("walk", 90, 120),
    ]


def test_c04_wrong_ranges_are_rejected(manifest):
    candidate = copy.deepcopy(manifest)
    _entry(candidate, "P045_C04_CORGI")["subclips"][0]["end_frame_exclusive"] = 29
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "INVALID_SUBCLIPS"


def test_v01_is_victory_effect_with_proposed_timing_only(manifest):
    confetti = _entry(manifest, "P045_V01_CONFETTI")
    assert confetti["role"] == "VICTORY_EFFECT"
    assert confetti["persistent_aura"] is False
    assert confetti["runtime_timing_profile"]["initial_runtime_direction"] == 2048
    assert confetti["timing_authority"] == "PROPOSED_ONLY"
    assert confetti["source_timing_authority"] == "NONE"


def test_v01_non_victory_role_is_rejected(manifest):
    candidate = copy.deepcopy(manifest)
    _entry(candidate, "P045_V01_CONFETTI")["role"] = "AURA"
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "INVALID_VFX_ROLE"


def test_hero_base_registry_is_bounded_to_existing_character_keys():
    assert DEFAULT_HERO_BASE_3D_REGISTRY.keys() == (
        "A1_BASIC_ADVENTURER",
        "A3_MONK",
        "K1_KNIGHT_01",
    )
    assert DEFAULT_HERO_BASE_3D_REGISTRY.resolve("A3_MONK").fixture_profile == "SMALL"
    assert DEFAULT_HERO_BASE_3D_REGISTRY.as_dict()["K1_KNIGHT_01"]["presentation_asset_key"] == "P040_K1_HERO_BASE"


def test_hero_registry_rejects_duplicate_authoritative_key():
    from shop_3d_presentation_foundation import HeroBase3DRegistry, HeroBaseProfile

    registry = HeroBase3DRegistry((HeroBaseProfile("A1", "STANDARD", "hero"),))
    with pytest.raises(ValueError, match="duplicate hero base key"):
        registry.register(HeroBaseProfile("A1", "STANDARD", "other"))


def test_companion_authority_is_reconciled_to_existing_source_truth(manifest):
    expected = {
        "supply_quantity": "pet_inventory",
        "functional_ownership": "pet_collection.pet_key",
        "active_selection": "user_pets.pet_key",
        "second_ownership_registry_created": False,
    }
    assert companion_authority_contract() == expected
    assert manifest["companion_authority"] == expected


def test_companion_authority_mismatch_fails_closed(manifest):
    candidate = copy.deepcopy(manifest)
    candidate["companion_authority"]["functional_ownership"] = "pet_inventory.item_key"
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "COMPANION_AUTHORITY_MISMATCH"


def test_presentation_gate_defaults_off_without_environment_override():
    assert presentation_gate_enabled({}) is False
    assert presentation_gate_enabled({PRESENTATION_GATE_NAME: "unexpected"}) is False


def test_model_requests_are_zero_when_gate_is_off():
    assert model_request_count_when_gate_off() == 0
    probe = ModelRequestProbe({PRESENTATION_GATE_NAME: "0"})
    assert probe.request("p045://deferred/model.glb") is None
    assert probe.count == 0
    assert probe.requests == ()


def test_model_request_seam_is_explicitly_enabled_only_by_gate():
    loaded = []
    probe = ModelRequestProbe({PRESENTATION_GATE_NAME: "true"})
    result = probe.request("p045://deferred/model.glb", loader=loaded.append)
    assert result is None
    assert probe.count == 1
    assert probe.requests == ("p045://deferred/model.glb",)
    assert loaded == ["p045://deferred/model.glb"]


def test_reference_manifest_records_asset_promotion_as_deferred(manifest):
    assert manifest["canonical_asset_promotion"] is False
    assert manifest["p045_runtime_asset_promotion_deferred"] is True
    assert all(item["runtime_asset"].startswith("p045://deferred/") for item in manifest["entries"])


def test_duplicate_presentation_identity_is_rejected(manifest):
    candidate = copy.deepcopy(manifest)
    candidate["entries"][1]["presentation_id"] = candidate["entries"][0]["presentation_id"]
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "DUPLICATE_PRESENTATION_ID"


def test_unknown_manifest_field_is_not_silently_ignored(manifest):
    candidate = copy.deepcopy(manifest)
    candidate["future_business_authority"] = "not allowed"
    with pytest.raises(ManifestValidationError) as error:
        validate_manifest(candidate)
    assert error.value.code == "UNKNOWN_FIELD"
