"""Pure server-side Zone-local Monster encounter selection for F009.

F009 owns encounter identity selection only.  It does not resolve combat
stats, mutate encounter state, settle a defeat, grant a drop/reward, emit a
Quest mutation, or decide World/Lord progression.

The selector accepts server-owned state as an explicit input because no
durable user+zone cycle ledger exists yet.  It therefore remains safe to
review and test without a schema change or a live route cutover.  A future
durable-state task can persist the same ``seen_monster_ids`` and last-
encounter fields without changing the selection policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from monster_profiles import (
    CANONICAL_MONSTER_PROFILE_REGISTRY,
    MonsterProfileRegistry,
)


MONSTER_ENCOUNTER_SELECTOR_COUNT = 1
SELECTOR_VERSION = "f009.v1"
SEEN_STATE_SCOPE = "USER_AND_ZONE"
UNSEEN_FIRST = True
NO_IMMEDIATE_MONSTER_REPEAT = True
FAMILY_REPEAT_AVOIDANCE = "SOFT_PREFERENCE"
SINGLE_CANDIDATE_POLICY = "ALLOW_REPEAT"
BATTLEFIELD_BOSS_ELIGIBILITY_SELECTOR_OWNED = False
SELECTOR_OWNS_MONSTER_STATS = False
SELECTOR_OWNS_WORLD_PROGRESSION = False
SELECTOR_OWNS_QUESTION_SELECTION = False
BATTLEFIELD_BOSS_IN_REGULAR_POOL = False
LORD_IN_GENERIC_SELECTOR = False
LORD_CLASSIFIED_AS_BATTLEFIELD_BOSS = False
RARITY_WEIGHT_POLICY_STATUS = "CANDIDATE_NOT_LIVE"
DURABLE_SELECTOR_STATE_GAP = True
MONSTER_SELECTOR_LIVE_ACTIVATED = False
F007_100_ROSTER_RUNTIME_ACTIVATED = False
SELECTOR_RANDOMNESS_MODEL = "SHA256_SERVER_OPERATION_AND_STATE"

COMMON_WEIGHT = 65
RARE_WEIGHT = 22
ELITE_WEIGHT = 13

SELECTOR_DECISION_ORDER = (
    "server_authoritative_zone",
    "valid_zone_local_pool",
    "encounter_intent",
    "immediate_repeat_exclusion",
    "unseen_first",
    "rarity_weights_assigned",
    "family_diversity_preference",
    "deterministic_weighted_identity_selection",
)

_MACHINE_KEY_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_CLASS_ALIASES = {
    "NORMAL": "COMMON",  # F004 legacy battlefield compatibility
    "COMMON": "COMMON",
    "RARE": "RARE",
    "ELITE": "ELITE",
    "BOSS": "BATTLEFIELD_BOSS",
    "BATTLEFIELD_BOSS": "BATTLEFIELD_BOSS",
}
_REGULAR_CLASSES = frozenset(("COMMON", "RARE", "ELITE"))
_VALID_CLASSES = frozenset((*_REGULAR_CLASSES, "BATTLEFIELD_BOSS"))
_CLASS_WEIGHTS = {
    "COMMON": COMMON_WEIGHT,
    "RARE": RARE_WEIGHT,
    "ELITE": ELITE_WEIGHT,
}


class MonsterEncounterSelectorError(ValueError):
    """Base error for explicit fail-closed selector/catalog rejection."""


class MonsterEncounterCatalogError(MonsterEncounterSelectorError):
    """Raised when a candidate catalog violates the identity contract."""


class MonsterEncounterSelectionError(MonsterEncounterSelectorError):
    """Raised when an authoritative selection cannot be made safely."""


@dataclass(frozen=True)
class MonsterSelectorPolicy:
    """Server-owned candidate policy; not a live player-balance switch."""

    common_weight: int = COMMON_WEIGHT
    rare_weight: int = RARE_WEIGHT
    elite_weight: int = ELITE_WEIGHT
    version: str = SELECTOR_VERSION

    def __post_init__(self) -> None:
        weights = (self.common_weight, self.rare_weight, self.elite_weight)
        if any(isinstance(value, bool) or int(value) <= 0 for value in weights):
            raise ValueError("selector rarity weights must be positive integers")
        if not str(self.version).strip():
            raise ValueError("selector policy version is required")

    @property
    def weights(self) -> Mapping[str, int]:
        return {
            "COMMON": int(self.common_weight),
            "RARE": int(self.rare_weight),
            "ELITE": int(self.elite_weight),
        }


DEFAULT_SELECTOR_POLICY = MonsterSelectorPolicy()


@dataclass(frozen=True)
class MonsterEncounterCandidate:
    """Presentation-independent candidate consumed by the selector."""

    monster_id: str
    zone_key: str
    encounter_class: str
    family_id: str
    rarity: str | None = None
    is_lord: bool = False


@dataclass(frozen=True)
class MonsterEncounterSelection:
    """Deterministic identity result; combat stats are resolved by F008."""

    monster_id: str
    zone_key: str
    encounter_class: str
    family_id: str
    rarity: str | None
    operation_id: str
    selector_version: str
    seen_state_scope: str
    candidate_count: int
    cycle_reset: bool
    deterministic_seed_digest: str

    @property
    def f008_profile_input(self) -> dict[str, str]:
        """The only Monster combat-profile input the selector exposes."""

        return {"monster_id": self.monster_id}

    def runtime_fields(self) -> dict[str, Any]:
        return {
            "monster_id": self.monster_id,
            "zone_key": self.zone_key,
            "encounter_class": self.encounter_class,
            "family_id": self.family_id,
            "rarity": self.rarity,
            "operation_id": self.operation_id,
            "selector_version": self.selector_version,
            "seen_state_scope": self.seen_state_scope,
            "candidate_count": self.candidate_count,
            "cycle_reset": self.cycle_reset,
            "deterministic_seed_digest": self.deterministic_seed_digest,
        }


def _normalise_class(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return _CLASS_ALIASES.get(str(value).strip().upper())


def _normalise_machine_key(value: Any, field_name: str) -> str:
    value = str(value or "").strip()
    if not value or not _MACHINE_KEY_RE.fullmatch(value):
        raise MonsterEncounterCatalogError(
            f"{field_name} must be a lowercase ASCII machine key"
        )
    return value


def _candidate_value(candidate: Any, *names: str) -> Any:
    if isinstance(candidate, Mapping):
        for name in names:
            if name in candidate:
                return candidate.get(name)
        return None
    for name in names:
        if hasattr(candidate, name):
            return getattr(candidate, name)
    return None


def _coerce_candidate(candidate: Any) -> MonsterEncounterCandidate:
    if isinstance(candidate, MonsterEncounterCandidate):
        source = candidate
    else:
        source = MonsterEncounterCandidate(
            monster_id=_candidate_value(candidate, "monster_id"),
            zone_key=_candidate_value(candidate, "zone_key", "zone_id", "zone"),
            encounter_class=_candidate_value(
                candidate, "encounter_class", "encounter_kind"
            ),
            family_id=_candidate_value(
                candidate, "family_id", "taxonomy_family", "family"
            ),
            rarity=_candidate_value(candidate, "rarity", "tier"),
            is_lord=bool(_candidate_value(candidate, "is_lord", "lord")),
        )

    monster_id = _normalise_machine_key(source.monster_id, "monster_id")
    zone_key = _normalise_machine_key(source.zone_key, "zone_key")
    family_id = _normalise_machine_key(source.family_id, "family_id")
    encounter_class = _normalise_class(source.encounter_class)
    if encounter_class not in _VALID_CLASSES:
        raise MonsterEncounterCatalogError(
            f"unknown encounter class for {monster_id}: {source.encounter_class!r}"
        )
    if bool(source.is_lord) or monster_id.startswith("lord_"):
        raise MonsterEncounterCatalogError(
            f"Lord identity is outside the generic Monster selector: {monster_id}"
        )

    rarity = _normalise_class(source.rarity) if source.rarity not in (None, "") else None
    if source.rarity not in (None, "") and rarity not in _VALID_CLASSES:
        raise MonsterEncounterCatalogError(
            f"invalid rarity for {monster_id}: {source.rarity!r}"
        )
    if encounter_class == "BATTLEFIELD_BOSS":
        if rarity not in (None, "BATTLEFIELD_BOSS"):
            raise MonsterEncounterCatalogError(
                f"Battlefield Boss rarity mismatch for {monster_id}"
            )
        rarity = None
    else:
        if rarity not in (None, encounter_class):
            raise MonsterEncounterCatalogError(
                f"encounter class/rarity mismatch for {monster_id}"
            )
        rarity = encounter_class

    return MonsterEncounterCandidate(
        monster_id=monster_id,
        zone_key=zone_key,
        encounter_class=encounter_class,
        family_id=family_id,
        rarity=rarity,
        is_lord=False,
    )


def validate_monster_encounter_catalog(
    candidates: Iterable[Any],
) -> tuple[MonsterEncounterCandidate, ...]:
    """Validate and normalize a server-owned candidate catalog.

    Validation is intentionally cardinality agnostic.  A catalog may contain
    the current 20 legacy entries, a future 100-entry candidate catalog, or a
    small test pool.  It must never contain duplicate identities or multiple
    Battlefield Boss identities for one zone.
    """

    if candidates is None:
        raise MonsterEncounterCatalogError("Monster candidate catalog is required")
    normalized = tuple(_coerce_candidate(candidate) for candidate in candidates)
    if not normalized:
        raise MonsterEncounterCatalogError("Monster candidate catalog is empty")

    by_id: dict[str, MonsterEncounterCandidate] = {}
    bosses_by_zone: dict[str, str] = {}
    for candidate in normalized:
        if candidate.monster_id in by_id:
            raise MonsterEncounterCatalogError(
                f"duplicate canonical monster_id: {candidate.monster_id}"
            )
        by_id[candidate.monster_id] = candidate
        if candidate.encounter_class == "BATTLEFIELD_BOSS":
            previous = bosses_by_zone.get(candidate.zone_key)
            if previous is not None:
                raise MonsterEncounterCatalogError(
                    "duplicate Battlefield Boss in zone "
                    f"{candidate.zone_key}: {previous}, {candidate.monster_id}"
                )
            bosses_by_zone[candidate.zone_key] = candidate.monster_id
    return normalized


def build_legacy_selector_candidates(
    profile_registry: MonsterProfileRegistry = CANONICAL_MONSTER_PROFILE_REGISTRY,
) -> tuple[MonsterEncounterCandidate, ...]:
    """Adapt the current F004 20-entry registry without changing live paths."""

    candidates = []
    for profile in profile_registry.profiles:
        encounter_class = _normalise_class(profile.encounter_class)
        if encounter_class is None:
            raise MonsterEncounterCatalogError(
                f"legacy profile has unknown encounter class: {profile.monster_id}"
            )
        candidates.append(
            MonsterEncounterCandidate(
                monster_id=profile.monster_id,
                zone_key=profile.zone_key,
                encounter_class=encounter_class,
                family_id=profile.taxonomy_family,
                rarity=None,
            )
        )
    return validate_monster_encounter_catalog(candidates)


def _seen_ids(value: Iterable[Any] | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        value = (value,)
    return frozenset(str(item).strip() for item in value if str(item).strip())


def _seed_digest(
    *,
    user_scope: str,
    zone_key: str,
    encounter_intent: str,
    operation_id: str,
    seen_ids: frozenset[str],
    last_monster_id: str | None,
    last_family_id: str | None,
    candidates: Sequence[MonsterEncounterCandidate],
    policy: MonsterSelectorPolicy,
) -> str:
    payload = {
        "selector_version": SELECTOR_VERSION,
        "policy_version": policy.version,
        "policy_weights": dict(policy.weights),
        "user_scope": user_scope,
        "zone_key": zone_key,
        "encounter_intent": encounter_intent,
        "operation_id": operation_id,
        "seen_monster_ids": sorted(seen_ids),
        "last_monster_id": last_monster_id,
        "last_family_id": last_family_id,
        "candidates": [
            {
                "monster_id": candidate.monster_id,
                "zone_key": candidate.zone_key,
                "encounter_class": candidate.encounter_class,
                "family_id": candidate.family_id,
                "rarity": candidate.rarity,
            }
            for candidate in sorted(candidates, key=lambda item: item.monster_id)
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _weighted_pick(
    candidates: Sequence[MonsterEncounterCandidate],
    *,
    seed_digest: str,
    policy: MonsterSelectorPolicy,
    assigned_weights: Mapping[str, int] | None = None,
) -> MonsterEncounterCandidate:
    if not candidates:
        raise MonsterEncounterSelectionError("no candidates remain after selector policy")
    ordered = tuple(sorted(candidates, key=lambda item: item.monster_id))
    # The configured weights are class weights, not per-identity weights.
    # Applying 65 to each of five Common identities would accidentally turn
    # the intended 65/22/13 class policy into an 82/11/7 policy for a 5/2/2
    # pool.  Select a class first, then select an identity uniformly and
    # deterministically within that class.
    by_class: dict[str, tuple[MonsterEncounterCandidate, ...]] = {}
    for class_name in ("COMMON", "RARE", "ELITE"):
        members = tuple(
            candidate for candidate in ordered if candidate.encounter_class == class_name
        )
        if members:
            by_class[class_name] = members
    weighted_classes = [
        (
            class_name,
            int(
                (assigned_weights or {}).get(
                    by_class[class_name][0].monster_id,
                    policy.weights[class_name],
                )
            ),
        )
        for class_name in ("COMMON", "RARE", "ELITE")
        if class_name in by_class
    ]
    total = sum(weight for _class_name, weight in weighted_classes)
    position = int(seed_digest, 16) % total
    selected_class = weighted_classes[-1][0]
    for class_name, weight in weighted_classes:
        if position < weight:
            selected_class = class_name
            break
        position -= weight
    class_candidates = by_class[selected_class]
    candidate_digest = hashlib.sha256(
        f"{seed_digest}:{selected_class}".encode("ascii")
    ).hexdigest()
    return class_candidates[int(candidate_digest, 16) % len(class_candidates)]


def select_monster_encounter(
    candidates: Iterable[Any],
    *,
    user_id: Any,
    zone_key: Any,
    encounter_intent: str = "REGULAR",
    seen_monster_ids: Iterable[Any] | None = None,
    last_monster_id: Any = None,
    last_family_id: Any = None,
    operation_id: Any,
    policy: MonsterSelectorPolicy = DEFAULT_SELECTOR_POLICY,
    battlefield_boss_authorized: bool = False,
) -> MonsterEncounterSelection:
    """Select one deterministic Monster identity from a zone-local pool.

    ``battlefield_boss_authorized`` is a server-only boundary marker.  The
    selector does not calculate eligibility; a caller owning World/Adventure
    progression must set it after independently authorizing the intent.
    """

    if not isinstance(policy, MonsterSelectorPolicy):
        raise MonsterEncounterSelectionError("invalid selector policy")
    user_scope = str(user_id or "").strip()
    if not user_scope:
        raise MonsterEncounterSelectionError("server user scope is required")
    requested_zone = _normalise_machine_key(zone_key, "zone_key")
    operation = str(operation_id or "").strip()
    if not operation:
        raise MonsterEncounterSelectionError("server operation identity is required")

    intent = str(encounter_intent or "").strip().upper()
    if intent not in ("REGULAR", "BATTLEFIELD_BOSS"):
        raise MonsterEncounterSelectionError(
            f"unknown encounter intent: {encounter_intent!r}"
        )
    catalog = validate_monster_encounter_catalog(candidates)
    zone_candidates = tuple(
        candidate for candidate in catalog if candidate.zone_key == requested_zone
    )
    if not zone_candidates:
        raise MonsterEncounterSelectionError(
            f"no valid Monster candidates for authoritative zone {requested_zone}"
        )

    if intent == "BATTLEFIELD_BOSS":
        if not battlefield_boss_authorized:
            raise MonsterEncounterSelectionError(
                "Battlefield Boss eligibility is not owned by the selector"
            )
        bosses = tuple(
            candidate
            for candidate in zone_candidates
            if candidate.encounter_class == "BATTLEFIELD_BOSS"
        )
        if len(bosses) != 1:
            raise MonsterEncounterSelectionError(
                "authoritative zone must have exactly one Battlefield Boss"
            )
        selected = bosses[0]
        digest = _seed_digest(
            user_scope=user_scope,
            zone_key=requested_zone,
            encounter_intent=intent,
            operation_id=operation,
            seen_ids=_seen_ids(seen_monster_ids),
            last_monster_id=(str(last_monster_id).strip() if last_monster_id else None),
            last_family_id=(str(last_family_id).strip() if last_family_id else None),
            candidates=bosses,
            policy=policy,
        )
        return MonsterEncounterSelection(
            monster_id=selected.monster_id,
            zone_key=selected.zone_key,
            encounter_class=selected.encounter_class,
            family_id=selected.family_id,
            rarity=selected.rarity,
            operation_id=operation,
            selector_version=SELECTOR_VERSION,
            seen_state_scope=SEEN_STATE_SCOPE,
            candidate_count=len(bosses),
            cycle_reset=False,
            deterministic_seed_digest=digest,
        )

    regular = tuple(
        candidate
        for candidate in zone_candidates
        if candidate.encounter_class in _REGULAR_CLASSES
    )
    if not regular:
        raise MonsterEncounterSelectionError(
            f"zone {requested_zone} has no regular Monster candidates"
        )

    seen = _seen_ids(seen_monster_ids)
    last_id = str(last_monster_id).strip() if last_monster_id else None
    last_candidate = next(
        (candidate for candidate in regular if candidate.monster_id == last_id),
        None,
    )
    if last_candidate is not None:
        effective_last_family = last_candidate.family_id
    else:
        effective_last_family = (
            str(last_family_id).strip() if last_family_id else None
        )

    # Immediate-repeat exclusion is applied before cycle selection.  A lone
    # valid candidate is explicitly allowed to repeat rather than failing.
    if len(regular) >= 2 and last_candidate is not None:
        immediate_filtered = tuple(
            candidate for candidate in regular if candidate.monster_id != last_id
        )
    else:
        immediate_filtered = regular

    regular_ids = frozenset(candidate.monster_id for candidate in regular)
    seen_in_zone = seen.intersection(regular_ids)
    cycle_reset = bool(regular_ids) and seen_in_zone == regular_ids
    cycle_seen = frozenset() if cycle_reset else seen_in_zone
    unseen = tuple(
        candidate
        for candidate in immediate_filtered
        if candidate.monster_id not in cycle_seen
    )
    pool = unseen or immediate_filtered
    if not pool:
        # This branch is only possible for malformed caller state; a valid
        # one-candidate pool is retained by the explicit single-candidate
        # policy above.
        pool = regular

    # Assign class weights before the soft family preference.  The weights
    # remain class-level policy values even if the family filter narrows the
    # candidate set afterwards.
    assigned_weights = {
        candidate.monster_id: int(policy.weights[candidate.encounter_class])
        for candidate in pool
    }

    # Rarity weights are assigned before the family preference.  The family
    # rule is soft: if an alternate family exists, narrow to it; otherwise
    # leave the weighted pool intact so selection always succeeds.
    alternate_family_pool = tuple(
        candidate
        for candidate in pool
        if effective_last_family is None
        or candidate.family_id != effective_last_family
    )
    if alternate_family_pool:
        pool = alternate_family_pool

    digest = _seed_digest(
        user_scope=user_scope,
        zone_key=requested_zone,
        encounter_intent=intent,
        operation_id=operation,
        seen_ids=cycle_seen,
        last_monster_id=last_id,
        last_family_id=effective_last_family,
        candidates=pool,
        policy=policy,
    )
    selected = _weighted_pick(
        pool,
        seed_digest=digest,
        policy=policy,
        assigned_weights=assigned_weights,
    )
    return MonsterEncounterSelection(
        monster_id=selected.monster_id,
        zone_key=selected.zone_key,
        encounter_class=selected.encounter_class,
        family_id=selected.family_id,
        rarity=selected.rarity,
        operation_id=operation,
        selector_version=SELECTOR_VERSION,
        seen_state_scope=SEEN_STATE_SCOPE,
        candidate_count=len(regular),
        cycle_reset=cycle_reset,
        deterministic_seed_digest=digest,
    )


__all__ = [
    "BATTLEFIELD_BOSS_IN_REGULAR_POOL",
    "BATTLEFIELD_BOSS_ELIGIBILITY_SELECTOR_OWNED",
    "COMMON_WEIGHT",
    "DEFAULT_SELECTOR_POLICY",
    "DURABLE_SELECTOR_STATE_GAP",
    "ELITE_WEIGHT",
    "F007_100_ROSTER_RUNTIME_ACTIVATED",
    "FAMILY_REPEAT_AVOIDANCE",
    "LORD_CLASSIFIED_AS_BATTLEFIELD_BOSS",
    "LORD_IN_GENERIC_SELECTOR",
    "MonsterEncounterCandidate",
    "MonsterEncounterCatalogError",
    "MonsterEncounterSelection",
    "MonsterEncounterSelectionError",
    "MonsterEncounterSelectorError",
    "MonsterSelectorPolicy",
    "MONSTER_SELECTOR_LIVE_ACTIVATED",
    "MONSTER_ENCOUNTER_SELECTOR_COUNT",
    "NO_IMMEDIATE_MONSTER_REPEAT",
    "RARE_WEIGHT",
    "RARITY_WEIGHT_POLICY_STATUS",
    "SEEN_STATE_SCOPE",
    "SELECTOR_DECISION_ORDER",
    "SELECTOR_OWNS_MONSTER_STATS",
    "SELECTOR_OWNS_QUESTION_SELECTION",
    "SELECTOR_OWNS_WORLD_PROGRESSION",
    "SELECTOR_RANDOMNESS_MODEL",
    "SELECTOR_VERSION",
    "SINGLE_CANDIDATE_POLICY",
    "UNSEEN_FIRST",
    "build_legacy_selector_candidates",
    "select_monster_encounter",
    "validate_monster_encounter_catalog",
]
