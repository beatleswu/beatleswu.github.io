"""Reusable server-owned Adventure Normal zone authority template.

This module extracts the data-independent part of the E055 Zone 3 slice:
explicit M-ID bindings, deterministic question-to-monster selection, persisted
binding validation, combat-profile construction, and presentation projection.

It deliberately does not import ``app`` or own routes, schema, progression,
Lord state, rewards, Spirit state, or client state. A zone module supplies
content and references the existing settlement registries; later app wiring is
a separate owner-gated change.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Mapping

from monster_combat_profiles import MonsterCombatProfile
from monster_drop_profiles import CANONICAL_DROP_PROFILE_REGISTRY
from monster_profiles import (
    CanonicalMonsterProfile,
    MonsterDropProfile as FoundationDropProfile,
    MonsterPresentationProfile,
    MonsterProfileRegistry,
    MonsterRewardProfile as FoundationRewardProfile,
    MonsterStatProfile,
)
from monster_reward_profiles import CANONICAL_REWARD_PROFILE_REGISTRY


_MONSTER_ID_PATTERN = re.compile(r"^M(\d{3})$")


class AdventureZoneAuthorityError(ValueError):
    """Raised when a server-owned Adventure zone binding is invalid."""


@dataclass(frozen=True)
class AdventureMonsterSpec:
    """One explicit normal-monster content row supplied by a zone module."""

    monster_id: str
    display_name: str
    display_name_en: str
    taxonomy_family: str
    presentation_asset: str


@dataclass(frozen=True)
class AdventureZoneAuthoritySpec:
    """Stable configuration needed to build one normal-only zone."""

    zone_key: str
    display_key: str
    binding_source: str
    binding_version: str
    profile_version: str
    profile_namespace: str
    normal_max_hp: int
    normal_attack: int
    combat_stat_source: str
    combat_compatibility_mode: str
    drop_legacy_type: str
    normal_specs: tuple[AdventureMonsterSpec, ...]


@dataclass(frozen=True)
class AdventureMonsterBinding:
    """Immutable server-owned binding persisted with one Adventure battle."""

    monster_id: str
    roster_slot: int
    zone_key: str
    encounter_class: str
    taxonomy_family: str
    display_name: str
    display_name_en: str
    presentation_asset: str
    profile_id: str
    profile_version: str
    max_hp: int
    attack: int
    drop_profile_id: str
    reward_profile_id: str

    def to_presentation_payload(
        self,
        *,
        hp: int | None = None,
        defeated: bool = False,
    ) -> dict[str, Any]:
        """Project safe render fields without exposing settlement authority."""

        current_hp = self.max_hp if hp is None else max(0, min(self.max_hp, int(hp)))
        return {
            "monster_id": self.monster_id,
            "name": self.display_name,
            "name_en": self.display_name_en,
            "avatar": self.presentation_asset,
            "zone_key": self.zone_key,
            "encounter_class": self.encounter_class,
            "role": "NORMAL",
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "hp": current_hp,
            "max_hp": self.max_hp,
            "defeated": bool(defeated or current_hp == 0),
        }


@dataclass(frozen=True)
class AdventureZoneAuthority:
    """Built authority bundle used by a zone adapter without app imports."""

    spec: AdventureZoneAuthoritySpec
    profile_registry: MonsterProfileRegistry
    bindings: Mapping[str, AdventureMonsterBinding]
    drop_registry: Mapping[str, Any]
    reward_registry: Mapping[str, Any]

    @property
    def binding_count(self) -> int:
        return len(self.bindings)

    def get_binding(self, monster_id: Any) -> AdventureMonsterBinding | None:
        if monster_id in (None, ""):
            return None
        return self.bindings.get(str(monster_id).strip())

    def require_binding(self, monster_id: Any) -> AdventureMonsterBinding:
        binding = self.get_binding(monster_id)
        if binding is None:
            raise AdventureZoneAuthorityError(
                f"unknown Adventure Monster identity for {self.spec.zone_key}"
            )
        return binding

    def select_binding(self, question_id: Any) -> AdventureMonsterBinding:
        """Select deterministically from the explicit server-owned roster."""

        try:
            question_key = str(int(question_id))
        except (TypeError, ValueError) as exc:
            raise AdventureZoneAuthorityError("question identity is invalid") from exc
        if int(question_key) <= 0:
            raise AdventureZoneAuthorityError("question identity is invalid")
        digest = hashlib.sha256(
            f"{self.spec.zone_key}:{question_key}".encode("utf-8")
        ).digest()
        index = int.from_bytes(digest[:4], "big") % self.binding_count
        monster_id = tuple(self.bindings)[index]
        return self.require_binding(monster_id)

    def combat_profile(self, binding: AdventureMonsterBinding) -> MonsterCombatProfile:
        if not isinstance(binding, AdventureMonsterBinding):
            raise AdventureZoneAuthorityError("Adventure binding is invalid")
        if binding.zone_key != self.spec.zone_key:
            raise AdventureZoneAuthorityError("Adventure binding zone is invalid")
        return MonsterCombatProfile(
            canonical_monster_id=binding.monster_id,
            zone_key=binding.zone_key,
            roster_slot=binding.roster_slot,
            encounter_class=binding.encounter_class,
            max_hp=binding.max_hp,
            attack=binding.attack,
            profile_id=binding.profile_id,
            stat_source=self.spec.combat_stat_source,
            compatibility_mode=self.spec.combat_compatibility_mode,
            profile_version=binding.profile_version,
            provenance=(
                ("source", self.spec.binding_source),
                ("monster_id", binding.monster_id),
                ("profile_id", binding.profile_id),
            ),
        )

    def encode_binding(self, binding: AdventureMonsterBinding) -> str:
        if not isinstance(binding, AdventureMonsterBinding):
            raise AdventureZoneAuthorityError("Adventure binding is invalid")
        if binding.zone_key != self.spec.zone_key:
            raise AdventureZoneAuthorityError("Adventure binding zone is invalid")
        return ":".join(
            (
                self.spec.binding_version,
                binding.monster_id,
                binding.profile_id,
                binding.profile_version,
            )
        )

    def decode_binding(self, battle: Mapping[str, Any]) -> AdventureMonsterBinding:
        if str(battle.get("zone_key") or "") != self.spec.zone_key:
            raise AdventureZoneAuthorityError("battle is not this Adventure zone")
        if str(battle.get("migration_source") or "") != self.spec.binding_source:
            raise AdventureZoneAuthorityError("Adventure binding source is missing")
        parts = str(battle.get("migration_version") or "").split(":")
        if len(parts) != 4 or parts[0] != self.spec.binding_version:
            raise AdventureZoneAuthorityError("Adventure binding version is invalid")
        binding = self.require_binding(parts[1])
        if binding.profile_id != parts[2] or binding.profile_version != parts[3]:
            raise AdventureZoneAuthorityError("Adventure profile binding does not match")
        return binding

    def presentation_for_battle(self, battle: Mapping[str, Any]) -> dict[str, Any]:
        binding = self.decode_binding(battle)
        return binding.to_presentation_payload(
            hp=int(battle.get("monster_hp") or 0),
            defeated=(
                str(battle.get("state") or "") == "COMPLETED"
                and int(battle.get("monster_hp") or 0) == 0
            ),
        )


def build_adventure_zone_authority(
    spec: AdventureZoneAuthoritySpec,
) -> AdventureZoneAuthority:
    """Build one explicit normal-only zone against existing settlement refs."""

    if not spec.zone_key or not spec.binding_source or not spec.binding_version:
        raise ValueError("Adventure zone identity metadata is required")
    if not spec.normal_specs:
        raise ValueError("Adventure zone requires at least one normal binding")
    if spec.normal_max_hp <= 0 or spec.normal_attack < 0:
        raise ValueError("Adventure normal combat values are invalid")
    ids = tuple(row.monster_id for row in spec.normal_specs)
    if len(set(ids)) != len(ids):
        raise ValueError("Adventure Monster IDs must be unique")
    for monster_id in ids:
        match = _MONSTER_ID_PATTERN.fullmatch(monster_id)
        if match is None or int(match.group(1)) > 120:
            raise ValueError("Adventure bindings must use existing M001-M120 IDs")
    drop_id = f"drop_legacy_{spec.drop_legacy_type}"
    if drop_id not in CANONICAL_DROP_PROFILE_REGISTRY:
        raise ValueError(f"existing drop profile is unavailable: {drop_id}")
    reward_id = "reward_battlefield_legacy"
    if reward_id not in CANONICAL_REWARD_PROFILE_REGISTRY:
        raise ValueError("existing reward profile is unavailable")

    stat_profiles: dict[str, MonsterStatProfile] = {}
    drop_profiles: dict[str, FoundationDropProfile] = {}
    reward_profiles: dict[str, FoundationRewardProfile] = {}
    presentation_profiles: dict[str, MonsterPresentationProfile] = {}
    profiles: list[CanonicalMonsterProfile] = []
    bindings: dict[str, AdventureMonsterBinding] = {}

    drop_profiles[drop_id] = FoundationDropProfile(
        profile_id=drop_id,
        legacy_monster_type=spec.drop_legacy_type,
        source_ref="monster_drop_profiles.CANONICAL_DROP_PROFILE_REGISTRY",
    )
    reward_profiles[reward_id] = FoundationRewardProfile(
        profile_id=reward_id,
        source_ref="monster_reward_profiles.CANONICAL_REWARD_PROFILE_REGISTRY",
    )

    for roster_slot, row in enumerate(spec.normal_specs, start=1):
        profile_id = f"{spec.profile_namespace}_normal_{row.monster_id}"
        stat_id = f"stat_{profile_id}"
        presentation_id = f"presentation_{profile_id}"
        stat_profiles[stat_id] = MonsterStatProfile(
            profile_id=stat_id,
            max_hp=spec.normal_max_hp,
            attack=spec.normal_attack,
        )
        presentation_profiles[presentation_id] = MonsterPresentationProfile(
            profile_id=presentation_id,
            display_key=f"{spec.display_key}.{row.monster_id}",
            source_ref=f"{spec.binding_source} presentation binding",
        )
        profiles.append(
            CanonicalMonsterProfile(
                monster_id=row.monster_id,
                roster_slot=roster_slot,
                zone_key=spec.zone_key,
                encounter_class="NORMAL",
                taxonomy_family=row.taxonomy_family,
                display_key=f"{spec.display_key}.{row.monster_id}",
                stat_profile_id=stat_id,
                drop_profile_id=drop_id,
                reward_profile_id=reward_id,
                presentation_profile_id=presentation_id,
                enabled=True,
                legacy_aliases=(),
                boss_role=None,
            )
        )
        bindings[row.monster_id] = AdventureMonsterBinding(
            monster_id=row.monster_id,
            roster_slot=roster_slot,
            zone_key=spec.zone_key,
            encounter_class="NORMAL",
            taxonomy_family=row.taxonomy_family,
            display_name=row.display_name,
            display_name_en=row.display_name_en,
            presentation_asset=row.presentation_asset,
            profile_id=profile_id,
            profile_version=spec.profile_version,
            max_hp=spec.normal_max_hp,
            attack=spec.normal_attack,
            drop_profile_id=drop_id,
            reward_profile_id=reward_id,
        )

    registry = MonsterProfileRegistry(
        profiles=tuple(profiles),
        by_id={profile.monster_id: profile for profile in profiles},
        by_roster_slot={profile.roster_slot: profile for profile in profiles},
        stat_profiles=stat_profiles,
        drop_profiles=drop_profiles,
        reward_profiles=reward_profiles,
        presentation_profiles=presentation_profiles,
    )
    return AdventureZoneAuthority(
        spec=spec,
        profile_registry=registry,
        bindings=bindings,
        drop_registry=CANONICAL_DROP_PROFILE_REGISTRY,
        reward_registry=CANONICAL_REWARD_PROFILE_REGISTRY,
    )


__all__ = [
    "AdventureMonsterBinding",
    "AdventureMonsterSpec",
    "AdventureZoneAuthority",
    "AdventureZoneAuthorityError",
    "AdventureZoneAuthoritySpec",
    "build_adventure_zone_authority",
]
