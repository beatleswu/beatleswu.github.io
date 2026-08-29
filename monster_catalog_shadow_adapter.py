"""E046 shadow adapter for comparing runtime Monster inputs with E045.

This module is deliberately an observation boundary.  It translates an
already server-resolved identity and an explicitly named context into the
E045 catalog/profile model, then reports parity without changing the input or
any live gameplay result.

The adapter accepts only presentation-independent identity fields:
``monster_id`` or the explicit F003 ``roster_slot``.  It never resolves an
identity from a display name, art filename, array index, roster count, or
derived formula.  Adventure and Lord contexts return an explicit no-profile
result until those contexts acquire their own authoritative profiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from monster_catalog_foundation import (
    ADVENTURE_NORMAL,
    BATTLEFIELD_BOSS,
    BATTLEFIELD_NORMAL,
    CANONICAL_MONSTER_CATALOG,
    LORD,
    SUPPORTED_CONTEXTS,
    MonsterCatalog,
    MonsterCatalogEntry,
    UnknownContextError,
    UnknownMonsterError,
    UnknownProfileError,
    MissingCombatProfileError,
    get_monster,
    resolve_context_profile,
)
from monster_identity import CANONICAL_MONSTER_IDENTITY_REGISTRY


SHADOW_ADAPTER_VERSION = "e046.shadow.v1"
SHADOW_ADAPTER_CREATED = True
SHADOW_ADAPTER_RUNTIME_AUTHORITY = False
ACTIVE_GAMEPLAY_OUTPUT_CHANGED = False
MONSTER_ID_DERIVED_FROM_PRESENTATION = False
LORD_NUMERIC_PROFILE_CREATED = False
LORD_SHADOW_CLASSIFICATION = "EXPLICIT_LORD_NO_NUMERIC_PROFILE"
ADVENTURE_MISSING_PROFILE_FAILS_CLOSED = True
WORLD_PROGRESS_AUTHORITY_CHANGED = False
ART_CONTENT_ZONE_USED_FOR_GAMEPLAY = False
GENERATED_PROFILE_FORMULA_FALLBACK = False

# E046 observes F009's existing flag but does not activate or replace it.
try:
    from monster_encounter_selector import MONSTER_SELECTOR_LIVE_ACTIVATED
except ImportError:  # pragma: no cover - repository source is present in runtime
    MONSTER_SELECTOR_LIVE_ACTIVATED = False
F009_ENABLED = bool(MONSTER_SELECTOR_LIVE_ACTIVATED)


class ShadowAdapterError(ValueError):
    """Base error for malformed or unresolvable shadow inputs."""


class ShadowIdentityInputError(ShadowAdapterError):
    """Raised when a caller provides no accepted stable identity input."""


@dataclass(frozen=True)
class ShadowComparison:
    """Immutable comparison output; it has no write or gameplay side effect."""

    current_monster_id: str | None
    foundation_monster_id: str | None
    current_context: str
    foundation_context: str | None
    current_hp: int | None
    foundation_hp: int | None
    current_atk: int | None
    foundation_atk: int | None
    foundation_profile_id: str | None
    foundation_profile_version: str | None
    foundation_encounter_class: str | None
    profile_status: str
    parity: str
    reason: str

    def as_contract(self) -> dict[str, Any]:
        """Return the deterministic, non-player-visible shadow contract."""

        return {
            "CURRENT_MONSTER_ID": self.current_monster_id,
            "FOUNDATION_MONSTER_ID": self.foundation_monster_id,
            "CURRENT_CONTEXT": self.current_context,
            "FOUNDATION_CONTEXT": self.foundation_context,
            "CURRENT_HP": self.current_hp,
            "FOUNDATION_HP": self.foundation_hp,
            "CURRENT_ATK": self.current_atk,
            "FOUNDATION_ATK": self.foundation_atk,
            "FOUNDATION_PROFILE_ID": self.foundation_profile_id,
            "FOUNDATION_PROFILE_VERSION": self.foundation_profile_version,
            "FOUNDATION_ENCOUNTER_CLASS": self.foundation_encounter_class,
            "PROFILE_STATUS": self.profile_status,
            "PARITY": self.parity,
            "REASON": self.reason,
        }


def _value(source: Mapping[str, Any], key: str) -> Any:
    return source.get(key)


def _stable_identity_from_runtime(
    current_runtime: Mapping[str, Any],
    *,
    catalog: MonsterCatalog,
) -> tuple[str | None, MonsterCatalogEntry | None]:
    """Resolve only an explicit Monster ID or F003 roster slot.

    ``roster_slot`` is accepted because F003 defines it as a server-owned
    identity field.  ``monster_idx`` is intentionally rejected: accepting it
    here would turn an array/index convention into new catalog authority.
    """

    explicit_id = _value(current_runtime, "monster_id")
    slot_value = _value(current_runtime, "roster_slot")
    presentation_only = any(
        current_runtime.get(key) not in (None, "")
        for key in ("display_name", "monster_name", "name", "avatar", "art_filename", "image_filename")
    )

    if explicit_id not in (None, ""):
        entry = get_monster(explicit_id, catalog=catalog)
        if entry is None:
            raise UnknownMonsterError(
                f"unknown canonical Monster ID: {explicit_id!r}"
            )
        identity = CANONICAL_MONSTER_IDENTITY_REGISTRY.by_id.get(entry.monster_id)
        if identity is None:
            raise UnknownMonsterError(
                f"E045 catalog identity has no F003 identity: {entry.monster_id!r}"
            )
        if slot_value not in (None, ""):
            try:
                requested_slot = int(slot_value)
            except (TypeError, ValueError) as error:
                raise ShadowIdentityInputError("roster_slot must be an integer") from error
            if requested_slot != identity.roster_slot:
                raise ShadowIdentityInputError(
                    "explicit Monster ID and F003 roster_slot disagree"
                )
        return identity.monster_id, entry

    if slot_value not in (None, ""):
        try:
            requested_slot = int(slot_value)
        except (TypeError, ValueError) as error:
            raise ShadowIdentityInputError("roster_slot must be an integer") from error
        identity = CANONICAL_MONSTER_IDENTITY_REGISTRY.by_roster_slot.get(requested_slot)
        if identity is None:
            raise UnknownMonsterError(
                f"unknown F003 Monster roster_slot: {slot_value!r}"
            )
        entry = get_monster(identity.monster_id, catalog=catalog)
        if entry is None:
            raise UnknownMonsterError(
                f"F003 identity has no E045 catalog entry: {identity.monster_id!r}"
            )
        return identity.monster_id, entry

    if presentation_only or _value(current_runtime, "monster_idx") not in (None, ""):
        raise ShadowIdentityInputError(
            "shadow identity requires explicit monster_id or F003 roster_slot"
        )
    return None, None


def _observed_positive_int(current_runtime: Mapping[str, Any], key: str) -> int | None:
    value = _value(current_runtime, key)
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _validate_context(context: Any) -> str:
    if context in (None, ""):
        raise UnknownContextError("Monster shadow context is required")
    context_key = str(context).strip()
    if context_key not in SUPPORTED_CONTEXTS:
        raise UnknownContextError(f"unknown Monster context: {context!r}")
    return context_key


def _no_profile_result(
    *,
    current_monster_id: str | None,
    context: str,
    current_hp: int | None,
    current_atk: int | None,
    reason: str,
) -> ShadowComparison:
    return ShadowComparison(
        current_monster_id=current_monster_id,
        foundation_monster_id=current_monster_id,
        current_context=context,
        foundation_context=context,
        current_hp=current_hp,
        foundation_hp=None,
        current_atk=current_atk,
        foundation_atk=None,
        foundation_profile_id=None,
        foundation_profile_version=None,
        foundation_encounter_class=None,
        profile_status="NOT_DEFINED",
        parity="NOT_APPLICABLE",
        reason=reason,
    )


def compare_runtime_encounter(
    current_runtime: Mapping[str, Any] | None,
    *,
    context: Any,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> ShadowComparison:
    """Compare one already-resolved runtime tuple against E045.

    The caller supplies the encounter context explicitly.  E046 never infers
    context from Zone, ELO, presentation, rarity, or a client field.  The
    accepted observed stat keys are ``current_hp`` and ``current_atk``; they
    are compared only and are never replaced by the foundation values.
    """

    values = dict(current_runtime or {})
    context_key = _validate_context(context)
    current_hp = _observed_positive_int(values, "current_hp")
    current_atk = _observed_positive_int(values, "current_atk")
    current_id, entry = _stable_identity_from_runtime(values, catalog=catalog)

    # These contexts have no Monster numeric profile in E045.  A missing
    # identity is a valid no-profile observation for the Lord route and for an
    # Adventure consumer that has not yet acquired a canonical Monster ID.
    if context_key == LORD and current_id is None:
        return _no_profile_result(
            current_monster_id=None,
            context=context_key,
            current_hp=current_hp,
            current_atk=current_atk,
            reason=LORD_SHADOW_CLASSIFICATION,
        )
    if context_key == ADVENTURE_NORMAL and current_id is None:
        return _no_profile_result(
            current_monster_id=None,
            context=context_key,
            current_hp=current_hp,
            current_atk=current_atk,
            reason="NO_EXPLICIT_ADVENTURE_PROFILE",
        )

    if entry is None or current_id is None:
        raise UnknownMonsterError(
            "shadow comparison requires an explicit canonical Monster identity"
        )

    try:
        profile = resolve_context_profile(
            current_id,
            context_key,
            catalog=catalog,
        )
    except MissingCombatProfileError:
        # Known identity plus absent context reference is a truthful
        # not-applicable result, not permission to inherit Battlefield stats.
        if context_key in (ADVENTURE_NORMAL, LORD):
            return _no_profile_result(
                current_monster_id=current_id,
                context=context_key,
                current_hp=current_hp,
                current_atk=current_atk,
                reason=(
                    "NO_EXPLICIT_ADVENTURE_PROFILE"
                    if context_key == ADVENTURE_NORMAL
                    else LORD_SHADOW_CLASSIFICATION
                ),
            )
        raise
    except UnknownProfileError:
        # Do not convert a broken explicit reference into a guessed profile.
        raise

    parity = (
        "PASS"
        if current_hp is not None
        and current_atk is not None
        and current_hp == profile.max_hp
        and current_atk == profile.attack
        else "MISMATCH"
        if current_hp is not None and current_atk is not None
        else "NOT_APPLICABLE"
    )
    reason = (
        "explicit_profile_values_match"
        if parity == "PASS"
        else "explicit_profile_values_differ"
        if parity == "MISMATCH"
        else "runtime_stat_tuple_missing_or_invalid"
    )
    return ShadowComparison(
        current_monster_id=current_id,
        foundation_monster_id=entry.monster_id,
        current_context=context_key,
        foundation_context=context_key,
        current_hp=current_hp,
        foundation_hp=profile.max_hp,
        current_atk=current_atk,
        foundation_atk=profile.attack,
        foundation_profile_id=profile.profile_id,
        foundation_profile_version=profile.version,
        foundation_encounter_class=entry.encounter_class,
        profile_status=profile.status,
        parity=parity,
        reason=reason,
    )


def compare_runtime_encounters(
    encounters: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    *,
    context: Any,
    catalog: MonsterCatalog = CANONICAL_MONSTER_CATALOG,
) -> tuple[ShadowComparison, ...]:
    """Compare a deterministic batch without selecting or mutating anything."""

    return tuple(
        compare_runtime_encounter(item, context=context, catalog=catalog)
        for item in encounters
    )


__all__ = [
    "ACTIVE_GAMEPLAY_OUTPUT_CHANGED",
    "ADVENTURE_MISSING_PROFILE_FAILS_CLOSED",
    "BATTLEFIELD_BOSS",
    "BATTLEFIELD_NORMAL",
    "F009_ENABLED",
    "GENERATED_PROFILE_FORMULA_FALLBACK",
    "LORD_NUMERIC_PROFILE_CREATED",
    "LORD_SHADOW_CLASSIFICATION",
    "MONSTER_ID_DERIVED_FROM_PRESENTATION",
    "ShadowAdapterError",
    "ShadowComparison",
    "ShadowIdentityInputError",
    "SHADOW_ADAPTER_CREATED",
    "SHADOW_ADAPTER_RUNTIME_AUTHORITY",
    "SHADOW_ADAPTER_VERSION",
    "compare_runtime_encounter",
    "compare_runtime_encounters",
]
