"""Bounded Zone 3 presentation bindings for the Wave 1 asset drop.

This module is a presentation contract, not a second Monster authority.  The
13 Normal rows are derived from ``adventure_zone3_monster_authority`` so the
existing server-owned IDs, profiles, and asset paths remain the source of
truth.  The Battlefield Boss row is an explicit legacy presentation binding
and is kept separate from the Lord identity.

The Goblin Centurion rows are bound to the six exact Owner-approved source
images and separately generated runtime derivatives.  They intentionally
never fall back to an ordinary Monster or Boss asset.  Missing presentation
art therefore affects only presentation availability; it cannot create or
change combat, reward, or progression authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping

from adventure_zone3_monster_authority import (
    ZONE3_KEY,
    ZONE3_LORD_CLASSIFICATION,
    ZONE3_LORD_ID,
    ZONE3_MONSTER_PROFILE_REGISTRY,
    ZONE3_NORMAL_IDS,
    get_zone3_binding,
)


PRESENTATION_FALLBACK_HIDE: Final = "HIDE_UNAVAILABLE_SAME_IDENTITY"
CURRENT_CANONICAL: Final = "CURRENT_CANONICAL"
PENDING_OWNER_ART: Final = "PENDING_OWNER_ART"
LORD_STYLE: Final = "B — STYLIZED_ADVENTURE"
OWNER_PACKAGE_SHA256: Final = (
    "7d57988635b20339f877817375f41260bd7aa6480aa2b3a6110a09ceb88e0b43"
)


@dataclass(frozen=True, slots=True)
class Zone3NormalMonsterPresentationBinding:
    """A read-only presentation projection of one existing Normal binding."""

    monster_id: str
    presentation_id: str
    zone_key: str
    encounter_class: str
    runtime_asset_path: str
    source_profile_id: str
    asset_status: str
    reuse_as_is: bool = True
    redraw_required: bool = False
    fallback_policy: str = PRESENTATION_FALLBACK_HIDE
    gameplay_authority: bool = False

def _build_normal_presentation_bindings() -> tuple[
    Zone3NormalMonsterPresentationBinding, ...
]:
    rows: list[Zone3NormalMonsterPresentationBinding] = []
    for monster_id in ZONE3_NORMAL_IDS:
        binding = get_zone3_binding(monster_id)
        profile = ZONE3_MONSTER_PROFILE_REGISTRY.by_id.get(monster_id)
        if binding is None or profile is None:
            raise RuntimeError(
                f"Zone 3 presentation binding has no canonical source: {monster_id}"
            )
        rows.append(
            Zone3NormalMonsterPresentationBinding(
                monster_id=binding.monster_id,
                presentation_id=profile.presentation_profile_id,
                zone_key=binding.zone_key,
                encounter_class=binding.encounter_class,
                runtime_asset_path=binding.presentation_asset,
                source_profile_id=binding.profile_id,
                asset_status=CURRENT_CANONICAL,
            )
        )
    return tuple(rows)


ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS: Final[
    tuple[Zone3NormalMonsterPresentationBinding, ...]
] = _build_normal_presentation_bindings()
ZONE3_NORMAL_MONSTER_PRESENTATION_BY_ID: Final[
    Mapping[str, Zone3NormalMonsterPresentationBinding]
] = MappingProxyType({row.monster_id: row for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS})
ZONE3_ELITE_COUNT: Final = 0


@dataclass(frozen=True, slots=True)
class Zone3BattlefieldBossPresentationBinding:
    """The current Zone 3 Battlefield Boss presentation, not a Lord."""

    presentation_id: str
    runtime_id: str
    identity_zh: str
    identity_en: str
    zone_key: str
    encounter_class: str
    runtime_asset_path: str
    asset_status: str
    distinct_from_lord: bool = True
    fallback_policy: str = PRESENTATION_FALLBACK_HIDE
    gameplay_authority: bool = False


ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID: Final = "legacy_bf_03_boss"
ZONE3_BATTLEFIELD_BOSS_ASSET: Final = "/assets/monsters/orc_shield_chibi.png"
ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING: Final = (
    Zone3BattlefieldBossPresentationBinding(
        presentation_id=ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID,
        runtime_id=ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID,
        identity_zh="LV3 做眼厚壁兵",
        identity_en="LV3 Eye-Shape Shield Guard",
        zone_key=ZONE3_KEY,
        encounter_class="BATTLEFIELD_BOSS",
        runtime_asset_path=ZONE3_BATTLEFIELD_BOSS_ASSET,
        asset_status=CURRENT_CANONICAL,
    )
)


@dataclass(frozen=True, slots=True)
class Zone3LordPresentationAssetSlot:
    """One Owner-approved Goblin Centurion presentation asset binding."""

    slot_id: str
    lord_id: str
    role: str
    subject: str
    pose: str
    silhouette: str
    style: str
    transparent_background: bool
    master_dimensions: tuple[int, int]
    runtime_dimensions: tuple[int, int]
    world_placement_contract: str
    expected_runtime_path: str
    source_path: str
    source_sha256: str
    source_dimensions: tuple[int, int]
    runtime_sha256: str
    owner_approved: bool

    @property
    def runtime_path(self) -> str:
        """Expose the manifest's runtime path without removing the prep name."""

        return self.expected_runtime_path

    master_format: str = "PNG_OR_JPEG"
    runtime_format: str = "WEBP"
    asset_status: str = PENDING_OWNER_ART
    present: bool = False
    pending: bool = True
    placeholder: bool = False
    fallback_policy: str = PRESENTATION_FALLBACK_HIDE
    gameplay_authority: bool = False


_LORD_SUBJECT: Final = (
    "Goblin Centurion / 哥布林百夫長; grounded Goblin Cave commander; "
    "angular ears, centurion crest, shoulder/faction cave gear, asymmetrical "
    "read; child-safe, no gore"
)
_LORD_SILHOUETTE: Final = (
    "Compact goblin biped with a readable crest-and-shoulder command shape; "
    "must not match or reuse an M-ID Monster silhouette"
)
_LORD_STYLE_CONTRACT: Final = (
    f"{LORD_STYLE}; polished high-detail fantasy RPG; limestone, ore, fungus, "
    "and lantern-amber cave materials; no baked text, UI, route, stats, or CTA"
)


def _lord_slot(
    *,
    slot_id: str,
    role: str,
    filename: str,
    master_dimensions: tuple[int, int],
    pose: str,
    world_placement_contract: str,
    source_sha256: str,
    runtime_sha256: str,
) -> Zone3LordPresentationAssetSlot:
    source_path = f"/assets/e10/art/zone3/lord_trial/{filename}.png"
    runtime_path = f"/assets/e10/art/zone3/lord_trial/{filename}.webp"
    return Zone3LordPresentationAssetSlot(
        slot_id=slot_id,
        lord_id=ZONE3_LORD_ID,
        role=role,
        subject=_LORD_SUBJECT,
        pose=pose,
        silhouette=_LORD_SILHOUETTE,
        style=_LORD_STYLE_CONTRACT,
        transparent_background=False,
        master_dimensions=master_dimensions,
        runtime_dimensions=master_dimensions,
        world_placement_contract=world_placement_contract,
        expected_runtime_path=runtime_path,
        source_path=source_path,
        source_sha256=source_sha256,
        source_dimensions=master_dimensions,
        runtime_sha256=runtime_sha256,
        owner_approved=True,
        master_format="PNG",
        asset_status="OWNER_APPROVED_PRESENT",
        present=True,
        pending=False,
    )


ZONE3_LORD_PRESENTATION_SLOTS: Final[tuple[Zone3LordPresentationAssetSlot, ...]] = (
    _lord_slot(
        slot_id="Z3_LORD_RITUAL_KEY_ART",
        role="LORD_RITUAL_KEY_ART",
        filename="zone3_lord_01_ritual_key_art",
        master_dimensions=(1448, 1086),
        pose="Grounded three-quarter command stance at the cave threshold, ritual-ready.",
        world_placement_contract=(
            "Full-bleed Lord approach/ritual visual; Go stones, effects, labels, "
            "and route state remain DOM/runtime layers."
        ),
        source_sha256="fa98c1fc2ccc351c37958a99e71da7f037bf967e8b4f948580a57424f0f314ee",
        runtime_sha256="0cadd81786f9fc76d2555917aca28bffd48326fd76298521e15dddac23cff423",
    ),
    _lord_slot(
        slot_id="Z3_LORD_CHALLENGE_BACKPLATE",
        role="LORD_CHALLENGE_BACKPLATE",
        filename="zone3_lord_02_challenge_backplate",
        master_dimensions=(1024, 1536),
        pose="Three-quarter challenge-facing command stance with crest unobscured.",
        world_placement_contract=(
            "Full-bleed Lord Challenge Card backplate in the existing boss-cinematic "
            "surface; identity, stats, and CTA remain DOM/runtime layers."
        ),
        source_sha256="ea7d18554be39c956f374f7802006d1b4ffa2cb2958e661e8ebe3efc627c3704",
        runtime_sha256="8c465f2f24a8adb15b81b40d2da5ce6bf16b5b73596ca9b4aa12d86163eee2d3",
    ),
    _lord_slot(
        slot_id="Z3_LORD_FAILURE_BACKPLATE",
        role="LORD_FAILURE_BACKPLATE",
        filename="zone3_lord_03_failure_backplate",
        master_dimensions=(1024, 1536),
        pose="Low, nonlethal retraining reaction; same face and crest identity.",
        world_placement_contract=(
            "Full-bleed failure/retraining result surface; result copy and CTA "
            "remain DOM/runtime layers."
        ),
        source_sha256="9749b28e968e748adf578b32e5a5ff629deb69d1cbdb5321a69869f4dbad1c56",
        runtime_sha256="73e5760c120f0c3bc0a4b720b7fbc096c6c1abb3d0d1c29a64c52b2d8f4aed0c",
    ),
    _lord_slot(
        slot_id="Z3_FIRST_STAR_SUCCESS_BACKPLATE",
        role="FIRST_STAR_SUCCESS_BACKPLATE",
        filename="zone3_lord_04_first_star_success_backplate",
        master_dimensions=(1086, 1448),
        pose="Relaxed three-quarter acknowledgement/recovery stance; crest remains legible.",
        world_placement_contract=(
            "Full-bleed success/recovery/reward result surface; stars, rewards, "
            "and route state remain DOM/server layers."
        ),
        source_sha256="30aded5b2adf5cf113b72d14fe111a91e16295ea58f5314ef8fba79b72133be5",
        runtime_sha256="4cd9570539bf9253da800031c78465f90f18119db85654ced2375a181a15898f",
    ),
    _lord_slot(
        slot_id="Z3_LORD_PORTRAIT",
        role="LORD_PORTRAIT",
        filename="zone3_lord_05_lord_portrait",
        master_dimensions=(1254, 1254),
        pose="Chest-up three-quarter command portrait; eyes and centurion crest forward.",
        world_placement_contract=(
            "Challenge-card focal portrait; head and crest must remain inside the "
            "safe crop and never resolve to a generic Monster panel."
        ),
        source_sha256="cbcdda5c6c51f7f0d664710bd5ef15cd28601f6046c585670fcee753c9b1ce8c",
        runtime_sha256="18f157d094d3f5bf5807400def5738f43cefa3a5db1b443c71ed18c83edbe35e",
    ),
    _lord_slot(
        slot_id="Z3_SUCCESS_LORD_PORTRAIT",
        role="SUCCESS_LORD_PORTRAIT",
        filename="zone3_lord_06_success_lord_portrait",
        master_dimensions=(1254, 1254),
        pose="Chest-up to waist-up three-quarter calm acknowledgement portrait.",
        world_placement_contract=(
            "Success-card focal portrait paired with the success backplate; reward "
            "and route state remain DOM/server layers."
        ),
        source_sha256="759dbcc871bf551d5ba63bbfbefad730d5be6293c7d4df57f37781613c40368a",
        runtime_sha256="13b4437bd72de85d51ba377264cdb8a11bac40b8e21d3e475cb511b4f19e7827",
    ),
)
ZONE3_LORD_PRESENTATION_SLOT_BY_ID: Final[
    Mapping[str, Zone3LordPresentationAssetSlot]
] = MappingProxyType({slot.slot_id: slot for slot in ZONE3_LORD_PRESENTATION_SLOTS})
ZONE3_LORD_ASSET_SLOT_COUNT: Final = len(ZONE3_LORD_PRESENTATION_SLOTS)


@dataclass(frozen=True, slots=True)
class Zone3LordPresentationResolution:
    """Safe resolution result for a Lord image lookup."""

    slot_id: str
    lord_id: str
    available: bool
    runtime_asset_path: str | None
    fallback_policy: str | None
    gameplay_authority: bool = False

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "slot_id": self.slot_id,
            "lord_id": self.lord_id,
            "available": self.available,
            "gameplay_authority": self.gameplay_authority,
        }
        if self.runtime_asset_path is not None:
            payload["runtime_asset_path"] = self.runtime_asset_path
        if self.fallback_policy is not None:
            payload["fallback_policy"] = self.fallback_policy
        return payload


def resolve_zone3_lord_presentation(
    slot_id: str,
    *,
    asset_present: bool | None = None,
) -> Zone3LordPresentationResolution:
    """Resolve a Lord slot without substituting an ordinary Monster asset.

    ``asset_present`` is supplied only after an Owner asset has been ingested
    and verified.  Until then the immutable slot remains pending.  An absent
    image returns an unavailable same-identity result and no combat fields.
    """

    try:
        slot = ZONE3_LORD_PRESENTATION_SLOT_BY_ID[slot_id]
    except KeyError as exc:
        raise KeyError(f"unknown Zone 3 Lord presentation slot: {slot_id}") from exc

    available = slot.present if asset_present is None else bool(asset_present)
    return Zone3LordPresentationResolution(
        slot_id=slot.slot_id,
        lord_id=slot.lord_id,
        available=available,
        runtime_asset_path=slot.expected_runtime_path if available else None,
        fallback_policy=None if available else slot.fallback_policy,
    )


def _validate_contract() -> None:
    """Fail fast if this presentation contract drifts from current authority."""

    bound_ids = tuple(row.monster_id for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS)
    if bound_ids != ZONE3_NORMAL_IDS or len(set(bound_ids)) != 13:
        raise RuntimeError("Zone 3 normal presentation IDs are not the exact approved set")
    if any(row.encounter_class != "NORMAL" for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS):
        raise RuntimeError("Zone 3 presentation contract promoted a Normal Monster")
    if any(
        not row.reuse_as_is or row.redraw_required
        for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS
    ):
        raise RuntimeError("Zone 3 Normal art drifted from the approved reuse-as-is set")
    if ZONE3_LORD_ID in bound_ids:
        raise RuntimeError("Zone 3 Lord was conflated with a Normal Monster")
    if ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID == ZONE3_LORD_ID:
        raise RuntimeError("Zone 3 Battlefield Boss was conflated with the Lord")
    if ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING.encounter_class != "BATTLEFIELD_BOSS":
        raise RuntimeError("Zone 3 Battlefield Boss class drifted")
    if ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING.runtime_asset_path in {
        row.runtime_asset_path for row in ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS
    }:
        raise RuntimeError("Zone 3 Battlefield Boss asset was reused as a Normal asset")
    slot_ids = tuple(slot.slot_id for slot in ZONE3_LORD_PRESENTATION_SLOTS)
    if len(slot_ids) != 6 or len(set(slot_ids)) != 6:
        raise RuntimeError("Zone 3 Lord presentation slots are not exactly six unique slots")
    if any(
        slot.lord_id != ZONE3_LORD_ID
        or slot.asset_status != "OWNER_APPROVED_PRESENT"
        or not slot.owner_approved
        or not slot.present
        or slot.pending
        or slot.placeholder
        or slot.gameplay_authority
        or not slot.source_path.endswith(".png")
        or not slot.expected_runtime_path.endswith(".webp")
        or not slot.source_sha256
        or not slot.runtime_sha256
        or slot.expected_runtime_path.startswith(("/art/monsters/", "/assets/monsters/"))
        for slot in ZONE3_LORD_PRESENTATION_SLOTS
    ):
        raise RuntimeError("Zone 3 Lord slots contain invalid provenance, fallback, or authority")
    if {
        slot.slot_id for slot in ZONE3_LORD_PRESENTATION_SLOTS
        if slot.slot_id in {"Z3_LORD_PORTRAIT", "Z3_SUCCESS_LORD_PORTRAIT"}
    } != {"Z3_LORD_PORTRAIT", "Z3_SUCCESS_LORD_PORTRAIT"}:
        raise RuntimeError("Zone 3 Lord portrait slots are incomplete")
    portraits = {
        slot.slot_id: slot.expected_runtime_path
        for slot in ZONE3_LORD_PRESENTATION_SLOTS
        if slot.slot_id in {"Z3_LORD_PORTRAIT", "Z3_SUCCESS_LORD_PORTRAIT"}
    }
    if portraits["Z3_LORD_PORTRAIT"] == portraits["Z3_SUCCESS_LORD_PORTRAIT"]:
        raise RuntimeError("Zone 3 pre-trial and success portraits must remain distinct")
    if ZONE3_LORD_CLASSIFICATION != "LORD_ONLY":
        raise RuntimeError("Zone 3 Lord classification drifted")


_validate_contract()


__all__ = [
    "CURRENT_CANONICAL",
    "OWNER_PACKAGE_SHA256",
    "PENDING_OWNER_ART",
    "PRESENTATION_FALLBACK_HIDE",
    "Zone3BattlefieldBossPresentationBinding",
    "Zone3LordPresentationAssetSlot",
    "Zone3LordPresentationResolution",
    "Zone3NormalMonsterPresentationBinding",
    "ZONE3_BATTLEFIELD_BOSS_ASSET",
    "ZONE3_BATTLEFIELD_BOSS_PRESENTATION_BINDING",
    "ZONE3_BATTLEFIELD_BOSS_RUNTIME_ID",
    "ZONE3_ELITE_COUNT",
    "ZONE3_LORD_ASSET_SLOT_COUNT",
    "ZONE3_LORD_PRESENTATION_SLOT_BY_ID",
    "ZONE3_LORD_PRESENTATION_SLOTS",
    "ZONE3_NORMAL_MONSTER_PRESENTATION_BINDINGS",
    "ZONE3_NORMAL_MONSTER_PRESENTATION_BY_ID",
    "resolve_zone3_lord_presentation",
]
