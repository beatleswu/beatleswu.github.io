"""Shared server-owned Adventure Monster runtime contract.

This module defines the admission seam used by Adventure and Map Battle.  It
does not select encounters, create Monster values, or settle rewards.  A
provider must return a complete, server-owned binding before a caller may use
it for combat or defeat settlement.

The registry is deliberately explicit: a missing, disabled, ambiguous, or
wrong-zone provider is an error.  There is no legacy fallback in this layer.
The existing Legacy Map Battle behaviour is represented only by the
``LegacyCompatibilityAdapter`` provider class.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


RUNTIME_CONTRACT_VERSION = "adventure-monster-runtime.v1"
LEGACY_COMPATIBILITY_ADAPTER_ID = "legacy-adventure-compatibility-adapter"
E055_ZONE3_PROVIDER_ID = "e055-zone3-adventure-provider"
CANONICAL_PROVIDER_SLOT_ID = "canonical-adventure-provider-slot"


class AdventureMonsterRuntimeContractError(ValueError):
    """Base class for fail-closed runtime contract failures."""


class MissingZoneError(AdventureMonsterRuntimeContractError):
    """The request or authoritative battle has no zone identity."""


class MissingBindingError(AdventureMonsterRuntimeContractError):
    """A provider did not return a complete Monster binding."""


class ProviderDispatchError(AdventureMonsterRuntimeContractError):
    """The shared provider registry cannot dispatch the requested zone."""


class UnknownProviderError(ProviderDispatchError):
    """The requested provider or zone has no registered provider."""


class ProviderDisabledError(ProviderDispatchError):
    """The selected provider is registered but not admitted."""


class WrongZoneBindingError(AdventureMonsterRuntimeContractError):
    """A provider or binding does not match the requested zone."""


class StaleQuestionBindingError(AdventureMonsterRuntimeContractError):
    """A binding was produced for a different question identity/revision."""


class ProfileBindingMismatchError(AdventureMonsterRuntimeContractError):
    """A profile identity/version does not match the binding."""


class InvalidHpStateError(AdventureMonsterRuntimeContractError):
    """A persisted or proposed HP state is not internally valid."""


class ClientAuthorityClaimError(AdventureMonsterRuntimeContractError):
    """The client attempted to provide a server-owned Monster field."""


class ProviderConfigurationError(AdventureMonsterRuntimeContractError):
    """A provider does not satisfy the shared protocol shape."""


@dataclass(frozen=True, slots=True)
class AdventureQuestionBinding:
    """The server question identity carried into a Monster binding."""

    question_id: Any = None
    question_revision: str | None = None


@dataclass(frozen=True, slots=True)
class AdventureMonsterRuntimeBinding:
    """One immutable server-owned Monster runtime binding.

    The optional-looking fields are intentional.  A provider may represent a
    not-yet-admitted Zone 4-10 slot with ``None`` values, but validation will
    reject that binding before it can reach combat or settlement.  No missing
    gameplay value is synthesized here.

    ``zone_id``, ``taxonomy_family``, ``binding_authority``, and
    ``combat_reference`` are compatibility aliases for vocabulary used by
    existing Adventure/F006 surfaces.  When both spellings are present,
    validation requires them to agree.
    """

    provider_id: str | None = None
    zone_key: str | None = None
    zone_id: str | None = None
    monster_id: str | None = None
    roster_slot: int | None = None
    encounter_class: str | None = None
    family_id: str | None = None
    taxonomy_family: str | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    max_hp: int | None = None
    combat_profile: Any = None
    combat_reference: Any = None
    question_binding: AdventureQuestionBinding | Mapping[str, Any] | None = None
    binding_source: str | None = None
    binding_authority: str | None = None
    binding_version: str | None = None
    persistence_source: str | None = None
    persistence_version: str | None = None
    drop_profile_id: str | None = None
    reward_profile_id: str | None = None
    server_enabled: bool = False
    enabled: bool | None = None

    def __post_init__(self) -> None:
        if self.zone_key is None and self.zone_id is not None:
            object.__setattr__(self, "zone_key", self.zone_id)
        if self.zone_id is None and self.zone_key is not None:
            object.__setattr__(self, "zone_id", self.zone_key)
        if self.family_id is None and self.taxonomy_family is not None:
            object.__setattr__(self, "family_id", self.taxonomy_family)
        if self.taxonomy_family is None and self.family_id is not None:
            object.__setattr__(self, "taxonomy_family", self.family_id)
        if self.binding_source is None and self.binding_authority is not None:
            object.__setattr__(self, "binding_source", self.binding_authority)
        if self.binding_authority is None and self.binding_source is not None:
            object.__setattr__(self, "binding_authority", self.binding_source)
        if self.combat_profile is None and self.combat_reference is not None:
            object.__setattr__(self, "combat_profile", self.combat_reference)
        if self.combat_reference is None and self.combat_profile is not None:
            object.__setattr__(self, "combat_reference", self.combat_profile)
        if self.enabled is not None and self.server_enabled is False:
            object.__setattr__(self, "server_enabled", self.enabled)


@runtime_checkable
class AdventureMonsterRuntimeProvider(Protocol):
    """Protocol for one explicit server-owned Adventure Monster provider."""

    provider_id: str
    enabled: bool

    def supports_zone(self, zone_key: str) -> bool:
        """Return whether this provider owns the exact zone key."""

    def resolve_binding(
        self,
        *,
        zone_key: str,
        question_binding: AdventureQuestionBinding,
        battle: Mapping[str, Any] | None = None,
        user_id: int | None = None,
    ) -> AdventureMonsterRuntimeBinding | None:
        """Resolve one server-owned binding or return no binding."""


_CLIENT_AUTHORITY_CLAIM_FIELDS = frozenset(
    {
        "monster_id",
        "monster_type",
        "battle_monster_type",
        "monster_family",
        "family_id",
        "taxonomy_family",
        "roster_slot",
        "encounter_class",
        "encounter_kind",
        "encounter_type",
        "is_boss",
        "max_hp",
        "monster_hp",
        "monster_hp_max",
        "monster_atk",
        "monster_attack",
        "attack",
        "profile_id",
        "profile_version",
        "stat_source",
        "combat_profile",
        "combat_reference",
        "binding_source",
        "binding_authority",
        "binding_version",
        "persistence_source",
        "persistence_version",
        "drop_profile_id",
        "reward_profile_id",
        "server_enabled",
        "enabled",
        "provider_id",
        "runtime_provider",
    }
)
CLIENT_AUTHORITY_CLAIM_FIELDS = _CLIENT_AUTHORITY_CLAIM_FIELDS


def reject_client_authority_claims(payload: Mapping[str, Any]) -> None:
    """Reject Monster authority fields supplied by a client request."""

    if not isinstance(payload, Mapping):
        raise ClientAuthorityClaimError("request payload must be an object")
    claimed = sorted(
        str(key)
        for key in payload
        if str(key).casefold()
        in {field.casefold() for field in _CLIENT_AUTHORITY_CLAIM_FIELDS}
    )
    if claimed:
        raise ClientAuthorityClaimError(
            "client supplied server-owned Monster authority: " + claimed[0]
        )


def validate_client_authority_claims(payload: Mapping[str, Any]) -> None:
    """Named alias for callers that prefer a validation verb."""

    reject_client_authority_claims(payload)


def _required_text(value: Any, label: str, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{label} is required")
    return value.strip()


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise InvalidHpStateError(f"{label} must be a positive integer")
    if isinstance(value, float) and not value.is_integer():
        raise InvalidHpStateError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise InvalidHpStateError(f"{label} must be a positive integer") from error
    if parsed <= 0:
        raise InvalidHpStateError(f"{label} must be a positive integer")
    return parsed


def validate_hp_state(current_hp: Any, max_hp: Any, *, label: str = "Monster") -> tuple[int, int]:
    """Validate one server-owned current/max HP pair."""

    if isinstance(current_hp, bool) or isinstance(max_hp, bool):
        raise InvalidHpStateError(f"invalid {label} HP state")
    if any(
        isinstance(value, float) and not value.is_integer()
        for value in (current_hp, max_hp)
    ):
        raise InvalidHpStateError(f"invalid {label} HP state")
    try:
        current = int(current_hp)
        maximum = int(max_hp)
    except (TypeError, ValueError) as error:
        raise InvalidHpStateError(f"invalid {label} HP state") from error
    if current < 0 or maximum <= 0 or current > maximum:
        raise InvalidHpStateError(f"invalid {label} HP state")
    return current, maximum


def _alias_value(binding: AdventureMonsterRuntimeBinding, primary: str, alias: str, label: str) -> Any:
    first = getattr(binding, primary)
    second = getattr(binding, alias)
    if first not in (None, "") and second not in (None, "") and first != second:
        raise ProfileBindingMismatchError(f"{label} aliases disagree")
    return first if first not in (None, "") else second


def _question_binding(value: Any) -> AdventureQuestionBinding:
    if isinstance(value, AdventureQuestionBinding):
        return value
    if isinstance(value, Mapping):
        return AdventureQuestionBinding(
            question_id=value.get("question_id"),
            question_revision=value.get("question_revision"),
        )
    raise StaleQuestionBindingError("question binding is missing")


def _validate_question_binding(
    actual: Any,
    expected: AdventureQuestionBinding | Mapping[str, Any] | None,
) -> AdventureQuestionBinding:
    if expected is None:
        raise StaleQuestionBindingError("expected question binding is missing")
    actual_binding = _question_binding(actual)
    expected_binding = _question_binding(expected)
    if actual_binding.question_id in (None, "") or not isinstance(
        actual_binding.question_revision, str
    ) or not actual_binding.question_revision.strip():
        raise StaleQuestionBindingError("provider returned an incomplete question binding")
    if actual_binding.question_id != expected_binding.question_id:
        raise StaleQuestionBindingError("question identity is stale")
    if actual_binding.question_revision != expected_binding.question_revision:
        raise StaleQuestionBindingError("question revision is stale")
    return actual_binding


def _validate_combat_profile(binding: AdventureMonsterRuntimeBinding) -> Any:
    profile = binding.combat_profile
    if profile is None:
        raise MissingBindingError("combat profile binding is missing")
    for field in ("max_hp", "attack", "profile_id", "profile_version"):
        if getattr(profile, field, None) in (None, ""):
            raise ProfileBindingMismatchError(f"combat profile field is missing: {field}")
    try:
        profile_max_hp = _positive_int(profile.max_hp, "combat profile max_hp")
        _positive_int(profile.attack, "combat profile attack")
    except InvalidHpStateError as error:
        raise ProfileBindingMismatchError(str(error)) from error
    if profile_max_hp != int(binding.max_hp):
        raise ProfileBindingMismatchError("combat profile max_hp does not match binding")
    if str(profile.profile_id) != str(binding.profile_id):
        raise ProfileBindingMismatchError("combat profile id does not match binding")
    if str(profile.profile_version) != str(binding.profile_version):
        raise ProfileBindingMismatchError("combat profile version does not match binding")
    profile_zone = getattr(profile, "zone_key", None)
    if profile_zone not in (None, "") and profile_zone != binding.zone_key:
        raise WrongZoneBindingError("combat profile belongs to a different zone")
    profile_monster = getattr(profile, "canonical_monster_id", None)
    if profile_monster not in (None, "") and profile_monster != binding.monster_id:
        raise ProfileBindingMismatchError("combat profile Monster id does not match binding")
    return profile


def _validate_battle_state(
    binding: AdventureMonsterRuntimeBinding,
    battle: Mapping[str, Any],
) -> None:
    if not isinstance(battle, Mapping):
        raise InvalidHpStateError("authoritative battle state is not an object")
    battle_zone = battle.get("zone_key", battle.get("zone_id"))
    if battle_zone in (None, ""):
        raise MissingZoneError("authoritative battle zone is missing")
    if str(battle_zone) != str(binding.zone_key):
        raise WrongZoneBindingError("battle and Monster binding zones disagree")
    for current_key, max_key, label in (
        ("monster_hp", "monster_hp_max", "Monster"),
        ("player_hp", "player_hp_max", "player"),
    ):
        has_current = current_key in battle
        has_maximum = max_key in battle
        if has_current != has_maximum:
            raise InvalidHpStateError(f"incomplete {label} HP state")
        if has_current:
            current, maximum = validate_hp_state(
                battle[current_key], battle[max_key], label=label
            )
            if label == "Monster" and maximum != int(binding.max_hp):
                raise InvalidHpStateError(
                    "persisted Monster max_hp does not match runtime binding"
                )
    migration_source = battle.get("migration_source")
    migration_version = battle.get("migration_version")
    if migration_source in (None, "") or migration_version in (None, ""):
        raise MissingBindingError("persisted Monster binding provenance is missing")
    if migration_source != binding.persistence_source:
        raise ProfileBindingMismatchError("persisted binding source does not match provider")
    if migration_version != binding.persistence_version:
        raise ProfileBindingMismatchError("persisted binding version does not match provider")
    for field in ("profile_id", "profile_version"):
        if field in battle and battle.get(field) not in (None, getattr(binding, field)):
            raise ProfileBindingMismatchError(f"persisted {field} does not match provider")


def validate_runtime_binding(
    binding: AdventureMonsterRuntimeBinding | None,
    *,
    expected_zone_key: str | None,
    expected_question_binding: AdventureQuestionBinding | Mapping[str, Any] | None,
    expected_provider_id: str | None = None,
    expected_profile_id: str | None = None,
    expected_profile_version: str | None = None,
    battle: Mapping[str, Any] | None = None,
    require_persistence: bool = True,
) -> AdventureMonsterRuntimeBinding:
    """Validate a provider result before any shared runtime consumer uses it."""

    zone = _required_text(expected_zone_key, "zone", MissingZoneError)
    if binding is None:
        raise MissingBindingError("Monster runtime binding is missing")
    if not isinstance(binding, AdventureMonsterRuntimeBinding):
        raise MissingBindingError("provider returned an invalid binding object")
    binding_zone = _alias_value(binding, "zone_key", "zone_id", "zone")
    if binding_zone in (None, ""):
        raise MissingZoneError("Monster runtime binding zone is missing")
    if str(binding_zone) != zone:
        raise WrongZoneBindingError("Monster runtime binding belongs to a different zone")
    provider_id = _required_text(binding.provider_id, "provider_id", ProviderConfigurationError)
    if expected_provider_id is not None and provider_id != expected_provider_id:
        raise ProviderConfigurationError("binding provider id does not match dispatched provider")
    if binding.server_enabled is not True:
        raise ProviderDisabledError("Monster runtime binding is not enabled")
    if binding.enabled is not None and binding.enabled is not binding.server_enabled:
        raise ProviderDisabledError("Monster runtime binding enabled aliases disagree")
    for field in ("monster_id", "encounter_class", "profile_id", "profile_version"):
        _required_text(getattr(binding, field), field, MissingBindingError)
    family = _alias_value(binding, "family_id", "taxonomy_family", "family")
    _required_text(family, "family", MissingBindingError)
    if not isinstance(binding.roster_slot, int) or isinstance(binding.roster_slot, bool) or binding.roster_slot <= 0:
        raise MissingBindingError("roster_slot is required")
    binding_max_hp = _positive_int(binding.max_hp, "binding max_hp")
    if expected_profile_id is not None and binding.profile_id != expected_profile_id:
        raise ProfileBindingMismatchError("provider profile id is not admitted")
    if expected_profile_version is not None and binding.profile_version != expected_profile_version:
        raise ProfileBindingMismatchError("provider profile version is not admitted")
    _validate_question_binding(binding.question_binding, expected_question_binding)
    if require_persistence:
        _required_text(binding.persistence_source, "persistence_source", MissingBindingError)
        _required_text(binding.persistence_version, "persistence_version", MissingBindingError)
    _required_text(binding.binding_source, "binding_source", MissingBindingError)
    _required_text(binding.binding_version, "binding_version", MissingBindingError)
    _validate_combat_profile(binding)
    if battle is not None:
        _validate_battle_state(binding, battle)
    if binding_max_hp != int(binding.combat_profile.max_hp):
        raise ProfileBindingMismatchError("binding max_hp does not match combat profile")
    return binding


def persistence_metadata(binding: AdventureMonsterRuntimeBinding) -> dict[str, str]:
    """Return values that fit the existing Map Battle migration columns."""

    _required_text(binding.persistence_source, "persistence_source", MissingBindingError)
    _required_text(binding.persistence_version, "persistence_version", MissingBindingError)
    return {
        "migration_source": binding.persistence_source,
        "migration_version": binding.persistence_version,
    }


def build_f006_defeat_event_fields(
    binding: AdventureMonsterRuntimeBinding,
    *,
    settlement_id: Any,
    user_id: Any,
    hp_before: Any,
    hp_after: Any,
) -> dict[str, Any]:
    """Adapt a validated binding to the existing F006 event constructor.

    This is an adapter only.  F006 remains responsible for profile lookup,
    idempotency, drops, rewards, and the durable event/outbox write.
    """

    validate_runtime_binding(
        binding,
        expected_zone_key=binding.zone_key,
        expected_question_binding=binding.question_binding,
        expected_provider_id=binding.provider_id,
    )
    try:
        before = int(hp_before)
        after = int(hp_after)
        uid = int(user_id)
    except (TypeError, ValueError) as error:
        raise InvalidHpStateError("invalid F006 defeat event values") from error
    if uid <= 0 or before <= 0 or after != 0:
        raise InvalidHpStateError("F006 defeat event requires a server HP boundary")
    return {
        "settlement_id": settlement_id,
        "user_id": uid,
        "monster_id": binding.monster_id,
        "zone_id": binding.zone_key,
        "roster_slot": binding.roster_slot,
        "encounter_class": binding.encounter_class,
        "family_id": binding.family_id,
        "hp_before": before,
        "hp_after": after,
    }


class CallableAdventureMonsterRuntimeProvider:
    """Small protocol adapter for an existing server-owned authority."""

    runtime_role = "canonical"

    def __init__(
        self,
        *,
        provider_id: str,
        zone_keys: Iterable[str],
        binding_resolver: Callable[..., AdventureMonsterRuntimeBinding | None],
        enabled: bool = True,
        runtime_role: str | None = None,
    ) -> None:
        self.provider_id = _required_text(provider_id, "provider_id", ProviderConfigurationError)
        self.supported_zone_keys = frozenset(
            _required_text(zone, "zone", MissingZoneError) for zone in zone_keys
        )
        if not self.supported_zone_keys:
            raise ProviderConfigurationError("provider must own at least one zone")
        if not callable(binding_resolver):
            raise ProviderConfigurationError("binding resolver is required")
        if not isinstance(enabled, bool):
            raise ProviderConfigurationError("provider enabled state must be boolean")
        self.enabled = enabled
        self._binding_resolver = binding_resolver
        if runtime_role is not None:
            self.runtime_role = _required_text(
                runtime_role, "runtime_role", ProviderConfigurationError
            )

    def supports_zone(self, zone_key: str) -> bool:
        return zone_key in self.supported_zone_keys

    def resolve_binding(
        self,
        *,
        zone_key: str,
        question_binding: AdventureQuestionBinding,
        battle: Mapping[str, Any] | None = None,
        user_id: int | None = None,
    ) -> AdventureMonsterRuntimeBinding | None:
        return self._binding_resolver(
            zone_key=zone_key,
            question_binding=question_binding,
            battle=battle,
            user_id=user_id,
        )

    def bind(self, **kwargs: Any) -> AdventureMonsterRuntimeBinding | None:
        """Compatibility spelling for callers using a bind-style provider."""

        return self.resolve_binding(**kwargs)


class LegacyCompatibilityAdapter(CallableAdventureMonsterRuntimeProvider):
    """Explicit Z1/Z2 compatibility adapter; never a second combat engine."""

    runtime_role = "legacy_compatibility_adapter"

    def __init__(
        self,
        *,
        zone_keys: Iterable[str],
        binding_resolver: Callable[..., AdventureMonsterRuntimeBinding | None],
        provider_id: str = LEGACY_COMPATIBILITY_ADAPTER_ID,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            zone_keys=zone_keys,
            binding_resolver=binding_resolver,
            enabled=enabled,
            runtime_role=self.runtime_role,
        )


class E055Zone3ProviderAdapter(CallableAdventureMonsterRuntimeProvider):
    """Adapter for the existing E055 Zone 3 provider authority."""

    runtime_role = "e055_provider"

    def __init__(
        self,
        *,
        zone_keys: Iterable[str],
        binding_resolver: Callable[..., AdventureMonsterRuntimeBinding | None],
        provider_id: str = E055_ZONE3_PROVIDER_ID,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            zone_keys=zone_keys,
            binding_resolver=binding_resolver,
            enabled=enabled,
            runtime_role=self.runtime_role,
        )


class CanonicalAdventureProviderSlot:
    """A canonical Zone 4-10 slot with admission disabled by default."""

    runtime_role = "canonical_provider_slot"

    def __init__(
        self,
        *,
        zone_keys: Iterable[str],
        provider_id: str = CANONICAL_PROVIDER_SLOT_ID,
    ) -> None:
        self.provider_id = _required_text(provider_id, "provider_id", ProviderConfigurationError)
        self.supported_zone_keys = frozenset(
            _required_text(zone, "zone", MissingZoneError) for zone in zone_keys
        )
        if not self.supported_zone_keys:
            raise ProviderConfigurationError("canonical provider slot needs a zone scope")
        self.enabled = False

    def supports_zone(self, zone_key: str) -> bool:
        return zone_key in self.supported_zone_keys

    def resolve_binding(self, **_: Any) -> AdventureMonsterRuntimeBinding:
        raise ProviderDisabledError("canonical Adventure provider admission is disabled")


class AdventureMonsterRuntimeProviderRegistry:
    """Explicit shared provider registry and zone dispatch boundary."""

    def __init__(self, providers: Iterable[AdventureMonsterRuntimeProvider] = ()) -> None:
        self._providers: dict[str, AdventureMonsterRuntimeProvider] = {}
        for provider in providers:
            self.register(provider)

    @property
    def providers(self) -> tuple[AdventureMonsterRuntimeProvider, ...]:
        return tuple(self._providers.values())

    def register(self, provider: AdventureMonsterRuntimeProvider) -> None:
        provider_id = _required_text(
            getattr(provider, "provider_id", None),
            "provider_id",
            ProviderConfigurationError,
        )
        if provider_id in self._providers:
            raise ProviderConfigurationError(f"duplicate provider id: {provider_id}")
        if not callable(getattr(provider, "supports_zone", None)):
            raise ProviderConfigurationError("provider does not implement supports_zone")
        if not isinstance(getattr(provider, "enabled", None), bool):
            raise ProviderConfigurationError("provider enabled state is not boolean")
        if not callable(getattr(provider, "resolve_binding", None)) and not callable(
            getattr(provider, "bind", None)
        ):
            raise ProviderConfigurationError("provider does not implement resolve_binding")
        self._providers[provider_id] = provider

    def dispatch(self, *, zone_key: str | None, provider_id: str | None = None) -> AdventureMonsterRuntimeProvider:
        zone = _required_text(zone_key, "zone", MissingZoneError)
        if provider_id is not None:
            provider = self._providers.get(provider_id)
            if provider is None:
                raise UnknownProviderError(f"unknown Adventure Monster provider: {provider_id}")
            if not provider.supports_zone(zone):
                raise WrongZoneBindingError("provider does not own the requested zone")
        else:
            candidates = [
                provider
                for provider in self._providers.values()
                if provider.supports_zone(zone)
            ]
            if not candidates:
                raise UnknownProviderError(f"no provider is registered for zone: {zone}")
            if len(candidates) != 1:
                raise ProviderConfigurationError(
                    f"multiple providers are registered for zone: {zone}"
                )
            provider = candidates[0]
        if provider.enabled is not True:
            raise ProviderDisabledError(
                f"Adventure Monster provider is disabled: {provider.provider_id}"
            )
        return provider

    def provider_for(self, *, zone_key: str | None, provider_id: str | None = None):
        return self.dispatch(zone_key=zone_key, provider_id=provider_id)

    def resolve_binding(
        self,
        *,
        zone_key: str | None,
        question_binding: AdventureQuestionBinding | Mapping[str, Any] | None,
        battle: Mapping[str, Any] | None = None,
        user_id: int | None = None,
        provider_id: str | None = None,
        expected_profile_id: str | None = None,
        expected_profile_version: str | None = None,
    ) -> AdventureMonsterRuntimeBinding:
        provider = self.dispatch(zone_key=zone_key, provider_id=provider_id)
        return _resolve_from_provider(
            provider,
            zone_key=zone_key,
            question_binding=question_binding,
            battle=battle,
            user_id=user_id,
            expected_profile_id=expected_profile_id,
            expected_profile_version=expected_profile_version,
        )

    def resolve(self, **kwargs: Any) -> AdventureMonsterRuntimeBinding:
        return self.resolve_binding(**kwargs)


def _invoke_provider(
    provider: AdventureMonsterRuntimeProvider,
    *,
    zone_key: str,
    question_binding: AdventureQuestionBinding,
    battle: Mapping[str, Any] | None,
    user_id: int | None,
) -> AdventureMonsterRuntimeBinding | None:
    resolver = getattr(provider, "resolve_binding", None)
    if not callable(resolver):
        resolver = getattr(provider, "bind", None)
    if not callable(resolver):
        raise ProviderConfigurationError("provider does not implement a binding resolver")
    try:
        return resolver(
            zone_key=zone_key,
            question_binding=question_binding,
            battle=battle,
            user_id=user_id,
        )
    except AdventureMonsterRuntimeContractError:
        raise
    except Exception as error:  # pragma: no cover - defensive provider boundary
        raise MissingBindingError("provider binding resolution failed") from error


def _resolve_from_provider(
    provider: AdventureMonsterRuntimeProvider,
    *,
    zone_key: str | None,
    question_binding: AdventureQuestionBinding | Mapping[str, Any] | None,
    battle: Mapping[str, Any] | None,
    user_id: int | None,
    expected_profile_id: str | None,
    expected_profile_version: str | None,
) -> AdventureMonsterRuntimeBinding:
    zone = _required_text(zone_key, "zone", MissingZoneError)
    provider_id = _required_text(
        getattr(provider, "provider_id", None),
        "provider_id",
        ProviderConfigurationError,
    )
    if getattr(provider, "enabled", None) is not True:
        raise ProviderDisabledError(f"Adventure Monster provider is disabled: {provider_id}")
    supports_zone = getattr(provider, "supports_zone", None)
    if not callable(supports_zone):
        raise ProviderConfigurationError("provider does not implement supports_zone")
    if not supports_zone(zone):
        raise WrongZoneBindingError("provider does not own the requested zone")
    expected_question = _question_binding(question_binding)
    binding = _invoke_provider(
        provider,
        zone_key=zone,
        question_binding=expected_question,
        battle=battle,
        user_id=user_id,
    )
    return validate_runtime_binding(
        binding,
        expected_zone_key=zone,
        expected_question_binding=expected_question,
        expected_provider_id=provider_id,
        expected_profile_id=expected_profile_id,
        expected_profile_version=expected_profile_version,
        battle=battle,
    )


def resolve_runtime_binding(
    provider_or_registry: AdventureMonsterRuntimeProvider | AdventureMonsterRuntimeProviderRegistry,
    *,
    zone_key: str | None,
    question_binding: AdventureQuestionBinding | Mapping[str, Any] | None,
    battle: Mapping[str, Any] | None = None,
    user_id: int | None = None,
    provider_id: str | None = None,
    expected_profile_id: str | None = None,
    expected_profile_version: str | None = None,
) -> AdventureMonsterRuntimeBinding:
    """Resolve through the one shared provider contract without fallback."""

    if isinstance(provider_or_registry, AdventureMonsterRuntimeProviderRegistry):
        return provider_or_registry.resolve_binding(
            zone_key=zone_key,
            question_binding=question_binding,
            battle=battle,
            user_id=user_id,
            provider_id=provider_id,
            expected_profile_id=expected_profile_id,
            expected_profile_version=expected_profile_version,
        )
    if provider_id is not None and provider_id != getattr(provider_or_registry, "provider_id", None):
        raise UnknownProviderError(f"unknown Adventure Monster provider: {provider_id}")
    return _resolve_from_provider(
        provider_or_registry,
        zone_key=zone_key,
        question_binding=question_binding,
        battle=battle,
        user_id=user_id,
        expected_profile_id=expected_profile_id,
        expected_profile_version=expected_profile_version,
    )


# Readable aliases for adapters and tests that use shorter registry names.
SharedAdventureMonsterRuntimeRegistry = AdventureMonsterRuntimeProviderRegistry
AdventureMonsterRuntimeError = AdventureMonsterRuntimeContractError
CanonicalProviderSlot = CanonicalAdventureProviderSlot


__all__ = [
    "AdventureMonsterRuntimeBinding",
    "AdventureMonsterRuntimeContractError",
    "AdventureMonsterRuntimeError",
    "AdventureMonsterRuntimeProvider",
    "AdventureMonsterRuntimeProviderRegistry",
    "AdventureQuestionBinding",
    "CANONICAL_PROVIDER_SLOT_ID",
    "CLIENT_AUTHORITY_CLAIM_FIELDS",
    "CanonicalAdventureProviderSlot",
    "CanonicalProviderSlot",
    "ClientAuthorityClaimError",
    "CallableAdventureMonsterRuntimeProvider",
    "E055_ZONE3_PROVIDER_ID",
    "E055Zone3ProviderAdapter",
    "InvalidHpStateError",
    "LEGACY_COMPATIBILITY_ADAPTER_ID",
    "LegacyCompatibilityAdapter",
    "MissingBindingError",
    "MissingZoneError",
    "ProfileBindingMismatchError",
    "ProviderConfigurationError",
    "ProviderDisabledError",
    "ProviderDispatchError",
    "RUNTIME_CONTRACT_VERSION",
    "SharedAdventureMonsterRuntimeRegistry",
    "StaleQuestionBindingError",
    "UnknownProviderError",
    "WrongZoneBindingError",
    "build_f006_defeat_event_fields",
    "persistence_metadata",
    "reject_client_authority_claims",
    "resolve_runtime_binding",
    "validate_client_authority_claims",
    "validate_hp_state",
    "validate_runtime_binding",
]
