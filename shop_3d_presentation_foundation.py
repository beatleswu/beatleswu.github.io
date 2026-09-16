"""Bounded, presentation-only foundation for the future 3D Shop runtime.

This module intentionally has no Flask route, database writer, commerce
writer, asset loader, or Three.js dependency.  It owns the small contract that
the future Product runtime will consume after a separate enablement decision:

* typed presentation identity, separate from business identity;
* strict, fail-closed presentation-manifest validation;
* external deterministic admission hashing;
* a bounded HeroBase3DRegistry;
* reconciled companion authority labels; and
* a default-OFF model-request gate.

P045 binaries remain outside canonical in this task.  The checked-in P045
reference manifest is metadata only and points at the isolated admission
package until a later runtime task explicitly promotes assets.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


PRESENTATION_GATE_NAME = "3D_SHOP_PRESENTATION_ENABLED"
PRESENTATION_FOUNDATION_CONTRACT = "3D_SHOP_V1_PRESENTATION_FOUNDATION"
MANIFEST_SCHEMA_ID = "https://godokoro.com/schemas/3d_shop_presentation_manifest.schema.json"

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ALLOWED_MODEL_FORMATS = frozenset({"GLB", "GLB_EXTERNAL_PNG", "PNG_SPRITESHEET"})
_ALLOWED_DOMAINS = frozenset(
    {
        "HEAD_PRESENTATION",
        "BACK_PRESENTATION",
        "COMPANION_PRESENTATION",
        "VICTORY_EFFECT_PRESENTATION",
    }
)
_ALLOWED_MOBILE_CLASSES = frozenset({"LOW", "MEDIUM", "HIGH"})
_FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "item_id",
        "universal_item_id",
        "shop_sku",
        "sku",
        "product_id",
        "equipment_id",
        "functional_item_id",
        "pet_id",
        "ownership_id",
        "owner_id",
        "commerce_id",
        "inventory_id",
        "order_id",
        "payment_id",
        "transaction_id",
        "price",
        "currency",
        "purchase_url",
    }
)
_FORBIDDEN_SELF_HASH_FIELDS = frozenset(
    {
        "manifest_sha256",
        "external_admission_sha256",
    }
)
_FORBIDDEN_FIELDS = _FORBIDDEN_AUTHORITY_FIELDS | _FORBIDDEN_SELF_HASH_FIELDS

_ROOT_FIELDS = frozenset(
    {
        "manifest_name",
        "manifest_version",
        "foundation_contract",
        "canonical_asset_promotion",
        "p045_runtime_asset_promotion_deferred",
        "owner_visual_gate",
        "feature_gate",
        "provenance_policy",
        "companion_authority",
        "precedent_contracts",
        "entries",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "presentation_id",
        "authority_domain",
        "authority_id",
        "model_format",
        "runtime_asset",
        "runtime_sha256",
        "fallback_runtime_asset",
        "fallback_runtime_sha256",
        "runtime_texture_assets",
        "normalized_asset_scale",
        "presentation_scale",
        "orientation",
        "pivot",
        "attachment_slot",
        "attachment_anchor",
        "local_position_offset",
        "local_forward_offset",
        "offset_semantics",
        "adapter_profile",
        "adapter_per_character_transform",
        "follow_anchor",
        "follow_offset",
        "animation_profile",
        "animation_source",
        "skeleton_profile",
        "subclips",
        "fps",
        "vfx_profile",
        "role",
        "persistent_aura",
        "atlas_metadata",
        "frame_metadata",
        "texture_class",
        "runtime_timing_profile",
        "timing_authority",
        "source_timing_authority",
        "source_provenance",
        "mobile_class",
        "runtime_bytes",
        "geometry",
        "material_count",
        "texture_count",
        "presentation_tags",
    }
)
_PROVENANCE_FIELDS = frozenset(
    {
        "author",
        "source_url",
        "license",
        "commercial_use_allowed",
        "derivative_work_allowed",
        "attribution_required",
        "original_source_sha256",
        "derivative_sha256",
    }
)
_SUBCLIP_FIELDS = frozenset(
    {"name", "source_clip", "start_frame", "end_frame_exclusive", "fps"}
)
_P040_FIELDS = frozenset(
    {
        "owner_uat",
        "sword_presentation_scale",
        "shield_presentation_scale",
        "shield_original_baseline",
        "shield_world_scale",
        "shield_local_forward_offset",
        "shield_local_forward_direction",
    }
)


class ManifestValidationError(ValueError):
    """Stable, fail-closed manifest validation failure."""

    def __init__(self, code: str, message: str, *, path: str = "manifest") -> None:
        super().__init__(message)
        self.code = code
        self.path = path

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": str(self)}


def _fail(code: str, message: str, *, path: str) -> None:
    raise ManifestValidationError(code, message, path=path)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_SHAPE", f"{path} must be an object", path=path)
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("INVALID_VALUE", f"{path} must be a non-empty string", path=path)
    return value.strip()


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        _fail("INVALID_VALUE", f"{path} must be boolean", path=path)
    return value


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail("INVALID_VALUE", f"{path} must be a finite number", path=path)
    return float(value)


def _positive_number(value: Any, path: str) -> float:
    number = _finite_number(value, path)
    if number <= 0:
        _fail("INVALID_VALUE", f"{path} must be greater than zero", path=path)
    return number


def _vector3(value: Any, path: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        _fail("INVALID_VALUE", f"{path} must contain exactly three numbers", path=path)
    return tuple(_finite_number(component, f"{path}[{index}]") for index, component in enumerate(value))  # type: ignore[return-value]


def _sha256(value: Any, path: str) -> str:
    text = _text(value, path)
    if not _SHA256_RE.fullmatch(text):
        _fail("INVALID_SHA256", f"{path} must be a 64-character SHA-256 hex digest", path=path)
    return text


def _reject_forbidden_fields(value: Any, path: str = "manifest") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in _FORBIDDEN_SELF_HASH_FIELDS:
                _fail(
                    "SELF_HASH_FORBIDDEN",
                    f"{child_path} is not accepted; admission hashes are external to the manifest",
                    path=child_path,
                )
            if key_text in _FORBIDDEN_AUTHORITY_FIELDS:
                _fail(
                    "FORBIDDEN_AUTHORITY_FIELD",
                    f"{child_path} is a business/commerce authority field and is not allowed",
                    path=child_path,
                )
            _reject_forbidden_fields(child, child_path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            _reject_forbidden_fields(child, f"{path}[{index}]")


def _reject_unknown(value: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(str(key) for key in value) - set(allowed))
    if unknown:
        _fail(
            "UNKNOWN_FIELD",
            f"{path} contains unsupported field(s): {', '.join(unknown)}",
            path=path,
        )


def _required(mapping: Mapping[str, Any], name: str, path: str) -> Any:
    if name not in mapping:
        _fail("MISSING_FIELD", f"{path}.{name} is required", path=f"{path}.{name}")
    return mapping[name]


def _validate_provenance(value: Any, path: str) -> None:
    provenance = _mapping(value, path)
    _reject_unknown(provenance, _PROVENANCE_FIELDS, path)
    for field in ("author", "source_url", "license"):
        _text(_required(provenance, field, path), f"{path}.{field}")
    url = _text(provenance["source_url"], f"{path}.source_url")
    if not url.startswith(("https://", "http://")):
        _fail("INVALID_VALUE", f"{path}.source_url must be an explicit web URL", path=f"{path}.source_url")
    for field in ("commercial_use_allowed", "derivative_work_allowed", "attribution_required"):
        _bool(_required(provenance, field, path), f"{path}.{field}")
    _sha256(_required(provenance, "original_source_sha256", path), f"{path}.original_source_sha256")
    _sha256(_required(provenance, "derivative_sha256", path), f"{path}.derivative_sha256")


def _validate_subclips(value: Any, path: str) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        _fail("INVALID_SUBCLIPS", f"{path} must contain exactly four subclips", path=path)
    expected = (
        ("idle", 0, 30),
        ("attack", 30, 60),
        ("dead", 60, 90),
        ("walk", 90, 120),
    )
    for index, (subclip, expected_values) in enumerate(zip(value, expected)):
        item_path = f"{path}[{index}]"
        item = _mapping(subclip, item_path)
        _reject_unknown(item, _SUBCLIP_FIELDS, item_path)
        name, start, end = expected_values
        if _text(_required(item, "name", item_path), f"{item_path}.name") != name:
            _fail("INVALID_SUBCLIPS", f"{item_path}.name must be {name!r}", path=f"{item_path}.name")
        if _text(_required(item, "source_clip", item_path), f"{item_path}.source_clip") != "clip":
            _fail("INVALID_SUBCLIPS", f"{item_path}.source_clip must be 'clip'", path=f"{item_path}.source_clip")
        if _required(item, "start_frame", item_path) != start:
            _fail("INVALID_SUBCLIPS", f"{item_path}.start_frame must be {start}", path=f"{item_path}.start_frame")
        if _required(item, "end_frame_exclusive", item_path) != end:
            _fail(
                "INVALID_SUBCLIPS",
                f"{item_path}.end_frame_exclusive must be {end}",
                path=f"{item_path}.end_frame_exclusive",
            )
        if _required(item, "fps", item_path) != 24:
            _fail("INVALID_SUBCLIPS", f"{item_path}.fps must be 24", path=f"{item_path}.fps")


def _validate_entry(entry: Any, index: int) -> str:
    path = f"manifest.entries[{index}]"
    item = _mapping(entry, path)
    _reject_unknown(item, _ENTRY_FIELDS, path)
    presentation_id = _text(_required(item, "presentation_id", path), f"{path}.presentation_id")
    domain = _text(_required(item, "authority_domain", path), f"{path}.authority_domain")
    if domain not in _ALLOWED_DOMAINS:
        _fail("INVALID_DOMAIN", f"{path}.authority_domain is unsupported", path=f"{path}.authority_domain")
    _text(_required(item, "authority_id", path), f"{path}.authority_id")
    model_format = _text(_required(item, "model_format", path), f"{path}.model_format")
    if model_format not in _ALLOWED_MODEL_FORMATS:
        _fail("INVALID_MODEL_FORMAT", f"{path}.model_format is unsupported", path=f"{path}.model_format")
    _text(_required(item, "runtime_asset", path), f"{path}.runtime_asset")
    _sha256(_required(item, "runtime_sha256", path), f"{path}.runtime_sha256")
    for optional_hash in ("fallback_runtime_sha256",):
        if optional_hash in item:
            _sha256(item[optional_hash], f"{path}.{optional_hash}")
    for optional_asset in ("fallback_runtime_asset",):
        if optional_asset in item:
            _text(item[optional_asset], f"{path}.{optional_asset}")
    if "runtime_texture_assets" in item:
        assets = item["runtime_texture_assets"]
        if not isinstance(assets, Sequence) or isinstance(assets, (str, bytes)):
            _fail("INVALID_VALUE", f"{path}.runtime_texture_assets must be an array", path=f"{path}.runtime_texture_assets")
        for texture_index, asset in enumerate(assets):
            _text(asset, f"{path}.runtime_texture_assets[{texture_index}]")
    _validate_provenance(_required(item, "source_provenance", path), f"{path}.source_provenance")

    if domain == "VICTORY_EFFECT_PRESENTATION":
        if model_format != "PNG_SPRITESHEET":
            _fail("INVALID_VFX_FORMAT", f"{path} victory effects must use PNG_SPRITESHEET", path=path)
        for field in (
            "vfx_profile",
            "role",
            "atlas_metadata",
            "frame_metadata",
            "texture_class",
            "runtime_timing_profile",
            "timing_authority",
            "source_timing_authority",
        ):
            _text(_required(item, field, path), f"{path}.{field}") if field in {"vfx_profile", "role", "texture_class", "timing_authority", "source_timing_authority"} else _mapping(_required(item, field, path), f"{path}.{field}")
        if item["role"] != "VICTORY_EFFECT":
            _fail("INVALID_VFX_ROLE", f"{path}.role must be VICTORY_EFFECT", path=f"{path}.role")
        if item["timing_authority"] != "PROPOSED_ONLY":
            _fail("INVALID_VFX_TIMING", f"{path}.timing_authority must be PROPOSED_ONLY", path=f"{path}.timing_authority")
        if item["source_timing_authority"] != "NONE":
            _fail("INVALID_VFX_TIMING", f"{path}.source_timing_authority must be NONE", path=f"{path}.source_timing_authority")
        return presentation_id

    for field in (
        "normalized_asset_scale",
        "presentation_scale",
        "orientation",
        "pivot",
        "attachment_slot",
        "attachment_anchor",
        "adapter_profile",
    ):
        value = _required(item, field, path)
        if field in {"normalized_asset_scale", "presentation_scale"}:
            _positive_number(value, f"{path}.{field}")
        else:
            _text(value, f"{path}.{field}")
    _vector3(_required(item, "local_position_offset", path), f"{path}.local_position_offset")
    _vector3(_required(item, "local_forward_offset", path), f"{path}.local_forward_offset")
    if "adapter_per_character_transform" in item:
        _bool(item["adapter_per_character_transform"], f"{path}.adapter_per_character_transform")

    if domain == "COMPANION_PRESENTATION":
        for field in ("follow_anchor", "animation_profile", "animation_source"):
            _text(_required(item, field, path), f"{path}.{field}")
        _vector3(_required(item, "follow_offset", path), f"{path}.follow_offset")
        animation_profile = item["animation_profile"]
        if animation_profile == "RIGID_TRANSFORM":
            if "subclips" in item or "skeleton_profile" in item:
                _fail(
                    "INVALID_COMPANION_PROFILE",
                    f"{path} rigid-transform companions cannot declare skinned timeline fields",
                    path=path,
                )
        elif animation_profile == "SKINNED_SEGMENTED_TIMELINE":
            _text(_required(item, "skeleton_profile", path), f"{path}.skeleton_profile")
            if _required(item, "animation_source", path) != "clip":
                _fail("INVALID_COMPANION_PROFILE", f"{path}.animation_source must be clip", path=f"{path}.animation_source")
            _validate_subclips(_required(item, "subclips", path), f"{path}.subclips")
            if _required(item, "fps", path) != 24:
                _fail("INVALID_COMPANION_PROFILE", f"{path}.fps must be 24", path=f"{path}.fps")
        else:
            _fail("INVALID_COMPANION_PROFILE", f"{path}.animation_profile is unsupported", path=f"{path}.animation_profile")
    return presentation_id


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and detach a presentation-only manifest.

    Unknown fields and known business-authority fields are rejected before any
    consumer can accidentally treat presentation metadata as a Shop, item,
    equipment, inventory, or ownership authority.
    """

    _reject_forbidden_fields(manifest)
    root = _mapping(manifest, "manifest")
    _reject_unknown(root, _ROOT_FIELDS, "manifest")
    if _text(_required(root, "foundation_contract", "manifest"), "manifest.foundation_contract") != PRESENTATION_FOUNDATION_CONTRACT:
        _fail("INVALID_CONTRACT", "manifest.foundation_contract is unsupported", path="manifest.foundation_contract")
    _text(_required(root, "manifest_name", "manifest"), "manifest.manifest_name")
    _text(_required(root, "manifest_version", "manifest"), "manifest.manifest_version")
    if _required(root, "canonical_asset_promotion", "manifest") is not False:
        _fail("INVALID_BOUNDARY", "manifest.canonical_asset_promotion must be false", path="manifest.canonical_asset_promotion")
    if _required(root, "p045_runtime_asset_promotion_deferred", "manifest") is not True:
        _fail("INVALID_BOUNDARY", "manifest.p045_runtime_asset_promotion_deferred must be true", path="manifest.p045_runtime_asset_promotion_deferred")
    if _text(_required(root, "owner_visual_gate", "manifest"), "manifest.owner_visual_gate") != "PASS":
        _fail("INVALID_GATE", "manifest.owner_visual_gate must be PASS from P045", path="manifest.owner_visual_gate")

    feature_gate = _mapping(_required(root, "feature_gate", "manifest"), "manifest.feature_gate")
    _reject_unknown(feature_gate, frozenset({"name", "default_enabled", "model_request_when_off"}), "manifest.feature_gate")
    if _text(_required(feature_gate, "name", "manifest.feature_gate"), "manifest.feature_gate.name") != PRESENTATION_GATE_NAME:
        _fail("INVALID_GATE", "manifest.feature_gate.name does not match the foundation gate", path="manifest.feature_gate.name")
    if _required(feature_gate, "default_enabled", "manifest.feature_gate") is not False:
        _fail("INVALID_GATE", "manifest.feature_gate.default_enabled must be false", path="manifest.feature_gate.default_enabled")
    if _required(feature_gate, "model_request_when_off", "manifest.feature_gate") != 0:
        _fail("INVALID_GATE", "manifest.feature_gate.model_request_when_off must be zero", path="manifest.feature_gate.model_request_when_off")

    provenance_policy = _mapping(_required(root, "provenance_policy", "manifest"), "manifest.provenance_policy")
    _reject_unknown(provenance_policy, frozenset({"license_required", "source_sha_required", "derivative_sha_required"}), "manifest.provenance_policy")
    for field in ("license_required", "source_sha_required", "derivative_sha_required"):
        if _required(provenance_policy, field, "manifest.provenance_policy") is not True:
            _fail("INVALID_PROVENANCE_POLICY", f"manifest.provenance_policy.{field} must be true", path=f"manifest.provenance_policy.{field}")

    companion_authority = _mapping(_required(root, "companion_authority", "manifest"), "manifest.companion_authority")
    _reject_unknown(
        companion_authority,
        frozenset({"supply_quantity", "functional_ownership", "active_selection", "second_ownership_registry_created"}),
        "manifest.companion_authority",
    )
    expected_companion_authority = companion_authority_contract()
    if companion_authority != expected_companion_authority:
        _fail("COMPANION_AUTHORITY_MISMATCH", "manifest.companion_authority does not match canonical source truth", path="manifest.companion_authority")

    precedent_contracts = _mapping(_required(root, "precedent_contracts", "manifest"), "manifest.precedent_contracts")
    _reject_unknown(precedent_contracts, frozenset({"p040_equipment"}), "manifest.precedent_contracts")
    p040 = _mapping(_required(precedent_contracts, "p040_equipment", "manifest.precedent_contracts"), "manifest.precedent_contracts.p040_equipment")
    _reject_unknown(p040, _P040_FIELDS, "manifest.precedent_contracts.p040_equipment")
    if _text(_required(p040, "owner_uat", "manifest.precedent_contracts.p040_equipment"), "manifest.precedent_contracts.p040_equipment.owner_uat") != "PASS":
        _fail("INVALID_PRECEDENT", "P040 equipment contract must remain PASS", path="manifest.precedent_contracts.p040_equipment.owner_uat")
    if _positive_number(_required(p040, "sword_presentation_scale", "manifest.precedent_contracts.p040_equipment"), "p040 sword scale") != 5.0:
        _fail("INVALID_PRECEDENT", "P040 sword scale must remain 5.0", path="manifest.precedent_contracts.p040_equipment.sword_presentation_scale")
    if _positive_number(_required(p040, "shield_presentation_scale", "manifest.precedent_contracts.p040_equipment"), "p040 shield scale") != 3.5:
        _fail("INVALID_PRECEDENT", "P040 shield scale must remain 3.5", path="manifest.precedent_contracts.p040_equipment.shield_presentation_scale")
    _positive_number(_required(p040, "shield_original_baseline", "manifest.precedent_contracts.p040_equipment"), "p040 shield baseline")
    _positive_number(_required(p040, "shield_world_scale", "manifest.precedent_contracts.p040_equipment"), "p040 shield world scale")
    _vector3(_required(p040, "shield_local_forward_offset", "manifest.precedent_contracts.p040_equipment"), "p040 shield forward offset")
    if _text(_required(p040, "shield_local_forward_direction", "manifest.precedent_contracts.p040_equipment"), "p040 shield direction") != "+Z":
        _fail("INVALID_PRECEDENT", "P040 shield direction must remain +Z", path="manifest.precedent_contracts.p040_equipment.shield_local_forward_direction")

    entries = _required(root, "entries", "manifest")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)) or not entries:
        _fail("INVALID_ENTRIES", "manifest.entries must be a non-empty array", path="manifest.entries")
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        presentation_id = _validate_entry(entry, index)
        if presentation_id in seen:
            _fail("DUPLICATE_PRESENTATION_ID", f"{presentation_id} is repeated", path=f"manifest.entries[{index}].presentation_id")
        seen.add(presentation_id)
    return copy.deepcopy(dict(root))


def canonical_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Return the documented canonical serialization for an external hash."""

    _reject_forbidden_fields(manifest)
    try:
        return json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError("NON_CANONICAL_JSON", str(exc), path="manifest") from exc


def manifest_external_sha256(manifest: Mapping[str, Any]) -> str:
    """Compute the out-of-band admission hash; no hash field is self-included."""

    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def verify_external_admission_hash(manifest: Mapping[str, Any], expected_sha256: str) -> bool:
    """Compare an external release/admission digest without accepting self-hash metadata."""

    expected = _sha256(expected_sha256, "expected_sha256").lower()
    return manifest_external_sha256(manifest) == expected


@dataclass(frozen=True)
class PresentationIdentity:
    """Presentation identity bridge, never a Shop or ownership identity."""

    authority_domain: str
    authority_id: str
    presentation_id: str

    @classmethod
    def from_entry(cls, entry: Mapping[str, Any]) -> "PresentationIdentity":
        _validate_entry(entry, 0)
        return cls(
            authority_domain=str(entry["authority_domain"]),
            authority_id=str(entry["authority_id"]),
            presentation_id=str(entry["presentation_id"]),
        )

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.authority_domain, self.authority_id, self.presentation_id)


@dataclass(frozen=True)
class HeroBaseProfile:
    """Presentation fixture mapping keyed by an existing character key."""

    authoritative_character_key: str
    fixture_profile: str
    presentation_asset_key: str


class HeroBase3DRegistry:
    """Bounded presentation registry; it does not own hero or item records."""

    def __init__(self, profiles: Sequence[HeroBaseProfile] = ()) -> None:
        self._profiles: dict[str, HeroBaseProfile] = {}
        for profile in profiles:
            self.register(profile)

    def register(self, profile: HeroBaseProfile) -> None:
        if not isinstance(profile, HeroBaseProfile):
            raise TypeError("profile must be HeroBaseProfile")
        if not profile.authoritative_character_key.strip() or not profile.presentation_asset_key.strip():
            raise ValueError("hero base profile keys must be non-empty")
        if profile.authoritative_character_key in self._profiles:
            raise ValueError(f"duplicate hero base key: {profile.authoritative_character_key}")
        self._profiles[profile.authoritative_character_key] = profile

    def resolve(self, authoritative_character_key: str) -> HeroBaseProfile:
        try:
            return self._profiles[authoritative_character_key]
        except KeyError as exc:
            raise KeyError(f"unknown hero base presentation key: {authoritative_character_key}") from exc

    def keys(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def as_dict(self) -> dict[str, dict[str, str]]:
        return {
            key: {
                "fixture_profile": profile.fixture_profile,
                "presentation_asset_key": profile.presentation_asset_key,
            }
            for key, profile in self._profiles.items()
        }


DEFAULT_HERO_BASE_3D_REGISTRY = HeroBase3DRegistry(
    (
        HeroBaseProfile("A1_BASIC_ADVENTURER", "STANDARD", "P040_A1_HERO_BASE"),
        HeroBaseProfile("A3_MONK", "SMALL", "P040_A3_HERO_BASE"),
        HeroBaseProfile("K1_KNIGHT_01", "LARGE", "P040_K1_HERO_BASE"),
    )
)


COMPANION_AUTHORITY_CONTRACT = MappingProxyType(
    {
        "supply_quantity": "pet_inventory",
        "functional_ownership": "pet_collection.pet_key",
        "active_selection": "user_pets.pet_key",
        "second_ownership_registry_created": False,
    }
)


def companion_authority_contract() -> dict[str, Any]:
    """Return a detached view of the existing companion authority map."""

    return dict(COMPANION_AUTHORITY_CONTRACT)


P040_EQUIPMENT_PRESENTATION_CONTRACT = MappingProxyType(
    {
        "owner_uat": "PASS",
        "sword_presentation_scale": 5.0,
        "shield_presentation_scale": 3.5,
        "shield_original_baseline": 0.3315,
        "shield_world_scale": 1.16025,
        "shield_local_forward_offset": (0.0, 0.0, 0.13),
        "shield_local_forward_direction": "+Z",
    }
)


def presentation_gate_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Read the explicit presentation gate; unset and invalid values are OFF."""

    values = os.environ if environ is None else environ
    value = str(values.get(PRESENTATION_GATE_NAME, "")).strip().lower()
    return value in {"1", "true", "yes", "on"}


class ModelRequestProbe:
    """Small seam for a future loader; it cannot request models while gated off."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ
        self._requests: list[str] = []

    @property
    def count(self) -> int:
        return len(self._requests)

    @property
    def requests(self) -> tuple[str, ...]:
        return tuple(self._requests)

    def request(self, runtime_asset: str, *, loader: Callable[[str], Any] | None = None) -> Any:
        if not presentation_gate_enabled(self._environ):
            return None
        asset = _text(runtime_asset, "runtime_asset")
        self._requests.append(asset)
        return loader(asset) if loader is not None else asset


def model_request_count_when_gate_off() -> int:
    """Probe the kill-switch invariant without importing a model/runtime."""

    probe = ModelRequestProbe({PRESENTATION_GATE_NAME: "false"})
    probe.request("p045://deferred/model.glb")
    return probe.count


__all__ = [
    "COMPANION_AUTHORITY_CONTRACT",
    "DEFAULT_HERO_BASE_3D_REGISTRY",
    "HeroBase3DRegistry",
    "HeroBaseProfile",
    "MANIFEST_SCHEMA_ID",
    "ManifestValidationError",
    "ModelRequestProbe",
    "P040_EQUIPMENT_PRESENTATION_CONTRACT",
    "PRESENTATION_FOUNDATION_CONTRACT",
    "PRESENTATION_GATE_NAME",
    "PresentationIdentity",
    "canonical_manifest_bytes",
    "companion_authority_contract",
    "manifest_external_sha256",
    "model_request_count_when_gate_off",
    "presentation_gate_enabled",
    "validate_manifest",
    "verify_external_admission_hash",
]
