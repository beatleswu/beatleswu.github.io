"""One canonical server-side Monster combat-stat resolver.

F008 closes the stat-authority split without changing the current combat
balance.  F004 profiles are the normal source for canonical battlefield
identities.  The existing Map Battle persisted-state/default behaviour is
represented explicitly as a compatibility override *inside this resolver*;
no combat consumer reads question HP/ATK fields directly.

This module intentionally does not select encounters, mutate current HP,
settle defeats, grant rewards, or write persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from monster_identity import (
    ENCOUNTER_CLASS_BATTLEFIELD_BOSS,
    ENCOUNTER_CLASS_NORMAL,
    MonsterIdentityRegistry,
    resolve_monster_identity,
)
from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    MonsterProfileRegistry,
    get_monster_profile,
    get_stat_profile,
)


MAP_BATTLE_DEFAULT_HP = 100
MAP_BATTLE_DEFAULT_ATTACK = 8
MONSTER_COMBAT_PROFILE_VERSION = "f008.v1"

_DISPLAY_ONLY_KEYS = frozenset({
    "display_name",
    "monster_name",
    "name",
    "avatar",
    "art_key",
    "css_class",
})
_IDENTITY_HINT_KEYS = frozenset({
    "monster_id",
    "monster_type",
    "battle_monster_type",
    "monster_family",
    "family_id",
    "zone_id",
    "zone",
    "stage",
    "encounter_type",
    "encounter_class",
    "encounter_kind",
    "roster_slot",
    "monster_idx",
})


class MonsterCombatProfileError(ValueError):
    """Raised when a server-side Monster stat binding cannot be resolved."""


@dataclass(frozen=True)
class MonsterCombatProfile:
    """Resolved immutable combat definition for one active Monster."""

    canonical_monster_id: str | None
    zone_key: str | None
    roster_slot: int | None
    encounter_class: str | None
    max_hp: int
    attack: int
    profile_id: str
    stat_source: str
    compatibility_mode: str
    profile_version: str = MONSTER_COMBAT_PROFILE_VERSION
    override_reason: str | None = None
    override_source: str | None = None
    allowed_override_fields: tuple[str, ...] = ()
    provenance: tuple[tuple[str, Any], ...] = ()

    @property
    def legacy_encounter_kind(self) -> str:
        """Preserve the existing response vocabulary without new authority."""

        return (
            "boss"
            if self.encounter_class == ENCOUNTER_CLASS_BATTLEFIELD_BOSS
            else "normal"
        )

    @property
    def stage(self) -> int | None:
        if self.roster_slot is None:
            return None
        return (int(self.roster_slot) - 1) // 2 + 1

    def runtime_fields(self) -> dict[str, Any]:
        """Return safe diagnostics/projection fields for tests and adapters."""

        return {
            "canonical_monster_id": self.canonical_monster_id,
            "monster_id": self.canonical_monster_id,
            "zone_key": self.zone_key,
            "roster_slot": self.roster_slot,
            "encounter_class": self.encounter_class,
            "max_hp": self.max_hp,
            "monster_hp_max": self.max_hp,
            "attack": self.attack,
            "monster_attack": self.attack,
            "profile_id": self.profile_id,
            "stat_source": self.stat_source,
            "compatibility_mode": self.compatibility_mode,
            "profile_version": self.profile_version,
            "override_reason": self.override_reason,
            "override_source": self.override_source,
            "allowed_override_fields": self.allowed_override_fields,
            "provenance": dict(self.provenance),
        }

    def __getitem__(self, key: str) -> Any:
        """Small legacy adapter for existing response-only profile access."""

        aliases = {
            "attack": self.attack,
            "max_hp": self.max_hp,
            "encounter_kind": self.legacy_encounter_kind,
            "stage": self.stage,
        }
        if key in aliases:
            return aliases[key]
        return self.runtime_fields()[key]


def _positive_int(value: Any, fallback: int | None = None) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    if parsed <= 0:
        return fallback
    return parsed


def _canonical_encounter_class(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().upper()
    if text in (ENCOUNTER_CLASS_NORMAL, "COMMON"):
        return "COMMON"
    if text == "RARE":
        return "RARE"
    if text == "ELITE":
        return "ELITE"
    if text == ENCOUNTER_CLASS_BATTLEFIELD_BOSS:
        return ENCOUNTER_CLASS_BATTLEFIELD_BOSS
    return None


def _identity_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """Keep stable server vocabularies; exclude labels and art aliases.

    The current question corpus has meaningful ``monster_name`` labels that
    do not equal the legacy Battlefield display names.  F003 correctly treats
    display names as validation aliases, so F008 binds identity from the
    stable stage/type/family fields and never from localized text.
    """

    return {
        key: value
        for key, value in source.items()
        if key not in _DISPLAY_ONLY_KEYS
    }


def _has_identity_hints(source: Mapping[str, Any]) -> bool:
    return any(
        key in source and source.get(key) not in (None, "")
        for key in _IDENTITY_HINT_KEYS
    )


def _normalise_overrides(overrides: Mapping[str, Any] | None) -> dict[str, int]:
    if not overrides:
        return {}
    normalised: dict[str, int] = {}
    for key in ("max_hp", "monster_hp_max"):
        if key in overrides and overrides[key] not in (None, ""):
            value = _positive_int(overrides[key])
            if value is None:
                raise MonsterCombatProfileError(
                    f"invalid trusted Monster max HP override: {overrides[key]!r}"
                )
            normalised["max_hp"] = value
            break
    for key in ("attack", "monster_attack", "monster_atk"):
        if key in overrides and overrides[key] not in (None, ""):
            value = _positive_int(overrides[key], fallback=0)
            if value is None:
                raise MonsterCombatProfileError(
                    f"invalid trusted Monster attack override: {overrides[key]!r}"
                )
            normalised["attack"] = value
            break
    return normalised


def build_map_battle_compatibility_overrides(
    source: Mapping[str, Any] | None = None,
    *,
    persisted_max_hp: Any = None,
) -> dict[str, int]:
    """Translate existing server-owned Map Battle fallback inputs.

    The old runtime selected max HP from the persisted battle state (or the
    question's ``monster_hp_max``/``monster_hp`` field, then 100) and attack
    from server-loaded question metadata (then 8).  This helper preserves that
    exact behaviour while making the defaults part of the single resolver
    contract.  It must only be called with server-loaded data.
    """

    values = dict(source or {})
    if persisted_max_hp not in (None, ""):
        max_hp = _positive_int(persisted_max_hp, fallback=MAP_BATTLE_DEFAULT_HP)
    elif values.get("monster_hp_max") not in (None, ""):
        max_hp = _positive_int(
            values.get("monster_hp_max"), fallback=MAP_BATTLE_DEFAULT_HP
        )
    elif values.get("monster_hp") not in (None, ""):
        max_hp = _positive_int(
            values.get("monster_hp"), fallback=MAP_BATTLE_DEFAULT_HP
        )
    else:
        max_hp = MAP_BATTLE_DEFAULT_HP

    attack = _positive_int(
        values.get("monster_atk", values.get("monster_attack")),
        fallback=MAP_BATTLE_DEFAULT_ATTACK,
    )
    return {"max_hp": int(max_hp), "attack": int(attack)}


def build_legacy_battlefield_compatibility_overrides(
    source: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Expose persisted legacy HP only as a governed state compatibility input."""

    values = dict(source or {})
    if values.get("max_hp") in (None, ""):
        return {}
    max_hp = _positive_int(values.get("max_hp"))
    if max_hp is None:
        raise MonsterCombatProfileError(
            f"invalid persisted Battlefield max HP: {values.get('max_hp')!r}"
        )
    return {"max_hp": max_hp}


def resolve_monster_combat_profile(
    source: Mapping[str, Any] | None = None,
    *,
    monster_id: Any = None,
    profile_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
    identity_registry: MonsterIdentityRegistry | None = None,
    trusted_compatibility_overrides: Mapping[str, Any] | None = None,
    compatibility_mode: str = "NONE",
    compatibility_reason: str | None = None,
    compatibility_source: str | None = None,
    allowed_override_fields: tuple[str, ...] = ("max_hp", "attack"),
    context: str = "GENERIC",
) -> MonsterCombatProfile:
    """Resolve one immutable Monster combat profile.

    ``trusted_compatibility_overrides`` is deliberately a separate argument:
    raw client/question mappings never become stat authority by themselves.
    Callers must first identify the server-owned compatibility context (for
    example a persisted Map Battle state) and pass only the allowed fields.
    """

    values = dict(source or {})
    requested_id = monster_id if monster_id not in (None, "") else values.get("monster_id")
    profile = get_monster_profile(requested_id, registry=profile_registry)
    identity = None

    if requested_id not in (None, "") and profile is None:
        raise MonsterCombatProfileError(
            f"unknown canonical Monster identity: {requested_id!r}"
        )

    if profile is None:
        identity_values = _identity_source(values)
        # Battlefield roster index is server-owned state.  Legacy fixtures
        # and old rows can carry stale type/name labels; do not let those
        # labels veto the canonical slot binding.
        if (
            str(context).upper() == "LEGACY_BATTLEFIELD"
            and values.get("monster_idx") not in (None, "")
            and requested_id in (None, "")
        ):
            identity_values = {"monster_idx": values.get("monster_idx")}
        identity = resolve_monster_identity(
            identity_values,
            registry=identity_registry,
        )
        if identity is not None:
            profile = get_monster_profile(identity.monster_id, registry=profile_registry)
            if profile is None:
                raise MonsterCombatProfileError(
                    f"Monster identity has no canonical stat profile: {identity.monster_id!r}"
                )

    overrides = _normalise_overrides(trusted_compatibility_overrides)
    is_map_compatibility = str(context).upper() == "MAP_BATTLE"
    if profile is None and not is_map_compatibility:
        raise MonsterCombatProfileError(
            "server Monster identity/profile did not resolve"
        )
    if profile is None and _has_identity_hints(values):
        raise MonsterCombatProfileError(
            "unknown or ambiguous server Monster identity; refusing fallback"
        )

    if profile is not None:
        stat = get_stat_profile(profile.stat_profile_id, registry=profile_registry)
        if stat is None:
            raise MonsterCombatProfileError(
                f"Monster profile has no stat definition: {profile.stat_profile_id!r}"
            )
        max_hp = int(stat.max_hp)
        attack = int(stat.attack)
        canonical_id = profile.monster_id
        zone_key = profile.zone_key
        roster_slot = int(profile.roster_slot)
        encounter_class = _canonical_encounter_class(profile.encounter_class)
        profile_id = profile.stat_profile_id
        source_name = "F004_MONSTER_PROFILE_REGISTRY"
        mode = "NONE"
    else:
        # Existing Map Battle fixtures/legacy encounters without canonical
        # identity retain the old 100 HP / 8 ATK fallback, now in one place.
        max_hp = MAP_BATTLE_DEFAULT_HP
        attack = MAP_BATTLE_DEFAULT_ATTACK
        canonical_id = None
        zone_key = values.get("zone_key")
        roster_slot = None
        encounter_class = None
        profile_id = "compat_map_battle_v1"
        source_name = "MAP_BATTLE_LEGACY_FALLBACK"
        mode = "MAP_BATTLE_LEGACY_FALLBACK"

    if overrides:
        if "max_hp" in overrides:
            max_hp = overrides["max_hp"]
        if "attack" in overrides:
            attack = overrides["attack"]
        source_name = f"{source_name}+COMPATIBILITY_OVERRIDE"
        if mode == "NONE":
            mode = compatibility_mode or "COMPATIBILITY_OVERRIDE"
        elif compatibility_mode:
            mode = compatibility_mode

    if max_hp <= 0 or attack < 0:
        raise MonsterCombatProfileError("resolved Monster combat stats are invalid")

    provenance = {
        "context": context,
        "profile_stat_values": (
            {"max_hp": int(stat.max_hp), "attack": int(stat.attack)}
            if profile is not None
            else None
        ),
        "compatibility_overrides_applied": tuple(sorted(overrides)),
        "identity_source": (
            "canonical_monster_id"
            if requested_id not in (None, "")
            else "server_legacy_vocabulary"
            if identity is not None
            else "map_battle_legacy_fallback"
        ),
    }
    return MonsterCombatProfile(
        canonical_monster_id=canonical_id,
        zone_key=zone_key,
        roster_slot=roster_slot,
        encounter_class=encounter_class,
        max_hp=int(max_hp),
        attack=int(attack),
        profile_id=profile_id,
        stat_source=source_name,
        compatibility_mode=mode,
        override_reason=compatibility_reason if overrides else None,
        override_source=compatibility_source if overrides else None,
        allowed_override_fields=tuple(allowed_override_fields) if overrides else (),
        provenance=tuple(provenance.items()),
    )


__all__ = [
    "MAP_BATTLE_DEFAULT_ATTACK",
    "MAP_BATTLE_DEFAULT_HP",
    "MONSTER_COMBAT_PROFILE_VERSION",
    "MonsterCombatProfile",
    "MonsterCombatProfileError",
    "build_legacy_battlefield_compatibility_overrides",
    "build_map_battle_compatibility_overrides",
    "resolve_monster_combat_profile",
]
