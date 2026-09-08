"""Owner-approved exact Adventure Monster provider for Zones 4-10.

This module is a bounded provider implementation only.  It consumes the
canonical C2A identity authority and the canonical E1A policy authority,
implements the Owner-approved OPTION_B / PROFILE_B_EXACT values, and exposes
the existing shared Adventure Monster runtime protocol.  It does not import
``app.py``, register a live caller, settle rewards, or create schema.

Taxonomy is intentionally deferred.  ``family_id`` remains ``None`` all the
way through the binding and F006 adapter boundary; no name, art, zone, or
class-derived family is invented.
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
    StaleQuestionBindingError,
    WrongZoneBindingError,
    validate_runtime_binding,
)
from adventure_zone4_10_monster_identity_authority import (
    ZONE4_10_MONSTER_IDENTITIES,
    get_zone4_10_monster_identity,
)
from adventure_zone4_10_monster_reward_policy import (
    get_zone4_10_monster_reward_policy,
)
from monster_combat_profiles import MonsterCombatProfile


ZONE4_10_KEYS: tuple[str, ...] = tuple(f"Z{zone}" for zone in range(4, 11))
ZONE4_10_PROVIDER_ID: Final = "canonical-adventure-zone4-10-provider"
ZONE4_10_BINDING_SOURCE: Final = "C2A_E1A_ADVENTURE_ZONE4_10_PROVIDER"
ZONE4_10_BINDING_VERSION: Final = "w2.z4_10.provider.v1"
ZONE4_10_PERSISTENCE_VERSION: Final = "w2.z4_10.binding.v1"
ZONE4_10_PROFILE_VERSION: Final = "w2.z4_10.profile.v1"
E1A_POLICY_REFERENCE: Final = "adventure_zone4_10_monster_reward_policy"


@dataclass(frozen=True, slots=True)
class Zone4_10ExactProfileValues:
    """One exact Owner-approved zone/class combat value pair."""

    max_hp: int
    attack: int


@dataclass(frozen=True, slots=True)
class Zone4_10MonsterProfileAuthority:
    """Complete exact provider-side profile record for one C2A identity."""

    monster_id: str
    zone_key: str
    roster_slot: int
    encounter_class: str
    max_hp: int
    attack: int
    profile_id: str
    profile_version: str
    family_id: str | None
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
            stat_source="OWNER_APPROVED_PROFILE_B_EXACT",
            compatibility_mode="ADVENTURE_ZONE4_10_EXACT_PROFILE",
            profile_version=self.profile_version,
            provenance=(
                ("identity_authority", "C2A"),
                ("reward_policy_authority", "E1A"),
                ("taxonomy", "DEFERRED"),
            ),
        )


# This is the approved OPTION_B roster.  It is gameplay authority introduced
# by this implementation, not a reconstruction from names or art.
_APPROVED_CLASS_ROSTER: Mapping[str, Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "Z4": MappingProxyType(
            {
                "NORMAL": (
                    "M034", "M035", "M036", "M037", "M038", "M039", "M040", "M041",
                ),
                "ELITE": ("M042", "M043", "M044"),
                "BOSS": ("M045",),
            }
        ),
        "Z5": MappingProxyType(
            {
                "NORMAL": (
                    "M046", "M047", "M048", "M049", "M050", "M051", "M052",
                ),
                "ELITE": ("M053", "M054", "M055"),
                "BOSS": ("M056", "M057"),
            }
        ),
        "Z6": MappingProxyType(
            {
                "NORMAL": (
                    "M058", "M059", "M061", "M062", "M063", "M064", "M065",
                ),
                "ELITE": ("M066", "M067", "M068"),
                "BOSS": ("M069", "M070"),
            }
        ),
        "Z7": MappingProxyType(
            {
                "NORMAL": (
                    "M071", "M072", "M074", "M075", "M076", "M077",
                ),
                "ELITE": ("M078", "M079", "M080", "M081"),
                "BOSS": ("M082", "M083"),
            }
        ),
        "Z8": MappingProxyType(
            {
                "NORMAL": ("M084", "M085", "M086", "M087", "M089", "M090"),
                "ELITE": ("M092", "M093", "M095"),
                "BOSS": ("M096", "M097"),
            }
        ),
        "Z9": MappingProxyType(
            {
                "NORMAL": ("M098", "M099", "M101", "M102", "M103"),
                "ELITE": ("M104", "M106", "M108"),
                "BOSS": ("M109", "M111"),
            }
        ),
        "Z10": MappingProxyType(
            {
                "NORMAL": ("M073", "M112", "M113", "M114", "M115"),
                "ELITE": ("M116", "M117", "M118"),
                "BOSS": ("M119", "M120"),
            }
        ),
    }
)


_PROFILE_VALUES: Mapping[str, Mapping[str, Zone4_10ExactProfileValues]] = MappingProxyType(
    {
        "Z4": MappingProxyType(
            {
                "NORMAL": Zone4_10ExactProfileValues(143, 9),
                "ELITE": Zone4_10ExactProfileValues(229, 11),
                "BOSS": Zone4_10ExactProfileValues(329, 12),
            }
        ),
        "Z5": MappingProxyType(
            {
                "NORMAL": Zone4_10ExactProfileValues(180, 10),
                "ELITE": Zone4_10ExactProfileValues(288, 12),
                "BOSS": Zone4_10ExactProfileValues(414, 14),
            }
        ),
        "Z6": MappingProxyType(
            {
                "NORMAL": Zone4_10ExactProfileValues(223, 12),
                "ELITE": Zone4_10ExactProfileValues(357, 14),
                "BOSS": Zone4_10ExactProfileValues(513, 16),
            }
        ),
        "Z7": MappingProxyType(
            {
                "NORMAL": Zone4_10ExactProfileValues(278, 13),
                "ELITE": Zone4_10ExactProfileValues(445, 16),
                "BOSS": Zone4_10ExactProfileValues(639, 18),
            }
        ),
        "Z8": MappingProxyType(
            {
                "NORMAL": Zone4_10ExactProfileValues(340, 15),
                "ELITE": Zone4_10ExactProfileValues(544, 18),
                "BOSS": Zone4_10ExactProfileValues(782, 20),
            }
        ),
        "Z9": MappingProxyType(
            {
                "NORMAL": Zone4_10ExactProfileValues(420, 16),
                "ELITE": Zone4_10ExactProfileValues(672, 19),
                "BOSS": Zone4_10ExactProfileValues(966, 22),
            }
        ),
        "Z10": MappingProxyType(
            {
                "NORMAL": Zone4_10ExactProfileValues(520, 18),
                "ELITE": Zone4_10ExactProfileValues(832, 22),
                "BOSS": Zone4_10ExactProfileValues(1196, 24),
            }
        ),
    }
)


def _build_class_by_id() -> Mapping[str, str]:
    result: dict[str, str] = {}
    for zone_key, classes in _APPROVED_CLASS_ROSTER.items():
        if zone_key not in ZONE4_10_KEYS:
            raise ProviderConfigurationError("class roster contains an unknown zone")
        for encounter_class, monster_ids in classes.items():
            for monster_id in monster_ids:
                if monster_id in result:
                    raise ProviderConfigurationError(
                        f"duplicate approved class assignment: {monster_id}"
                    )
                result[monster_id] = encounter_class
    canonical_ids = {identity.monster_id for identity in ZONE4_10_MONSTER_IDENTITIES}
    if set(result) != canonical_ids or len(result) != 79:
        raise ProviderConfigurationError(
            "approved Zone4-10 class roster does not exactly cover C2A"
        )
    return MappingProxyType(result)


def _build_roster_slots() -> Mapping[str, int]:
    result: dict[str, int] = {}
    for zone_key in ZONE4_10_KEYS:
        # C2A's canonical tuple order is the roster order.  Derive the
        # per-zone view from that source rather than maintaining a second
        # identity/zone table in the provider.
        identities = tuple(
            identity
            for identity in ZONE4_10_MONSTER_IDENTITIES
            if identity.zone_key == zone_key
        )
        if not identities:
            raise ProviderConfigurationError(f"C2A has no identities for {zone_key}")
        for roster_slot, identity in enumerate(identities, start=1):
            if identity.monster_id in result:
                raise ProviderConfigurationError(
                    f"duplicate C2A roster identity: {identity.monster_id}"
                )
            result[identity.monster_id] = roster_slot
    if len(result) != 79:
        raise ProviderConfigurationError("C2A roster slot coverage is not 79")
    return MappingProxyType(result)


_CLASS_BY_ID = _build_class_by_id()
_ROSTER_SLOT_BY_ID = _build_roster_slots()


def _profile_id(monster_id: str, zone_key: str, encounter_class: str) -> str:
    return f"adventure_{zone_key.lower()}_{encounter_class.lower()}_{monster_id}"


def _build_profile_records() -> tuple[Zone4_10MonsterProfileAuthority, ...]:
    records: list[Zone4_10MonsterProfileAuthority] = []
    profile_ids: set[str] = set()
    for identity in ZONE4_10_MONSTER_IDENTITIES:
        encounter_class = _CLASS_BY_ID[identity.monster_id]
        values = _PROFILE_VALUES[identity.zone_key][encounter_class]
        profile_id = _profile_id(
            identity.monster_id,
            identity.zone_key,
            encounter_class,
        )
        if profile_id in profile_ids:
            raise ProviderConfigurationError(f"duplicate profile id: {profile_id}")
        profile_ids.add(profile_id)
        records.append(
            Zone4_10MonsterProfileAuthority(
                monster_id=identity.monster_id,
                zone_key=identity.zone_key,
                roster_slot=_ROSTER_SLOT_BY_ID[identity.monster_id],
                encounter_class=encounter_class,
                max_hp=values.max_hp,
                attack=values.attack,
                profile_id=profile_id,
                profile_version=ZONE4_10_PROFILE_VERSION,
                family_id=None,
                server_enabled=True,
            )
        )
    if len(records) != 79 or len(profile_ids) != 79:
        raise ProviderConfigurationError("Zone4-10 exact profile coverage is not 79")
    return tuple(records)


ZONE4_10_MONSTER_PROFILE_RECORDS = _build_profile_records()
ZONE4_10_MONSTER_PROFILE_BY_ID: Mapping[str, Zone4_10MonsterProfileAuthority] = MappingProxyType(
    {record.monster_id: record for record in ZONE4_10_MONSTER_PROFILE_RECORDS}
)


def get_zone4_10_monster_profile(
    monster_id: object,
) -> Zone4_10MonsterProfileAuthority | None:
    normalized = str(monster_id).strip() if monster_id not in (None, "") else ""
    return ZONE4_10_MONSTER_PROFILE_BY_ID.get(normalized)


def require_zone4_10_monster_profile(monster_id: object) -> Zone4_10MonsterProfileAuthority:
    profile = get_zone4_10_monster_profile(monster_id)
    if profile is None:
        raise MissingBindingError("unknown Zone4-10 Monster profile")
    return profile


def iter_zone4_10_monster_profiles() -> tuple[Zone4_10MonsterProfileAuthority, ...]:
    return ZONE4_10_MONSTER_PROFILE_RECORDS


def _question_binding(value: AdventureQuestionBinding | Mapping[str, Any]) -> AdventureQuestionBinding:
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
        raise MissingZoneError("Zone4-10 provider zone is required")
    normalized = zone_key.strip()
    if normalized not in ZONE4_10_KEYS:
        raise WrongZoneBindingError("Zone4-10 provider does not own this zone")
    return normalized


def _c2a_zone_identities(zone_key: str) -> tuple[Any, ...]:
    identities = tuple(
        identity
        for identity in ZONE4_10_MONSTER_IDENTITIES
        if identity.zone_key == zone_key
    )
    if not identities:
        raise ProviderConfigurationError(f"C2A has no identities for {zone_key}")
    return identities


def _select_profile_for_question(
    zone_key: str,
    question_binding: AdventureQuestionBinding,
) -> Zone4_10MonsterProfileAuthority:
    identities = _c2a_zone_identities(zone_key)
    digest = hashlib.sha256(
        f"{zone_key}:{question_binding.question_id}".encode("utf-8")
    ).digest()
    bucket = int.from_bytes(digest[:4], "big") % len(identities)
    return require_zone4_10_monster_profile(identities[bucket].monster_id)


def select_zone4_10_monster_profile(
    zone_key: object,
    question_id: object,
) -> Zone4_10MonsterProfileAuthority:
    """Select one exact server-owned profile using the E055 hash pattern."""

    zone = _required_zone(zone_key)
    question = _question_binding(
        AdventureQuestionBinding(question_id=question_id, question_revision="selection-only")
    )
    return _select_profile_for_question(zone, question)


def _persistence_version(profile: Zone4_10MonsterProfileAuthority) -> str:
    return ":".join(
        (
            ZONE4_10_PERSISTENCE_VERSION,
            profile.zone_key,
            profile.monster_id,
            profile.profile_id,
            profile.profile_version,
        )
    )


def _binding_for_profile(
    profile: Zone4_10MonsterProfileAuthority,
    question_binding: AdventureQuestionBinding,
) -> AdventureMonsterRuntimeBinding:
    identity = get_zone4_10_monster_identity(profile.monster_id)
    if identity is None or identity.zone_key != profile.zone_key:
        raise MissingBindingError("C2A identity authority cannot resolve profile")
    policy = get_zone4_10_monster_reward_policy(
        profile.monster_id,
        claimed_zone_key=profile.zone_key,
    )
    if policy is None:
        raise MissingBindingError("E1A reward policy authority cannot resolve profile")
    return AdventureMonsterRuntimeBinding(
        provider_id=ZONE4_10_PROVIDER_ID,
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
        binding_source=ZONE4_10_BINDING_SOURCE,
        binding_version=ZONE4_10_BINDING_VERSION,
        persistence_source=ZONE4_10_BINDING_SOURCE,
        persistence_version=_persistence_version(profile),
        reward_profile_id=E1A_POLICY_REFERENCE,
        server_enabled=True,
        enabled=True,
    )


class AdventureZone4_10MonsterRuntimeProvider:
    """One provider under the shared Adventure Monster runtime contract."""

    runtime_role = "canonical_zone4_10_provider"

    def __init__(self, *, enabled: bool = True) -> None:
        if not isinstance(enabled, bool):
            raise ProviderConfigurationError("provider enabled state must be boolean")
        self.provider_id = ZONE4_10_PROVIDER_ID
        self.supported_zone_keys = frozenset(ZONE4_10_KEYS)
        self.enabled = enabled

    def supports_zone(self, zone_id: str) -> bool:
        return isinstance(zone_id, str) and zone_id in self.supported_zone_keys

    def bind_new_battle(
        self,
        user_id: int | None,
        zone_id: str,
        question: AdventureQuestionBinding | Mapping[str, Any],
        eligibility: Mapping[str, Any] | None = None,
    ) -> AdventureMonsterRuntimeBinding:
        """Create a new immutable binding from server-owned question data."""

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
        """Restore only the persisted identity; never reselect on restore."""

        if not isinstance(battle, Mapping):
            raise MissingBindingError("persisted battle binding is not an object")
        zone_key = _required_zone(battle.get("zone_key", battle.get("zone_id")))
        if battle.get("migration_source") != ZONE4_10_BINDING_SOURCE:
            raise MissingBindingError("Zone4-10 persistence source is missing")
        token = str(battle.get("migration_version") or "")
        parts = token.split(":")
        if len(parts) != 5 or parts[0] != ZONE4_10_PERSISTENCE_VERSION:
            raise MissingBindingError("Zone4-10 persistence version is invalid")
        if parts[1] != zone_key:
            raise WrongZoneBindingError("persisted profile belongs to another zone")
        profile = require_zone4_10_monster_profile(parts[2])
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
                raise StaleQuestionBindingError(
                    "persisted question binding is stale"
                )
        # Validate the persisted M-ID against the same server-side selector
        # used for new battles.  The selected value is only a consistency
        # check; the persisted profile remains the immutable identity returned.
        expected_profile = _select_profile_for_question(zone_key, question_binding)
        if expected_profile.monster_id != profile.monster_id:
            raise StaleQuestionBindingError(
                "persisted Monster identity does not match the question binding"
            )
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
        return binding

    def presentation_payload(
        self,
        binding: AdventureMonsterRuntimeBinding,
        battle: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        """Return a presentation-safe projection without adding art authority."""

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

    def reward_policy_for(self, monster_id: object):
        """Resolve E1A directly; no reward values are duplicated here."""

        profile = get_zone4_10_monster_profile(monster_id)
        if profile is None:
            return None
        return get_zone4_10_monster_reward_policy(
            profile.monster_id,
            claimed_zone_key=profile.zone_key,
        )

    def resolve_binding(
        self,
        *,
        zone_key: str,
        question_binding: AdventureQuestionBinding,
        battle: Mapping[str, Any] | None = None,
        user_id: int | None = None,
    ) -> AdventureMonsterRuntimeBinding:
        """Implement the canonical protocol without fallback."""

        if battle is None:
            return self.bind_new_battle(user_id, zone_key, question_binding, None)
        return self.restore_binding(battle, question_binding)

    def bind(self, **kwargs: Any) -> AdventureMonsterRuntimeBinding:
        return self.resolve_binding(**kwargs)


ZONE4_10_MONSTER_RUNTIME_PROVIDER = AdventureZone4_10MonsterRuntimeProvider()


__all__ = [
    "AdventureZone4_10MonsterRuntimeProvider",
    "E1A_POLICY_REFERENCE",
    "ZONE4_10_BINDING_SOURCE",
    "ZONE4_10_BINDING_VERSION",
    "ZONE4_10_KEYS",
    "ZONE4_10_MONSTER_PROFILE_BY_ID",
    "ZONE4_10_MONSTER_PROFILE_RECORDS",
    "ZONE4_10_MONSTER_RUNTIME_PROVIDER",
    "ZONE4_10_PERSISTENCE_VERSION",
    "ZONE4_10_PROFILE_VERSION",
    "ZONE4_10_PROVIDER_ID",
    "Zone4_10ExactProfileValues",
    "Zone4_10MonsterProfileAuthority",
    "get_zone4_10_monster_profile",
    "iter_zone4_10_monster_profiles",
    "require_zone4_10_monster_profile",
    "select_zone4_10_monster_profile",
]
