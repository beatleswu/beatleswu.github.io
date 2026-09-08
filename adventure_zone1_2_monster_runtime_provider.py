"""Owner-approved exact Adventure Monster authority for Zones 1 and 2.

This module is a bounded source-authority provider under the existing shared
Adventure Monster runtime contract.  It records the exact 28-row Owner
decision and supplies immutable server-side bindings for future integration.
It deliberately does not register a live caller, retire legacy paths, settle
rewards, or infer taxonomy from names or art.

Reward and drop policy are explicitly deferred.  The shared binding therefore
keeps both policy references nullable instead of promoting legacy battlefield
values or inventing a placeholder policy.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from adventure_monster_runtime_contract import (
    AdventureMonsterRuntimeBinding,
    AdventureQuestionBinding,
    MissingBindingError,
    MissingZoneError,
    ProfileBindingMismatchError,
    ProviderConfigurationError,
    ProviderDisabledError,
    StaleQuestionBindingError,
    WrongZoneBindingError,
    validate_runtime_binding,
)
from monster_combat_profiles import MonsterCombatProfile


ZONE1_2_KEYS: tuple[str, ...] = ("Z1", "Z2")
ZONE1_2_PROVIDER_ID: Final = "canonical-adventure-zone1-2-provider"
ZONE1_2_BINDING_SOURCE: Final = "OWNER_Z1_Z2_EXACT_28_ROW_AUTHORITY"
ZONE1_2_BINDING_VERSION: Final = "w2.z1_z2.provider.v1"
ZONE1_2_PERSISTENCE_VERSION: Final = "w2.z1_z2.binding.v1"
ZONE1_2_PROFILE_VERSION: Final = "w2.z1_z2.profile.v1"
DEFERRED_REWARD_DROP_POLICY: Final = "DEFER_Z1_Z2_REWARD_DROP_POLICY"


ZONE1_2_MONSTER_IDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "Z1": (
            "M001",
            "M002",
            "M003",
            "M004",
            "M005",
            "M006",
            "M007",
            "M008",
            "M009",
            "M010",
            "M100",
            "M105",
            "M107",
            "M110",
        ),
        "Z2": (
            "M011",
            "M012",
            "M013",
            "M014",
            "M015",
            "M016",
            "M017",
            "M018",
            "M019",
            "M020",
            "M021",
            "M088",
            "M091",
            "M094",
        ),
    }
)


_APPROVED_CLASS_ROSTER: Mapping[str, Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "Z1": MappingProxyType(
            {
                "NORMAL": (
                    "M001",
                    "M002",
                    "M003",
                    "M004",
                    "M005",
                    "M006",
                    "M007",
                    "M008",
                    "M009",
                    "M010",
                ),
                "ELITE": ("M100", "M105", "M107"),
                "BOSS": ("M110",),
            }
        ),
        "Z2": MappingProxyType(
            {
                "NORMAL": (
                    "M011",
                    "M012",
                    "M013",
                    "M014",
                    "M015",
                    "M016",
                    "M017",
                    "M018",
                    "M019",
                ),
                "ELITE": ("M020", "M021", "M088", "M091"),
                "BOSS": ("M094",),
            }
        ),
    }
)


@dataclass(frozen=True, slots=True)
class Zone1_2ExactProfileValues:
    """One exact Owner-approved zone/class combat value pair."""

    max_hp: int
    attack: int


_PROFILE_VALUES: Mapping[str, Mapping[str, Zone1_2ExactProfileValues]] = MappingProxyType(
    {
        "Z1": MappingProxyType(
            {
                "NORMAL": Zone1_2ExactProfileValues(60, 5),
                "ELITE": Zone1_2ExactProfileValues(78, 6),
                "BOSS": Zone1_2ExactProfileValues(96, 7),
            }
        ),
        "Z2": MappingProxyType(
            {
                "NORMAL": Zone1_2ExactProfileValues(80, 6),
                "ELITE": Zone1_2ExactProfileValues(104, 8),
                "BOSS": Zone1_2ExactProfileValues(128, 9),
            }
        ),
    }
)


@dataclass(frozen=True, slots=True)
class Zone1_2MonsterProfileAuthority:
    """Complete source-authority record for one approved Monster row."""

    monster_id: str
    zone_key: str
    roster_slot: int
    encounter_class: str
    max_hp: int
    attack: int
    profile_id: str
    profile_version: str
    family_id: str | None
    taxonomy_status: str
    reward_drop_policy: str
    server_enabled: bool

    def combat_profile(self) -> MonsterCombatProfile:
        return MonsterCombatProfile(
            canonical_monster_id=self.monster_id,
            zone_key=self.zone_key,
            roster_slot=self.roster_slot,
            encounter_class=self.encounter_class,
            max_hp=self.max_hp,
            attack=self.attack,
            profile_id=self.profile_id,
            stat_source="OWNER_APPROVED_Z1_Z2_EXACT",
            compatibility_mode="ADVENTURE_ZONE1_2_EXACT_PROFILE",
            profile_version=self.profile_version,
            provenance=(
                ("source", ZONE1_2_BINDING_SOURCE),
                ("taxonomy_status", self.taxonomy_status),
                ("reward_drop_policy", self.reward_drop_policy),
            ),
        )


def _build_class_by_id() -> Mapping[str, str]:
    result: dict[str, str] = {}
    for zone_key, classes in _APPROVED_CLASS_ROSTER.items():
        if zone_key not in ZONE1_2_KEYS:
            raise ProviderConfigurationError("class roster contains an unknown zone")
        for encounter_class, monster_ids in classes.items():
            for monster_id in monster_ids:
                if monster_id in result:
                    raise ProviderConfigurationError(
                        f"duplicate approved class assignment: {monster_id}"
                    )
                result[monster_id] = encounter_class
    canonical_ids = {
        monster_id
        for zone_key in ZONE1_2_KEYS
        for monster_id in ZONE1_2_MONSTER_IDS[zone_key]
    }
    if set(result) != canonical_ids or len(result) != 28:
        raise ProviderConfigurationError(
            "approved Zone1-2 class roster does not exactly cover 28 rows"
        )
    return MappingProxyType(result)


def _build_roster_slots() -> Mapping[str, int]:
    result: dict[str, int] = {}
    for zone_key in ZONE1_2_KEYS:
        for roster_slot, monster_id in enumerate(
            ZONE1_2_MONSTER_IDS[zone_key],
            start=1,
        ):
            if monster_id in result:
                raise ProviderConfigurationError(
                    f"duplicate Zone1-2 roster identity: {monster_id}"
                )
            result[monster_id] = roster_slot
    if len(result) != 28:
        raise ProviderConfigurationError("Zone1-2 roster slot coverage is not 28")
    return MappingProxyType(result)


_CLASS_BY_ID = _build_class_by_id()
_ROSTER_SLOT_BY_ID = _build_roster_slots()


def _profile_id(monster_id: str, zone_key: str, encounter_class: str) -> str:
    return f"adventure_{zone_key.lower()}_{encounter_class.lower()}_{monster_id}"


def _build_profile_records() -> tuple[Zone1_2MonsterProfileAuthority, ...]:
    records: list[Zone1_2MonsterProfileAuthority] = []
    profile_ids: set[str] = set()
    for zone_key in ZONE1_2_KEYS:
        for monster_id in ZONE1_2_MONSTER_IDS[zone_key]:
            encounter_class = _CLASS_BY_ID[monster_id]
            values = _PROFILE_VALUES[zone_key][encounter_class]
            profile_id = _profile_id(monster_id, zone_key, encounter_class)
            if profile_id in profile_ids:
                raise ProviderConfigurationError(f"duplicate profile id: {profile_id}")
            profile_ids.add(profile_id)
            records.append(
                Zone1_2MonsterProfileAuthority(
                    monster_id=monster_id,
                    zone_key=zone_key,
                    roster_slot=_ROSTER_SLOT_BY_ID[monster_id],
                    encounter_class=encounter_class,
                    max_hp=values.max_hp,
                    attack=values.attack,
                    profile_id=profile_id,
                    profile_version=ZONE1_2_PROFILE_VERSION,
                    family_id=None,
                    taxonomy_status="DEFER_TAXONOMY",
                    reward_drop_policy=DEFERRED_REWARD_DROP_POLICY,
                    server_enabled=True,
                )
            )
    if len(records) != 28 or len(profile_ids) != 28:
        raise ProviderConfigurationError("Zone1-2 exact profile coverage is not 28")
    return tuple(records)


ZONE1_2_MONSTER_PROFILE_RECORDS = _build_profile_records()
ZONE1_2_MONSTER_PROFILE_BY_ID: Mapping[str, Zone1_2MonsterProfileAuthority] = MappingProxyType(
    {record.monster_id: record for record in ZONE1_2_MONSTER_PROFILE_RECORDS}
)


def get_zone1_2_monster_profile(
    monster_id: object,
) -> Zone1_2MonsterProfileAuthority | None:
    normalized = str(monster_id).strip() if monster_id not in (None, "") else ""
    return ZONE1_2_MONSTER_PROFILE_BY_ID.get(normalized)


def require_zone1_2_monster_profile(
    monster_id: object,
) -> Zone1_2MonsterProfileAuthority:
    profile = get_zone1_2_monster_profile(monster_id)
    if profile is None:
        raise MissingBindingError("unknown Zone1-2 Monster profile")
    return profile


def iter_zone1_2_monster_profiles() -> tuple[Zone1_2MonsterProfileAuthority, ...]:
    return ZONE1_2_MONSTER_PROFILE_RECORDS


def _question_binding(
    value: AdventureQuestionBinding | Mapping[str, Any],
) -> AdventureQuestionBinding:
    if isinstance(value, AdventureQuestionBinding):
        question_id = value.question_id
        question_revision = value.question_revision
    elif isinstance(value, Mapping):
        question_id = value.get("question_id", value.get("id"))
        question_revision = value.get("question_revision")
        if question_revision is None:
            question_revision = value.get("content_revision", value.get("content_sha256"))
    else:
        raise StaleQuestionBindingError("question binding must be an object")
    try:
        normalized_id = int(str(question_id).strip())
    except (TypeError, ValueError) as error:
        raise StaleQuestionBindingError("question identity is invalid") from error
    if normalized_id <= 0:
        raise StaleQuestionBindingError("question identity is invalid")
    if not isinstance(question_revision, str) or not question_revision.strip():
        raise StaleQuestionBindingError("question revision is required")
    return AdventureQuestionBinding(normalized_id, question_revision.strip())


def _required_zone(zone_key: object) -> str:
    if not isinstance(zone_key, str) or not zone_key.strip():
        raise MissingZoneError("Zone1-2 provider zone is required")
    normalized = zone_key.strip()
    if normalized not in ZONE1_2_KEYS:
        raise WrongZoneBindingError("Zone1-2 provider does not own this zone")
    return normalized


def _select_profile_for_question(
    zone_key: str,
    question_binding: AdventureQuestionBinding,
) -> Zone1_2MonsterProfileAuthority:
    monster_ids = ZONE1_2_MONSTER_IDS[zone_key]
    digest = hashlib.sha256(
        f"{zone_key}:{question_binding.question_id}".encode("utf-8")
    ).digest()
    bucket = int.from_bytes(digest[:4], "big") % len(monster_ids)
    return require_zone1_2_monster_profile(monster_ids[bucket])


def select_zone1_2_monster_profile(
    zone_key: object,
    question_id: object,
) -> Zone1_2MonsterProfileAuthority:
    """Select one exact server-owned profile from a question identity."""

    zone = _required_zone(zone_key)
    question = _question_binding(
        AdventureQuestionBinding(
            question_id=question_id,
            question_revision="selection-only",
        )
    )
    return _select_profile_for_question(zone, question)


def _persistence_version(profile: Zone1_2MonsterProfileAuthority) -> str:
    return ":".join(
        (
            ZONE1_2_PERSISTENCE_VERSION,
            profile.zone_key,
            profile.monster_id,
            profile.profile_id,
            profile.profile_version,
        )
    )


def _binding_for_profile(
    profile: Zone1_2MonsterProfileAuthority,
    question_binding: AdventureQuestionBinding,
) -> AdventureMonsterRuntimeBinding:
    return AdventureMonsterRuntimeBinding(
        provider_id=ZONE1_2_PROVIDER_ID,
        zone_key=profile.zone_key,
        monster_id=profile.monster_id,
        roster_slot=profile.roster_slot,
        encounter_class=profile.encounter_class,
        family_id=None,
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        max_hp=profile.max_hp,
        combat_profile=profile.combat_profile(),
        question_binding=question_binding,
        binding_source=ZONE1_2_BINDING_SOURCE,
        binding_version=ZONE1_2_BINDING_VERSION,
        persistence_source=ZONE1_2_BINDING_SOURCE,
        persistence_version=_persistence_version(profile),
        drop_profile_id=None,
        reward_profile_id=None,
        server_enabled=True,
        enabled=True,
    )


class AdventureZone1_2MonsterRuntimeProvider:
    """One exact Zone1/2 provider under the shared runtime contract."""

    runtime_role = "canonical_zone1_2_provider"

    def __init__(self, *, enabled: bool = True) -> None:
        if not isinstance(enabled, bool):
            raise ProviderConfigurationError("provider enabled state must be boolean")
        self.provider_id = ZONE1_2_PROVIDER_ID
        self.supported_zone_keys = frozenset(ZONE1_2_KEYS)
        self.enabled = enabled

    def supports_zone(self, zone_id: str) -> bool:
        return isinstance(zone_id, str) and zone_id in self.supported_zone_keys

    def _require_enabled(self) -> None:
        if self.enabled is not True:
            raise ProviderDisabledError(
                f"Zone1-2 Adventure provider is disabled: {self.provider_id}"
            )

    def bind_new_battle(
        self,
        user_id: int | None,
        zone_id: str,
        question: AdventureQuestionBinding | Mapping[str, Any],
        eligibility: Mapping[str, Any] | None = None,
    ) -> AdventureMonsterRuntimeBinding:
        """Create a server-owned binding; client identity claims are ignored."""

        self._require_enabled()
        if user_id is not None:
            try:
                if int(user_id) <= 0:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise ProviderConfigurationError("user_id is invalid") from error
        _ = eligibility
        zone_key = _required_zone(zone_id)
        question_binding = _question_binding(question)
        profile = _select_profile_for_question(zone_key, question_binding)
        return _binding_for_profile(profile, question_binding)

    def restore_binding(
        self,
        battle: Mapping[str, Any],
        attempt: AdventureQuestionBinding | Mapping[str, Any],
    ) -> AdventureMonsterRuntimeBinding:
        """Restore the persisted Monster identity without rerolling it."""

        self._require_enabled()
        if not isinstance(battle, Mapping):
            raise MissingBindingError("persisted battle binding is not an object")
        zone_key = _required_zone(battle.get("zone_key", battle.get("zone_id")))
        if battle.get("migration_source") != ZONE1_2_BINDING_SOURCE:
            raise MissingBindingError("Zone1-2 persistence source is missing")
        token = str(battle.get("migration_version") or "")
        parts = token.split(":")
        if len(parts) != 5 or parts[0] != ZONE1_2_PERSISTENCE_VERSION:
            raise MissingBindingError("Zone1-2 persistence version is invalid")
        if parts[1] != zone_key:
            raise WrongZoneBindingError("persisted profile belongs to another zone")
        profile = require_zone1_2_monster_profile(parts[2])
        if profile.zone_key != zone_key:
            raise WrongZoneBindingError("persisted M-ID belongs to another zone")
        if parts[3] != profile.profile_id or parts[4] != profile.profile_version:
            raise ProfileBindingMismatchError("persisted profile identity is inconsistent")

        question_binding = _question_binding(attempt)
        persisted_question_fields = {
            key: battle[key]
            for key in ("question_id", "question_revision")
            if key in battle
        }
        if persisted_question_fields:
            if set(persisted_question_fields) != {"question_id", "question_revision"}:
                raise StaleQuestionBindingError(
                    "persisted question binding is incomplete"
                )
            persisted_question = _question_binding(persisted_question_fields)
            if persisted_question != question_binding:
                raise StaleQuestionBindingError("persisted question binding is stale")

        binding = _binding_for_profile(profile, question_binding)
        if battle.get("profile_id") not in (None, "", binding.profile_id):
            raise ProfileBindingMismatchError("persisted profile_id does not match")
        if battle.get("profile_version") not in (None, "", binding.profile_version):
            raise ProfileBindingMismatchError("persisted profile_version does not match")
        if battle.get("monster_hp_max") not in (None, ""):
            try:
                if int(battle["monster_hp_max"]) != binding.max_hp:
                    raise ValueError
            except (TypeError, ValueError) as error:
                raise ProfileBindingMismatchError(
                    "persisted Monster max_hp does not match"
                ) from error
        return validate_runtime_binding(
            binding,
            expected_zone_key=zone_key,
            expected_question_binding=question_binding,
            expected_provider_id=self.provider_id,
            battle=battle,
        )

    def presentation_payload(
        self,
        binding: AdventureMonsterRuntimeBinding,
        battle: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Expose presentation data without creating gameplay authority."""

        self._require_enabled()
        validate_runtime_binding(
            binding,
            expected_zone_key=binding.zone_key,
            expected_question_binding=binding.question_binding,
            expected_provider_id=self.provider_id,
            battle=battle,
        )
        monster_hp = None
        defeated = False
        if battle is not None:
            monster_hp = int(battle.get("monster_hp") or 0)
            defeated = str(battle.get("state") or "") == "COMPLETED" and monster_hp == 0
        return {
            "provider_id": self.provider_id,
            "monster_id": binding.monster_id,
            "zone_key": binding.zone_key,
            "encounter_class": binding.encounter_class,
            "profile_id": binding.profile_id,
            "profile_version": binding.profile_version,
            "max_hp": binding.max_hp,
            "attack": binding.combat_profile.attack,
            "family_id": None,
            "server_enabled": True,
            "monster_hp": monster_hp,
            "monster_hp_max": binding.max_hp,
            "defeated": defeated,
        }

    def reward_policy_for(self, monster_id: object) -> None:
        """Return no policy until the separately governed decision exists."""

        if get_zone1_2_monster_profile(monster_id) is None:
            return None
        return None

    def resolve_binding(
        self,
        *,
        zone_key: str,
        question_binding: AdventureQuestionBinding,
        battle: Mapping[str, Any] | None = None,
        user_id: int | None = None,
    ) -> AdventureMonsterRuntimeBinding:
        """Implement the shared protocol without any legacy fallback."""

        if battle is None:
            return self.bind_new_battle(user_id, zone_key, question_binding, None)
        return self.restore_binding(battle, question_binding)

    def bind(self, **kwargs: Any) -> AdventureMonsterRuntimeBinding:
        return self.resolve_binding(**kwargs)


ZONE1_2_MONSTER_RUNTIME_PROVIDER = AdventureZone1_2MonsterRuntimeProvider()


__all__ = [
    "AdventureZone1_2MonsterRuntimeProvider",
    "DEFERRED_REWARD_DROP_POLICY",
    "ZONE1_2_BINDING_SOURCE",
    "ZONE1_2_BINDING_VERSION",
    "ZONE1_2_KEYS",
    "ZONE1_2_MONSTER_IDS",
    "ZONE1_2_MONSTER_PROFILE_BY_ID",
    "ZONE1_2_MONSTER_PROFILE_RECORDS",
    "ZONE1_2_MONSTER_RUNTIME_PROVIDER",
    "ZONE1_2_PERSISTENCE_VERSION",
    "ZONE1_2_PROFILE_VERSION",
    "ZONE1_2_PROVIDER_ID",
    "Zone1_2ExactProfileValues",
    "Zone1_2MonsterProfileAuthority",
    "get_zone1_2_monster_profile",
    "iter_zone1_2_monster_profiles",
    "require_zone1_2_monster_profile",
    "select_zone1_2_monster_profile",
]
